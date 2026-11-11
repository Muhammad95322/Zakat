"""Model Invitation (Undangan bergabung ke tenant)."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String
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


class Invitation(Base):
    """Undangan untuk bergabung ke lembaga."""

    __tablename__ = "invitations"

    id = Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUIDType, ForeignKey("tenants.id"), nullable=False)
    email = Column(String(200), nullable=False)
    peran = Column(
        Enum("admin", "staf", "pembaca", name="invitation_peran_enum"),
        nullable=False,
    )
    token_hash = Column(String(255), nullable=False, index=True)
    invited_by = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="invitations")
    invited_by_user = relationship(
        "User", back_populates="invitations_sent", foreign_keys=[invited_by]
    )

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    @property
    def is_accepted(self) -> bool:
        return self.accepted_at is not None

    def __repr__(self) -> str:
        return f"<Invitation id={self.id} email='{self.email}' tenant_id={self.tenant_id}>"
