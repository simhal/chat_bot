"""Add html to resource_type_enum

Revision ID: 022_add_html_resource_type
Revises: 021_add_popup_html_to_article_resources
Create Date: 2025-12-22

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '022_add_html_resource_type'
down_revision: Union[str, Sequence[str], None] = '021_popup_html'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'html' value to resource_type_enum."""
    # PostgreSQL ALTER TYPE ADD VALUE cannot run inside a transaction
    # Use IF NOT EXISTS to make it idempotent
    op.execute("ALTER TYPE resource_type_enum ADD VALUE IF NOT EXISTS 'html'")


def downgrade() -> None:
    """Remove 'html' value from resource_type_enum.

    Note: PostgreSQL doesn't support removing enum values directly.
    We would need to create a new enum type without 'html' and migrate.
    For simplicity, we'll leave this as a no-op since removing enum values
    is rarely needed and requires complex migration.
    """
    pass
