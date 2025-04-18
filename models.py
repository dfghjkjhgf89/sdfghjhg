from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, 
    ForeignKey, BigInteger, Enum, Index, Float, Text, CheckConstraint
)
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import func
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.ext.hybrid import hybrid_property
from contextlib import contextmanager
import datetime
import enum
import re
from config import DATABASE_URL

Base = declarative_base()

class PaymentStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

class PaymentMethod(enum.Enum):
    CARD = "card"
    CRYPTO = "crypto"
    BANK_TRANSFER = "bank_transfer"

class SubscriptionType(enum.Enum):
    BASIC = "basic"
    PREMIUM = "premium"
    VIP = "vip"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    telegram_username = Column(String(50))
    email = Column(String, unique=True, nullable=False)
    registration_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_active = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Реферальная система
    referral_code = Column(String(50), unique=True)
    referral_balance = Column(Float, default=0.0, nullable=False)
    
    # Связи
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    referrals_made = relationship("Referral", back_populates="referrer", 
                                foreign_keys="[Referral.referrer_id]", cascade="all, delete-orphan")
    referrals_received = relationship("Referral", back_populates="referred", 
                                    foreign_keys="[Referral.referred_id]", cascade="all, delete-orphan")

    # Индексы
    __table_args__ = (
        Index('idx_user_telegram', 'telegram_id'),
        Index('idx_user_email', 'email'),
        Index('idx_user_active', 'is_active')
    )

    @hybrid_property
    def has_active_subscription(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        return any(sub.is_active and sub.end_date > now for sub in self.subscriptions)

    def __repr__(self):
        return f"<User {self.telegram_username or self.telegram_id}>"

class TariffPlan(Base):
    __tablename__ = 'tariff_plans'
    
    id = Column(Integer, primary_key=True)
    type = Column(Enum(SubscriptionType), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    duration_days = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связи
    subscriptions = relationship("Subscription", back_populates="tariff")
    
    __table_args__ = (
        UniqueConstraint('type', name='uq_tariff_type'),
    )

class Subscription(Base):
    __tablename__ = 'subscriptions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    tariff_id = Column(Integer, ForeignKey('tariff_plans.id'), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Автоплатежи
    auto_renewal = Column(Boolean, default=False)
    rebill_id = Column(String)
    last_renewal_attempt = Column(DateTime(timezone=True))
    renewal_failed_count = Column(Integer, default=0)
    notification_sent = Column(Boolean, default=False)  # Флаг отправки уведомления
    next_payment_date = Column(DateTime(timezone=True))  # Дата следующего платежа
    payment_amount = Column(Float, default=1500.0)  # Сумма платежа
    
    # Связи
    user = relationship("User", back_populates="subscriptions")
    tariff = relationship("TariffPlan", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription", cascade="all, delete-orphan")

    # Индексы
    __table_args__ = (
        Index('idx_sub_user_active', 'user_id', 'is_active'),
        Index('idx_sub_dates', 'start_date', 'end_date'),
        CheckConstraint('end_date > start_date', name='valid_dates')
    )

    def __repr__(self):
        return f"<Subscription {self.user_id} {self.tariff.type.value}>"

class Payment(Base):
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    subscription_id = Column(Integer, ForeignKey('subscriptions.id', ondelete='CASCADE'))
    external_id = Column(String, unique=True)  # ID транзакции во внешней системе
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default='RUB', nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    payment_method = Column(Enum(PaymentMethod), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    
    # Дополнительная информация
    error_message = Column(Text)
    payment_data = Column(Text)  # JSON с деталями платежа
    
    # Связи
    user = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")

    # Индексы
    __table_args__ = (
        Index('idx_payment_user', 'user_id'),
        Index('idx_payment_status', 'status'),
        Index('idx_payment_dates', 'created_at', 'completed_at'),
    )

class Referral(Base):
    __tablename__ = 'referrals'
    
    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    referred_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reward_amount = Column(Float, default=0.0, nullable=False)
    is_paid = Column(Boolean, default=False, nullable=False)
    paid_at = Column(DateTime(timezone=True))
    
    # Связи
    referrer = relationship("User", back_populates="referrals_made", foreign_keys=[referrer_id])
    referred = relationship("User", back_populates="referrals_received", foreign_keys=[referred_id])

    # Ограничения
    __table_args__ = (
        UniqueConstraint('referred_id', name='uq_referral_referred'),
        Index('idx_referral_referrer', 'referrer_id'),
        Index('idx_referral_referred', 'referred_id'),
    )

class StopCommand(Base):
    __tablename__ = 'stop_commands'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    telegram_id = Column(BigInteger, nullable=False, unique=True)
    stopped_at = Column(DateTime(timezone=True), server_default=func.now())
    reason = Column(String)
    
    # Индексы
    __table_args__ = (
        Index('idx_stop_telegram', 'telegram_id'),
        Index('idx_stop_user', 'user_id'),
    )

class Whitelist(Base):
    __tablename__ = 'whitelist'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    added_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason = Column(String)
    expires_at = Column(DateTime(timezone=True))  # Null означает бессрочный доступ
    
    __table_args__ = (
        Index('idx_whitelist_telegram', 'telegram_id'),
        CheckConstraint('expires_at IS NULL OR expires_at > added_date', name='valid_expiration')
    )

class Admin(Base):
    __tablename__ = 'admins'
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    email = Column(String, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(String(20), default='admin', nullable=False)  # admin, moderator, etc.

    __table_args__ = (
        UniqueConstraint('username', name='uq_admin_username'),
        UniqueConstraint('email', name='uq_admin_email')
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)