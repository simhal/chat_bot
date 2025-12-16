"""Add multi-agent support: PromptTemplate, User.custom_prompt, AgentInteraction

Revision ID: 003
Revises: 002
Create Date: 2025-12-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create prompt_templates table
    op.create_table(
        'prompt_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_type', sa.String(length=50), nullable=False),
        sa.Column('template_name', sa.String(length=100), nullable=False, server_default='default'),
        sa.Column('template_text', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('agent_type', 'template_name', 'is_active', name='uix_agent_template_active')
    )

    # Create indexes for prompt_templates
    op.create_index('ix_prompt_templates_id', 'prompt_templates', ['id'])
    op.create_index('ix_prompt_templates_agent_type', 'prompt_templates', ['agent_type'])
    op.create_index('ix_prompt_templates_is_active', 'prompt_templates', ['is_active'])

    # Add custom_prompt column to users table
    op.add_column('users', sa.Column('custom_prompt', sa.Text(), nullable=True))

    # Create agent_interactions table
    op.create_table(
        'agent_interactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('agent_type', sa.String(length=50), nullable=False),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('routing_reason', sa.Text(), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )

    # Create indexes for agent_interactions
    op.create_index('ix_agent_interactions_id', 'agent_interactions', ['id'])
    op.create_index('ix_agent_interactions_user_id', 'agent_interactions', ['user_id'])
    op.create_index('ix_agent_interactions_agent_type', 'agent_interactions', ['agent_type'])
    op.create_index('ix_agent_interactions_created_at', 'agent_interactions', ['created_at'])


def downgrade() -> None:
    # Drop tables and columns in reverse order
    op.drop_index('ix_agent_interactions_created_at', 'agent_interactions')
    op.drop_index('ix_agent_interactions_agent_type', 'agent_interactions')
    op.drop_index('ix_agent_interactions_user_id', 'agent_interactions')
    op.drop_index('ix_agent_interactions_id', 'agent_interactions')
    op.drop_table('agent_interactions')

    op.drop_column('users', 'custom_prompt')

    op.drop_index('ix_prompt_templates_is_active', 'prompt_templates')
    op.drop_index('ix_prompt_templates_agent_type', 'prompt_templates')
    op.drop_index('ix_prompt_templates_id', 'prompt_templates')
    op.drop_table('prompt_templates')
