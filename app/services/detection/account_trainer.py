"""
ACCOUNT MODEL TRAINER
======================
Trains a per-Stripe-account Isolation Forest model from real
daily_revenue_metrics data stored in the database.

Design:
  - Same 6 rolling z-score features as the base model (scale-invariant).
  - Requires MIN_DAYS_FOR_TRAINING (30) days of feature rows.
  - Model saved as models/account_{stripe_account_id}.pkl
  - Metadata saved as models/account_{stripe_account_id}_meta.json

Feature vector (order must match isolation_forest.py and train_base_model.py):
  z_gross_revenue, z_charge_count, z_avg_charge_value,
  fee_rate, refund_rate, dispute_rate_by_value
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.models.daily_revenue import DailyRevenueMetrics

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "models"))

MIN_DAYS_FOR_TRAINING = 30
ROLLING_WINDOW = 14
CONTAMINATION = 0.05
N_ESTIMATORS = 100

MODEL_FEATURE_NAMES = [
    "z_gross_revenue",
    "z_charge_count",
    "z_avg_charge_value",
    "fee_rate",
    "refund_rate",
    "dispute_rate_by_value",
]


def _model_path(stripe_account_id: str) -> str:
    return os.path.join(MODEL_DIR, f"account_{stripe_account_id}.pkl")


def _meta_path(stripe_account_id: str) -> str:
    return os.path.join(MODEL_DIR, f"account_{stripe_account_id}_meta.json")


def model_exists(stripe_account_id: str) -> bool:
    return os.path.exists(_model_path(stripe_account_id))


def read_model_meta(stripe_account_id: str) -> Optional[dict]:
    path = _meta_path(stripe_account_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _load_feature_matrix(
    db: Session,
    tenant_id: int,
    stripe_account_id: str,
) -> tuple[np.ndarray, list[date]]:
    """
    Load daily_revenue_metrics for this account and convert to
    rolling z-score feature matrix.

    Returns:
        (X, dates) where X has shape (n_days - ROLLING_WINDOW, 6)
        and dates is the corresponding list of snapshot_dates.
        X is empty if not enough rows.
    """
    rows = (
        db.query(DailyRevenueMetrics)
        .filter(
            DailyRevenueMetrics.tenant_id == tenant_id,
            DailyRevenueMetrics.stripe_account_id == stripe_account_id,
        )
        .order_by(DailyRevenueMetrics.snapshot_date.asc())
        .all()
    )

    if len(rows) <= ROLLING_WINDOW:
        return np.empty((0, len(MODEL_FEATURE_NAMES)), dtype=np.float64), []

    # Convert to raw arrays (dollars, not cents)
    gross   = np.array([(r.gross_revenue_usd or 0) / 100   for r in rows], dtype=np.float64)
    count   = np.array([float(r.charge_count or 0)          for r in rows], dtype=np.float64)
    avg_chg = np.array(
        [(r.avg_charge_value_usd / 100) if r.avg_charge_value_usd else 0.0 for r in rows],
        dtype=np.float64,
    )
    fee_rate    = np.array([float(r.fee_rate or 0)    for r in rows], dtype=np.float64)
    refund_rate = np.array([float(r.refund_rate or 0) for r in rows], dtype=np.float64)
    dispute_usd = np.array([(r.dispute_amount_usd or 0) / 100 for r in rows], dtype=np.float64)
    dates = [r.snapshot_date for r in rows]

    n = len(rows)
    out = np.empty((n - ROLLING_WINDOW, len(MODEL_FEATURE_NAMES)), dtype=np.float64)
    out_dates: list[date] = []

    for t in range(ROLLING_WINDOW, n):
        hist_gross   = gross[t - ROLLING_WINDOW:t]
        hist_count   = count[t - ROLLING_WINDOW:t]
        hist_avg_chg = avg_chg[t - ROLLING_WINDOW:t]

        def zscore(hist: np.ndarray, val: float) -> float:
            mu, sigma = hist.mean(), hist.std()
            return float((val - mu) / (sigma + 1e-8))

        g = gross[t]
        dispute_rate = float(dispute_usd[t] / g) if g > 0 else 0.0

        out[t - ROLLING_WINDOW] = [
            zscore(hist_gross,   gross[t]),
            zscore(hist_count,   count[t]),
            zscore(hist_avg_chg, avg_chg[t]),
            fee_rate[t],
            refund_rate[t],
            dispute_rate,
        ]
        out_dates.append(dates[t])

    return out, out_dates


def train_account_model(
    db: Session,
    tenant_id: int,
    stripe_account_id: str,
) -> Optional[dict]:
    """
    Train a per-account Isolation Forest model from real Stripe data.

    Returns a metadata dict on success, or None if not enough data.
    Raises on unexpected errors (caller logs).
    """
    import joblib
    from sklearn.ensemble import IsolationForest

    X, dates = _load_feature_matrix(db, tenant_id, stripe_account_id)

    days_available = len(X) + ROLLING_WINDOW  # total daily_revenue rows, incl. warm-up
    if len(X) < MIN_DAYS_FOR_TRAINING - ROLLING_WINDOW:
        logger.info(
            "Account trainer: %s has %d feature rows (need %d) — skipped",
            stripe_account_id, len(X), MIN_DAYS_FOR_TRAINING - ROLLING_WINDOW,
        )
        return None

    # Drop NaN rows (defensive)
    nan_mask = np.isnan(X).any(axis=1)
    if nan_mask.any():
        X = X[~nan_mask]
        dates = [d for d, m in zip(dates, nan_mask) if not m]

    if len(X) == 0:
        return None

    clf = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=CONTAMINATION,
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X)

    os.makedirs(MODEL_DIR, exist_ok=True)
    mp = _model_path(stripe_account_id)
    joblib.dump(clf, mp)

    trained_at = datetime.now(timezone.utc)
    meta = {
        "trained_at":        trained_at.isoformat(),
        "tenant_id":         tenant_id,
        "stripe_account_id": stripe_account_id,
        "days_available":    days_available,
        "feature_rows":      int(len(X)),
        "first_date":        str(dates[0]) if dates else None,
        "last_date":         str(dates[-1]) if dates else None,
        "rolling_window":    ROLLING_WINDOW,
        "contamination":     CONTAMINATION,
        "n_estimators":      N_ESTIMATORS,
        "feature_names":     MODEL_FEATURE_NAMES,
    }
    with open(_meta_path(stripe_account_id), "w") as f:
        json.dump(meta, f, indent=2)

    # Bust in-process model cache so the new model is picked up immediately
    from app.services.detection.isolation_forest import invalidate_cache
    invalidate_cache(stripe_account_id)

    logger.info(
        "Account trainer: trained model for %s — %d feature rows, saved to %s",
        stripe_account_id, len(X), mp,
    )
    return meta
