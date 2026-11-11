"""Repository untuk manipulasi data Upload (File unggahan)."""
from typing import Optional, List
from sqlalchemy.orm import Session
from src.models.upload import Upload

def get_upload_by_id(db: Session, upload_id: str, tenant_id: str) -> Optional[Upload]:
    """Mendapatkan data upload dengan isolasi tenant_id."""
    return db.query(Upload).filter(Upload.id == upload_id, Upload.tenant_id == tenant_id).first()

def get_uploads_by_tenant(db: Session, tenant_id: str) -> List[Upload]:
    """Mendapatkan daftar upload milik tenant tertentu."""
    return db.query(Upload).filter(Upload.tenant_id == tenant_id).order_by(Upload.created_at.desc()).all()

