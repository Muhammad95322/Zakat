"""Repository untuk manipulasi data User."""
from typing import Optional, List
from sqlalchemy.orm import Session
from src.models.user import User

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.strip().lower()).first()

def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()

def get_users_by_tenant(db: Session, tenant_id: str) -> List[User]:
    return db.query(User).filter(User.tenant_id == tenant_id).all()

