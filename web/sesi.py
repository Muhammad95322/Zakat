"""Sesi login web: padanan tipis ``src/auth/session.py`` dan ``src/auth/decorators.py`` tanpa Streamlit.

- Cookie hanya berisi ID sesi acak (``secrets.token_urlsafe(32)``); DB menyimpan SHA-256-nya
  (``src.services.auth_service.hash_token``) di tabel ``sesi_web``.
- Login memakai ``auth_service.login`` apa adanya (penguncian akun, waktu respons seragam, audit, refresh
  token di tabel ``tokens``). Sesi ditautkan ke baris refresh token itu; logout menandainya ``used_at``,
  persis cara ``auth_service.logout`` mencabut refresh token.
- Setiap permintaan memvalidasi ulang hal yang sama dengan ``validasi_sesi_data`` versi Streamlit:
  pengguna aktif dan terverifikasi, ``sesi_versi`` sama, lembaga aktif. Peran dibaca dari DB setiap kali,
  jadi perubahan peran langsung berlaku.
"""
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.config import settings
from src.models.sesi_web import SesiWeb
from src.models.tenant import Tenant
from src.models.token_model import Token
from src.models.user import User
from src.services.audit_service import catat_log
from src.services.auth_service import hash_token
from src.waktu import utc_now

# Sama dengan src/auth/session.py (tidak diimpor dari sana karena modul itu memuat Streamlit)
HIERARKI_PERAN = {"super_admin": 4, "admin": 3, "staf": 2, "pembaca": 1}
NAMA_PERAN = {"super_admin": "Super admin", "admin": "Admin", "staf": "Staf", "pembaca": "Pembaca"}


@dataclass(frozen=True)
class Pengguna:
    id: str
    nama: str
    email: str
    peran: str
    tenant_id: Optional[str]
    nama_lembaga: Optional[str]
    csrf: str

    def boleh(self, peran_minimal: str) -> bool:
        """Padanan ``has_permission``: peran pengguna >= peran minimal."""
        return HIERARKI_PERAN.get(self.peran, 0) >= HIERARKI_PERAN.get(peran_minimal, 99)

    @property
    def nama_peran(self) -> str:
        return NAMA_PERAN.get(self.peran, self.peran)


def masa_berlaku() -> timedelta:
    """Masa sesi = masa access token versi Streamlit (JWT_ACCESS_EXPIRE_HOURS, bawaan 8 jam)."""
    return timedelta(hours=settings.JWT_ACCESS_EXPIRE_HOURS)


def buat_sesi(db: Session, user_id: str, refresh_token: Optional[str]) -> str:
    """Simpan sesi baru dan kembalikan ID mentah untuk cookie (tidak pernah disimpan di DB)."""
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("pengguna tidak ditemukan")
    token_row = None
    if refresh_token:
        token_row = db.query(Token).filter(Token.user_id == user_id, Token.jenis == "refresh",
                                           Token.token_hash == hash_token(refresh_token)).first()
    sekarang = utc_now()
    # Bersihkan sesi kedaluwarsa milik pengguna ini agar tabel tidak tumbuh tanpa batas
    db.query(SesiWeb).filter(SesiWeb.user_id == user_id, SesiWeb.kedaluwarsa < sekarang).delete()
    mentah = secrets.token_urlsafe(32)
    db.add(SesiWeb(
        id_hash=hash_token(mentah),
        user_id=user_id,
        refresh_token_id=token_row.id if token_row else None,
        sesi_versi=user.sesi_versi or 0,
        csrf=secrets.token_urlsafe(32),
        dibuat=sekarang,
        kedaluwarsa=sekarang + masa_berlaku(),
    ))
    db.commit()
    return mentah


def baca_sesi(db: Session, mentah: Optional[str]) -> Optional[Pengguna]:
    """Pengguna untuk ID sesi di cookie, atau None bila sesi tidak sah lagi karena alasan apa pun."""
    if not mentah or len(mentah) > 128:
        return None
    sesi = db.get(SesiWeb, hash_token(mentah))
    sekarang = utc_now()
    if sesi is None or sesi.dicabut is not None or sesi.kedaluwarsa <= sekarang:
        return None
    user = db.get(User, sesi.user_id)
    if user is None or not user.is_active or not user.is_verified:
        return None
    if (user.sesi_versi or 0) != (sesi.sesi_versi or 0):
        return None  # sandi diganti/direset atau anggota dinonaktifkan: semua sesi lama berakhir
    nama_lembaga = None
    if user.tenant_id:
        tenant = db.get(Tenant, user.tenant_id)
        if tenant is None or not tenant.is_active:
            return None
        nama_lembaga = tenant.nama
    elif user.peran != "super_admin":
        return None
    if sesi.refresh_token_id:
        tok = db.get(Token, sesi.refresh_token_id)
        if tok is None or tok.used_at is not None or tok.expires_at <= sekarang:
            return None
    return Pengguna(id=str(user.id), nama=user.nama_lengkap, email=user.email, peran=user.peran,
                    tenant_id=str(user.tenant_id) if user.tenant_id else None, nama_lembaga=nama_lembaga,
                    csrf=sesi.csrf)


def cabut_sesi(db: Session, mentah: Optional[str], ip: Optional[str] = None, ua: Optional[str] = None) -> bool:
    """Logout: cabut sesi dan refresh token tautannya di server. True bila ada sesi yang dicabut."""
    if not mentah or len(mentah) > 128:
        return False
    sesi = db.get(SesiWeb, hash_token(mentah))
    if sesi is None or sesi.dicabut is not None:
        return False
    sekarang = utc_now()
    sesi.dicabut = sekarang
    if sesi.refresh_token_id:
        tok = db.get(Token, sesi.refresh_token_id)
        if tok is not None and tok.used_at is None:
            tok.used_at = sekarang  # sama dengan auth_service.logout
    db.commit()
    user = db.get(User, sesi.user_id)
    catat_log(db, sesi.user_id, "logout", tenant_id=user.tenant_id if user else None, ip=ip, ua=ua)
    return True
