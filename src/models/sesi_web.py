"""Sesi login frontend web (web/, FastAPI).

Cookie browser hanya berisi ID sesi acak; yang disimpan di sini hanya hash SHA-256-nya.
Sengaja TANPA foreign key: ``hapus_pengguna``/``hapus_lembaga`` yang sudah ada menghapus pengguna dan
token tanpa mengenal tabel ini. Baris yatim tidak berbahaya karena validasi sesi selalu memeriksa
pengguna dan refresh token yang ditautkan masih ada.
"""
from sqlalchemy import Column, DateTime, Integer, String

from src.database import Base
from src.waktu import utc_now


class SesiWeb(Base):
    __tablename__ = "sesi_web"

    id_hash = Column(String(64), primary_key=True)          # SHA-256 dari ID sesi di cookie
    user_id = Column(String(36), nullable=False, index=True)
    refresh_token_id = Column(String(36), nullable=True)    # baris tokens (jenis refresh) dari login()
    sesi_versi = Column(Integer, nullable=False, default=0)  # harus sama dengan users.sesi_versi
    csrf = Column(String(64), nullable=False)
    dibuat = Column(DateTime, nullable=False, default=utc_now)
    kedaluwarsa = Column(DateTime, nullable=False, index=True)
    dicabut = Column(DateTime, nullable=True)
