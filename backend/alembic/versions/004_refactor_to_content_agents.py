"""Refactor to content agent architecture

Revision ID: 004_refactor_to_content_agents
Revises: 003
Create Date: 2025-12-13

This migration transforms the multi-agent system into a content-based architecture where:
- Main chat agent has customizable prompts (global + user-specific)
- Content agents (macro, equity, fixed_income, esg) create reusable articles
- Articles are stored with metadata (headline, readership, ratings)
- Prompt templates support both main_chat and content_agent types
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '004_refactor_to_content_agents'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    # ========================================
    # 1. Create content_articles table
    # ========================================
    op.create_table(
        'content_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=50), nullable=False),
        sa.Column('headline', sa.String(length=500), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('readership_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('rating_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('keywords', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by_agent', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_content_articles_id', 'content_articles', ['id'])
    op.create_index('ix_content_articles_topic', 'content_articles', ['topic'])
    op.create_index('ix_content_articles_headline', 'content_articles', ['headline'])
    op.create_index('ix_content_articles_readership_count', 'content_articles', ['readership_count'])
    op.create_index('ix_content_articles_rating', 'content_articles', ['rating'])
    op.create_index('ix_content_articles_created_at', 'content_articles', ['created_at'])
    op.create_index('ix_content_articles_is_active', 'content_articles', ['is_active'])

    # ========================================
    # 2. Create content_ratings table
    # ========================================
    op.create_table(
        'content_ratings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['content_articles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('article_id', 'user_id', name='uix_article_user_rating')
    )
    op.create_index('ix_content_ratings_id', 'content_ratings', ['id'])
    op.create_index('ix_content_ratings_article_id', 'content_ratings', ['article_id'])
    op.create_index('ix_content_ratings_user_id', 'content_ratings', ['user_id'])

    # ========================================
    # 3. Update prompt_templates table
    # ========================================

    # Step 3a: Drop the old unique constraint
    op.drop_constraint('uix_agent_template_active', 'prompt_templates', type_='unique')

    # Step 3b: Add new columns (nullable initially)
    op.add_column('prompt_templates', sa.Column('template_type', sa.String(length=50), nullable=True))
    op.add_column('prompt_templates', sa.Column('scope', sa.String(length=20), nullable=True))
    op.add_column('prompt_templates', sa.Column('user_id', sa.Integer(), nullable=True))

    # Step 3c: Migrate existing data
    # Set template_type='content_agent' and scope='global' for all existing records
    op.execute("""
        UPDATE prompt_templates
        SET template_type = 'content_agent',
            scope = 'global'
    """)

    # Step 3d: Make template_type and scope non-nullable
    op.alter_column('prompt_templates', 'template_type',
                    existing_type=sa.String(length=50),
                    nullable=False)
    op.alter_column('prompt_templates', 'scope',
                    existing_type=sa.String(length=20),
                    nullable=False,
                    server_default='global')

    # Step 3e: Add foreign key for user_id
    op.create_foreign_key('fk_prompt_templates_user_id',
                         'prompt_templates',
                         'users',
                         ['user_id'],
                         ['id'],
                         ondelete='CASCADE')

    # Step 3f: Add indexes for new columns
    op.create_index('ix_prompt_templates_template_type', 'prompt_templates', ['template_type'])
    op.create_index('ix_prompt_templates_scope', 'prompt_templates', ['scope'])
    op.create_index('ix_prompt_templates_user_id', 'prompt_templates', ['user_id'])


def downgrade():
    # ========================================
    # Reverse the upgrade in reverse order
    # ========================================

    # Drop prompt_templates changes
    op.drop_index('ix_prompt_templates_user_id', 'prompt_templates')
    op.drop_index('ix_prompt_templates_scope', 'prompt_templates')
    op.drop_index('ix_prompt_templates_template_type', 'prompt_templates')
    op.drop_constraint('fk_prompt_templates_user_id', 'prompt_templates', type_='foreignkey')
    op.drop_column('prompt_templates', 'user_id')
    op.drop_column('prompt_templates', 'scope')
    op.drop_column('prompt_templates', 'template_type')

    # Restore old unique constraint
    op.create_unique_constraint('uix_agent_template_active',
                               'prompt_templates',
                               ['agent_type', 'template_name', 'is_active'])

    # Drop content_ratings table
    op.drop_index('ix_content_ratings_user_id', 'content_ratings')
    op.drop_index('ix_content_ratings_article_id', 'content_ratings')
    op.drop_index('ix_content_ratings_id', 'content_ratings')
    op.drop_table('content_ratings')

    # Drop content_articles table
    op.drop_index('ix_content_articles_is_active', 'content_articles')
    op.drop_index('ix_content_articles_created_at', 'content_articles')
    op.drop_index('ix_content_articles_rating', 'content_articles')
    op.drop_index('ix_content_articles_readership_count', 'content_articles')
    op.drop_index('ix_content_articles_headline', 'content_articles')
    op.drop_index('ix_content_articles_topic', 'content_articles')
    op.drop_index('ix_content_articles_id', 'content_articles')
    op.drop_table('content_articles')
