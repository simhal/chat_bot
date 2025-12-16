"""Add analyst groups for content management

Revision ID: 005_add_analyst_groups
Revises: 004_refactor_to_content_agents
Create Date: 2025-12-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision = '005_add_analyst_groups'
down_revision = '004_refactor_to_content_agents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create 4 new analyst groups for content management:
    - equity_analyst: Can edit equity content
    - fi_analyst: Can edit fixed income content
    - macro_analyst: Can edit macro content
    - esg_analyst: Can edit ESG content
    """
    # Create a groups table reference for bulk insert
    groups_table = table('groups',
        column('name', sa.String),
        column('description', sa.String)
    )

    # Insert the 4 new analyst groups
    op.bulk_insert(groups_table, [
        {
            'name': 'equity_analyst',
            'description': 'Equity analysts - can edit equity research content'
        },
        {
            'name': 'fi_analyst',
            'description': 'Fixed Income analysts - can edit fixed income research content'
        },
        {
            'name': 'macro_analyst',
            'description': 'Macro analysts - can edit macroeconomic research content'
        },
        {
            'name': 'esg_analyst',
            'description': 'ESG analysts - can edit ESG research content'
        }
    ])


def downgrade() -> None:
    """Remove the analyst groups."""
    op.execute(
        "DELETE FROM groups WHERE name IN ('equity_analyst', 'fi_analyst', 'macro_analyst', 'esg_analyst')"
    )
