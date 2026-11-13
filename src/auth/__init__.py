"""Auth package.

Impor malas (PEP 562): ``from src.auth import get_current_user`` tetap bekerja, tetapi mengimpor
``src.auth.hashing`` atau ``src.auth.jwt_handler`` tidak lagi ikut memuat ``src.auth.session`` (yang
memakai Streamlit). Dengan begitu layanan seperti ``auth_service`` dapat dipakai frontend web tanpa
Streamlit.
"""
from importlib import import_module

_NAMA_PER_MODUL = {
    "src.auth.hashing": ("hash_password", "verify_password", "validate_password_strength"),
    "src.auth.jwt_handler": ("create_access_token", "create_refresh_token", "decode_token",
                             "get_current_user_from_token"),
    "src.auth.session": ("get_current_user", "set_current_user", "clear_session", "is_logged_in",
                         "get_user_role", "get_tenant_id", "require_login", "has_permission"),
    "src.auth.decorators": ("check_role",),
}
_ASAL = {nama: modul for modul, daftar in _NAMA_PER_MODUL.items() for nama in daftar}

__all__ = list(_ASAL)


def __getattr__(nama):
    if nama in _ASAL:
        nilai = getattr(import_module(_ASAL[nama]), nama)
        globals()[nama] = nilai
        return nilai
    raise AttributeError(f"module 'src.auth' has no attribute {nama!r}")


def __dir__():
    return sorted(list(globals()) + __all__)
