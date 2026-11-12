"""Model pemetaan kolom berkas unggahan per lembaga (hasil wizard), agar unggahan berikutnya otomatis."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.types import JSON

from src.database import Base
from src.models.upload import UUIDType
from src.waktu import utc_now


class PemetaanKolom(Base):
    """Pemetaan {bidang standar: judul kolom asli} yang dikonfirmasi lembaga.

    Hanya menyimpan JUDUL kolom, bukan isi data. ``tanda_kolom`` adalah sidik jari susunan
    judul kolom berkas sehingga berkas dengan susunan sama langsung memakai pemetaan ini.
    """

    __tablename__ = "pemetaan_kolom"
    __table_args__ = (UniqueConstraint("tenant_id", "tanda_kolom", name="uq_pemetaan_kolom_tenant_tanda"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(UUIDType, ForeignKey("tenants.id"), nullable=False, index=True)
    tanda_kolom = Column(String(64), nullable=False)
    pemetaan = Column(JSON, nullable=False, default=dict)
    dibuat_oleh = Column(UUIDType, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    def __repr__(self) -> str:
        return f"<PemetaanKolom tenant={self.tenant_id} bidang={sorted(self.pemetaan or {})}>"
