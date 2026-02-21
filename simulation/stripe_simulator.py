"""
STRIPE SIMULATOR
=================
Generates realistic Stripe BalanceTransaction objects for algorithm calibration.

Design goals:
- Output is structurally identical to real Stripe API responses (validated against
  data_contracts/stripe_schemas.py).
- Business patterns are realistic: weekday/weekend rhythm, monthly growth trend,
  realistic fee rates, correlated refund bursts.
- Anomalies are injected explicitly and reproducibly (controlled by scenario dicts),
  not randomly, so detection tests have known ground truth.
- All monetary values in INTEGER CENTS.

Simulated business profiles:
  "saas_stable"    — B2B SaaS, steady MRR, low refund rate (~1.5%), ~$120 ATV
  "ecommerce"      — B2C e-commerce, high volume, higher refunds (~4%), ~$65 ATV,
                     strong weekend spikes
  "marketplace"    — High volume, variable ticket sizes, elevated disputes (~0.8%)

Usage:
  from simulation.stripe_simulator import StripeSimulator, SCENARIOS

  sim = StripeSimulator(profile="saas_stable", seed=42)
  txns = sim.generate(days=90, anomaly_scenarios=SCENARIOS["saas_stable"])
  # txns: list of dicts, each matching StripeBalanceTransaction schema
"""

import json
import random
import string
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np


# ── Stripe ID generators ──────────────────────────────────────────────────────

def _stripe_id(prefix: str, length: int = 24) -> str:
    """Generate a plausible Stripe object ID: e.g. txn_1ABCdef2GHIjkl3MNOpqr."""
    chars = string.ascii_letters + string.digits
    suffix = "".join(random.choices(chars, k=length))
    return f"{prefix}_{suffix}"


def _unix(dt: datetime) -> int:
    return int(dt.timestamp())


# ── Business profiles ─────────────────────────────────────────────────────────

@dataclass
class BusinessProfile:
    """
    Parameters that describe a business's normal payment patterns.
    All monetary values in CENTS.
    """
    name: str

    # Daily charge count (weekday baseline)
    daily_charges_mean: int       # mean number of charges per weekday
    daily_charges_std: float      # std dev as fraction of mean

    # Average charge value (cents)
    avg_charge_cents: int         # e.g. 12000 = $120.00
    charge_value_std: float       # std dev as fraction of mean (skewed right)

    # Stripe fee structure (approximate)
    stripe_pct_fee: float         # e.g. 0.029  (2.9%)
    stripe_fixed_fee: int         # e.g. 30     ($0.30 in cents)

    # Refund patterns
    refund_rate: float            # fraction of charge count that gets refunded
    refund_delay_days: tuple      # (min, max) days after charge

    # Dispute patterns
    dispute_rate: float           # fraction of charge count disputed
    dispute_delay_days: tuple     # (min, max) days after charge

    # Payout cadence
    payout_interval_days: int     # e.g. 2 (Stripe standard = T+2)

    # Weekend factor (weekend volume vs weekday)
    weekend_factor: float         # e.g. 0.3 means weekends are 30% of weekday volume

    # Monthly growth trend (fraction per month)
    monthly_growth: float         # e.g. 0.03 = 3% month-over-month volume growth

    # Currency
    currency: str = "usd"


