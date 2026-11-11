"""Model Analysis Session."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
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


class AnalysisSession(Base):
    """Sesi analisis data ZIS yang disimpan."""

    __tablename__ = "analysis_sessions"

    id = Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(UUIDType, ForeignKey("uploads.id"), nullable=False)
    tenant_id = Column(UUIDType, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    nama_sesi = Column(String(200))
    filter_json = Column(JSON, default=dict)
    summary_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    upload = relationship("Upload", back_populates="analysis_sessions")
    tenant = relationship("Tenant", back_populates="analysis_sessions")
    user = relationship("User", back_populates="analysis_sessions")

    def __repr__(self) -> str:
        return f"<AnalysisSession id={self.id} nama='{self.nama_sesi}'>"
