"""Pembatasan laju per IP yang disimpan di basis data (tahan restart, berlaku lintas proses/instans).

Melengkapi penguncian per akun (users.locked_until). IP mentah tidak disimpan: kunci = HMAC-SHA256
(APP_SECRET_KEY, "aksi|ip"). Baris lama dibersihkan oleh ``bersihkan_retensi``.
"""
import hashlib
import hmac
from datetime import timedelta
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config import settings
from src.models.batas_laju import BatasLaju
from src.waktu import utc_now

AKSI = {"login": "BATAS_LOGIN_IP", "daftar": "BATAS_DAFTAR_IP", "reset": "BATAS_RESET_IP",
        "verifikasi": "BATAS_VERIFIKASI_IP"}


def kebijakan(aksi: str) -> Tuple[int, int]:
    """(maksimum percobaan, jendela detik) dari pengaturan, mis. '20/900'."""
    teks = getattr(settings, AKSI[aksi])
    n, detik = teks.split("/")
    return int(n), int(detik)


def _kunci(aksi: str, ip: str) -> str:
    return hmac.new(settings.APP_SECRET_KEY.encode(), f"{aksi}|{ip}".encode(), hashlib.sha256).hexdigest()


def periksa(db: Session, aksi: str, ip: str, sekarang=None) -> Tuple[bool, int]:
    """(boleh, detik tunggu). Tidak mencatat apa pun."""
    maks, jendela = kebijakan(aksi)
    sekarang = sekarang or utc_now()
    batas = sekarang - timedelta(seconds=jendela)
    q = db.query(func.count(BatasLaju.id), func.min(BatasLaju.waktu)).filter(
        BatasLaju.kunci == _kunci(aksi, ip), BatasLaju.waktu > batas)
    n, tertua = q.one()
    if n < maks:
        return True, 0
    return False, max(1, int((tertua + timedelta(seconds=jendela) - sekarang).total_seconds()))


def catat(db: Session, aksi: str, ip: str, sekarang=None, ua: Optional[str] = None) -> None:
    """Catat satu percobaan. Bila percobaan ini mencapai batas, tulis peristiwa keamanan di log audit."""
    sekarang = sekarang or utc_now()
    db.add(BatasLaju(kunci=_kunci(aksi, ip), aksi=aksi, waktu=sekarang))
    db.commit()
    boleh, _ = periksa(db, aksi, ip, sekarang)
    maks, _ = kebijakan(aksi)
    if not boleh:
        n = db.query(func.count(BatasLaju.id)).filter(
            BatasLaju.kunci == _kunci(aksi, ip),
            BatasLaju.waktu > sekarang - timedelta(seconds=kebijakan(aksi)[1])).scalar()
        if n == maks:  # hanya sekali per jendela, agar log tidak banjir
            from src.services.audit_service import catat_log
            catat_log(db, None, "batas_laju_terlampaui", detail={"aksi": aksi}, ip=ip, ua=ua)


def periksa_dan_catat(db: Session, aksi: str, ip: str, ua: Optional[str] = None) -> Tuple[bool, int]:
    """Untuk aksi yang setiap permintaannya dihitung (daftar, reset, verifikasi)."""
    boleh, tunggu = periksa(db, aksi, ip)
    if not boleh:
        return False, tunggu
    catat(db, aksi, ip, ua=ua)
    return True, 0


def bersihkan(db: Session, sebelum) -> int:
    n = db.query(BatasLaju).filter(BatasLaju.waktu < sebelum).delete(synchronize_session=False)
    db.commit()
    return n


def pesan_terlalu_sering(tunggu_detik: int) -> str:
    menit = max(1, (tunggu_detik + 59) // 60)
    return f"⚠️ Terlalu banyak percobaan dari jaringan Anda. Coba lagi dalam {menit} menit."
