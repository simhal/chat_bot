"""Add access tracking fields and active status to users table

Revision ID: 002
Revises: 001
Create Date: 2025-12-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add active status field (default True for all existing users)
    op.add_column('users', sa.Column('active', sa.Boolean(), nullable=False, server_default='true'))

    # Add access tracking fields to users table
    op.add_column('users', sa.Column('last_access_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('access_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    # Remove tracking fields from users table
    op.drop_column('users', 'access_count')
    op.drop_column('users', 'last_access_at')
    op.drop_column('users', 'active')
