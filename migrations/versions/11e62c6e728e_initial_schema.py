"""initial schema

Revision ID: 11e62c6e728e
Revises:
Create Date: 2026-02-21 01:49:54.014226

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '11e62c6e728e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tenants ───────────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_tenants_id", "tenants", ["id"])
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"])

    # ── tenant_configs ────────────────────────────────────────────────────────
    # Initial state: has stripe_api_key, no slack columns yet
    # (slack added in 3f8a9b2c1d4e, stripe_api_key dropped in 9a2f3c8e5b1d)
    op.create_table(
        "tenant_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("stripe_api_key", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_index("ix_tenant_configs_id", "tenant_configs", ["id"])

    # ── anomaly_alerts ────────────────────────────────────────────────────────
    # Initial state: no stripe_account_id, 4-column uq_alert_dedup
    # (stripe_account_id added + constraint updated in 9a2f3c8e5b1d)
    op.create_table(
        "anomaly_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("metric_name", sa.String(50), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column(
            "detection_method",
            sa.Enum("MAD", "ZSCORE", "DUAL", name="detectionmethod"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("pct_deviation", sa.Float(), nullable=True),
        sa.Column("is_dual_confirmed", sa.Boolean(), nullable=False),
        sa.Column("hint", sa.String(500), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("LOW", "MEDIUM", "HIGH", name="alertseverity"),
            nullable=False,
        ),
        sa.Column("is_resolved", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "snapshot_date", "metric_name", "detection_method",
            name="uq_alert_dedup",
        ),
    )
    op.create_index("ix_anomaly_alerts_id", "anomaly_alerts", ["id"])
    op.create_index("ix_anomaly_alerts_tenant_id", "anomaly_alerts", ["tenant_id"])
    op.create_index("ix_anomaly_alerts_snapshot_date", "anomaly_alerts", ["snapshot_date"])

    # ── daily_revenue_metrics ─────────────────────────────────────────────────
    op.create_table(
        "daily_revenue_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("stripe_account_id", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("gross_revenue", sa.BigInteger(), nullable=False),
        sa.Column("total_fees", sa.BigInteger(), nullable=False),
        sa.Column("net_revenue", sa.BigInteger(), nullable=False),
        sa.Column("charge_count", sa.Integer(), nullable=False),
        sa.Column("avg_charge_value", sa.BigInteger(), nullable=True),
        sa.Column("fee_rate", sa.Float(), nullable=True),
        sa.Column("gross_revenue_usd", sa.BigInteger(), nullable=False),
        sa.Column("total_fees_usd", sa.BigInteger(), nullable=False),
        sa.Column("net_revenue_usd", sa.BigInteger(), nullable=False),
        sa.Column("avg_charge_value_usd", sa.BigInteger(), nullable=True),
        sa.Column("refund_amount", sa.BigInteger(), nullable=False),
        sa.Column("refund_count", sa.Integer(), nullable=False),
        sa.Column("refund_rate", sa.Float(), nullable=True),
        sa.Column("refund_amount_usd", sa.BigInteger(), nullable=False),
        sa.Column("dispute_amount", sa.BigInteger(), nullable=False),
        sa.Column("dispute_count", sa.Integer(), nullable=False),
        sa.Column("dispute_amount_usd", sa.BigInteger(), nullable=False),
        sa.Column("net_balance_change_usd", sa.BigInteger(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "stripe_account_id", "currency", "snapshot_date",
            name="uq_daily_rev_tenant_account_currency_date",
        ),
    )
    op.create_index("ix_daily_revenue_metrics_id", "daily_revenue_metrics", ["id"])
    op.create_index("ix_daily_revenue_metrics_tenant_id", "daily_revenue_metrics", ["tenant_id"])
    op.create_index("ix_daily_revenue_metrics_snapshot_date", "daily_revenue_metrics", ["snapshot_date"])
    op.create_index("ix_daily_rev_tenant_date", "daily_revenue_metrics", ["tenant_id", "snapshot_date"])

    # ── raw_balance_transactions ──────────────────────────────────────────────
    op.create_table(
        "raw_balance_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("stripe_account_id", sa.String(50), nullable=False),
        sa.Column("stripe_id", sa.String(50), nullable=False),
        sa.Column("stripe_object", sa.String(30), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("fee", sa.BigInteger(), nullable=False),
        sa.Column("net", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("usd_exchange_rate", sa.Float(), nullable=True),
        sa.Column("amount_usd", sa.BigInteger(), nullable=True),
        sa.Column("fee_usd", sa.BigInteger(), nullable=True),
        sa.Column("net_usd", sa.BigInteger(), nullable=True),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("reporting_category", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source_id", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("available_on", sa.DateTime(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fee_details_json", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), nullable=False),
        sa.Column("ingestion_source", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "stripe_account_id", "stripe_id",
            name="uq_raw_bt_tenant_account_stripe",
        ),
    )
    op.create_index("ix_raw_balance_transactions_id", "raw_balance_transactions", ["id"])
    op.create_index("ix_raw_balance_transactions_tenant_id", "raw_balance_transactions", ["tenant_id"])
    op.create_index("ix_raw_balance_transactions_stripe_account_id", "raw_balance_transactions", ["stripe_account_id"])
    op.create_index("ix_raw_balance_transactions_source_id", "raw_balance_transactions", ["source_id"])
    op.create_index("ix_raw_bt_tenant_account_created", "raw_balance_transactions", ["tenant_id", "stripe_account_id", "created_at"])
    op.create_index("ix_raw_bt_reporting_category", "raw_balance_transactions", ["reporting_category"])


def downgrade() -> None:
    op.drop_table("raw_balance_transactions")
    op.drop_table("daily_revenue_metrics")
    op.drop_table("anomaly_alerts")
    op.drop_table("tenant_configs")
    op.drop_table("users")
    op.drop_table("tenants")
    op.execute("DROP TYPE IF EXISTS detectionmethod")
    op.execute("DROP TYPE IF EXISTS alertseverity")
