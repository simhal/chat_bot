"""Add access_mainchat column to topics table

Revision ID: 018_add_access_mainchat
Revises: 017_add_topics
Create Date: 2025-12-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '018_add_access_mainchat'
down_revision: Union[str, Sequence[str], None] = '017_add_topics'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add access_mainchat column to topics table."""
    op.add_column(
        'topics',
        sa.Column('access_mainchat', sa.Boolean(), nullable=False, server_default='true')
    )


def downgrade() -> None:
    """Remove access_mainchat column from topics table."""
    op.drop_column('topics', 'access_mainchat')
