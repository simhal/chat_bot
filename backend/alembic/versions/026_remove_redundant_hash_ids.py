"""Remove redundant html_hash_id and pdf_hash_id from content_articles

Revision ID: 026
Revises: 025_article_pub_hash_ids
Create Date: 2025-01-09

These fields are redundant because HTML and PDF resources can be derived
from the parent popup resource via the parent_id relationship in the
resources table. Only popup_hash_id is needed for stable article links.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '026_remove_redundant_hash_ids'
down_revision = '025_article_pub_hash_ids'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_content_articles_html_hash_id', 'content_articles')
    op.drop_index('ix_content_articles_pdf_hash_id', 'content_articles')

    # Drop the redundant columns
    op.drop_column('content_articles', 'html_hash_id')
    op.drop_column('content_articles', 'pdf_hash_id')


def downgrade() -> None:
    # Re-add the columns
    op.add_column('content_articles', sa.Column('html_hash_id', sa.String(64), nullable=True))
    op.add_column('content_articles', sa.Column('pdf_hash_id', sa.String(64), nullable=True))

    # Re-create indexes
    op.create_index('ix_content_articles_html_hash_id', 'content_articles', ['html_hash_id'])
    op.create_index('ix_content_articles_pdf_hash_id', 'content_articles', ['pdf_hash_id'])
