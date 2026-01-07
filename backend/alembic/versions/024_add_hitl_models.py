"""Add HITL (Human-in-the-Loop) models for article approval workflow.

Revision ID: 024_add_hitl_models
Revises: 023_backfill_table_children
Create Date: 2025-01-02

This migration:
1. Adds PENDING_APPROVAL status to the article_status enum
2. Creates the approval_status enum
3. Creates the approval_requests table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '024_add_hitl_models'
down_revision: Union[str, Sequence[str], None] = '023_backfill_table_children'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add HITL models."""

    # Add PENDING_APPROVAL to article_status enum
    # PostgreSQL requires special handling for adding enum values
    op.execute("ALTER TYPE article_status ADD VALUE IF NOT EXISTS 'pending_approval'")

    # Create approval_status enum
    approval_status = postgresql.ENUM(
        'pending', 'approved', 'rejected', 'expired',
        name='approval_status',
        create_type=False
    )

    # Create the enum type first
    op.execute("CREATE TYPE approval_status AS ENUM ('pending', 'approved', 'rejected', 'expired')")

    # Create approval_requests table
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),

        # Article being approved
        sa.Column('article_id', sa.Integer(),
                  sa.ForeignKey('content_articles.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Request details
        sa.Column('requested_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True, index=True),
        sa.Column('requested_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('editor_notes', sa.Text(), nullable=True),

        # Status tracking
        sa.Column('status', approval_status, server_default='pending',
                  nullable=False, index=True),

        # Review details
        sa.Column('reviewed_by', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True, index=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),

        # Expiration
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),

        # LangGraph workflow tracking
        sa.Column('thread_id', sa.String(255), nullable=True, index=True),
    )

    # Create index for finding pending approvals by article
    op.create_index(
        'ix_approval_requests_article_pending',
        'approval_requests',
        ['article_id', 'status'],
        postgresql_where=sa.text("status = 'pending'")
    )


def downgrade() -> None:
    """Remove HITL models."""

    # Drop the index
    op.drop_index('ix_approval_requests_article_pending', table_name='approval_requests')

    # Drop the table
    op.drop_table('approval_requests')

    # Drop the approval_status enum
    op.execute("DROP TYPE approval_status")

    # Note: Removing enum values from PostgreSQL is complex and generally not recommended.
    # The 'pending_approval' value in article_status will remain but be unused.
    # To fully remove it would require:
    # 1. Creating a new enum type without the value
    # 2. Updating all columns to use the new type
    # 3. Dropping the old type
    # 4. Renaming the new type
    # This is left as a manual operation if truly needed.
