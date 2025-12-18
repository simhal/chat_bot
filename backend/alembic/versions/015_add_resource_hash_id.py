"""Add hash_id to resources for public-facing URLs.

Revision ID: 015_add_resource_hash_id
Revises: 014_add_resource_parent_id
Create Date: 2024-12-18

Adds a URL-safe hash_id column to resources table for use in public-facing
resource URLs like /resource/{hash_id}. This allows serving resource content
(e.g., images) without exposing internal database IDs.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '015_add_resource_hash_id'
down_revision = '014_add_resource_parent_id'
branch_labels = None
depends_on = None


def generate_hash_id(length: int = 32) -> str:
    """Generate a URL-safe unique hash ID."""
    import secrets
    import string
    alphabet = string.ascii_lowercase + string.digits
    alphabet = alphabet.replace('0', '').replace('o', '').replace('l', '').replace('1', '')
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def upgrade() -> None:
    # Add hash_id column to resources table (nullable first for existing rows)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'resources' AND column_name = 'hash_id'
            ) THEN
                ALTER TABLE resources ADD COLUMN hash_id VARCHAR(64);
            END IF;
        END
        $$;
    """)

    # Generate hash_ids for existing resources using Python
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT id FROM resources WHERE hash_id IS NULL"))
    rows = result.fetchall()

    for row in rows:
        hash_id = generate_hash_id()
        # Ensure uniqueness by checking and regenerating if needed
        while True:
            check = conn.execute(
                sa.text("SELECT 1 FROM resources WHERE hash_id = :hash_id"),
                {"hash_id": hash_id}
            ).fetchone()
            if not check:
                break
            hash_id = generate_hash_id()

        conn.execute(
            sa.text("UPDATE resources SET hash_id = :hash_id WHERE id = :id"),
            {"hash_id": hash_id, "id": row[0]}
        )

    # Now make the column NOT NULL and add unique constraint
    op.execute("""
        DO $$
        BEGIN
            -- Make column NOT NULL
            ALTER TABLE resources ALTER COLUMN hash_id SET NOT NULL;

            -- Add unique constraint if not exists
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_resources_hash_id'
            ) THEN
                ALTER TABLE resources ADD CONSTRAINT uq_resources_hash_id UNIQUE (hash_id);
            END IF;
        END
        $$;
    """)

    # Create index on hash_id for efficient lookups
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes WHERE indexname = 'ix_resources_hash_id'
            ) THEN
                CREATE INDEX ix_resources_hash_id ON resources(hash_id);
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    # Drop index
    op.execute("DROP INDEX IF EXISTS ix_resources_hash_id")

    # Drop unique constraint
    op.execute("ALTER TABLE resources DROP CONSTRAINT IF EXISTS uq_resources_hash_id")

    # Drop hash_id column
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'resources' AND column_name = 'hash_id'
            ) THEN
                ALTER TABLE resources DROP COLUMN hash_id;
            END IF;
        END
        $$;
    """)
