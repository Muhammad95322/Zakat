"""Manajemen state sesi Streamlit untuk autentikasi dan peran pengguna."""
import streamlit as st
from typing import Optional, Dict, Any

ROLE_HIERARCHY = {
    "super_admin": 4,
    "admin": 3,
    "staf": 2,
    "pembaca": 1
}

def get_current_user() -> Optional[Dict[str, Any]]:
    """Mendapatkan dictionary user yang sedang aktif dari session state."""
    return st.session_state.get("current_user")


def set_current_user(user_dict: Dict[str, Any]) -> None:
    """Menyimpan data user yang login ke session state."""
    st.session_state["current_user"] = user_dict
    st.session_state["is_logged_in"] = True


def clear_session() -> None:
    """Menghapus sesi pengguna saat logout."""
    if "current_user" in st.session_state:
        del st.session_state["current_user"]
    st.session_state["is_logged_in"] = False


def is_logged_in() -> bool:
    """Memeriksa apakah sesi saat ini sudah login."""
    return st.session_state.get("is_logged_in", False) and st.session_state.get("current_user") is not None


def get_user_role() -> Optional[str]:
    """Mendapatkan peran pengguna aktif: 'super_admin', 'admin', 'staf', atau 'pembaca'."""
    user = get_current_user()
    return user.get("peran") if user else None


def get_tenant_id() -> Optional[str]:
    """Mendapatkan tenant_id (lembaga) dari pengguna aktif."""
    user = get_current_user()
    return user.get("tenant_id") if user else None


def has_permission(required_role: str) -> bool:
    """Memeriksa apakah pengguna memiliki hak akses sesuai hierarki peran."""
    user_role = get_user_role()
    if not user_role:
        return False
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level


def require_login():
    """Redirect atau stop jika pengguna belum login."""
    if not is_logged_in():
        st.session_state["page"] = "login"
        st.rerun()



def update_session_user(perubahan: Dict[str, Any]) -> None:
    user = get_current_user()
    if user is not None:
        user.update(perubahan)
        st.session_state["current_user"] = user


def validasi_sesi_data(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Periksa sesi terhadap token dan DB; kembalikan data peran/lembaga terkini atau None bila tidak berlaku.

    Sesi berlaku hanya jika: token akses ada, belum kedaluwarsa, milik pengguna itu, akun masih aktif
    dan terverifikasi, lembaganya aktif, dan sesi_versi token sama dengan di DB.
    """
    from src.auth.jwt_handler import get_current_user_from_token, decode_token
    from src.database import get_db
    from src.models.user import User

    if not user or not user.get("access_token"):
        return None
    data = get_current_user_from_token(user["access_token"])
    if not data or str(data.get("user_id")) != str(user.get("id")):
        return None
    sv = (decode_token(user["access_token"]) or {}).get("sv", 0)
    with get_db() as db:
        u = db.query(User).filter(User.id == user.get("id")).first()
        if not u or not u.is_active or not u.is_verified or (u.sesi_versi or 0) != sv:
            return None
        if u.tenant is not None and not u.tenant.is_active:
            return None
        return {"peran": u.peran, "tenant_id": str(u.tenant_id) if u.tenant_id else None,
                "nama_lengkap": u.nama_lengkap, "email": u.email}


def validasi_sesi() -> bool:
    """Dipanggil di setiap muat halaman terlindungi. Sesi tidak berlaku -> dihapus."""
    terkini = validasi_sesi_data(get_current_user())
    if terkini is None:
        clear_session()
        return False
    update_session_user(terkini)  # peran/lembaga selalu dari DB (perubahan peran langsung berlaku)
    return True
