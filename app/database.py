from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# SQLite requires check_same_thread=False for multi-threaded use.
# PostgreSQL does not need it — pass only for SQLite.
_connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args)

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
    """
    Initialise the database at startup.

    - SQLite (local dev): create all tables directly via SQLAlchemy.
      Fast, no migration overhead, fine for iterating locally.
    - PostgreSQL (production): run Alembic migrations to head.
      Safe for schema changes on a live database.
    """
    # Import all models so SQLAlchemy / Alembic can see them
    from app.models import (  # noqa: F401
        alert,
        daily_revenue,
        email_alert_config,
        invitation,
        raw_balance_transaction,
        stripe_connection,
        tenant,
        tenant_config,
        user,
    )

    if settings.DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    else:
        from alembic.config import Config
        from alembic import command
        import os

        # alembic.ini lives at the project root (one level up from app/)
        ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        alembic_cfg = Config(os.path.abspath(ini_path))
        command.upgrade(alembic_cfg, "head")
