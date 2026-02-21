"""add invitations table

Revision ID: 7c4d1e9f2a3b
Revises: 3f8a9b2c1d4e
Create Date: 2026-02-21 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '7c4d1e9f2a3b'
down_revision: Union[str, Sequence[str], None] = '3f8a9b2c1d4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'invitations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('invited_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False, index=True),
        sa.Column('token', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('role', sa.String(20), nullable=False, server_default='member'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('invitations')
