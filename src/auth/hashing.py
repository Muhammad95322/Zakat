"""Password hashing dan validasi menggunakan bcrypt."""
import re

import bcrypt


# bcrypt hanya memakai 72 byte pertama; bcrypt 5 melempar ValueError bila lebih
MAKS_BYTE_BCRYPT = 72
# Hash tiruan untuk menyamakan waktu respons login saat email tidak terdaftar
_HASH_TIRUAN = None


def verifikasi_tiruan(plain: str) -> None:
    """Jalankan bcrypt terhadap hash tiruan agar waktu respons tidak membocorkan keberadaan email."""
    global _HASH_TIRUAN
    if _HASH_TIRUAN is None:
        _HASH_TIRUAN = hash_password("Tiruan-Penyama-Waktu-1")
    verify_password(plain, _HASH_TIRUAN)


def hash_password(plain: str) -> str:
    """Hash password menggunakan bcrypt.

    Args:
        plain: Password plaintext.

    Returns:
        String hash bcrypt.
    """
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifikasi password plaintext terhadap hash bcrypt.

    Args:
        plain: Password plaintext dari input pengguna.
        hashed: Hash bcrypt yang tersimpan di database.

    Returns:
        True jika cocok, False jika tidak.
    """
    try:
        if len(plain.encode("utf-8")) > MAKS_BYTE_BCRYPT:
            return False
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validasi kekuatan password.

    Kriteria:
    - Minimal 8 karakter
    - Minimal 1 huruf besar
    - Minimal 1 angka

    Args:
        password: Password yang akan divalidasi.

    Returns:
        Tuple (is_valid, pesan_error). is_valid=True dan pesan kosong jika valid.
    """
    if len(password) < 8:
        return False, "Password minimal 8 karakter."

    if len(password.encode("utf-8")) > MAKS_BYTE_BCRYPT:
        return False, f"Password maksimal {MAKS_BYTE_BCRYPT} byte."

    if not re.search(r"[A-Z]", password):
        return False, "Password harus mengandung minimal 1 huruf besar."

    if not re.search(r"\d", password):
        return False, "Password harus mengandung minimal 1 angka."

    return True, ""
