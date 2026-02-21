"""add slack config columns

Revision ID: 3f8a9b2c1d4e
Revises: 11e62c6e728e
Create Date: 2026-02-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f8a9b2c1d4e'
down_revision: Union[str, Sequence[str], None] = '11e62c6e728e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table handles SQLite's limited ALTER TABLE support
    with op.batch_alter_table('tenant_configs') as batch_op:
        batch_op.add_column(sa.Column('slack_webhook_url', sa.String(500), nullable=True))
        batch_op.add_column(sa.Column('slack_alert_level', sa.String(20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tenant_configs') as batch_op:
        batch_op.drop_column('slack_alert_level')
        batch_op.drop_column('slack_webhook_url')
