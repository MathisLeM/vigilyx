"""
BUSINESS SIMULATOR
==================
Generates realistic daily revenue feature vectors for ML corpus generation.

Unlike StripeSimulator (transaction-level, for DB seeding), this module
produces daily aggregate metrics directly -- 100x faster, suitable for
generating the large training corpus needed by the Isolation Forest base model.

Statistical improvements over the transaction-level simulator:
  - AR(1) autocorrelation: revenue is sticky day-to-day (prevents fully
    independent draws that make "normal" look noisier than reality)
  - Month-end renewal spikes: SaaS sees +20-35% on days 28-31 of each month
  - Quarter-end closes: B2B sees +40-55% in last 7 days of Q (Mar/Jun/Sep/Dec)
  - Correlated refund_rate: elevated refund periods persist 3-7 days via AR(1)
  - Sparse disputes: Poisson process (most days zero disputes)
  - Metric consistency: fee_rate is nearly constant per business (Stripe charges
    a fixed %, so it shouldn't vary much day to day)

Business profiles:
  "saas_stable"      B2B SaaS, MRR-driven, low refunds (~1.2%), month-end spikes
  "ecommerce"        B2C, high volume, weekend peaks, higher refunds (~3.8%)
  "marketplace"      Mixed, high value variance, moderate disputes
  "high_ticket_b2b"  Enterprise / consulting, low volume, very high ATV, Q-end spikes

Usage:
  from simulation.business_simulator import BusinessSimulator, FEATURE_NAMES

  sim = BusinessSimulator()

  # Single company (for inspection / demo seeding)
  features = sim.generate_company(profile="saas_stable", days=180, seed=42)
  # features: list[DailyFeatures]

  # Bulk corpus for ML training
  X = sim.generate_corpus(n_companies=500, days=180, seed=0)
  # X: np.ndarray shape (90_000, len(FEATURE_NAMES))  -- ready for IF training
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import numpy as np


# ── Feature names (order must match DailyFeatures.to_array()) ─────────────────

FEATURE_NAMES: list[str] = [
    "gross_revenue_usd",
    "net_revenue_usd",
    "charge_count",
    "avg_charge_value_usd",
    "fee_rate",
    "refund_amount_usd",
    "refund_rate",
    "dispute_amount_usd",
    "net_balance_change_usd",
]


# ── Output type ────────────────────────────────────────────────────────────────

@dataclass
class DailyFeatures:
    """
    One day of aggregated revenue metrics for a simulated company.
    All monetary values in USD (float). Mirrors daily_revenue_metrics columns.
    """
    date: date
    gross_revenue_usd: float
    net_revenue_usd: float
    charge_count: int
    avg_charge_value_usd: float
    fee_rate: float               # 0.0 – 1.0
    refund_amount_usd: float
    refund_rate: float            # 0.0 – 1.0
    dispute_amount_usd: float
    net_balance_change_usd: float

    def to_array(self) -> np.ndarray:
        """Return feature vector matching FEATURE_NAMES order."""
        return np.array([
            self.gross_revenue_usd,
            self.net_revenue_usd,
            self.charge_count,
            self.avg_charge_value_usd,
            self.fee_rate,
            self.refund_amount_usd,
            self.refund_rate,
            self.dispute_amount_usd,
            self.net_balance_change_usd,
        ], dtype=np.float64)


# ── Business profiles ──────────────────────────────────────────────────────────

@dataclass
class SimProfile:
    """
    Full parameter set describing a business archetype's daily revenue patterns.
    """
    name: str

    # Daily charge volume
    daily_charges_mean: float     # weekday baseline
    daily_charges_cv: float       # coefficient of variation (std / mean)

    # Charge value distribution (USD, log-normal)
    avg_charge_usd: float
    charge_value_cv: float        # higher = more right-skewed

    # Stripe fee structure
    fee_pct: float                # e.g. 0.029
    fee_fixed_usd: float          # e.g. 0.30

    # Refund patterns
    refund_rate_mean: float       # baseline fraction of gross revenue
    refund_rate_cv: float         # day-to-day noise on refund_rate
    refund_autocorr: float        # AR(1) coefficient (0 = no memory, 1 = full memory)

    # Dispute patterns (Poisson: most days = 0)
    dispute_rate_mean: float      # expected disputes per charge
    dispute_value_fraction: float # dispute amount as fraction of avg_charge_usd

    # Seasonality
    weekend_factor: float         # weekend volume vs weekday (< 1 = drops, > 1 = peaks)
    month_end_factor: float       # days 28-31 multiplier (SaaS renewal spike)
    quarter_end_boost: float      # last 7 days of Mar/Jun/Sep/Dec (B2B deal close)

    # Autocorrelation for revenue
    revenue_ar1: float            # AR(1) coeff for daily gross revenue (0.2 – 0.5)

    # Growth
    monthly_growth: float         # compound monthly growth rate


PROFILES: dict[str, SimProfile] = {
    "saas_stable": SimProfile(
        name="SaaS Stable",
        daily_charges_mean=85,
        daily_charges_cv=0.10,
        avg_charge_usd=120.0,
        charge_value_cv=0.30,
        fee_pct=0.029,
        fee_fixed_usd=0.30,
        refund_rate_mean=0.012,
        refund_rate_cv=0.35,
        refund_autocorr=0.35,
        dispute_rate_mean=0.002,
        dispute_value_fraction=1.0,
        weekend_factor=0.15,
        month_end_factor=1.28,    # subscription renewals cluster here
        quarter_end_boost=1.0,
        revenue_ar1=0.35,
        monthly_growth=0.04,
    ),
    "ecommerce": SimProfile(
        name="E-Commerce",
        daily_charges_mean=320,
        daily_charges_cv=0.15,
        avg_charge_usd=65.0,
        charge_value_cv=0.55,
        fee_pct=0.029,
        fee_fixed_usd=0.30,
        refund_rate_mean=0.038,
        refund_rate_cv=0.35,
        refund_autocorr=0.25,
        dispute_rate_mean=0.006,
        dispute_value_fraction=0.90,
        weekend_factor=1.35,      # e-commerce peaks on weekends
        month_end_factor=1.0,
        quarter_end_boost=1.0,
        revenue_ar1=0.25,
        monthly_growth=0.06,
    ),
    "marketplace": SimProfile(
        name="Marketplace",
        daily_charges_mean=210,
        daily_charges_cv=0.18,
        avg_charge_usd=95.0,
        charge_value_cv=0.70,     # wide range: $5 gigs to $500 projects
        fee_pct=0.029,
        fee_fixed_usd=0.30,
        refund_rate_mean=0.025,
        refund_rate_cv=0.45,
        refund_autocorr=0.30,
        dispute_rate_mean=0.008,
        dispute_value_fraction=0.85,
        weekend_factor=0.80,
        month_end_factor=1.05,
        quarter_end_boost=1.10,
        revenue_ar1=0.30,
        monthly_growth=0.08,
    ),
    "high_ticket_b2b": SimProfile(
        name="High-Ticket B2B",
        daily_charges_mean=12,
        daily_charges_cv=0.35,    # high variance: some days 0 charges, some days 30+
        avg_charge_usd=4_500.0,
        charge_value_cv=0.85,     # $500 – $50k deals
        fee_pct=0.029,
        fee_fixed_usd=0.30,
        refund_rate_mean=0.005,
        refund_rate_cv=0.50,
        refund_autocorr=0.20,
        dispute_rate_mean=0.001,
        dispute_value_fraction=1.0,
        weekend_factor=0.05,      # nearly no B2B on weekends
        month_end_factor=1.15,
        quarter_end_boost=1.55,   # strong Q-end deal close push
        revenue_ar1=0.45,         # enterprise pipelines create strong autocorr
        monthly_growth=0.05,
    ),
}


# ── Core simulator ─────────────────────────────────────────────────────────────

class BusinessSimulator:
    """
    Generates realistic daily revenue feature vectors per business profile.

    Two main methods:
      generate_company() — one company's full time series (list[DailyFeatures])
      generate_corpus()  — bulk matrix for ML training (np.ndarray)
    """

    # ── Season helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _is_weekend(d: date) -> bool:
        return d.weekday() >= 5

    @staticmethod
    def _month_end_factor(d: date, profile: SimProfile) -> float:
        """Return the month-end multiplier if in the last 4 days of the month."""
        # Check if within last 4 days by testing if (d + 4 days).month != d.month
        next_month_start = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        days_to_month_end = (next_month_start - d).days
        if days_to_month_end <= 4:
            return profile.month_end_factor
        return 1.0

    @staticmethod
    def _quarter_end_factor(d: date, profile: SimProfile) -> float:
        """Return the quarter-end boost if in the last 7 days of a quarter."""
        quarter_ends = {3: 31, 6: 30, 9: 30, 12: 31}
        if d.month not in quarter_ends:
            return 1.0
        last_day = quarter_ends[d.month]
        if (last_day - d.day) < 7:
            return profile.quarter_end_boost
        return 1.0

    # ── Sampling helpers ──────────────────────────────────────────────────────

    def _sample_charge_value(self, rng: np.random.Generator, profile: SimProfile) -> float:
        """Log-normal charge value in USD (right-skewed, always positive)."""
        mean = profile.avg_charge_usd
        cv = profile.charge_value_cv
        sigma = np.sqrt(np.log(1 + cv ** 2))
        mu = np.log(mean) - sigma ** 2 / 2
        val = float(rng.lognormal(mu, sigma))
        return max(0.50, min(val, 50_000.0))

    def _calc_fee(self, amount_usd: float, profile: SimProfile) -> float:
        """Stripe fee for a charge (percentage + fixed)."""
        return amount_usd * profile.fee_pct + profile.fee_fixed_usd

    # ── Single company generation ─────────────────────────────────────────────

    def generate_company(
        self,
        profile: str = "saas_stable",
        days: int = 180,
        seed: int = 42,
        start_date: Optional[date] = None,
    ) -> list[DailyFeatures]:
        """
        Generate `days` daily feature records for one simulated company.

        The time series includes:
          - Compound monthly growth
          - Weekly seasonality (weekend_factor)
          - Monthly seasonality (month_end_factor)
          - Quarterly seasonality (quarter_end_boost)
          - AR(1) autocorrelation for revenue and refund_rate
          - Poisson-process disputes (sparse)

        Returns a list of DailyFeatures sorted by date (oldest first).
        """
        if profile not in PROFILES:
            raise ValueError(f"Unknown profile {profile!r}. Choose from: {list(PROFILES)}")
        p = PROFILES[profile]
        rng = np.random.default_rng(seed)

        start = start_date or (date.today() - timedelta(days=days - 1))
        result: list[DailyFeatures] = []

        # ── AR(1) state variables ─────────────────────────────────────────────
        # Initialize revenue AR state at the expected baseline for day 0
        ar_revenue: float = p.daily_charges_mean * p.avg_charge_usd
        ar_refund_rate: float = p.refund_rate_mean

        for offset in range(days):
            d = start + timedelta(days=offset)

            # ── Growth trend (compound monthly) ──────────────────────────────
            growth = (1 + p.monthly_growth) ** (offset / 30.0)

            # ── Seasonality multipliers ───────────────────────────────────────
            season_mult = 1.0
            if self._is_weekend(d):
                season_mult *= p.weekend_factor
            season_mult *= self._month_end_factor(d, p)
            season_mult *= self._quarter_end_factor(d, p)

            # ── Expected daily revenue (baseline) ────────────────────────────
            baseline_revenue = p.daily_charges_mean * p.avg_charge_usd * growth * season_mult

            # ── AR(1) revenue with noise ──────────────────────────────────────
            noise_std = baseline_revenue * p.daily_charges_cv
            innovation = float(rng.normal(0.0, noise_std))
            ar_revenue = (
                p.revenue_ar1 * ar_revenue
                + (1.0 - p.revenue_ar1) * baseline_revenue
                + innovation
            )
            gross_revenue = max(0.0, ar_revenue)

            # ── Charge count from gross revenue ──────────────────────────────
            # avg_charge_value is lightly noisy around the profile mean
            avg_charge = self._sample_charge_value(rng, p)
            charge_count = max(0, int(gross_revenue / avg_charge)) if avg_charge > 0 else 0

            # Recompute gross to be consistent with discrete charge count
            if charge_count > 0:
                gross_revenue = charge_count * avg_charge
            else:
                gross_revenue = 0.0

            # ── Fees ──────────────────────────────────────────────────────────
            fee_per_charge = self._calc_fee(avg_charge, p) if charge_count > 0 else 0.0
            total_fees = fee_per_charge * charge_count
            fee_rate = (total_fees / gross_revenue) if gross_revenue > 0 else p.fee_pct
            net_revenue = gross_revenue - total_fees

            # ── AR(1) refund rate ─────────────────────────────────────────────
            refund_noise_std = p.refund_rate_mean * p.refund_rate_cv
            refund_innovation = float(rng.normal(0.0, refund_noise_std))
            ar_refund_rate = (
                p.refund_autocorr * ar_refund_rate
                + (1.0 - p.refund_autocorr) * p.refund_rate_mean
                + refund_innovation
            )
            refund_rate = float(np.clip(ar_refund_rate, 0.0, 0.90))

            refund_amount = gross_revenue * refund_rate

            # ── Disputes (Poisson, sparse) ────────────────────────────────────
            expected_disputes = charge_count * p.dispute_rate_mean
            n_disputes = int(rng.poisson(max(0.0, expected_disputes)))
            dispute_amount = n_disputes * avg_charge * p.dispute_value_fraction

            # ── Net balance change ────────────────────────────────────────────
            net_balance_change = net_revenue - refund_amount - dispute_amount

            result.append(DailyFeatures(
                date=d,
                gross_revenue_usd=round(gross_revenue, 2),
                net_revenue_usd=round(net_revenue, 2),
                charge_count=charge_count,
                avg_charge_value_usd=round(avg_charge, 2),
                fee_rate=round(fee_rate, 6),
                refund_amount_usd=round(refund_amount, 2),
                refund_rate=round(refund_rate, 6),
                dispute_amount_usd=round(dispute_amount, 2),
                net_balance_change_usd=round(net_balance_change, 2),
            ))

        return result

    # ── Bulk corpus generation ────────────────────────────────────────────────

    def generate_corpus(
        self,
        n_companies: int = 500,
        days: int = 180,
        profile_weights: Optional[dict[str, float]] = None,
        seed: int = 0,
    ) -> np.ndarray:
        """
        Generate n_companies × days daily feature vectors for ML training.

        Each company is generated with a random seed derived from `seed`, so
        results are fully reproducible. Profiles are sampled according to
        `profile_weights` (default: equal weight across all 4 profiles).

        Returns:
            np.ndarray of shape (n_companies * days, len(FEATURE_NAMES))
            Row order: company 0 days 0-N, company 1 days 0-N, ...
        """
        if profile_weights is None:
            profile_weights = {p: 1.0 for p in PROFILES}

        # Normalize weights to probabilities
        profiles = list(profile_weights.keys())
        weights = np.array([profile_weights[p] for p in profiles], dtype=float)
        probs = weights / weights.sum()

        master_rng = np.random.default_rng(seed)
        all_rows: list[np.ndarray] = []

        for company_idx in range(n_companies):
            # Pick a profile for this company
            profile = str(master_rng.choice(profiles, p=probs))
            company_seed = int(master_rng.integers(0, 2**31))

            features = self.generate_company(
                profile=profile,
                days=days,
                seed=company_seed,
            )
            for f in features:
                all_rows.append(f.to_array())

        return np.vstack(all_rows)
