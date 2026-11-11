"""Database engine, session factory, and initialization."""
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import settings


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
_connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=settings.APP_ENV == "development",
)

# Enable WAL mode for SQLite to improve concurrency
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@contextmanager
def get_db():
    """Context manager yang menyediakan database session."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Buat semua tabel yang belum ada di database."""
    # Import semua model agar metadata terdaftar
    from src.models import (  # noqa: F401
        AuditLog,
        AnalysisSession,
        Invitation,
        Tenant,
        Token,
        Upload,
        User,
    )

    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized successfully.")
