"""add autopayment fields

Revision ID: 001
Revises: 
Create Date: 2024-03-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем новые колонки
    op.add_column('subscriptions', sa.Column('rebill_id', sa.String(), nullable=True))
    op.add_column('subscriptions', sa.Column('last_payment_date', sa.DateTime(), nullable=True))
    op.add_column('subscriptions', sa.Column('next_payment_date', sa.DateTime(), nullable=True))
    op.add_column('subscriptions', sa.Column('payment_amount', sa.Float(), nullable=True))
    op.add_column('subscriptions', sa.Column('failed_payments', sa.Integer(), server_default='0', nullable=False))
    
    # Создаем индекс для оптимизации запросов по next_payment_date
    op.create_index('idx_sub_next_payment', 'subscriptions', ['next_payment_date'])


def downgrade() -> None:
    # Удаляем индекс
    op.drop_index('idx_sub_next_payment')
    
    # Удаляем колонки
    op.drop_column('subscriptions', 'failed_payments')
    op.drop_column('subscriptions', 'payment_amount')
    op.drop_column('subscriptions', 'next_payment_date')
    op.drop_column('subscriptions', 'last_payment_date')
    op.drop_column('subscriptions', 'rebill_id') 