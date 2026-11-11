"""Model Tenant (Lembaga Zakat)."""
import re
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, String as SAString

from src.database import Base


class UUIDType(TypeDecorator):
    """UUID yang kompatibel dengan SQLite (disimpan sebagai string) dan PostgreSQL."""
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


def _slugify(text: str) -> str:
    """Konversi teks menjadi slug URL-friendly."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text


class Tenant(Base):
    """Lembaga zakat yang menggunakan platform."""

    __tablename__ = "tenants"

    id = Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    nama = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    email_kontak = Column(String(200), nullable=False)
    telepon = Column(String(20))
    alamat = Column(Text)
    logo_url = Column(String(500))
    paket = Column(
        Enum("basic", "pro", "enterprise", name="paket_enum"),
        default="basic",
        nullable=False,
    )
    paket_mulai = Column(Date)
    paket_berakhir = Column(Date)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    uploads = relationship("Upload", back_populates="tenant", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="tenant")
    invitations = relationship("Invitation", back_populates="tenant", cascade="all, delete-orphan")
    analysis_sessions = relationship("AnalysisSession", back_populates="tenant")

    def __init__(self, **kwargs):
        if "nama" in kwargs and "slug" not in kwargs:
            base_slug = _slugify(kwargs["nama"])
            kwargs["slug"] = base_slug
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} nama='{self.nama}' paket='{self.paket}'>"
