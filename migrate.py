from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from datetime import datetime, timezone
from models import PaymentStatus, PaymentMethod, SubscriptionType

def upgrade():
    # Создаем новые таблицы
    op.create_table(
        'tariff_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Enum(SubscriptionType), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('type', name='uq_tariff_type')
    )

    # Обновляем существующие таблицы
    with op.batch_alter_table('users') as batch_op:
        # Удаляем старые колонки
        batch_op.drop_column('username')
        batch_op.drop_column('first_name')
        batch_op.drop_column('last_name')
        batch_op.drop_column('created_at')
        batch_op.drop_column('referral_link_override')
        batch_op.drop_column('referral_status_override')
        
        # Добавляем новые колонки
        batch_op.add_column(sa.Column('registration_date', sa.DateTime(timezone=True), server_default=sa.func.now()))
        batch_op.add_column(sa.Column('referral_code', sa.String(50), unique=True))
        
        # Обновляем типы данных
        batch_op.alter_column('telegram_id',
                            existing_type=sa.Integer(),
                            type_=sa.BigInteger(),
                            existing_nullable=False)
        
        # Добавляем проверку email
        batch_op.create_check_constraint(
            'valid_email',
            "email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'"
        )

    # Обновляем таблицу подписок
    with op.batch_alter_table('subscriptions') as batch_op:
        # Добавляем новые колонки
        batch_op.add_column(sa.Column('tariff_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('auto_renewal', sa.Boolean(), default=False))
        batch_op.add_column(sa.Column('last_renewal_attempt', sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column('renewal_failed_count', sa.Integer(), default=0))
        
        # Удаляем старые колонки
        batch_op.drop_column('auto_payment')
        batch_op.drop_column('payment_amount')
        batch_op.drop_column('last_payment_date')
        batch_op.drop_column('next_payment_date')
        batch_op.drop_column('failed_payments')
        batch_op.drop_column('notification_sent')
        
        # Добавляем внешний ключ
        batch_op.create_foreign_key(
            'fk_subscription_tariff',
            'tariff_plans',
            ['tariff_id'],
            ['id'],
            ondelete='CASCADE'
        )
        
        # Добавляем проверку дат
        batch_op.create_check_constraint(
            'valid_dates',
            'end_date > start_date'
        )

    # Обновляем таблицу платежей
    with op.batch_alter_table('payments') as batch_op:
        # Переименовываем колонку
        batch_op.alter_column('payment_id',
                            new_column_name='external_id',
                            existing_type=sa.String())
        
        # Добавляем новую колонку
        batch_op.add_column(sa.Column('error_message', sa.Text()))
        
        # Обновляем тип данных для currency
        batch_op.alter_column('currency',
                            existing_type=sa.String(),
                            type_=sa.String(3),
                            existing_nullable=False)

    # Обновляем таблицу whitelist
    with op.batch_alter_table('whitelist') as batch_op:
        batch_op.add_column(sa.Column('expires_at', sa.DateTime(timezone=True)))
        batch_op.drop_column('added_by')
        
        # Добавляем проверку срока действия
        batch_op.create_check_constraint(
            'valid_expiration',
            'expires_at IS NULL OR expires_at > added_date'
        )

    # Обновляем таблицу админов
    with op.batch_alter_table('admins') as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(20), nullable=False, server_default='admin'))
        
        # Добавляем проверку email
        batch_op.create_check_constraint(
            'valid_admin_email',
            "email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'"
        )

    # Удаляем таблицу stop_commands
    op.drop_table('stop_commands')

    # Создаем базовые тарифные планы
    op.execute(
        """
        INSERT INTO tariff_plans (type, name, description, price, duration_days, is_active)
        VALUES 
        ('basic', 'Базовый', 'Базовый тарифный план', 1500.0, 30, true),
        ('premium', 'Премиум', 'Премиум тарифный план с расширенными возможностями', 2500.0, 30, true),
        ('vip', 'VIP', 'VIP тарифный план с полным доступом', 5000.0, 30, true)
        """
    )

    # Обновляем существующие подписки
    op.execute(
        """
        UPDATE subscriptions s
        SET tariff_id = (SELECT id FROM tariff_plans WHERE type = 'basic')
        WHERE tariff_id IS NULL
        """
    )

    # Делаем tariff_id обязательным
    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.alter_column('tariff_id',
                            existing_type=sa.Integer(),
                            nullable=False)

def downgrade():
    # Откатываем все изменения в обратном порядке
    with op.batch_alter_table('subscriptions') as batch_op:
        batch_op.drop_constraint('fk_subscription_tariff')
        batch_op.drop_constraint('valid_dates')
        batch_op.drop_column('tariff_id')
        batch_op.drop_column('auto_renewal')
        batch_op.drop_column('last_renewal_attempt')
        batch_op.drop_column('renewal_failed_count')
        batch_op.add_column(sa.Column('auto_payment', sa.Boolean(), default=False))
        batch_op.add_column(sa.Column('payment_amount', sa.Float(), default=1500.0))
        batch_op.add_column(sa.Column('last_payment_date', sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column('next_payment_date', sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column('failed_payments', sa.Integer(), default=0))
        batch_op.add_column(sa.Column('notification_sent', sa.Boolean(), default=False))

    op.drop_table('tariff_plans')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('valid_email')
        batch_op.drop_column('registration_date')
        batch_op.drop_column('referral_code')
        batch_op.alter_column('telegram_id',
                            existing_type=sa.BigInteger(),
                            type_=sa.Integer(),
                            existing_nullable=False)
        batch_op.add_column(sa.Column('username', sa.String(50)))
        batch_op.add_column(sa.Column('first_name', sa.String(50)))
        batch_op.add_column(sa.Column('last_name', sa.String(50)))
        batch_op.add_column(sa.Column('created_at', sa.DateTime()))
        batch_op.add_column(sa.Column('referral_link_override', sa.String()))
        batch_op.add_column(sa.Column('referral_status_override', sa.Boolean()))

    with op.batch_alter_table('payments') as batch_op:
        batch_op.alter_column('external_id',
                            new_column_name='payment_id',
                            existing_type=sa.String())
        batch_op.drop_column('error_message')
        batch_op.alter_column('currency',
                            existing_type=sa.String(3),
                            type_=sa.String(),
                            existing_nullable=False)

    with op.batch_alter_table('whitelist') as batch_op:
        batch_op.drop_constraint('valid_expiration')
        batch_op.drop_column('expires_at')
        batch_op.add_column(sa.Column('added_by', sa.Integer()))

    with op.batch_alter_table('admins') as batch_op:
        batch_op.drop_constraint('valid_admin_email')
        batch_op.drop_column('role')

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