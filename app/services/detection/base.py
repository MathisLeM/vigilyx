"""
BASE DETECTOR — Phase 3
=========================
Abstract base class for anomaly detectors.

Implementing this interface makes the detection layer ML-ready:
  - Statistical detectors (MAD, Z-score) implement it today.
  - Isolation Forest, LSTM, or any future model implements the same interface.
  - alert_service.py orchestrates a list of BaseDetector instances —
    swapping or adding detectors requires zero changes to the orchestration layer.

Contract:
  - score(series) receives a pandas Series indexed by snapshot_date (sorted ascending).
  - Returns (scores, baselines):
      scores:    Series[float] — anomaly score for each point (same index as input).
      baselines: Series[float] | None — rolling median/mean used as baseline for
                 % deviation calculation. None if the detector has no natural baseline.
  - Points with scores above self.threshold are flagged as anomalies.
  - name and threshold are used by the orchestrator to build the anomaly dict.
"""

from abc import ABC, abstractmethod

import pandas as pd


class BaseDetector(ABC):
    """Abstract anomaly detector. All detectors must implement this interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. 'MAD' or 'ZSCORE'. Used in alert records."""
        ...

    @property
    @abstractmethod
    def threshold(self) -> float:
        """Score above which a data point is flagged as anomalous."""
        ...

    @abstractmethod
    def score(
        self, series: pd.Series
    ) -> tuple[pd.Series, pd.Series | None]:
        """
        Compute anomaly scores for each point in the series.

        Args:
            series: Float series indexed by snapshot_date, sorted ascending,
                    NaNs already dropped.

        Returns:
            (scores, baselines)
            - scores:    same index as series, float >= 0
            - baselines: same index as series, or None
        """
        ...
