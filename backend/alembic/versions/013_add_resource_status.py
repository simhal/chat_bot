"""Add status field to resources table for editorial workflow.

Revision ID: 013_add_resource_status
Revises: 012_add_resources
Create Date: 2024-12-18

Resources follow the same editorial workflow as articles:
- draft: Initial state, being worked on
- editor: Ready for review
- published: Approved and published
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013_add_resource_status'
down_revision = '012_add_resources'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type for resource status (if it doesn't exist)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'resource_status_enum') THEN
                CREATE TYPE resource_status_enum AS ENUM ('draft', 'editor', 'published');
            END IF;
        END
        $$;
    """)

    # Add status column to resources table
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'resources' AND column_name = 'status'
            ) THEN
                ALTER TABLE resources
                ADD COLUMN status resource_status_enum NOT NULL DEFAULT 'draft';
            END IF;
        END
        $$;
    """)

    # Create index on status column
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_resources_status'
            ) THEN
                CREATE INDEX ix_resources_status ON resources(status);
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    # Drop index
    op.execute("DROP INDEX IF EXISTS ix_resources_status")

    # Drop status column
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'resources' AND column_name = 'status'
            ) THEN
                ALTER TABLE resources DROP COLUMN status;
            END IF;
        END
        $$;
    """)

    # Note: We don't drop the enum type as it might be used elsewhere
