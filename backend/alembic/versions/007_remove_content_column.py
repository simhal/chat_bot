"""Remove content column from content_articles (content now in ChromaDB)

Revision ID: 007_remove_content_column
Revises: 006_add_author_editor_fields
Create Date: 2025-12-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007_remove_content_column'
down_revision = '006_add_author_editor_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Remove content column from content_articles table.
    Content is now stored exclusively in ChromaDB vector database.
    PostgreSQL only stores metadata (id, topic, headline, author, editor, ratings, etc.)
    """
    # Drop the content column
    # IMPORTANT: Make sure all content has been migrated to ChromaDB first!
    op.drop_column('content_articles', 'content')


def downgrade() -> None:
    """
    Re-add content column to content_articles table.
    NOTE: This will create an empty column. You'll need to manually
    restore content from ChromaDB if you downgrade.
    """
    # Re-add content column
    op.add_column('content_articles',
                  sa.Column('content', sa.Text(), nullable=True))
