"""Layanan pengelolaan file unggahan, kuota storage, dan isolasi tenant."""
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session

from src.models.upload import Upload
from src.models.tenant import Tenant
from src.services.tenant_service import PAKET_LIMITS, get_tenant
from src.middleware.security import validasi_file_upload, sanitasi_nama_file
from src.services.audit_service import catat_log
from src.config import settings
from src.loader import DataFileError
from src.penyimpanan import kunci_dari_storage_path, kunci_unggahan, penyimpanan

logger = logging.getLogger("zakat.unggahan")


def baca_berkas_unggahan(upload: Upload) -> bytes:
    """Isi berkas unggahan dari penyimpanan aktif. Raises FileNotFoundError bila hilang."""
    return penyimpanan().baca(kunci_dari_storage_path(upload.storage_path or ""))

def cek_kuota(db: Session, tenant_id: str, ukuran_bytes: int) -> Tuple[bool, str]:
    """Cek apakah penambahan file masih dalam batas kuota paket."""
    tenant = get_tenant(db, tenant_id)
    if not tenant:
        return False, "Lembaga tidak ditemukan."
        
    limits = PAKET_LIMITS.get(tenant.paket, PAKET_LIMITS["basic"])
    
    # Cek jumlah upload
    total_uploads = db.query(Upload).filter(Upload.tenant_id == tenant_id).count()
    if total_uploads >= limits["max_uploads"]:
        return False, f"Batas unggahan tercapai ({limits['max_uploads']} file). Tingkatkan ke paket yang lebih tinggi."
        
    # Cek kuota storage
    uploads = db.query(Upload).filter(Upload.tenant_id == tenant_id).all()
    current_bytes = sum(u.ukuran_bytes for u in uploads if u.ukuran_bytes)
    tambah_mb = (current_bytes + ukuran_bytes) / (1024 * 1024)
    if tambah_mb > limits["max_storage_mb"]:
        return False, f"Kapasitas penyimpanan tidak mencukupi (Maks: {limits['max_storage_mb']} MB). Silakan bersihkan file lama atau upgrade paket."
        
    return True, ""


def simpan_upload(
    db: Session,
    tenant_id: str,
    user_id: str,
    file_bytes: bytes,
    nama_file_asli: str
) -> Tuple[Optional[Upload], str]:
    """Menyimpan file upload baru dengan validasi dan isolasi penyimpanan."""
    nama_bersih = sanitasi_nama_file(nama_file_asli)
    is_valid, pesan = validasi_file_upload(nama_bersih, file_bytes)
    if not is_valid:
        return None, pesan
        
    # Validasi isi berkas sejak awal agar berkas rusak/kosong tidak tersimpan
    try:
        from src.pipeline import siapkan_data
        siapkan_data(file_bytes, nama_bersih)
    except DataFileError as e:
        return None, str(e)
    except Exception:
        return None, "Berkas tidak dapat dibaca. Pastikan berkas sesuai template, lalu coba lagi."

    bisa_unggah, pesan_kuota = cek_kuota(db, tenant_id, len(file_bytes))
    if not bisa_unggah:
        return None, pesan_kuota
        
    ext = Path(nama_bersih).suffix.lstrip(".")
    upload_id = str(uuid.uuid4())
    nama_file_simpan = f"{upload_id}.{ext}"
    kunci = kunci_unggahan(str(tenant_id), upload_id, ext)  # <tenant>/<uuid>.<ext>
    store = penyimpanan()

    try:
        store.simpan(kunci, file_bytes)

        upload = Upload(
            id=upload_id,
            tenant_id=tenant_id,
            user_id=user_id,
            nama_file_asli=nama_bersih,
            nama_file_simpan=nama_file_simpan,
            ukuran_bytes=len(file_bytes),
            jenis_file=ext,
            status="siap",
            storage_path=kunci
        )
        db.add(upload)
        db.commit()
        
        catat_log(
            db, user_id, "upload_file",
            tenant_id=tenant_id,
            detail={"file": nama_bersih, "ukuran": len(file_bytes)}
        )
        return upload, "File berhasil diunggah."
    except Exception as e:
        db.rollback()
        try:
            store.hapus(kunci)
        except Exception:
            logger.exception("gagal membersihkan berkas setelah penyimpanan gagal")
        logger.error("gagal menyimpan unggahan", extra={"galat": type(e).__name__})
        return None, "Terjadi kesalahan saat menyimpan file. Coba lagi; bila berulang, hubungi admin."


def get_uploads(db: Session, tenant_id: str) -> List[Upload]:
    """Mengambil daftar unggahan dengan isolasi tenant_id."""
    return db.query(Upload).filter(Upload.tenant_id == tenant_id).order_by(Upload.created_at.desc()).all()


def get_upload(db: Session, upload_id: str, tenant_id: str) -> Optional[Upload]:
    """Mengambil detail satu upload dengan filter isolasi tenant_id wajib."""
    return db.query(Upload).filter(Upload.id == upload_id, Upload.tenant_id == tenant_id).first()


def hapus_upload(db: Session, upload_id: str, tenant_id: str, user_id: str) -> bool:
    """Menghapus file dari disk dan database dengan isolasi tenant_id."""
    upload = get_upload(db, upload_id, tenant_id)
    if not upload:
        return False
        
    # Hapus berkas di penyimpanan (lokal/S3); sisa yang gagal dihapus dibersihkan retensi
    if upload.storage_path:
        try:
            penyimpanan().hapus(kunci_dari_storage_path(upload.storage_path))
        except Exception as e:
            logger.error("gagal menghapus berkas unggahan", extra={"galat": type(e).__name__})

    nama_file = upload.nama_file_asli
    db.delete(upload)
    db.commit()
    
    catat_log(db, user_id, "hapus_upload", tenant_id=tenant_id, detail={"file": nama_file})
    return True

