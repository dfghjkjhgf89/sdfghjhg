"""add stop_commands table

Revision ID: add_stop_commands
Revises: 
Create Date: 2024-03-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_stop_commands'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'stop_commands',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('stopped_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('reason', sa.String()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_id')
    )
    op.create_index('idx_stop_telegram', 'stop_commands', ['telegram_id'])
    op.create_index('idx_stop_user', 'stop_commands', ['user_id'])

def downgrade():
    op.drop_index('idx_stop_user', table_name='stop_commands')
    op.drop_index('idx_stop_telegram', table_name='stop_commands')
    op.drop_table('stop_commands') 