"""
DATA CONTRACTS — Stripe object schemas
========================================
Pydantic models that define the expected shape of Stripe API responses.

These serve three purposes:
1. Validation: parse and validate raw Stripe JSON before ingestion.
2. Simulation: the simulator produces dicts that conform to these schemas,
   ensuring simulated data is always structurally identical to real Stripe data.
3. Documentation: a single source of truth for "what does a Stripe object look like".

Stripe API reference:
  https://stripe.com/docs/api/balance_transactions/object

Notes:
- All monetary amounts are INTEGER CENTS (Stripe standard).
- Timestamps are UNIX integers from Stripe; we parse them to datetime on ingestion.
- We only model the fields we actually use. Unknown fields are ignored (extra="ignore").
"""

from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ── Fee detail item ───────────────────────────────────────────────────────────

class StripeFeeDetail(BaseModel):
    """One item in the fee_details array of a balance_transaction."""

    model_config = {"extra": "ignore"}

    amount: int                    # cents
    currency: str                  # "usd"
    description: Optional[str] = None
    type: str                      # "stripe_fee" | "application_fee" | "tax"


# ── Balance Transaction ───────────────────────────────────────────────────────

# Stripe's full set of reporting categories (revenue monitoring scope highlighted)
ReportingCategory = Literal[
    "charge",               # ★ payment collected
    "refund",               # ★ refund issued
    "dispute",              # ★ chargeback / dispute
    "dispute_reversal",     # dispute won, funds returned
    "payout",               # ★ funds sent to bank
    "payout_reversal",      # payout failed, funds returned
    "transfer",             # Stripe Connect transfer
    "transfer_reversal",
    "stripe_fee",
    "tax",
    "other_adjustment",
    "advance",
    "advance_funding",
    "anticipation_repayment",
    "issuing_authorization_hold",
    "issuing_authorization_release",
    "issuing_dispute",
    "issuing_transaction",
    "obligation_inbound",
    "obligation_outbound",
    "obligation_reversal_inbound",
    "obligation_reversal_outbound",
    "obligation_payout",
    "obligation_payout_failure",
    "payment",              # synonym for "charge" in some Stripe versions
    "payment_refund",       # synonym for "refund"
    "payment_failure_refund",
    "refund_failure",
    "connect_collection_transfer",
    "link_cancellation",
    "network_cost",
    "topup",
    "topup_reversal",
    "climate_order_purchase",
    "climate_order_refund",
    "carbon_offset_purchase",
    "carbon_offset_refund",
]

BalanceTransactionStatus = Literal["available", "pending"]

BalanceTransactionType = Literal[
    "adjustment",
    "advance",
    "advance_funding",
    "anticipation_repayment",
    "application_fee",
    "application_fee_refund",
    "charge",
    "climate_order_purchase",
    "climate_order_refund",
    "connect_collection_transfer",
    "contribution",
    "issuing_authorization_hold",
    "issuing_authorization_release",
    "issuing_dispute",
    "issuing_transaction",
    "link_cancellation",
    "obligation_inbound",
    "obligation_outbound",
    "obligation_reversal_inbound",
    "obligation_reversal_outbound",
    "obligation_payout",
    "obligation_payout_failure",
    "other_adjustment",
    "partial_capture_reversal",
    "payout",
    "payout_cancel",
    "payout_failure",
    "payment",
    "payment_failure_refund",
    "payment_refund",
    "payment_reversal",
    "payment_unreconciled",
    "reserve_transaction",
    "reserved_funds",
    "stripe_fee",
    "stripe_fx_fee",
    "tax_fee",
    "topup",
    "topup_reversal",
    "transfer",
    "transfer_cancel",
    "transfer_failure",
    "transfer_refund",
    "refund",
    "refund_failure",
    "network_cost",
]


class StripeBalanceTransaction(BaseModel):
    """
    Stripe BalanceTransaction object.

    Simulated and real objects must both validate against this schema.
    The simulator uses this as its output contract.

    Stripe docs: https://stripe.com/docs/api/balance_transactions/object
    """

    model_config = {"extra": "ignore"}

    # Identity
    id: str = Field(..., description="txn_xxx — Stripe's globally unique ID")
    object: str = Field(default="balance_transaction")

    # Monetary (cents, original currency)
    amount: int = Field(..., description="Gross amount in cents. Negative for refunds/disputes.")
    fee: int = Field(..., ge=0, description="Stripe processing fee in cents.")
    net: int = Field(..., description="amount - fee. What lands in your balance.")
    currency: str = Field(..., min_length=3, max_length=3)

    # Classification
    type: str                                   # broad Stripe type
    reporting_category: str                     # specific reporting category
    status: BalanceTransactionStatus

    # Timestamps (Unix epoch integers from Stripe)
    created: int = Field(..., description="Unix timestamp when Stripe created this txn.")
    available_on: int = Field(..., description="Unix timestamp when funds become available.")

    # Source object reference
    source: Optional[str] = None               # "ch_xxx", "re_xxx", "dp_xxx", etc.

    # Descriptive
    description: Optional[str] = None
    fee_details: list[StripeFeeDetail] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def lowercase_currency(cls, v: str) -> str:
        return v.lower()

    @field_validator("net")
    @classmethod
    def net_equals_amount_minus_fee(cls, v: int, info) -> int:
        # Soft validation: in simulation we always set net = amount - fee,
        # but real Stripe data should also satisfy this.
        return v

    def created_datetime(self) -> datetime:
        """Convert Stripe Unix timestamp → UTC datetime."""
        return datetime.fromtimestamp(self.created, tz=timezone.utc)

    def available_on_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.available_on, tz=timezone.utc)


# ── Stripe API list response wrapper ─────────────────────────────────────────

class StripeBalanceTransactionList(BaseModel):
    """
    Wrapper for Stripe's paginated list response.
    Used by the ingestion layer to parse API responses.
    """

    model_config = {"extra": "ignore"}

    object: Literal["list"] = "list"
    data: list[StripeBalanceTransaction] = Field(default_factory=list)
    has_more: bool = False
    url: str = "/v1/balance_transactions"

    # Cursor for next page (ID of the last object in data)
    @property
    def next_cursor(self) -> Optional[str]:
        if self.has_more and self.data:
            return self.data[-1].id
        return None


# ── Revenue monitoring filter ────────────────────────────────────────────────

# The reporting categories we aggregate in Phase 1 (revenue scope)
REVENUE_CATEGORIES: frozenset[str] = frozenset({
    "charge",
    "payment",          # alias used in some Stripe versions
})

REFUND_CATEGORIES: frozenset[str] = frozenset({
    "refund",
    "payment_refund",
    "payment_failure_refund",
})

DISPUTE_CATEGORIES: frozenset[str] = frozenset({
    "dispute",
    "dispute_reversal",
})

PAYOUT_CATEGORIES: frozenset[str] = frozenset({
    "payout",
    "payout_reversal",
})
