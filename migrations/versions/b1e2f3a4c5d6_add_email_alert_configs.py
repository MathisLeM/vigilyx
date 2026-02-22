"""add email_alert_configs table

Revision ID: b1e2f3a4c5d6
Revises: 9a2f3c8e5b1d
Create Date: 2026-02-22

"""
from alembic import op
import sqlalchemy as sa

revision = "b1e2f3a4c5d6"
down_revision = "9a2f3c8e5b1d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_alert_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("alert_email", sa.String(255), nullable=False),
        sa.Column("alert_level", sa.String(20), nullable=False, server_default="HIGH"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verification_token", sa.String(100), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_email_alert_configs_tenant"),
        sa.UniqueConstraint("verification_token", name="uq_email_alert_configs_token"),
    )
    op.create_index("ix_email_alert_configs_id", "email_alert_configs", ["id"])
    op.create_index(
        "ix_email_alert_configs_token", "email_alert_configs", ["verification_token"]
    )


def downgrade() -> None:
    op.drop_index("ix_email_alert_configs_token", table_name="email_alert_configs")
    op.drop_index("ix_email_alert_configs_id", table_name="email_alert_configs")
    op.drop_table("email_alert_configs")
