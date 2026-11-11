"""Layanan pengelolaan data Lembaga (Tenant) dan paket langganan."""
from typing import Optional, List, Dict, Any
from datetime import date
from sqlalchemy.orm import Session

from src.models.tenant import Tenant
from src.models.user import User
from src.models.upload import Upload
from src.services.audit_service import catat_log

PAKET_LIMITS = {
    "basic": {
        "max_users": 2,
        "max_storage_mb": 100,
        "max_uploads": 10,
        "fitur_rfm": False,
        "fitur_peramalan": False,
        "fitur_ekspor": False,
        "audit_retensi_hari": 0
    },
    "pro": {
        "max_users": 10,
        "max_storage_mb": 2048, # 2 GB
        "max_uploads": 100,
        "fitur_rfm": True,
        "fitur_peramalan": True,
        "fitur_ekspor": True,
        "audit_retensi_hari": 30
    },
    "enterprise": {
        "max_users": 999999,
        "max_storage_mb": 20480, # 20 GB
        "max_uploads": 999999,
        "fitur_rfm": True,
        "fitur_peramalan": True,
        "fitur_ekspor": True,
        "audit_retensi_hari": 365
    }
}

def get_tenant(db: Session, tenant_id: str) -> Optional[Tenant]:
    return db.query(Tenant).filter(Tenant.id == tenant_id).first()

def update_tenant(db: Session, tenant_id: str, **kwargs) -> Optional[Tenant]:
    tenant = get_tenant(db, tenant_id)
    if not tenant:
        return None
    for k, v in kwargs.items():
        if hasattr(tenant, k):
            setattr(tenant, k, v)
    db.commit()
    catat_log(db, None, "update_tenant", tenant_id=tenant_id, detail=kwargs)
    return tenant

def set_paket(
    db: Session,
    tenant_id: str,
    paket: str,
    mulai: Optional[date] = None,
    berakhir: Optional[date] = None
) -> Optional[Tenant]:
    tenant = get_tenant(db, tenant_id)
    if not tenant:
        return None
    tenant.paket = paket
    tenant.paket_mulai = mulai
    tenant.paket_berakhir = berakhir
    db.commit()
    catat_log(db, None, "set_paket", tenant_id=tenant_id, detail={"paket": paket})
    return tenant

def get_all_tenants(db: Session) -> List[Tenant]:
    return db.query(Tenant).all()

def nonaktifkan_tenant(db: Session, tenant_id: str) -> None:
    tenant = get_tenant(db, tenant_id)
    if tenant:
        tenant.is_active = False
        db.commit()
        catat_log(db, None, "nonaktifkan_tenant", tenant_id=tenant_id)

def get_tenant_stats(db: Session, tenant_id: str) -> Dict[str, Any]:
    tenant = get_tenant(db, tenant_id)
    if not tenant:
        return {}
        
    user_count = db.query(User).filter(User.tenant_id == tenant_id).count()
    uploads = db.query(Upload).filter(Upload.tenant_id == tenant_id).all()
    upload_count = len(uploads)
    total_bytes = sum(u.ukuran_bytes for u in uploads if u.ukuran_bytes)
    total_mb = round(total_bytes / (1024 * 1024), 2)
    
    limits = PAKET_LIMITS.get(tenant.paket, PAKET_LIMITS["basic"])
    
    return {
        "nama": tenant.nama,
        "paket": tenant.paket,
        "user_count": user_count,
        "max_users": limits["max_users"],
        "upload_count": upload_count,
        "max_uploads": limits["max_uploads"],
        "storage_mb": total_mb,
        "max_storage_mb": limits["max_storage_mb"],
        "limits": limits
    }

