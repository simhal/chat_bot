"""restructure groups to groupname:role format

Revision ID: 008_restructure_groups
Revises: 007_remove_content_column
Create Date: 2025-12-17 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = '008_restructure_groups'
down_revision = '007_remove_content_column'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns for groupname and role
    op.add_column('groups', sa.Column('groupname', sa.String(100), nullable=True))
    op.add_column('groups', sa.Column('role', sa.String(50), nullable=True))

    # Get connection for data migration
    conn = op.get_bind()

    # Migrate existing group data
    # Mapping: old_name -> (groupname, role, new_name)
    migrations = {
        'admin': ('global', 'admin', 'global:admin'),
        'macro_analyst': ('macro', 'analyst', 'macro:analyst'),
        'equity_analyst': ('equity', 'analyst', 'equity:analyst'),
        'fi_analyst': ('fixed_income', 'analyst', 'fixed_income:analyst'),
        'esg_analyst': ('esg', 'analyst', 'esg:analyst'),
    }

    # Update existing groups
    for old_name, (groupname, role, new_name) in migrations.items():
        conn.execute(
            text("""
                UPDATE groups
                SET groupname = :groupname,
                    role = :role,
                    name = :new_name
                WHERE name = :old_name
            """),
            {
                'groupname': groupname,
                'role': role,
                'new_name': new_name,
                'old_name': old_name
            }
        )

    # Delete any unmapped groups (e.g., 'user', 'test') that don't fit the new structure
    mapped_names = list(migrations.keys())
    placeholders = ', '.join([f':name{i}' for i in range(len(mapped_names))])
    params = {f'name{i}': name for i, name in enumerate(mapped_names)}

    conn.execute(
        text(f"DELETE FROM groups WHERE name NOT IN ({placeholders})"),
        params
    )

    # Create editor roles for all topic groups
    editor_groups = [
        ('macro', 'editor', 'macro:editor', 'Editor for Macroeconomic content'),
        ('equity', 'editor', 'equity:editor', 'Editor for Equity content'),
        ('fixed_income', 'editor', 'fixed_income:editor', 'Editor for Fixed Income content'),
        ('esg', 'editor', 'esg:editor', 'Editor for ESG content'),
        ('global', 'editor', 'global:editor', 'Global editor role'),
    ]

    for groupname, role, name, description in editor_groups:
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

    # Create reader roles for all topic groups
    reader_groups = [
        ('macro', 'reader', 'macro:reader', 'Reader for Macroeconomic content'),
        ('equity', 'reader', 'equity:reader', 'Reader for Equity content'),
        ('fixed_income', 'reader', 'fixed_income:reader', 'Reader for Fixed Income content'),
        ('esg', 'reader', 'esg:reader', 'Reader for ESG content'),
        ('global', 'reader', 'global:reader', 'Global reader role'),
    ]

    for groupname, role, name, description in reader_groups:
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

    # Make groupname and role required
    op.alter_column('groups', 'groupname', nullable=False)
    op.alter_column('groups', 'role', nullable=False)

    # Add unique constraint on (groupname, role)
    op.create_unique_constraint('uq_groups_groupname_role', 'groups', ['groupname', 'role'])

    # Add indexes
    op.create_index('ix_groups_groupname', 'groups', ['groupname'])
    op.create_index('ix_groups_role', 'groups', ['role'])


def downgrade():
    # Remove indexes
    op.drop_index('ix_groups_role', 'groups')
    op.drop_index('ix_groups_groupname', 'groups')

    # Remove unique constraint
    op.drop_constraint('uq_groups_groupname_role', 'groups', type_='unique')

    # Get connection for data migration
    conn = op.get_bind()

    # Reverse migrate group names
    reverse_migrations = {
        'global:admin': 'admin',
        'macro:analyst': 'macro_analyst',
        'equity:analyst': 'equity_analyst',
        'fixed_income:analyst': 'fi_analyst',
        'esg:analyst': 'esg_analyst',
    }

    for new_name, old_name in reverse_migrations.items():
        conn.execute(
            text("UPDATE groups SET name = :old_name WHERE name = :new_name"),
            {'old_name': old_name, 'new_name': new_name}
        )

    # Delete editor and reader groups
    conn.execute(
        text("DELETE FROM groups WHERE role IN ('editor', 'reader')")
    )

    # Remove new columns
    op.drop_column('groups', 'role')
    op.drop_column('groups', 'groupname')
