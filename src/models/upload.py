"""Model Upload File."""
import uuid
from src.waktu import utc_now

from sqlalchemy import BigInteger, Column, Date, DateTime, Enum, ForeignKey, Integer, String, Text
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


class Upload(Base):
    """File yang di-upload oleh tenant."""

    __tablename__ = "uploads"

    id = Column(UUIDType, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUIDType, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    nama_file_asli = Column(String(500), nullable=False)
    nama_file_simpan = Column(String(500))
    ukuran_bytes = Column(BigInteger, default=0)
    jenis_file = Column(String(20))
    status = Column(
        Enum("processing", "siap", "error", name="upload_status_enum"),
        default="processing",
        nullable=False,
    )
    error_pesan = Column(Text)
    periode_mulai = Column(Date)
    periode_selesai = Column(Date)
    jumlah_baris_penghimpunan = Column(Integer)
    jumlah_baris_penyaluran = Column(Integer)
    storage_path = Column(String(500))
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="uploads")
    user = relationship("User", back_populates="uploads")
    analysis_sessions = relationship("AnalysisSession", back_populates="upload", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Upload id={self.id} nama='{self.nama_file_asli}' status='{self.status}'>"
