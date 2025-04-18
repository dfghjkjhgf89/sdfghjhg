"""add notification_sent field

Revision ID: 002
Revises: 001
Create Date: 2024-03-19 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Добавляем новую колонку
    op.add_column('subscriptions', sa.Column('notification_sent', sa.Boolean(), server_default='false', nullable=False))

def downgrade() -> None:
    # Удаляем колонку
    op.drop_column('subscriptions', 'notification_sent') 