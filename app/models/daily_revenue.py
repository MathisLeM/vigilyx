"""
FEATURE LAYER — daily_revenue_metrics
=======================================
Aggregated daily revenue metrics derived from raw_balance_transactions.

Design principles:
- One row per (tenant_id, stripe_account_id, currency, snapshot_date).
- All monetary fields stored in INTEGER CENTS (original currency)
  AND duplicated in USD cents (*_usd columns) for cross-currency comparison.
- Fully recomputable: if aggregation logic changes, truncate this table
  and re-derive from raw_balance_transactions.
- computed_at tracks the last time this row was (re)computed.

Metrics computed per day:

  REVENUE (from reporting_category = 'charge')
  ─────────────────────────────────────────────
  gross_revenue       SUM(amount)  — what customers paid (pre-fee)
  total_fees          SUM(fee)     — Stripe's cut
  net_revenue         SUM(net)     — what lands in your balance
  charge_count        COUNT(*)
  avg_charge_value    gross_revenue / charge_count  (NULL if count = 0)
  fee_rate            total_fees / gross_revenue    (NULL if gross = 0)

  REFUNDS (from reporting_category = 'refund')
  ─────────────────────────────────────────────
  refund_amount       SUM(ABS(amount))  — Stripe amounts are negative here
  refund_count        COUNT(*)
  refund_rate         refund_amount / gross_revenue  (NULL if gross = 0)

  DISPUTES (from reporting_category = 'dispute')
  ────────────────────────────────────────────────
  dispute_amount      SUM(ABS(amount))
  dispute_count       COUNT(*)

  COMPOSITE
  ──────────
  net_balance_change  net_revenue - refund_amount - dispute_amount
                      Represents the true net impact on the account balance
                      before payouts.

Anomaly detection runs on the *_usd columns so metrics are
comparable across currencies within a tenant.
"""

from datetime import date, datetime, timezone
from sqlalchemy import (
    BigInteger, Column, Date, DateTime, Float,
    Index, Integer, String, UniqueConstraint,
)
from app.database import Base


class DailyRevenueMetrics(Base):
    __tablename__ = "daily_revenue_metrics"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "stripe_account_id", "currency", "snapshot_date",
            name="uq_daily_rev_tenant_account_currency_date",
        ),
        Index("ix_daily_rev_tenant_date", "tenant_id", "snapshot_date"),
    )

    # ── Internal PK ──────────────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True)

    # ── Scoping ───────────────────────────────────────────────────────────────
    tenant_id = Column(Integer, nullable=False, index=True)
    stripe_account_id = Column(String(50), nullable=False)
    currency = Column(String(3), nullable=False)            # "usd", "eur", etc.
    snapshot_date = Column(Date, nullable=False, index=True)

    # ── Revenue (original currency, cents) ───────────────────────────────────
    gross_revenue = Column(BigInteger, nullable=False, default=0)
    total_fees = Column(BigInteger, nullable=False, default=0)
    net_revenue = Column(BigInteger, nullable=False, default=0)
    charge_count = Column(Integer, nullable=False, default=0)
    avg_charge_value = Column(BigInteger, nullable=True)    # NULL if no charges
    fee_rate = Column(Float, nullable=True)                 # 0.0 – 1.0

    # ── Revenue (USD cents) ───────────────────────────────────────────────────
    gross_revenue_usd = Column(BigInteger, nullable=False, default=0)
    total_fees_usd = Column(BigInteger, nullable=False, default=0)
    net_revenue_usd = Column(BigInteger, nullable=False, default=0)
    avg_charge_value_usd = Column(BigInteger, nullable=True)

    # ── Refunds (original currency, cents) ───────────────────────────────────
    refund_amount = Column(BigInteger, nullable=False, default=0)
    refund_count = Column(Integer, nullable=False, default=0)
    refund_rate = Column(Float, nullable=True)              # refund_amount / gross_revenue

    # ── Refunds (USD cents) ───────────────────────────────────────────────────
    refund_amount_usd = Column(BigInteger, nullable=False, default=0)

    # ── Disputes (original currency, cents) ──────────────────────────────────
    dispute_amount = Column(BigInteger, nullable=False, default=0)
    dispute_count = Column(Integer, nullable=False, default=0)

    # ── Disputes (USD cents) ──────────────────────────────────────────────────
    dispute_amount_usd = Column(BigInteger, nullable=False, default=0)

    # ── Composite (USD cents) ─────────────────────────────────────────────────
    # net_revenue_usd - refund_amount_usd - dispute_amount_usd
    net_balance_change_usd = Column(BigInteger, nullable=True)

    # ── Bookkeeping ───────────────────────────────────────────────────────────
    computed_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<DailyRevenue date={self.snapshot_date} "
            f"tenant={self.tenant_id} "
            f"net_usd={self.net_revenue_usd}¢>"
        )
