"""Model Audit Log."""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON, TypeDecorator, String as SAString

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


class AuditLog(Base):
    """Log aktivitas pengguna untuk audit trail."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUIDType, ForeignKey("tenants.id"), nullable=True)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    aksi = Column(String(100), nullable=False, index=True)
    detail = Column(JSON, default=dict)
    ip_address = Column(String(50))
    user_agent = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} aksi='{self.aksi}' user_id={self.user_id}>"
