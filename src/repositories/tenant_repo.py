"""Repository untuk manipulasi data Tenant (Lembaga)."""
from typing import Optional, List
from sqlalchemy.orm import Session
from src.models.tenant import Tenant

def get_tenant_by_id(db: Session, tenant_id: str) -> Optional[Tenant]:
    return db.query(Tenant).filter(Tenant.id == tenant_id).first()

def get_tenant_by_slug(db: Session, slug: str) -> Optional[Tenant]:
    return db.query(Tenant).filter(Tenant.slug == slug).first()

def get_all_tenants(db: Session) -> List[Tenant]:
    return db.query(Tenant).all()

