"""
ISOLATION FOREST GATING LAYER
==============================
Applies the trained Isolation Forest as a gating layer on MAD/Z-score alerts.

Role (gating only — does NOT create new alerts):
  - IF score < 0 (day is anomalous): boost MEDIUM alerts to HIGH on that day
  - IF score >= 0 (day is normal):   suppress LOW alerts on that day
  - HIGH alerts always pass through regardless of IF score (never suppress critical)

Activation conditions:
  - Tenant must have >= MIN_DAYS_HISTORY days in the context window
  - The model file must exist (account-specific or base)
  - If either condition fails: all anomalies pass through unchanged (fail-safe)

Model resolution order (keyed by stripe_account_id):
  1. models/account_{stripe_account_id}.pkl — per-account model (trained after 30 days)
  2. models/base_isolation_forest.pkl        — pre-trained base model (ships with codebase)
  3. None — skip gating, log a warning

Feature vector (6 features, same as training):
  z_gross_revenue, z_charge_count, z_avg_charge_value,
  fee_rate, refund_rate, dispute_rate_by_value

Rolling window: 14 days (prior to the target date).
"""

import logging
import os
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "models"))

MIN_DAYS_HISTORY = 30   # minimum prior rows required in the context window
ROLLING_WINDOW   = 14   # days used to compute rolling z-scores

# ── Model cache (loaded once per process) ─────────────────────────────────────

_base_clf = None                          # base IsolationForest, shared fallback
_account_clf: dict[str, object] = {}     # per-account models, keyed by stripe_account_id


def _load_model(stripe_account_id: Optional[str]):
    """
    Return the best available IsolationForest for this Stripe account.
    Results are cached in module-level variables after the first load.
    Returns None if no model file is found.
    """
    global _base_clf

    if stripe_account_id:
        # Try account-specific model first
        if stripe_account_id not in _account_clf:
            path = os.path.join(MODEL_DIR, f"account_{stripe_account_id}.pkl")
            if os.path.exists(path):
                try:
                    import joblib
                    _account_clf[stripe_account_id] = joblib.load(path)
                    logger.info("IF: loaded account model for %s", stripe_account_id)
                except Exception as exc:
                    logger.warning("IF: failed to load account model %s: %s", path, exc)
                    _account_clf[stripe_account_id] = None
            else:
                _account_clf[stripe_account_id] = None  # cache miss

        if _account_clf.get(stripe_account_id) is not None:
            return _account_clf[stripe_account_id]

    # Fall back to base model
    if _base_clf is None:
        path = os.path.join(MODEL_DIR, "base_isolation_forest.pkl")
        if os.path.exists(path):
            try:
                import joblib
                _base_clf = joblib.load(path)
                logger.info("IF: loaded base model from %s", path)
            except Exception as exc:
                logger.warning("IF: failed to load base model %s: %s", path, exc)
                _base_clf = None

    return _base_clf   # may be None if no model available


def invalidate_cache(stripe_account_id: str) -> None:
    """
    Clear the cached model for a Stripe account so the next call reloads from disk.
    Called by account_trainer after per-account retraining completes.
    """
    _account_clf.pop(stripe_account_id, None)
    logger.debug("IF: cache invalidated for account %s", stripe_account_id)


# ── Feature computation ────────────────────────────────────────────────────────

def _compute_features(
    df: pd.DataFrame,
    target_ts: pd.Timestamp,
    window: int = ROLLING_WINDOW,
) -> Optional[np.ndarray]:
    """
    Build the 6-feature vector for `target_ts` using the prior `window` rows as context.

    Returns None if:
    - target_ts is not in the df index
    - fewer than `window` prior rows exist in the df

    Feature order matches MODEL_FEATURE_NAMES in scripts/train_base_model.py:
      [z_gross_revenue, z_charge_count, z_avg_charge_value,
       fee_rate, refund_rate, dispute_rate_by_value]
    """
    if target_ts not in df.index:
        return None

    loc = df.index.get_loc(target_ts)
    if loc < window:
        return None

    hist  = df.iloc[loc - window : loc]   # shape (window, n_cols)
    today = df.iloc[loc]

    def zscore(col: str) -> float:
        if col not in df.columns:
            return 0.0
        vals = hist[col].dropna().astype(float)
        if len(vals) == 0:
            return 0.0
        mu = vals.mean()
        sigma = vals.std()
        v = float(today[col]) if col in today.index and pd.notna(today[col]) else mu
        return float((v - mu) / (sigma + 1e-8))

    gross = float(today.get("gross_revenue_usd", 0) or 0)
    dispute = float(today.get("dispute_amount_usd", 0) or 0)
    dispute_rate = (dispute / gross) if gross > 0 else 0.0

    return np.array([
        zscore("gross_revenue_usd"),
        zscore("charge_count"),
        zscore("avg_charge_value_usd"),
        float(today.get("fee_rate") or 0),
        float(today.get("refund_rate") or 0),
        dispute_rate,
    ], dtype=np.float64)