PROFILES: dict[str, BusinessProfile] = {
    "saas_stable": BusinessProfile(
        name="SaaS Stable",
        daily_charges_mean=85,
        daily_charges_std=0.08,
        avg_charge_cents=12_000,        # $120 ATV
        charge_value_std=0.35,
        stripe_pct_fee=0.029,
        stripe_fixed_fee=30,
        refund_rate=0.015,
        refund_delay_days=(1, 14),
        dispute_rate=0.002,
        dispute_delay_days=(7, 60),
        payout_interval_days=2,
        weekend_factor=0.15,            # SaaS barely active on weekends
        monthly_growth=0.04,
        currency="usd",
    ),
    "ecommerce": BusinessProfile(
        name="E-Commerce",
        daily_charges_mean=320,
        daily_charges_std=0.12,
        avg_charge_cents=6_500,         # $65 ATV
        charge_value_std=0.55,
        stripe_pct_fee=0.029,
        stripe_fixed_fee=30,
        refund_rate=0.04,
        refund_delay_days=(1, 30),
        dispute_rate=0.006,
        dispute_delay_days=(7, 90),
        payout_interval_days=2,
        weekend_factor=1.35,            # e-commerce peaks on weekends
        monthly_growth=0.06,
        currency="usd",
    ),
    "marketplace": BusinessProfile(
        name="Marketplace",
        daily_charges_mean=210,
        daily_charges_std=0.15,
        avg_charge_cents=9_500,         # $95 ATV
        charge_value_std=0.70,          # high variance — from $5 to $500+
        stripe_pct_fee=0.029,
        stripe_fixed_fee=30,
        refund_rate=0.025,
        refund_delay_days=(1, 21),
        dispute_rate=0.008,
        dispute_delay_days=(7, 75),
        payout_interval_days=2,
        weekend_factor=0.80,
        monthly_growth=0.08,
        currency="usd",
    ),
    "high_ticket_b2b": BusinessProfile(
        name="High-Ticket B2B",
        daily_charges_mean=12,
        daily_charges_std=0.35,
        avg_charge_cents=450_000,       # $4,500 ATV
        charge_value_std=0.85,          # wide range: $500 – $50k
        stripe_pct_fee=0.029,
        stripe_fixed_fee=30,
        refund_rate=0.005,
        refund_delay_days=(1, 30),
        dispute_rate=0.001,
        dispute_delay_days=(14, 90),
        payout_interval_days=2,
        weekend_factor=0.05,            # almost no B2B on weekends
        monthly_growth=0.05,
        currency="usd",
    ),
}


# ── Anomaly scenarios ─────────────────────────────────────────────────────────

@dataclass
class AnomalyScenario:
    """
    A deliberate anomaly injected on a specific day offset from simulation start.

    day_offset: int — 0 = first day, N = Nth day of the simulation window
    category:   str — which reporting_category is affected
                     ("charge", "refund", "dispute")
    multiplier: float — applied to the *count* of transactions that day
                        e.g. 0.3 means 70% drop, 2.5 means 150% spike
    value_multiplier: float — optionally also multiply the charge value
                             (for avg_charge_value anomalies)
    label:      str — human-readable name for test assertions
    """
    day_offset: int
    category: str
    multiplier: float
    value_multiplier: float = 1.0
    label: str = ""


# Known ground-truth scenarios per profile.
# These are the anomalies the detection algorithm MUST find.
SCENARIOS: dict[str, list[AnomalyScenario]] = {
    "saas_stable": [
        AnomalyScenario(day_offset=7,  category="charge",  multiplier=0.40,
                        label="revenue_drop_40pct"),
        AnomalyScenario(day_offset=18, category="refund",  multiplier=4.5,
                        label="refund_spike_350pct"),
        AnomalyScenario(day_offset=31, category="charge",  multiplier=2.20,
                        label="revenue_spike_120pct"),
        AnomalyScenario(day_offset=45, category="charge",  multiplier=1.0,
                        value_multiplier=3.5,
                        label="avg_ticket_spike_250pct"),
        AnomalyScenario(day_offset=58, category="dispute", multiplier=8.0,
                        label="dispute_burst"),
        AnomalyScenario(day_offset=72, category="charge",  multiplier=0.25,
                        label="severe_revenue_drop_75pct"),
    ],
    "ecommerce": [
        AnomalyScenario(day_offset=5,  category="charge",  multiplier=2.80,
                        label="flash_sale_spike"),
        AnomalyScenario(day_offset=12, category="refund",  multiplier=5.0,
                        label="mass_return_event"),
        AnomalyScenario(day_offset=30, category="charge",  multiplier=0.30,
                        label="gateway_outage"),
        AnomalyScenario(day_offset=55, category="dispute", multiplier=6.0,
                        label="fraud_wave"),
        AnomalyScenario(day_offset=70, category="charge",  multiplier=3.50,
                        label="black_friday_spike"),
    ],
    "marketplace": [
        AnomalyScenario(day_offset=10, category="charge",  multiplier=0.20,
                        label="severe_drop"),
        AnomalyScenario(day_offset=25, category="refund",  multiplier=7.0,
                        label="refund_storm"),
        AnomalyScenario(day_offset=40, category="charge",  multiplier=2.60,
                        label="viral_spike"),
        AnomalyScenario(day_offset=60, category="dispute", multiplier=9.0,
                        label="dispute_wave"),
    ],
    "high_ticket_b2b": [
        AnomalyScenario(day_offset=8,  category="charge",  multiplier=0.0,
                        label="complete_outage_day"),
        AnomalyScenario(day_offset=20, category="charge",  multiplier=1.0,
                        value_multiplier=5.0,
                        label="enterprise_deal_spike"),
        AnomalyScenario(day_offset=45, category="refund",  multiplier=8.0,
                        label="contract_cancellation_wave"),
        AnomalyScenario(day_offset=70, category="dispute", multiplier=10.0,
                        label="chargeback_burst"),
    ],
}


