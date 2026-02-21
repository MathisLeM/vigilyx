"""
Z-SCORE DETECTOR — Phase 3
============================
Rolling Z-score anomaly detector.

Role in the dual-detection system:
  - Complements MAD: uses mean + std instead of median + MAD.
  - When both MAD and Z-score fire on the same (date, metric), the alert is
    marked is_dual_confirmed=True and severity is bumped one level.
  - This reduces false positives: a single-method alert is plausible;
    dual-method agreement signals high statistical confidence.

Algorithm:
  For each point i, the Z-score over a rolling window W is:

      z(i) = |x_i - mean(W)| / std(W)

  If std(W) == 0 (flat series), score is 0 to avoid division by zero.

Baseline: the rolling window mean — used for % deviation.
  Note: MAD uses the median as baseline, which is more robust. The Z-score
  baseline (mean) may be pulled by the anomaly itself in small windows, so
  the MAD median is preferred for severity calculation in the orchestrator.
"""

import numpy as np
import pandas as pd

from app.config import settings
from app.services.detection.base import BaseDetector


class ZScoreDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "ZSCORE"

    @property
    def threshold(self) -> float:
        return settings.ZSCORE_THRESHOLD

    def score(
        self, series: pd.Series
    ) -> tuple[pd.Series, pd.Series]:
        """
        Compute rolling Z-score and rolling mean baseline.

        Returns:
            (scores, means) — both Series with the same index as input.
        """
        window = settings.ROLLING_WINDOW_DAYS
        roll   = series.rolling(window=window, min_periods=7)
        means  = roll.mean()
        std    = roll.std().replace(0, np.nan)

        scores = ((series - means).abs() / std).fillna(0.0)

        return scores, means
