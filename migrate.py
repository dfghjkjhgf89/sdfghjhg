from sqlalchemy import create_engine, text
from config import DATABASE_URL

def migrate():
    engine = create_engine(DATABASE_URL)
    
    # Добавляем новые колонки
    with engine.connect() as connection:
        # Проверяем существование колонок перед добавлением
        existing_columns = connection.execute(text(
            "PRAGMA table_info(subscriptions)"
        )).fetchall()
        existing_column_names = [col[1] for col in existing_columns]
        
        # Добавляем колонки, если они не существуют
        if 'rebill_id' not in existing_column_names:
            connection.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN rebill_id TEXT"
            ))
        
        if 'last_payment_date' not in existing_column_names:
            connection.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN last_payment_date TIMESTAMP"
            ))
        
        if 'next_payment_date' not in existing_column_names:
            connection.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN next_payment_date TIMESTAMP"
            ))
        
        if 'payment_amount' not in existing_column_names:
            connection.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN payment_amount REAL"
            ))
        
        if 'failed_payments' not in existing_column_names:
            connection.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN failed_payments INTEGER DEFAULT 0 NOT NULL"
            ))
        
        # Создаем индекс
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_sub_next_payment ON subscriptions (next_payment_date)"
        ))
        
        connection.commit()
        print("Migration completed successfully!")

if __name__ == "__main__":
    migrate() 