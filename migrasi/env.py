"""Lingkungan Alembic: memakai engine & metadata aplikasi."""
from alembic import context

from src.database import Base, engine
import src.models  # noqa: F401  (daftarkan semua model ke metadata)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    koneksi = context.config.attributes.get("connection")
    if koneksi is not None:
        context.configure(connection=koneksi, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
