"""Extend hash_id length to 32 characters.

Revision ID: 016_extend_hash_id_length
Revises: 015_add_resource_hash_id
Create Date: 2024-12-18

Extends the hash_id column from 16 to 64 characters (to accommodate 32-char IDs)
and regenerates existing hash_ids with the new length.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '016_extend_hash_id_length'
down_revision = '015_add_resource_hash_id'
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
    # Extend column size to 64 characters
    op.execute("""
        ALTER TABLE resources ALTER COLUMN hash_id TYPE VARCHAR(64);
    """)

    # Regenerate all hash_ids with new 32-character length
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT id FROM resources"))
    rows = result.fetchall()

    for row in rows:
        hash_id = generate_hash_id(32)
        # Ensure uniqueness
        while True:
            check = conn.execute(
                sa.text("SELECT 1 FROM resources WHERE hash_id = :hash_id AND id != :id"),
                {"hash_id": hash_id, "id": row[0]}
            ).fetchone()
            if not check:
                break
            hash_id = generate_hash_id(32)

        conn.execute(
            sa.text("UPDATE resources SET hash_id = :hash_id WHERE id = :id"),
            {"hash_id": hash_id, "id": row[0]}
        )


def downgrade() -> None:
    # Regenerate with shorter 12-character hash_ids
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT id FROM resources"))
    rows = result.fetchall()

    for row in rows:
        hash_id = generate_hash_id(12)
        while True:
            check = conn.execute(
                sa.text("SELECT 1 FROM resources WHERE hash_id = :hash_id AND id != :id"),
                {"hash_id": hash_id, "id": row[0]}
            ).fetchone()
            if not check:
                break
            hash_id = generate_hash_id(12)

        conn.execute(
            sa.text("UPDATE resources SET hash_id = :hash_id WHERE id = :id"),
            {"hash_id": hash_id, "id": row[0]}
        )

    # Reduce column size back to 16
    op.execute("""
        ALTER TABLE resources ALTER COLUMN hash_id TYPE VARCHAR(16);
    """)
