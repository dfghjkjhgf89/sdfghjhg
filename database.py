from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from config import DATABASE_URL, DB_POOL_SIZE
from models import Base
from contextlib import contextmanager

engine = create_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine)
)

def init_db():
    Base.metadata.create_all(bind=engine)

@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 