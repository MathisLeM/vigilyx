"""
MAD DETECTOR
============
Median Absolute Deviation anomaly detector.

Why MAD over Z-score as the primary detector:
  - Robust to outliers: the median is not pulled by extreme values, so a single
    anomaly does not inflate the baseline and mask subsequent ones.
  - Gaussian-equivalent: the 1.4826 constant makes MAD a consistent estimator
    of sigma for normally distributed data, so thresholds are comparable.
  - Better on skewed financial data: revenue series are right-skewed; MAD
    handles this better than mean-based methods.

Algorithm:
  For each point i, compute a rolling window W of the previous ROLLING_WINDOW_DAYS
  data points (plus the current point). The MAD score is:

      score(i) = |x_i - median(W)| / (1.4826 * MAD(W))

  where MAD(W) = median(|W - median(W)|).

  The expanding window is used for early data (window grows from min_periods
  to ROLLING_WINDOW_DAYS) so the first few weeks still produce scores.

Baseline: the rolling window median — used downstream to compute % deviation
  for business-readable severity classification.
"""

import numpy as np
import pandas as pd

from app.config import settings
from app.services.detection.base import BaseDetector

MIN_PERIODS = 7  # minimum history points required to score


class MADDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "MAD"

    @property
    def threshold(self) -> float:
        return settings.MAD_THRESHOLD

    def score(
        self, series: pd.Series
    ) -> tuple[pd.Series, pd.Series]:
        """
        Compute expanding MAD score and rolling median baseline.

        Returns:
            (scores, medians) — both Series with the same index as input.
        """
        window = settings.ROLLING_WINDOW_DAYS
        scores  = pd.Series(0.0,       index=series.index)
        medians = pd.Series(np.nan,    index=series.index)

        for i in range(len(series)):
            start_idx = max(0, i - window + 1)
            w = series.iloc[start_idx : i + 1]  # includes current point

            if len(w) < MIN_PERIODS:
                continue

            median = w.median()
            medians.iloc[i] = median
            mad = (w - median).abs().median()

            if mad == 0:
                continue

            scores.iloc[i] = abs(series.iloc[i] - median) / (1.4826 * mad)

        return scores, medians
