"""Layanan pengelolaan file unggahan, kuota storage, dan isolasi tenant."""
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
        
    bisa_unggah, pesan_kuota = cek_kuota(db, tenant_id, len(file_bytes))
    if not bisa_unggah:
        return None, pesan_kuota
        
    ext = Path(nama_bersih).suffix.lstrip(".")
    upload_id = str(uuid.uuid4())
    nama_file_simpan = f"{upload_id}.{ext}"
    
    # Path folder per tenant
    tenant_dir = settings.UPLOAD_DIR / str(tenant_id)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    full_path = tenant_dir / nama_file_simpan
    
    try:
        with open(full_path, "wb") as f:
            f.write(file_bytes)
            
        upload = Upload(
            id=upload_id,
            tenant_id=tenant_id,
            user_id=user_id,
            nama_file_asli=nama_bersih,
            nama_file_simpan=nama_file_simpan,
            ukuran_bytes=len(file_bytes),
            jenis_file=ext,
            status="siap",
            storage_path=str(full_path)
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
        if full_path.exists():
            full_path.unlink()
        return None, f"Terjadi kesalahan saat menyimpan file: {e}"


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
        
    # Hapus file fisik
    if upload.storage_path and os.path.exists(upload.storage_path):
        try:
            os.remove(upload.storage_path)
        except Exception as e:
            print(f"[STORAGE WARNING] Gagal menghapus file fisik: {e}")
            
    nama_file = upload.nama_file_asli
    db.delete(upload)
    db.commit()
    
    catat_log(db, user_id, "hapus_upload", tenant_id=tenant_id, detail={"file": nama_file})
    return True

