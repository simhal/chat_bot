"""add admin roles for topic groups

Revision ID: 009_add_topic_admin_roles
Revises: 008_restructure_groups
Create Date: 2025-12-17 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = '009_add_topic_admin_roles'
down_revision = '008_restructure_groups'
branch_labels = None
depends_on = None


def upgrade():
    # Get connection for data operations
    conn = op.get_bind()

    # Create admin roles for all topic groups
    admin_groups = [
        ('macro', 'admin', 'macro:admin', 'Admin for Macroeconomic content'),
        ('equity', 'admin', 'equity:admin', 'Admin for Equity content'),
        ('fixed_income', 'admin', 'fixed_income:admin', 'Admin for Fixed Income content'),
        ('esg', 'admin', 'esg:admin', 'Admin for ESG content'),
    ]

    for groupname, role, name, description in admin_groups:
        # Check if group already exists
        result = conn.execute(
            text("SELECT id FROM groups WHERE name = :name"),
            {'name': name}
        ).fetchone()

        if not result:
            conn.execute(
                text("""
                    INSERT INTO groups (name, groupname, role, description, created_at)
                    VALUES (:name, :groupname, :role, :description, CURRENT_TIMESTAMP)
                """),
                {
                    'name': name,
                    'groupname': groupname,
                    'role': role,
                    'description': description
                }
            )


def downgrade():
    # Get connection for data operations
    conn = op.get_bind()

    # Remove admin roles for topic groups
    conn.execute(
        text("""
            DELETE FROM groups
            WHERE groupname IN ('macro', 'equity', 'fixed_income', 'esg')
            AND role = 'admin'
        """)
    )
