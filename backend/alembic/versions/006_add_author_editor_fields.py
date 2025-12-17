"""Add author and editor fields to content articles

Revision ID: 006_add_author_editor_fields
Revises: 005_add_analyst_groups
Create Date: 2025-12-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_add_author_editor_fields'
down_revision = '005_add_analyst_groups'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add author and editor fields to content_articles table.
    These fields store author and editor names as simple text.
    """
    # Add author field
    op.add_column('content_articles',
                  sa.Column('author', sa.String(length=255), nullable=True))

    # Add editor field
    op.add_column('content_articles',
                  sa.Column('editor', sa.String(length=255), nullable=True))

    # Create indexes for searchability
    op.create_index('ix_content_articles_author', 'content_articles', ['author'])
    op.create_index('ix_content_articles_editor', 'content_articles', ['editor'])


def downgrade() -> None:
    """Remove author and editor fields."""
    op.drop_index('ix_content_articles_editor', 'content_articles')
    op.drop_index('ix_content_articles_author', 'content_articles')
    op.drop_column('content_articles', 'editor')
    op.drop_column('content_articles', 'author')
