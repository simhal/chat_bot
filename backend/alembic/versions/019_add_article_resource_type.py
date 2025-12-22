"""Add article to resource_type_enum

Revision ID: 019_add_article_resource_type
Revises: 018_add_access_mainchat
Create Date: 2025-12-21

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '019_add_article_resource_type'
down_revision: Union[str, Sequence[str], None] = '018_add_access_mainchat'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'article' value to resource_type_enum."""
    # PostgreSQL ALTER TYPE ADD VALUE cannot run inside a transaction
    # Use IF NOT EXISTS to make it idempotent
    op.execute("ALTER TYPE resource_type_enum ADD VALUE IF NOT EXISTS 'article'")


def downgrade() -> None:
    """Remove 'article' value from resource_type_enum.

    Note: PostgreSQL doesn't support removing enum values directly.
    We would need to create a new enum type without 'article' and migrate.
    For simplicity, we'll leave this as a no-op since removing enum values
    is rarely needed and requires complex migration.
    """
    pass
