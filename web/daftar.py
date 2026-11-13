"""Validasi isian pendaftaran lembaga di server, sebelum memanggil ``auth_service.register_tenant``.

Aturan kata sandi TIDAK ditulis ulang: dipakai ``validate_password_strength`` milik layanan.
Batas panjang mengikuti kolom basis data (``users.nama_lengkap``/``users.email`` 200 karakter).
Nama lembaga dibatasi 90 karakter: ``register_lembaga`` membentuk ``tenants.slug`` (String(100)) dari
nama apa adanya plus akhiran "-N" untuk nama kembar, sehingga nama lebih panjang bisa gagal disimpan
di PostgreSQL.
"""
import re
from typing import Dict, Tuple

from src.auth.hashing import validate_password_strength

MAKS_NAMA_LEMBAGA = 90
MIN_NAMA_LEMBAGA = 3
MAKS_NAMA = 200
MAKS_EMAIL = 200
ATURAN_SANDI = "Minimal 8 karakter, memuat 1 huruf besar dan 1 angka."

_KONTROL = re.compile("[\\x00-\\x1f\\x7f\\u200b-\\u200f\\u2028-\\u202e\\u2066-\\u2069\\ufeff]")
_SPASI = re.compile(r"\s+")
# Sama dengan pemeriksaan format di halaman pendaftaran Streamlit
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _teks(nilai: str, label: str, minimal: int, maksimal: int) -> Tuple[str, str]:
    mentah = nilai or ""
    if _KONTROL.search(mentah.replace("\t", " ")):
        return "", f"{label} memuat karakter tak terlihat atau karakter kontrol. Ketik ulang tanpa menempel dari dokumen lain."
    bersih = _SPASI.sub(" ", mentah).strip()
    if not bersih:
        return "", f"Isi {label.lower()}."
    if len(bersih) < minimal:
        return bersih, f"{label} minimal {minimal} karakter."
    if len(bersih) > maksimal:
        return bersih, f"{label} paling panjang {maksimal} karakter; sekarang {len(bersih)}. Singkat bagian yang tidak perlu."
    return bersih, ""


def periksa(nama_lembaga: str, nama: str, email: str, sandi: str, ulangi: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """(nilai bersih, galat per kolom). Galat kosong berarti boleh dikirim ke layanan."""
    galat: Dict[str, str] = {}
    nilai: Dict[str, str] = {}
    nilai["nama_lembaga"], g = _teks(nama_lembaga, "Nama lembaga", MIN_NAMA_LEMBAGA, MAKS_NAMA_LEMBAGA)
    if g:
        galat["nama_lembaga"] = g
    nilai["nama"], g = _teks(nama, "Nama lengkap", 2, MAKS_NAMA)
    if g:
        galat["nama"] = g
    e = (email or "").strip().lower()
    nilai["email"] = e[:MAKS_EMAIL + 50]
    if not e:
        galat["email"] = "Isi email. Tautan verifikasi akan dikirim ke alamat ini."
    elif len(e) > MAKS_EMAIL or _KONTROL.search(e) or not _EMAIL.match(e):
        galat["email"] = "Format email belum benar. Contoh: nama@lembaga.or.id"
    if not sandi:
        galat["sandi"] = f"Isi kata sandi. {ATURAN_SANDI}"
    else:
        ok, pesan = validate_password_strength(sandi)
        if not ok:
            galat["sandi"] = pesan.replace("Password", "Kata sandi")  # pesan dari layanan
    if sandi and "sandi" not in galat and sandi != ulangi:
        galat["ulangi"] = "Kedua kata sandi tidak sama. Ketik ulang kata sandi yang sama persis."
    return nilai, galat
