from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite + threads
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called at app startup and in seed script."""
    # Import all models so SQLAlchemy registers them before create_all()
    from app.models import (  # noqa: F401
        alert,
        daily_revenue,
        raw_balance_transaction,
        tenant,
        tenant_config,
        user,
    )
    Base.metadata.create_all(bind=engine)
