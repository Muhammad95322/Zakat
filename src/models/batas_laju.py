"""Catatan percobaan per IP untuk pembatasan laju (login, daftar, reset, kirim ulang verifikasi)."""
from sqlalchemy import Column, DateTime, Integer, String

from src.database import Base
from src.waktu import utc_now


class BatasLaju(Base):
    """Satu baris = satu percobaan. ``kunci`` = HMAC(APP_SECRET_KEY, aksi|ip), jadi IP mentah tidak disimpan."""

    __tablename__ = "batas_laju"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kunci = Column(String(64), nullable=False, index=True)
    aksi = Column(String(20), nullable=False)
    waktu = Column(DateTime, default=utc_now, nullable=False, index=True)
