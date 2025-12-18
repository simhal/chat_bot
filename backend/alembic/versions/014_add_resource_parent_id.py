"""Add parent_id to resources for hierarchical resources.

Revision ID: 014_add_resource_parent_id
Revises: 013_add_resource_status
Create Date: 2024-12-18

Resources can now have parent resources, enabling hierarchical structures:
- A PDF can be parsed into child resources (text, images, tables)
- Child resources are automatically deleted when parent is deleted (CASCADE)
- Used for document parsing workflows
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '014_add_resource_parent_id'
down_revision = '013_add_resource_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add parent_id column to resources table
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'resources' AND column_name = 'parent_id'
            ) THEN
                ALTER TABLE resources
                ADD COLUMN parent_id INTEGER REFERENCES resources(id) ON DELETE CASCADE;
            END IF;
        END
        $$;
    """)

    # Create index on parent_id for efficient lookups
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_resources_parent_id'
            ) THEN
                CREATE INDEX ix_resources_parent_id ON resources(parent_id);
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    # Drop index
    op.execute("DROP INDEX IF EXISTS ix_resources_parent_id")

    # Drop parent_id column
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'resources' AND column_name = 'parent_id'
            ) THEN
                ALTER TABLE resources DROP COLUMN parent_id;
            END IF;
        END
        $$;
    """)
