"""Deteksi unggahan ganda utuh: berkas yang isinya persis sama dengan unggahan lembaga sebelumnya."""
import hashlib
import logging
from typing import Optional

from sqlalchemy.orm import Session

from src.models.upload import Upload

logger = logging.getLogger("zakat.unggahan")


def _isi(upload: Upload) -> Optional[bytes]:
    try:  # lapisan penyimpanan (bila tersedia), selain itu berkas lokal di storage_path
        from src.services.upload_service import baca_berkas_unggahan  # type: ignore[attr-defined]
        return baca_berkas_unggahan(upload)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("gagal membaca unggahan pembanding", extra={"galat": type(e).__name__})
        return None
    try:
        with open(upload.storage_path or "", "rb") as f:
            return f.read()
    except OSError:
        return None


def cari_unggahan_kembar(db: Session, tenant_id: str, isi: bytes, kecuali_id: Optional[str] = None) -> Optional[Upload]:
    """Unggahan lembaga ini yang isinya identik byte demi byte (dibandingkan lewat SHA-256)."""
    sidik = hashlib.sha256(isi).hexdigest()
    calon = (db.query(Upload).filter(Upload.tenant_id == tenant_id, Upload.ukuran_bytes == len(isi))
             .order_by(Upload.created_at.asc()).all())
    for up in calon:
        if up.id == kecuali_id:
            continue
        lain = _isi(up)
        if lain is not None and hashlib.sha256(lain).hexdigest() == sidik:
            return up
    return None