# ── Core simulator ────────────────────────────────────────────────────────────

class StripeSimulator:
    """
    Generates a list of Stripe-shaped BalanceTransaction dicts for a given
    business profile over a requested number of days.

    The output dicts are validated against StripeBalanceTransaction in seed_demo.py.
    """

    def __init__(
        self,
        profile: str = "saas_stable",
        seed: int = 42,
        stripe_account_id: str = "__default__",
        start_date: Optional[date] = None,
    ):
        if profile not in PROFILES:
            raise ValueError(f"Unknown profile {profile!r}. Choose from: {list(PROFILES)}")
        self.profile = PROFILES[profile]
        self.stripe_account_id = stripe_account_id
        self.start_date = start_date or (date.today() - timedelta(days=90))
        self._rng = np.random.default_rng(seed)
        random.seed(seed)
        self._used_ids: set[str] = set()

    # ── ID helpers ────────────────────────────────────────────────────────────

    def _unique_id(self, prefix: str) -> str:
        while True:
            sid = _stripe_id(prefix)
            if sid not in self._used_ids:
                self._used_ids.add(sid)
                return sid

    # ── Charge value sampler ──────────────────────────────────────────────────

    def _sample_charge_cents(self, value_multiplier: float = 1.0) -> int:
        """
        Sample a single charge amount in cents.
        Uses a log-normal distribution to simulate realistic right-skewed ticket sizes.
        """
        p = self.profile
        mean = p.avg_charge_cents * value_multiplier
        std = mean * p.charge_value_std
        # Log-normal: positive values, right-skewed
        sigma = np.sqrt(np.log(1 + (std / mean) ** 2))
        mu = np.log(mean) - sigma ** 2 / 2
        cents = int(self._rng.lognormal(mu, sigma))
        # Floor at $0.50, cap at $50,000 (Stripe practical max without special approval)
        return max(50, min(cents, 5_000_000))

    # ── Stripe fee calculator ─────────────────────────────────────────────────

    def _calc_fee(self, amount_cents: int) -> int:
        """Calculate Stripe's processing fee for a charge."""
        p = self.profile
        fee = int(amount_cents * p.stripe_pct_fee) + p.stripe_fixed_fee
        return fee

    # ── Day-level charge count ────────────────────────────────────────────────

    def _daily_charge_count(
        self,
        day_offset: int,
        is_weekend: bool,
        multiplier: float = 1.0,
    ) -> int:
        """
        How many charges occur on this day, accounting for:
        - growth trend (compounding monthly)
        - weekend factor
        - noise
        - anomaly multiplier
        """
        p = self.profile
        # Compound monthly growth: each day is 1/30 of a month
        growth = (1 + p.monthly_growth) ** (day_offset / 30)
        base = p.daily_charges_mean * growth

        # Weekend adjustment
        if is_weekend:
            base *= p.weekend_factor

        # Gaussian noise
        noise_scale = base * p.daily_charges_std
        count = int(self._rng.normal(base, noise_scale) * multiplier)
        return max(0, count)

    # ── Single transaction builders ───────────────────────────────────────────

    def _build_charge(
        self,
        dt: datetime,
        value_multiplier: float = 1.0,
    ) -> dict:
        amount = self._sample_charge_cents(value_multiplier)
        fee = self._calc_fee(amount)
        net = amount - fee
        charge_id = self._unique_id("ch")
        txn_id = self._unique_id("txn")
        available_dt = dt + timedelta(days=self.profile.payout_interval_days)
        return {
            "id": txn_id,
            "object": "balance_transaction",
            "amount": amount,
            "fee": fee,
            "net": net,
            "currency": self.profile.currency,
            "type": "charge",
            "reporting_category": "charge",
            "status": "available",
            "created": _unix(dt),
            "available_on": _unix(available_dt),
            "source": charge_id,
            "description": f"Charge for order",
            "fee_details": [
                {
                    "amount": fee,
                    "currency": self.profile.currency,
                    "description": "Stripe processing fees",
                    "type": "stripe_fee",
                }
            ],
            "metadata": {},
        }

    def _build_refund(self, dt: datetime, original_charge: dict) -> dict:
        """Build a refund transaction referencing a prior charge."""
        # Refund is partial (50–100% of original) or full
        refund_fraction = self._rng.uniform(0.5, 1.0)
        refund_amount = -int(abs(original_charge["amount"]) * refund_fraction)
        # Refunds incur no Stripe fee (fee is returned)
        refund_id = self._unique_id("re")
        txn_id = self._unique_id("txn")
        available_dt = dt + timedelta(days=self.profile.payout_interval_days)
        return {
            "id": txn_id,
            "object": "balance_transaction",
            "amount": refund_amount,    # negative
            "fee": 0,
            "net": refund_amount,       # no fee on refunds
            "currency": self.profile.currency,
            "type": "refund",
            "reporting_category": "refund",
            "status": "available",
            "created": _unix(dt),
            "available_on": _unix(available_dt),
            "source": refund_id,
            "description": "Refund",
            "fee_details": [],
            "metadata": {},
        }

    def _build_dispute(self, dt: datetime, original_charge: dict) -> dict:
        """Build a dispute/chargeback transaction."""
        dispute_amount = -abs(original_charge["amount"])  # full chargeback
        dispute_fee = 1500  # Stripe charges $15 dispute fee
        txn_id = self._unique_id("txn")
        dp_id = self._unique_id("dp")
        available_dt = dt + timedelta(days=self.profile.payout_interval_days)
        return {
            "id": txn_id,
            "object": "balance_transaction",
            "amount": dispute_amount,   # negative
            "fee": dispute_fee,
            "net": dispute_amount - dispute_fee,
            "currency": self.profile.currency,
            "type": "adjustment",
            "reporting_category": "dispute",
            "status": "available",
            "created": _unix(dt),
            "available_on": _unix(available_dt),
            "source": dp_id,
            "description": "Chargeback",
            "fee_details": [
                {
                    "amount": dispute_fee,
                    "currency": self.profile.currency,
                    "description": "Dispute fee",
                    "type": "stripe_fee",
                }
            ],
            "metadata": {},
        }

    def _build_payout(self, dt: datetime, net_amount: int) -> dict:
        """Build a payout transaction (funds sent to bank)."""
        txn_id = self._unique_id("txn")
        po_id = self._unique_id("po")
        return {
            "id": txn_id,
            "object": "balance_transaction",
            "amount": -abs(net_amount),   # negative = leaving Stripe balance
            "fee": 0,
            "net": -abs(net_amount),
            "currency": self.profile.currency,
            "type": "payout",
            "reporting_category": "payout",
            "status": "available",
            "created": _unix(dt),
            "available_on": _unix(dt),
            "source": po_id,
            "description": "STRIPE PAYOUT",
            "fee_details": [],
            "metadata": {},
        }

    # ── Main generation method ────────────────────────────────────────────────

    def generate(
        self,
        days: int = 90,
        anomaly_scenarios: Optional[list[AnomalyScenario]] = None,
    ) -> list[dict]:
        """
        Generate `days` days of Stripe balance_transaction dicts.

        Returns a flat list of transaction dicts, unsorted (Stripe returns
        newest-first; we sort at ingestion time).

        Anomaly injection:
        - Charge count multiplier changes daily volume.
        - Value multiplier changes per-transaction ticket size.
        - Refund/dispute multipliers increase the fraction of charges that
          get refunded/disputed on that day.
        """
        scenarios_by_day: dict[int, list[AnomalyScenario]] = {}
        for scenario in (anomaly_scenarios or []):
            scenarios_by_day.setdefault(scenario.day_offset, []).append(scenario)

        all_transactions: list[dict] = []
        # Track recent charges to generate correlated refunds/disputes
        recent_charges: list[dict] = []

        for day_offset in range(days):
            day_date = self.start_date + timedelta(days=day_offset)
            is_weekend = day_date.weekday() >= 5  # Saturday=5, Sunday=6
            day_scenarios = scenarios_by_day.get(day_offset, [])

            # ── Determine multipliers for this day ────────────────────────────
            charge_mult = 1.0
            value_mult = 1.0
            refund_rate_mult = 1.0
            dispute_rate_mult = 1.0

            for scenario in day_scenarios:
                if scenario.category == "charge":
                    charge_mult = scenario.multiplier
                    value_mult = scenario.value_multiplier
                elif scenario.category == "refund":
                    refund_rate_mult = scenario.multiplier
                elif scenario.category == "dispute":
                    dispute_rate_mult = scenario.multiplier

            # ── Generate charges ──────────────────────────────────────────────
            n_charges = self._daily_charge_count(day_offset, is_weekend, charge_mult)

            day_charges = []
            for i in range(n_charges):
                # Spread charges across the business day (8 AM – 10 PM local)
                hour = self._rng.integers(8, 22)
                minute = self._rng.integers(0, 60)
                second = self._rng.integers(0, 60)
                dt = datetime(
                    day_date.year, day_date.month, day_date.day,
                    int(hour), int(minute), int(second),
                    tzinfo=timezone.utc,
                )
                txn = self._build_charge(dt, value_mult)
                day_charges.append(txn)
                recent_charges.append(txn)

            all_transactions.extend(day_charges)

            # ── Generate refunds from recent charges ──────────────────────────
            effective_refund_rate = self.profile.refund_rate * refund_rate_mult
            # Cap at 95% to stay physically plausible
            effective_refund_rate = min(effective_refund_rate, 0.95)

            refund_pool = [
                c for c in recent_charges
                if abs(
                    day_date - datetime.fromtimestamp(c["created"], tz=timezone.utc).date()
                ).days <= self.profile.refund_delay_days[1]
            ]

            n_refunds = int(len(refund_pool) * effective_refund_rate * 0.1)
            # 0.1: refunds are spread over multiple days, so each day sees ~10% of the pool
            n_refunds = max(0, n_refunds)

            for charge in self._rng.choice(
                refund_pool, size=min(n_refunds, len(refund_pool)), replace=False
            ) if refund_pool else []:
                dt = datetime(
                    day_date.year, day_date.month, day_date.day,
                    int(self._rng.integers(9, 18)), 0, 0, tzinfo=timezone.utc
                )
                all_transactions.append(self._build_refund(dt, charge))

            # ── Generate disputes from older charges ──────────────────────────
            effective_dispute_rate = self.profile.dispute_rate * dispute_rate_mult
            effective_dispute_rate = min(effective_dispute_rate, 0.90)

            dispute_pool = [
                c for c in recent_charges
                if self.profile.dispute_delay_days[0] <= abs(
                    day_date - datetime.fromtimestamp(c["created"], tz=timezone.utc).date()
                ).days <= self.profile.dispute_delay_days[1]
            ]

            n_disputes = int(len(dispute_pool) * effective_dispute_rate * 0.02)
            n_disputes = max(0, n_disputes)

            for charge in self._rng.choice(
                dispute_pool, size=min(n_disputes, len(dispute_pool)), replace=False
            ) if dispute_pool else []:
                dt = datetime(
                    day_date.year, day_date.month, day_date.day,
                    int(self._rng.integers(9, 18)), 0, 0, tzinfo=timezone.utc
                )
                all_transactions.append(self._build_dispute(dt, charge))

            # ── Trim old charges from pool to save memory ─────────────────────
            cutoff_date = day_date - timedelta(days=self.profile.dispute_delay_days[1] + 5)
            recent_charges = [
                c for c in recent_charges
                if datetime.fromtimestamp(c["created"], tz=timezone.utc).date() >= cutoff_date
            ]

        # Stripe API returns newest first — mimic that for realism
        all_transactions.sort(key=lambda t: t["created"], reverse=True)
        return all_transactions

    def summary(self, transactions: list[dict]) -> dict:
        """
        Quick summary of a generated dataset for sanity-checking.
        Returns aggregate stats per reporting_category.
        """
        from collections import defaultdict
        stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_amount": 0})
        for t in transactions:
            cat = t["reporting_category"]
            stats[cat]["count"] += 1
            stats[cat]["total_amount"] += t["amount"]
        return dict(stats)
