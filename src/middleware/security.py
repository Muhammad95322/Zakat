"""Validasi dan sanitasi keamanan untuk file upload dan input."""
import re
from pathlib import Path
from src.config import settings

MAGIC_BYTES = {
    "xlsx": [b"PK\x03\x04"],          # ZIP container
    "xls": [b"\xD0\xCF\x11\xE0"],     # Compound Document
    "csv": None,                        # Plain text
}

ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv"}

def validasi_file_upload(nama_file: str, konten: bytes) -> tuple[bool, str]:
    """Validasi file upload: ekstensi, ukuran, magic bytes."""
    ext = Path(nama_file).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Format file '{ext}' tidak didukung. Gunakan: xlsx, xls, atau csv."
    
    ukuran_mb = len(konten) / (1024 * 1024)
    if ukuran_mb > settings.MAX_UPLOAD_SIZE_MB:
        return False, f"Ukuran file ({ukuran_mb:.1f} MB) melebihi batas {settings.MAX_UPLOAD_SIZE_MB} MB."
    
    magic_list = MAGIC_BYTES.get(ext)
    if magic_list is not None:
        valid_magic = any(konten[:len(m)] == m for m in magic_list)
        if not valid_magic:
            return False, "File tampaknya rusak atau bukan file yang valid. Pastikan file tidak terenkripsi."
    
    if ext == "csv":
        try:
            konten[:1000].decode("utf-8")
        except UnicodeDecodeError:
            return False, "File CSV harus berformat teks (UTF-8)."

    if ext == "xlsx":
        return periksa_arsip_xlsx(konten)

    return True, ""


def periksa_arsip_xlsx(konten: bytes) -> tuple[bool, str]:
    """Periksa daftar isi arsip xlsx SEBELUM diparsing: ukuran dekompresi, rasio, jumlah sheet, makro."""
    import io
    import zipfile

    try:
        arsip = zipfile.ZipFile(io.BytesIO(konten))
        isi = arsip.infolist()
    except (zipfile.BadZipFile, ValueError):
        return False, "File Excel rusak atau bukan file .xlsx yang valid."
    total = sum(i.file_size for i in isi)
    if total > settings.MAX_DEKOMPRESI_MB * 1024 * 1024:
        return False, (f"Isi file Excel terlalu besar setelah dekompresi ({total / 1e6:.0f} MB; "
                       f"batas {settings.MAX_DEKOMPRESI_MB} MB).")
    for i in isi:
        if i.compress_size > 0 and i.file_size / i.compress_size > settings.MAX_RASIO_KOMPRESI and i.file_size > 1024 * 1024:
            return False, "File Excel memiliki rasio kompresi tidak wajar (kemungkinan bom zip) dan ditolak."
    nama = [i.filename.lower() for i in isi]
    if any(n.endswith("vbaproject.bin") or n.endswith(".bin") and "vba" in n for n in nama):
        return False, "File Excel berisi makro (VBA) dan ditolak. Simpan ulang sebagai .xlsx tanpa makro."
    jumlah_sheet = sum(1 for n in nama if n.startswith("xl/worksheets/") and n.endswith(".xml"))
    if jumlah_sheet > settings.MAX_SHEET:
        return False, f"File Excel memiliki {jumlah_sheet} sheet (batas {settings.MAX_SHEET})."
    return True, ""


def sanitasi_nama_file(nama_file: str) -> str:
    """Sanitasi nama file: hapus path traversal dan karakter berbahaya."""
    nama = Path(nama_file).name
    nama = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nama)
    nama = nama.lstrip(". ")
    if len(nama) > 200:
        ext = Path(nama).suffix
        nama = nama[:196] + ext
    return nama or "file_unnamed"


def sanitasi_input(teks: str) -> str:
    """Sanitasi input teks: hapus karakter berbahaya dan control chars."""
    if not isinstance(teks, str):
        return ""
    teks = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', teks)
    return teks.strip()

