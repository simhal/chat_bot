"""Add publication hash_ids to content_articles

Revision ID: 025
Revises: 024_add_hitl_models
Create Date: 2025-01-09

These fields store the resource hash_ids for published articles.
They persist across republish cycles so that links to articles remain stable.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '025_article_pub_hash_ids'
down_revision = '024_add_hitl_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add publication hash_id fields to content_articles
    op.add_column('content_articles', sa.Column('popup_hash_id', sa.String(64), nullable=True))
    op.add_column('content_articles', sa.Column('html_hash_id', sa.String(64), nullable=True))
    op.add_column('content_articles', sa.Column('pdf_hash_id', sa.String(64), nullable=True))

    # Create indexes for the hash_id fields
    op.create_index('ix_content_articles_popup_hash_id', 'content_articles', ['popup_hash_id'])
    op.create_index('ix_content_articles_html_hash_id', 'content_articles', ['html_hash_id'])
    op.create_index('ix_content_articles_pdf_hash_id', 'content_articles', ['pdf_hash_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_content_articles_pdf_hash_id', 'content_articles')
    op.drop_index('ix_content_articles_html_hash_id', 'content_articles')
    op.drop_index('ix_content_articles_popup_hash_id', 'content_articles')

    # Drop columns
    op.drop_column('content_articles', 'pdf_hash_id')
    op.drop_column('content_articles', 'html_hash_id')
    op.drop_column('content_articles', 'popup_hash_id')
