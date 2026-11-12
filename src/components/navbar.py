"""Sidebar navigasi adaptif multi-peran."""
from html import escape

import streamlit as st

from src.components.tema import merek_html

_PERAN = {"super_admin": "Super admin", "admin": "Admin", "staf": "Staf", "pembaca": "Pembaca"}


def show_navbar(current_page: str = ""):
    with st.sidebar:
        st.markdown(merek_html(), unsafe_allow_html=True)

        from src.auth.session import is_logged_in, get_current_user, get_user_role

        if not is_logged_in():
            st.caption("Masuk untuk membuka menu.")
            return

        user = get_current_user()
        peran = get_user_role() or ""
        nama = escape(user.get("nama_lengkap") or "Pengguna")
        st.markdown(
            f'<div class="zi-pengguna"><b>{nama}</b><small>{_PERAN.get(peran, peran.replace("_", " ").title())}</small></div>',
            unsafe_allow_html=True,
        )

        # (ikon Material, label, kunci halaman)
        menu_items = [
            ("home", "Beranda", "dashboard"),
            ("monitoring", "Analisis & laporan", "analisis"),
            ("upload_file", "Unggah berkas", "upload"),
        ]
        if peran in ["admin", "super_admin"]:
            menu_items += [
                ("group", "Tim", "tim"),
                ("history", "Log audit", "audit"),
            ]
        menu_items += [
            ("workspace_premium", "Paket langganan", "langganan"),
            ("account_circle", "Profil akun", "profil"),
        ]
        if peran == "super_admin":
            menu_items.append(("admin_panel_settings", "Super admin", "superadmin"))

        for ikon, label, page_key in menu_items:
            aktif = current_page == page_key
            if st.button(label, key=f"nav_{page_key}", icon=f":material/{ikon}:", use_container_width=True,
                         type="primary" if aktif else "secondary"):
                st.session_state["page"] = page_key
                st.rerun()

        st.divider()
        if st.button("Keluar", key="nav_keluar", icon=":material/logout:", use_container_width=True):
            from src.auth.session import clear_session
            try:  # cabut refresh token di DB, bukan hanya menghapus sesi browser
                from src.database import get_db
                from src.services.auth_service import logout
                with get_db() as db:
                    logout(db, user.get("id"), user.get("refresh_token"))
            except Exception as e:  # logout lokal tetap jalan; catat kegagalan pencabutan token
                import logging
                logging.getLogger("zakat.sesi").warning("gagal mencabut refresh token saat logout",
                                                        extra={"galat": type(e).__name__})
            clear_session()
            st.session_state["page"] = "login"
            st.rerun()
