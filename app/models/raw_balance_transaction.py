"""
RAW LAYER — raw_balance_transactions
=====================================
Immutable mirror of Stripe BalanceTransaction objects.

Design principles:
- Insert-only: rows are never updated after ingestion (except ingested_at metadata).
- Dedup key: (tenant_id, stripe_account_id, stripe_id) — Stripe IDs are globally unique
  per account, so this guarantees idempotent ingestion.
- Monetary amounts stored as INTEGER CENTS in original currency (Stripe standard).
  USD-converted amounts are stored alongside for cross-currency aggregation.
- JSON fields (fee_details, metadata) stored as TEXT to stay Postgres-compatible
  (SQLite has no native JSON type; Postgres promotes TEXT → JSONB automatically
  when you switch engines).

Stripe reporting_category values covered by revenue monitoring scope:
  - "charge"           → payment collected from customer
  - "refund"           → refund issued to customer (amount is negative)
  - "dispute"          → chargeback / dispute adjustment (amount is negative)
  - "payout"           → funds sent to bank account
  - "stripe_fee"       → additional Stripe fees (rare)
  - "other_adjustment" → manual adjustments

Reference: https://stripe.com/docs/reports/balance-transaction-types
"""

from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Column, DateTime, Float, Index,
    Integer, String, Text, UniqueConstraint,
)
from app.database import Base


class RawBalanceTransaction(Base):
    __tablename__ = "raw_balance_transactions"
    __table_args__ = (
        # Primary dedup constraint: one Stripe txn ID per account per tenant
        UniqueConstraint(
            "tenant_id", "stripe_account_id", "stripe_id",
            name="uq_raw_bt_tenant_account_stripe",
        ),
        # Query patterns: most reads filter by (tenant, account, created_date range)
        Index("ix_raw_bt_tenant_account_created", "tenant_id", "stripe_account_id", "created_at"),
        Index("ix_raw_bt_reporting_category", "reporting_category"),
    )

    # ── Internal PK ──────────────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True)

    # ── Tenant / account scoping ─────────────────────────────────────────────
    tenant_id = Column(Integer, nullable=False, index=True)
    # Stripe Connect account ID (acct_xxx) or "__default__" for single-account keys
    stripe_account_id = Column(String(50), nullable=False, index=True)

    # ── Stripe identity ───────────────────────────────────────────────────────
    stripe_id = Column(String(50), nullable=False)          # txn_xxx
    stripe_object = Column(String(30), default="balance_transaction")

    # ── Monetary amounts (INTEGER CENTS, original Stripe currency) ────────────
    amount = Column(BigInteger, nullable=False)             # gross; negative for refunds/disputes
    fee = Column(BigInteger, nullable=False, default=0)     # Stripe processing fee (always >= 0)
    net = Column(BigInteger, nullable=False)                # amount - fee

    # ── Currency ──────────────────────────────────────────────────────────────
    currency = Column(String(3), nullable=False)            # ISO 4217 lowercase: "usd", "eur"

    # ── USD-converted amounts (for cross-currency feature aggregation) ─────────
    # Exchange rate applied at ingestion time. NULL if currency == base currency.
    usd_exchange_rate = Column(Float, nullable=True)        # 1.0 for USD rows
    amount_usd = Column(BigInteger, nullable=True)          # amount * usd_exchange_rate
    fee_usd = Column(BigInteger, nullable=True)
    net_usd = Column(BigInteger, nullable=True)

    # ── Classification ────────────────────────────────────────────────────────
    # Stripe's high-level type: "charge", "refund", "adjustment", "payout", etc.
    type = Column(String(50), nullable=False)
    # Stripe's reporting_category: more specific, used for feature aggregation
    reporting_category = Column(String(50), nullable=False, index=True)
    # Lifecycle status: "available" (settled) or "pending" (not yet settled)
    status = Column(String(20), nullable=False)

    # ── Source object ─────────────────────────────────────────────────────────
    source_id = Column(String(50), nullable=True, index=True)  # ch_xxx, re_xxx, dp_xxx

    # ── Timestamps (from Stripe, stored as UTC datetime) ─────────────────────
    created_at = Column(DateTime, nullable=False)           # when Stripe created the txn
    available_on = Column(DateTime, nullable=True)          # when funds settle to balance

    # ── Descriptive metadata ──────────────────────────────────────────────────
    description = Column(Text, nullable=True)
    # Raw Stripe fee_details array, serialised as JSON string
    fee_details_json = Column(Text, nullable=True)
    # Any extra metadata from the source object
    metadata_json = Column(Text, nullable=True)

    # ── Ingestion bookkeeping ─────────────────────────────────────────────────
    ingested_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    # "api_poll" | "webhook" | "simulation" — tracks how this row arrived
    ingestion_source = Column(String(20), nullable=False, default="simulation")

    def __repr__(self) -> str:
        return (
            f"<RawBalanceTxn stripe_id={self.stripe_id!r} "
            f"category={self.reporting_category!r} "
            f"amount={self.amount} {self.currency.upper()}>"
        )
