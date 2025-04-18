from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, 
    ForeignKey, BigInteger, Enum, Index, Float, Text
)
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import func
from sqlalchemy.schema import UniqueConstraint
from contextlib import contextmanager
import datetime
import enum
from config import DATABASE_URL

Base = declarative_base()

class SubscriptionType(enum.Enum):
    BASIC = "basic"
    PREMIUM = "premium"
    VIP = "vip"

class PaymentStatus(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

class PaymentMethod(enum.Enum):
    CARD = "card"
    CRYPTO = "crypto"
    BANK_TRANSFER = "bank_transfer"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    telegram_username = Column(String(50))
    username = Column(String(50))
    first_name = Column(String(50))
    last_name = Column(String(50))
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_active = Column(DateTime, default=datetime.datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Реферальная система
    referral_link_override = Column(String, nullable=True)
    referral_status_override = Column(Boolean, default=None, nullable=True)
    referral_balance = Column(Float, default=0.0, nullable=False)
    
    # Связи
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    referrals_made = relationship("Referral", back_populates="referrer", 
                                foreign_keys="[Referral.referrer_id]", cascade="all, delete-orphan")
    referrals_received = relationship("Referral", back_populates="referred", 
                                    foreign_keys="[Referral.referred_id]", cascade="all, delete-orphan")
    stop_command = relationship("StopCommand", back_populates="user", uselist=False, 
                              cascade="all, delete-orphan")

    # Индексы
    __table_args__ = (
        Index('idx_user_telegram', 'telegram_id'),
        Index('idx_user_email', 'email'),
        Index('idx_user_active', 'is_active'),
    )

    def __repr__(self):
        return f"<User {self.username or self.telegram_id}>"

class Subscription(Base):
    __tablename__ = 'subscriptions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    is_active = Column(Boolean, default=False)
    auto_payment = Column(Boolean, default=False)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Новые поля для автоплатежей
    rebill_id = Column(String, nullable=True)  # ID для рекуррентных платежей от Тинькофф
    last_payment_date = Column(DateTime, nullable=True)  # Дата последнего успешного платежа
    next_payment_date = Column(DateTime, nullable=True)  # Дата следующего платежа
    payment_amount = Column(Float, nullable=True)  # Сумма платежа
    failed_payments = Column(Integer, default=0)  # Счетчик неудачных попыток оплаты
    
    user = relationship("User", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription", cascade="all, delete-orphan")

    # Индексы
    __table_args__ = (
        Index('idx_sub_user_active', 'user_id', 'is_active'),
        Index('idx_sub_dates', 'start_date', 'end_date'),
        Index('idx_sub_next_payment', 'next_payment_date'),  # Новый индекс для автоплатежей
    )

    def __repr__(self):
        return f"<Subscription {self.user_id} {'Active' if self.is_active else 'Inactive'}>"

class Payment(Base):
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    subscription_id = Column(Integer, ForeignKey('subscriptions.id', ondelete='CASCADE'), nullable=True)
    payment_id = Column(String, unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default='RUB', nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    payment_method = Column(Enum(PaymentMethod), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Дополнительные данные платежа
    payment_data = Column(Text, nullable=True)  # JSON с деталями платежа
    
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
    paid_at = Column(DateTime(timezone=True), nullable=True)
    
    # Связи
    referrer = relationship("User", back_populates="referrals_made", foreign_keys=[referrer_id])
    referred = relationship("User", back_populates="referrals_received", foreign_keys=[referred_id])

    # Ограничения
    __table_args__ = (
        UniqueConstraint('referred_id', name='uq_referral_referred'),
        Index('idx_referral_referrer', 'referrer_id'),
        Index('idx_referral_referred', 'referred_id'),
    )

class Whitelist(Base):
    __tablename__ = 'whitelist'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    added_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason = Column(String, nullable=True)
    added_by = Column(Integer, ForeignKey('admins.id'), nullable=True)
    
    # Связи
    admin = relationship("Admin", back_populates="whitelist_entries")

    # Индексы
    __table_args__ = (
        Index('idx_whitelist_telegram', 'telegram_id'),
    )

class Admin(Base):
    __tablename__ = 'admins'
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Связи
    whitelist_entries = relationship("Whitelist", back_populates="admin")

class StopCommand(Base):
    __tablename__ = 'stop_commands'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    stopped_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reason = Column(String, nullable=True)
    
    # Связи
    user = relationship("User", back_populates="stop_command")

    # Индексы
    __table_args__ = (
        Index('idx_stop_telegram', 'telegram_id'),
        Index('idx_stop_user', 'user_id'),
    )

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)