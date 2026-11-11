"""Layanan pencatatan jejak audit (Audit Logging)."""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from src.models.audit_log import AuditLog

def catat_log(
    db: Session,
    user_id: Optional[str],
    aksi: str,
    tenant_id: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    ua: Optional[str] = None
) -> None:
    """Mencatat aktivitas ke audit_logs table tanpa melempar error."""
    try:
        log_entry = AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            aksi=aksi,
            detail=detail or {},
            ip_address=ip or "127.0.0.1",
            user_agent=ua or "ZakatInsight-Client"
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[AUDIT ERROR] Gagal mencatat log: {e}")

