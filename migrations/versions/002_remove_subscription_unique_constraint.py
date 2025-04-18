"""Remove subscription unique constraint

Revision ID: 002
Revises: 001
Create Date: 2025-04-18 18:55:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade():
    # Создаем временную таблицу
    op.execute('''
        CREATE TABLE subscriptions_new (
            id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            is_active BOOLEAN DEFAULT FALSE,
            auto_payment BOOLEAN DEFAULT FALSE,
            start_date DATETIME,
            end_date DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            rebill_id VARCHAR,
            last_payment_date DATETIME,
            next_payment_date DATETIME,
            payment_amount FLOAT,
            failed_payments INTEGER DEFAULT 0
        )
    ''')
    
    # Копируем данные
    op.execute('''
        INSERT INTO subscriptions_new 
        SELECT * FROM subscriptions
    ''')
    
    # Удаляем старую таблицу
    op.execute('DROP TABLE subscriptions')
    
    # Переименовываем новую таблицу
    op.execute('ALTER TABLE subscriptions_new RENAME TO subscriptions')

def downgrade():
    # В случае отката добавляем ограничение уникальности обратно
    op.execute('''
        CREATE TABLE subscriptions_new (
            id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) UNIQUE,
            is_active BOOLEAN DEFAULT FALSE,
            auto_payment BOOLEAN DEFAULT FALSE,
            start_date DATETIME,
            end_date DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            rebill_id VARCHAR,
            last_payment_date DATETIME,
            next_payment_date DATETIME,
            payment_amount FLOAT,
            failed_payments INTEGER DEFAULT 0
        )
    ''')
    
    op.execute('''
        INSERT INTO subscriptions_new 
        SELECT * FROM subscriptions
    ''')
    
    op.execute('DROP TABLE subscriptions')
    op.execute('ALTER TABLE subscriptions_new RENAME TO subscriptions') 