"""add stripe_connections and update anomaly_alerts

Revision ID: 9a2f3c8e5b1d
Revises: 7c4d1e9f2a3b
Create Date: 2026-02-21

Changes:
  - Create stripe_connections table (multi-account per tenant, max 5)
  - Add stripe_account_id column to anomaly_alerts
  - Drop old uq_alert_dedup constraint, recreate with stripe_account_id
  - Drop tenant_configs.stripe_api_key (clean break — users re-enter via new UI)
"""

from alembic import op
import sqlalchemy as sa

revision = "9a2f3c8e5b1d"
down_revision = "7c4d1e9f2a3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Create stripe_connections table ────────────────────────────────────
    op.create_table(
        "stripe_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("encrypted_api_key", sa.String(500), nullable=True),
        sa.Column("stripe_account_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "name", name="uq_stripe_conn_name"),
    )
    op.create_index("ix_stripe_connections_tenant_id", "stripe_connections", ["tenant_id"])

    # ── 2. Add stripe_account_id to anomaly_alerts ────────────────────────────
    with op.batch_alter_table("anomaly_alerts") as batch_op:
        batch_op.add_column(sa.Column("stripe_account_id", sa.String(100), nullable=True))
        batch_op.create_index("ix_anomaly_alerts_stripe_account_id", ["stripe_account_id"])
        # Drop old 4-column dedup constraint, recreate with stripe_account_id
        batch_op.drop_constraint("uq_alert_dedup", type_="unique")
        batch_op.create_unique_constraint(
            "uq_alert_dedup",
            ["tenant_id", "stripe_account_id", "snapshot_date", "metric_name", "detection_method"],
        )

    # ── 3. Drop tenant_configs.stripe_api_key (clean break) ──────────────────
    with op.batch_alter_table("tenant_configs") as batch_op:
        batch_op.drop_column("stripe_api_key")


def downgrade() -> None:
    # Restore tenant_configs.stripe_api_key
    with op.batch_alter_table("tenant_configs") as batch_op:
        batch_op.add_column(sa.Column("stripe_api_key", sa.String(255), nullable=True))

    # Revert anomaly_alerts constraint
    with op.batch_alter_table("anomaly_alerts") as batch_op:
        batch_op.drop_constraint("uq_alert_dedup", type_="unique")
        batch_op.drop_index("ix_anomaly_alerts_stripe_account_id")
        batch_op.drop_column("stripe_account_id")
        batch_op.create_unique_constraint(
            "uq_alert_dedup",
            ["tenant_id", "snapshot_date", "metric_name", "detection_method"],
        )

    # Drop stripe_connections
    op.drop_index("ix_stripe_connections_tenant_id", "stripe_connections")
    op.drop_table("stripe_connections")
