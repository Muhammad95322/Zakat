"""Model User."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, String as SAString

from src.database import Base


class UUIDType(TypeDecorator):
    """UUID yang kompatibel dengan SQLite dan PostgreSQL."""
    impl = SAString(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return str(value)


class User(Base):
    """Pengguna platform."""

    __tablename__ = "users"

    id = Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUIDType, ForeignKey("tenants.id"), nullable=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nama_lengkap = Column(String(200), nullable=False)
    peran = Column(
        Enum("super_admin", "admin", "staf", "pembaca", name="peran_enum"),
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    last_login = Column(DateTime)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    tokens = relationship("Token", back_populates="user", cascade="all, delete-orphan")
    uploads = relationship("Upload", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    invitations_sent = relationship(
        "Invitation", back_populates="invited_by_user", foreign_keys="Invitation.invited_by"
    )
    analysis_sessions = relationship("AnalysisSession", back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' peran='{self.peran}'>"
