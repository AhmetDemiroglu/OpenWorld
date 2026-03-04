"""Initial schema migration

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('tool_call_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sessions_sid', 'sessions', ['session_id'])
    
    # Tool usage table
    op.create_table(
        'tool_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('arguments', sa.Text(), nullable=True),
        sa.Column('result_summary', sa.String(length=500), nullable=True),
        sa.Column('success', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_tool_usage_sid', 'tool_usage', ['session_id'])
    op.create_index('idx_tool_usage_name', 'tool_usage', ['tool_name'])
    
    # Memory facts table
    op.create_table(
        'memory_facts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fact', sa.Text(), nullable=False),
        sa.Column('source', sa.String(), server_default='conversation', nullable=True),
        sa.Column('category', sa.String(), server_default='general', nullable=True),
        sa.Column('confidence', sa.Float(), server_default='0.7', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('last_accessed', sa.DateTime(), nullable=True),
        sa.Column('access_count', sa.Integer(), server_default='0', nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_memory_category', 'memory_facts', ['category'])
    
    # User preferences table
    op.create_table(
        'user_preferences',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )


def downgrade() -> None:
    op.drop_table('user_preferences')
    op.drop_table('memory_facts')
    op.drop_table('tool_usage')
    op.drop_table('sessions')
