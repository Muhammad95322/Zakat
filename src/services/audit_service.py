"""Layanan pencatatan jejak audit (Audit Logging).

IP & user agent hanya dicatat untuk peristiwa keamanan (login, gagal login, penguncian, reset sandi,
pendaftaran, batas laju). Email dan kata sandi TIDAK PERNAH dicatat. IP/UA dikosongkan setelah
IP_RETENSI_HARI (lihat ``bersihkan_retensi``) walaupun baris log masih disimpan sesuai retensi paket.
"""
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from src.models.audit_log import AuditLog

logger = logging.getLogger("zakat.audit")

KUNCI_DILARANG = {"email", "password", "kata_sandi", "sandi", "token", "password_hash"}


def catat_log(
    db: Session,
    user_id: Optional[str],
    aksi: str,
    tenant_id: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    ua: Optional[str] = None
) -> None:
    """Mencatat aktivitas ke audit_logs tanpa melempar error."""
    detail = {k: v for k, v in (detail or {}).items() if str(k).lower() not in KUNCI_DILARANG}
    try:
        from src.middleware.ip_klien import bersihkan_ua
        log_entry = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            aksi=aksi,
            detail=detail,
            ip_address=(ip or None) and str(ip)[:50],
            user_agent=bersihkan_ua(ua),
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("gagal mencatat log audit", extra={"aksi": aksi, "galat": type(e).__name__})
