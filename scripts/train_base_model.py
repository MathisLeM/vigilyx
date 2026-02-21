"""
Train the Isolation Forest base model on a synthetic corpus.

Run this script locally (or in CI) whenever you want to regenerate the base model:
    python scripts/train_base_model.py

Optional arguments:
    --n-companies   Number of synthetic companies to generate (default: 500)
    --days          Days of history per company (default: 180)
    --seed          Random seed for reproducibility (default: 0)

Output files (in models/):
    base_isolation_forest.pkl  -- trained IsolationForest, loaded at runtime
    base_model_meta.json       -- training params, feature names, timestamp

Design notes:
  - The IF is trained on ROLLING Z-SCORE features, not raw values.
    This makes the model scale-invariant: it works equally well for a
    $500/day startup and a $500k/day enterprise, because it learns the
    shape of anomalous deviation rather than absolute revenue levels.

  - Feature vector per day (6 features):
      z_gross_revenue     z-score vs prior 14-day window
      z_charge_count      z-score vs prior 14-day window
      z_avg_charge_value  z-score vs prior 14-day window
      fee_rate            raw ratio (Stripe fee %, near-constant per tenant)
      refund_rate         raw ratio (fraction of gross refunded)
      dispute_rate_by_value  dispute_amount / gross_revenue

  - Contamination = 0.05 (5%): the model treats the worst 5% of training
    days as anomalies, setting the decision boundary accordingly.

  - At inference time, the runtime detector computes the same 6 features
    using the tenant's last 14+ days as the rolling window, then calls
    clf.decision_function() to get the anomaly score:
        score < 0  -->  anomalous (IF agrees with MAD/Z-score)
        score >= 0 -->  normal    (IF disagrees, suppress LOW alerts)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import joblib
from sklearn.ensemble import IsolationForest

from simulation.business_simulator import BusinessSimulator, FEATURE_NAMES


# ── Config ─────────────────────────────────────────────────────────────────────

CONTAMINATION    = 0.05   # fraction of training days treated as anomalies
N_ESTIMATORS     = 200    # number of isolation trees (more = better, slower)
ROLLING_WINDOW   = 14     # days used to compute rolling mean/std for z-scores

MODEL_DIR        = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
MODEL_PATH       = os.path.join(MODEL_DIR, "base_isolation_forest.pkl")
META_PATH        = os.path.join(MODEL_DIR, "base_model_meta.json")

# The 6 features the IF is trained and evaluated on (order matters)
MODEL_FEATURE_NAMES = [
    "z_gross_revenue",
    "z_charge_count",
    "z_avg_charge_value",
    "fee_rate",
    "refund_rate",
    "dispute_rate_by_value",
]

# Column indices in the raw FEATURE_NAMES array from BusinessSimulator
_IDX = {name: i for i, name in enumerate(FEATURE_NAMES)}


# ── Feature engineering ────────────────────────────────────────────────────────

def rolling_features(raw: np.ndarray, window: int = ROLLING_WINDOW) -> np.ndarray:
    """
    Convert raw daily metric rows to rolling z-score feature vectors.

    Args:
        raw:    shape (n_days, 9) — output of BusinessSimulator.generate_corpus()
                for a single company
        window: look-back window for computing mean/std

    Returns:
        shape (max(0, n_days - window), 6) — one feature vector per day,
        starting from day `window` (days 0..window-1 are discarded as warm-up)
    """
    n = len(raw)
    if n <= window:
        return np.empty((0, len(MODEL_FEATURE_NAMES)), dtype=np.float64)

    out = np.empty((n - window, len(MODEL_FEATURE_NAMES)), dtype=np.float64)

    for t in range(window, n):
        hist = raw[t - window:t]   # shape (window, 9)
        today = raw[t]

        def zscore(col: str) -> float:
            idx = _IDX[col]
            vals = hist[:, idx]
            mu, sigma = vals.mean(), vals.std()
            return float((today[idx] - mu) / (sigma + 1e-8))

        gross = today[_IDX["gross_revenue_usd"]]
        dispute = today[_IDX["dispute_amount_usd"]]

        out[t - window] = [
            zscore("gross_revenue_usd"),
            zscore("charge_count"),
            zscore("avg_charge_value_usd"),
            float(today[_IDX["fee_rate"]]),
            float(today[_IDX["refund_rate"]]),
            float(dispute / gross) if gross > 0 else 0.0,
        ]

    return out


# ── Training ───────────────────────────────────────────────────────────────────

def main(n_companies: int = 500, days: int = 180, seed: int = 0) -> None:
    print(f"\n{'='*55}")
    print(f"  Isolation Forest Base Model — Training")
    print(f"{'='*55}")
    print(f"  Companies:      {n_companies}")
    print(f"  Days/company:   {days}")
    print(f"  Total raw rows: {n_companies * days:,}")
    print(f"  Rolling window: {ROLLING_WINDOW} days")
    print(f"  Contamination:  {CONTAMINATION:.0%}")
    print(f"  Trees:          {N_ESTIMATORS}")

    # ── Step 1: Generate synthetic corpus ─────────────────────────────────────
    print(f"\n[1/4] Generating synthetic corpus...")
    sim = BusinessSimulator()
    X_raw = sim.generate_corpus(n_companies=n_companies, days=days, seed=seed)
    print(f"  Raw shape: {X_raw.shape}")

    # ── Step 2: Compute rolling z-score features per company ──────────────────
    print(f"\n[2/4] Computing rolling features (window={ROLLING_WINDOW})...")
    company_blocks: list[np.ndarray] = []
    for i in range(n_companies):
        company_raw = X_raw[i * days : (i + 1) * days]
        feats = rolling_features(company_raw, window=ROLLING_WINDOW)
        if len(feats) > 0:
            company_blocks.append(feats)

    X = np.vstack(company_blocks)
    print(f"  Feature matrix shape: {X.shape}")
    print(f"  Features: {MODEL_FEATURE_NAMES}")

    # Remove NaN rows (defensive — shouldn't occur with well-formed data)
    nan_mask = np.isnan(X).any(axis=1)
    if nan_mask.any():
        print(f"  Dropping {nan_mask.sum()} rows with NaN")
        X = X[~nan_mask]

    # Sanity-check value ranges
    print(f"\n[3/4] Feature statistics:")
    for j, name in enumerate(MODEL_FEATURE_NAMES):
        col = X[:, j]
        print(f"  {name:<26}  mean={col.mean():+.3f}  std={col.std():.3f}  "
              f"min={col.min():+.3f}  max={col.max():+.3f}")

    # ── Step 3: Train IsolationForest ─────────────────────────────────────────
    print(f"\n[4/4] Training IsolationForest on {len(X):,} samples...")
    clf = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=CONTAMINATION,
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X)

    # Verify contamination alignment
    preds = clf.predict(X)
    actual_contamination = (preds == -1).mean()
    scores = clf.decision_function(X)
    print(f"  Flagged anomalies on training data: {actual_contamination:.1%}  (target {CONTAMINATION:.1%})")
    print(f"  Score range: [{scores.min():.4f}, {scores.max():.4f}]  "
          f"(negative = anomalous, positive = normal)")

    # ── Save model and metadata ───────────────────────────────────────────────
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    size_kb = os.path.getsize(MODEL_PATH) / 1024
    print(f"\n  Model saved:    {MODEL_PATH}  ({size_kb:.0f} KB)")

    meta = {
        "trained_at":         datetime.now(timezone.utc).isoformat(),
        "n_companies":        n_companies,
        "days_per_company":   days,
        "seed":               seed,
        "rolling_window":     ROLLING_WINDOW,
        "contamination":      CONTAMINATION,
        "n_estimators":       N_ESTIMATORS,
        "feature_names":      MODEL_FEATURE_NAMES,
        "training_samples":   int(len(X)),
        "actual_contamination": float(actual_contamination),
        "score_min":          float(scores.min()),
        "score_max":          float(scores.max()),
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Metadata saved: {META_PATH}")

    print(f"\n{'='*55}")
    print(f"  Done. Use the model in app/services/detection/isolation_forest.py")
    print(f"  Retrain anytime: python scripts/train_base_model.py")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the Isolation Forest base model")
    parser.add_argument("--n-companies", type=int, default=500,
                        help="Number of synthetic companies (default: 500)")
    parser.add_argument("--days", type=int, default=180,
                        help="Days of history per company (default: 180)")
    parser.add_argument("--seed", type=int, default=0,
                        help="Random seed (default: 0)")
    args = parser.parse_args()
    main(args.n_companies, args.days, args.seed)
