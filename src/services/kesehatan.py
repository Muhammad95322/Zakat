"""Pemeriksaan kesehatan bersama untuk halaman ?page=kesehatan dan scripts/check_health.py."""
import logging
from typing import Any, Dict, Optional, Tuple

from src.config import settings

logger = logging.getLogger("zakat.kesehatan")


def _db() -> Tuple[bool, str]:
    try:
        from sqlalchemy import text

        from src.database import get_db
        with get_db() as db:
            db.execute(text("select 1"))
        return True, "terhubung"
    except Exception as e:
        logger.error("cek basis data gagal", extra={"galat": type(e).__name__})
        return False, f"tidak dapat dihubungi ({type(e).__name__})"


def _penyimpanan() -> Tuple[bool, str]:
    try:
        from src.penyimpanan import penyimpanan
        penyimpanan().periksa()
        return True, f"{settings.PENYIMPANAN} dapat diakses"
    except Exception as e:
        logger.error("cek penyimpanan gagal", extra={"galat": type(e).__name__})
        return False, f"{settings.PENYIMPANAN} tidak dapat diakses ({type(e).__name__})"


def _email() -> Tuple[Optional[bool], str]:
    if not settings.EMAIL_ENABLED:
        return (False if settings.is_production else None), "nonaktif (EMAIL_ENABLED=false)"
    lengkap = all([settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_USER, settings.EMAIL_SMTP_PASS])
    return lengkap, ("terkonfigurasi (pengiriman nyata tidak diuji di sini)" if lengkap else "konfigurasi belum lengkap")


def _konfigurasi() -> Tuple[bool, str]:
    if not settings.is_production:
        return True, "development"
    galat, peringatan = settings.periksa_produksi()
    if galat:
        return False, f"{len(galat)} masalah konfigurasi (lihat log start)"
    return True, "aman" + (f", {len(peringatan)} peringatan" if peringatan else "")


def status_kesehatan(ip_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if ip_info is None:
        ip_info = {"terdeteksi": "-", "peer": "-", "proxy_tepercaya": settings.PROXY_TEPERCAYA}
        try:
            import streamlit as st

            from src.middleware.ip_klien import ip_klien
            ctx = st.context
            peer = getattr(ctx, "ip_address", None)
            ip_info.update({"terdeteksi": ip_klien(dict(ctx.headers or {}), peer), "peer": peer or "-"})
        except Exception as e:  # di luar konteks Streamlit (mis. skrip): diagnosis IP tidak tersedia
            logger.debug("diagnosis IP tidak tersedia", extra={"galat": type(e).__name__})
    periksa = {"Basis data": _db(), "Penyimpanan unggahan": _penyimpanan(), "Email": _email(),
               "Konfigurasi": _konfigurasi()}
    return {"sehat": all(ok is not False for ok, _ in periksa.values()), "periksa": periksa,
            "versi": settings.APP_VERSION, "lingkungan": settings.APP_ENV, "ip": ip_info}
