"""Add status column to content articles

Revision ID: 010_add_article_status
Revises: 009_add_topic_admin_roles
Create Date: 2025-12-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


# revision identifiers, used by Alembic.
revision = '010_add_article_status'
down_revision = '009_add_topic_admin_roles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add status column to content_articles table.
    Status can be: 'draft', 'editor', or 'published'
    Default is 'draft'
    """
    # Create the ENUM type
    article_status = ENUM('draft', 'editor', 'published', name='article_status', create_type=True)
    article_status.create(op.get_bind(), checkfirst=True)

    # Add status column with default value 'draft'
    op.add_column('content_articles',
                  sa.Column('status', article_status, nullable=False, server_default='draft'))

    # Create index for filtering by status
    op.create_index('ix_content_articles_status', 'content_articles', ['status'])


def downgrade() -> None:
    """Remove status column and ENUM type."""
    op.drop_index('ix_content_articles_status', 'content_articles')
    op.drop_column('content_articles', 'status')

    # Drop the ENUM type
    article_status = ENUM('draft', 'editor', 'published', name='article_status')
    article_status.drop(op.get_bind(), checkfirst=True)
