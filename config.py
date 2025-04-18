import os
from dotenv import load_dotenv

load_dotenv()

# Основные настройки бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "8139120177:AAHujI9lO-iTEScy1w-QOyTZM7fMzVbkyaU")
BOT_USERNAME = os.getenv("BOT_USERNAME", "sistemnik_helper_bot")

# Настройки базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/dbname")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', 10))

# Настройки администратора
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "123123")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_TG_ACCOUNT = os.getenv("ADMIN_TG_ACCOUNT")

# Настройки реферальной системы
DEFAULT_REFERRAL_STATUS = os.getenv("DEFAULT_REFERRAL_STATUS", "false").lower() == "true"
REFERRAL_REWARD_AMOUNT = float(os.getenv("REFERRAL_REWARD_AMOUNT", "100.0"))
MIN_WITHDRAWAL_AMOUNT = float(os.getenv("MIN_WITHDRAWAL_AMOUNT", "500.0"))

# Настройки подписок
SUBSCRIPTION_PRICES = {
    "BASIC": float(os.getenv("BASIC_PRICE", "1500.0")),
    "PREMIUM": float(os.getenv("PREMIUM_PRICE", "2500.0")),
    "VIP": float(os.getenv("VIP_PRICE", "5000.0"))
}

SUBSCRIPTION_DURATIONS = {
    "BASIC": int(os.getenv("BASIC_DURATION", "30")),
    "PREMIUM": int(os.getenv("PREMIUM_DURATION", "90")),
    "VIP": int(os.getenv("VIP_DURATION", "180"))
}

# Реквизиты компании
COMPANY_NAME = os.getenv("COMPANY_NAME", "Your Company Name")
COMPANY_REGISTRATION_NUMBER = os.getenv("COMPANY_REGISTRATION_NUMBER", "123456789")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "Company Address")
COMPANY_BANK = os.getenv("COMPANY_BANK", "Bank Name")
COMPANY_ACCOUNT = os.getenv("COMPANY_ACCOUNT", "123456789012")
COMPANY_SWIFT = os.getenv("COMPANY_SWIFT", "SWIFTCODE")
COMPANY_IBAN = os.getenv("COMPANY_IBAN", "IBAN123456789")

# Настройки платежной системы
TBANK_SHOP_ID = os.getenv("TBANK_SHOP_ID", "1744393098681")
TBANK_SECRET_KEY = os.getenv("TBANK_SECRET_KEY", "Vbn$Xf1WISAmLSpp")

# Настройки уведомлений
NOTIFY_BEFORE_EXPIRATION_DAYS = [7, 3, 1]  # За сколько дней уведомлять о скором окончании подписки
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@example.com")

# Настройки безопасности
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "3600"))  # 1 час
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_PERIOD = int(os.getenv("RATE_LIMIT_PERIOD", "3600"))  # 1 час

# Flask settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))