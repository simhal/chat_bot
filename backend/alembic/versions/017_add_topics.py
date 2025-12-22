"""Add topics table with FK to groups and articles

Revision ID: 017_add_topics
Revises: 016_extend_hash_id_length
Create Date: 2025-12-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017_add_topics'
down_revision: Union[str, Sequence[str], None] = '016_extend_hash_id_length'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add topics table and topic_id FK to groups and content_articles."""

    # Create topics table
    op.create_table(
        'topics',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('slug', sa.String(50), nullable=False, unique=True, index=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('visible', sa.Boolean(), nullable=False, default=True, server_default='true'),
        sa.Column('searchable', sa.Boolean(), nullable=False, default=True, server_default='true'),
        sa.Column('active', sa.Boolean(), nullable=False, default=True, server_default='true'),
        sa.Column('reader_count', sa.Integer(), nullable=False, default=0, server_default='0'),
        sa.Column('rating_average', sa.Float(), nullable=True),
        sa.Column('article_count', sa.Integer(), nullable=False, default=0, server_default='0'),
        sa.Column('agent_type', sa.String(50), nullable=True),
        sa.Column('agent_config', sa.JSON(), nullable=True),
        sa.Column('icon', sa.String(50), nullable=True),
        sa.Column('color', sa.String(20), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, default=0, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create indexes on topics
    op.create_index('ix_topics_id', 'topics', ['id'])
    op.create_index('ix_topics_visible', 'topics', ['visible'])
    op.create_index('ix_topics_active', 'topics', ['active'])
    op.create_index('ix_topics_sort_order', 'topics', ['sort_order'])

    # Add topic_id column to groups table (nullable for global groups)
    op.add_column('groups', sa.Column('topic_id', sa.Integer(), nullable=True))
    op.create_index('ix_groups_topic_id', 'groups', ['topic_id'])
    op.create_foreign_key(
        'fk_groups_topic_id',
        'groups', 'topics',
        ['topic_id'], ['id'],
        ondelete='CASCADE'
    )

    # Add topic_id column to content_articles table
    op.add_column('content_articles', sa.Column('topic_id', sa.Integer(), nullable=True))
    op.create_index('ix_content_articles_topic_id', 'content_articles', ['topic_id'])
    op.create_foreign_key(
        'fk_content_articles_topic_id',
        'content_articles', 'topics',
        ['topic_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Remove topics table and FK columns."""

    # Remove FK from content_articles
    op.drop_constraint('fk_content_articles_topic_id', 'content_articles', type_='foreignkey')
    op.drop_index('ix_content_articles_topic_id', table_name='content_articles')
    op.drop_column('content_articles', 'topic_id')

    # Remove FK from groups
    op.drop_constraint('fk_groups_topic_id', 'groups', type_='foreignkey')
    op.drop_index('ix_groups_topic_id', table_name='groups')
    op.drop_column('groups', 'topic_id')

    # Drop topics table indexes
    op.drop_index('ix_topics_sort_order', table_name='topics')
    op.drop_index('ix_topics_active', table_name='topics')
    op.drop_index('ix_topics_visible', table_name='topics')
    op.drop_index('ix_topics_id', table_name='topics')

    # Drop topics table
    op.drop_table('topics')
