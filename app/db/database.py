from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite for prototype simplicity; swap DATABASE_URL for Postgres/MySQL in production
DATABASE_URL = "sqlite:///./als_pipeline.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call once at startup or via a migration script."""
    from app.db import models  # noqa: F401  (ensures models are registered)
    Base.metadata.create_all(bind=engine)
