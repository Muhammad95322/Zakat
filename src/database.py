"""Database engine, session factory, and initialization."""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import settings


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
def normalisasi_url_db(url: str) -> str:
    """Pastikan URL PostgreSQL memakai driver psycopg (v3) yang ada di requirements.

    - 'postgres://' (format Render/Heroku) tidak dikenal SQLAlchemy -> diganti.
    - 'postgresql://' tanpa driver: SQLAlchemy 2.0 memilih psycopg2, 2.1 memilih
      psycopg; dibuat eksplisit agar sama di semua versi.
    URL lain (SQLite, atau yang sudah menyebut driver) tidak diubah.
    """
    for awalan in ("postgres://", "postgresql://"):
        if url.startswith(awalan):
            return "postgresql+psycopg://" + url[len(awalan):]
    return url


DATABASE_URL = normalisasi_url_db(settings.DATABASE_URL)

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    # Log SQL memuat parameter (hash sandi, token, data donatur): hanya bila diminta eksplisit
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
)

# Enable WAL mode for SQLite to improve concurrency
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
# expire_on_commit=False: halaman membaca atribut objek (mis. Upload, Tenant) setelah
# blok `with get_db()` selesai; tanpa ini SQLAlchemy melempar DetachedInstanceError.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


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

    hasil = jalankan_migrasi(engine)
    import logging
    logging.getLogger("zakat.database").info("database siap", extra={"status": hasil})


def jalankan_migrasi(eng=None) -> str:
    """Terapkan migrasi Alembic hingga revisi terbaru.

    - DB kosong: upgrade dari awal.
    - DB lama tanpa tabel alembic_version (dibuat create_all sebelum migrasi ada): di-stamp
      ke 0001 lalu di-upgrade; bila skemanya sudah terbaru (kolom sesi_versi ada) di-stamp ke head.
    - DB yang sudah bermigrasi: upgrade ke head.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    eng = eng or engine
    akar = Path(__file__).resolve().parent.parent
    cfg = Config(str(akar / "alembic.ini"))
    cfg.set_main_option("script_location", str(akar / "migrasi"))
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        insp = inspect(conn)
        tabel = set(insp.get_table_names())
        if "alembic_version" not in tabel and "users" in tabel:
            kolom = {c["name"] for c in insp.get_columns("users")}
            command.stamp(cfg, "head" if "sesi_versi" in kolom else "0001")
            keadaan = "DB lama di-stamp lalu dimigrasi"
        elif "users" not in tabel:
            keadaan = "skema dibuat dari migrasi"
        else:
            keadaan = "migrasi diperbarui"
        command.upgrade(cfg, "head")
    return keadaan
