"""Add article priority/sticky and topic article_order columns

Revision ID: 020_add_article_priority
Revises: 019_add_article_resource_type
Create Date: 2025-12-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020_add_article_priority'
down_revision: Union[str, Sequence[str], None] = '019_add_article_resource_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add priority and is_sticky to content_articles, article_order to topics."""
    # Add priority column to content_articles
    op.add_column(
        'content_articles',
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0')
    )
    op.create_index('ix_content_articles_priority', 'content_articles', ['priority'])

    # Add is_sticky column to content_articles
    op.add_column(
        'content_articles',
        sa.Column('is_sticky', sa.Boolean(), nullable=False, server_default='false')
    )
    op.create_index('ix_content_articles_is_sticky', 'content_articles', ['is_sticky'])

    # Add article_order column to topics
    op.add_column(
        'topics',
        sa.Column('article_order', sa.String(20), nullable=False, server_default='date')
    )


def downgrade() -> None:
    """Remove priority, is_sticky from content_articles and article_order from topics."""
    op.drop_column('topics', 'article_order')
    op.drop_index('ix_content_articles_is_sticky', 'content_articles')
    op.drop_column('content_articles', 'is_sticky')
    op.drop_index('ix_content_articles_priority', 'content_articles')
    op.drop_column('content_articles', 'priority')