# ── IF score per day ───────────────────────────────────────────────────────────

def _if_score(
    df: pd.DataFrame,
    target_date: date,
    clf,
) -> Optional[float]:
    """
    Return the IF decision_function score for a single day.
    Negative = anomalous, positive = normal, None = could not compute.
    """
    target_ts = pd.Timestamp(target_date)
    features = _compute_features(df, target_ts)
    if features is None:
        return None
    try:
        score = clf.decision_function(features.reshape(1, -1))
        return float(score[0])
    except Exception as exc:
        logger.warning("IF: scoring failed for %s: %s", target_date, exc)
        return None


# ── Preliminary severity helper ────────────────────────────────────────────────

def _preliminary_severity(anomaly: dict) -> str:
    """
    Estimate the severity of a raw anomaly dict (before persist_alerts()).
    Mirrors the logic in alert_service._compute_severity().
    """
    baseline = anomaly.get("baseline_median")
    value    = anomaly.get("metric_value", 0)
    if baseline and baseline != 0:
        pct_dev = abs(value - baseline) / abs(baseline) * 100
    else:
        pct_dev = 0.0

    if pct_dev < 75:
        return "LOW"
    if pct_dev < 200:
        return "MEDIUM"
    return "HIGH"


# ── Public API ─────────────────────────────────────────────────────────────────

def apply_if_gating(
    anomalies: list[dict],
    df: pd.DataFrame,
    tenant_id: int,
    stripe_account_id: Optional[str] = None,
) -> list[dict]:
    """
    Apply IF gating to a list of raw anomaly dicts.

    Args:
        anomalies:          output of _run_detectors(), filtered to detection window
        df:                 full context DataFrame (same one used for detection)
        tenant_id:          for logging only
        stripe_account_id:  used to resolve the correct account model

    Returns:
        Modified list of anomaly dicts:
        - LOW anomalies on IF-normal days are removed (suppressed)
        - Anomalies on IF-anomalous days gain {"if_boost": True}
        - Unchanged if model not available or not enough history
    """
    if not anomalies:
        return anomalies

    clf = _load_model(stripe_account_id)
    if clf is None:
        logger.debug(
            "IF: no model available for tenant=%d account=%s — gating skipped",
            tenant_id, stripe_account_id,
        )
        return anomalies

    # Check minimum history for the earliest detection date
    unique_dates: set[date] = {a["snapshot_date"] for a in anomalies}
    earliest = min(unique_dates)
    earliest_ts = pd.Timestamp(earliest)
    prior_rows = len(df[df.index < earliest_ts])
    if prior_rows < MIN_DAYS_HISTORY:
        logger.debug(
            "IF: tenant=%d account=%s has %d prior rows (need %d) — gating skipped",
            tenant_id, stripe_account_id, prior_rows, MIN_DAYS_HISTORY,
        )
        return anomalies

    # Compute IF score per unique date
    scores_by_date: dict[date, Optional[float]] = {}
    for d in unique_dates:
        scores_by_date[d] = _if_score(df, d, clf)

    # Apply gating rules
    result: list[dict] = []
    suppressed = 0
    boosted    = 0

    for anomaly in anomalies:
        d     = anomaly["snapshot_date"]
        score = scores_by_date.get(d)

        if score is None:
            # Could not compute score — pass through unchanged
            result.append(anomaly)
            continue

        if score >= 0:
            # IF considers this day normal — suppress LOW alerts only
            sev = _preliminary_severity(anomaly)
            if sev == "LOW":
                suppressed += 1
                continue
            result.append(anomaly)
        else:
            # IF considers this day anomalous — keep and optionally boost
            boosted_anomaly = dict(anomaly)
            sev = _preliminary_severity(anomaly)
            if sev == "MEDIUM":
                boosted_anomaly["if_boost"] = True
                boosted += 1
            result.append(boosted_anomaly)

    if suppressed or boosted:
        logger.info(
            "IF gating (tenant=%d account=%s): suppressed=%d LOW, boosted=%d MEDIUM→HIGH",
            tenant_id, stripe_account_id, suppressed, boosted,
        )

    return result
