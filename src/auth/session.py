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

