"""Navbar dan Sidebar Navigasi Adaptif Multi-Peran."""
import streamlit as st

def show_navbar(current_page: str = ""):
    with st.sidebar:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 20px;">
            <h2 style="color: #0d9488; margin: 0;">🕌 Zakat Insight</h2>
            <p style="color: #64748b; font-size: 0.85em; margin: 0;">SaaS Analitik Lembaga Zakat</p>
        </div>
        """, unsafe_allow_html=True)
        
        from src.auth.session import is_logged_in, get_current_user, get_user_role
        
        if not is_logged_in():
            st.info("Silakan login untuk mengakses menu.")
            return
            
        user = get_current_user()
        peran = get_user_role() or ""
        
        st.markdown(f"**{user.get('nama_lengkap', 'Pengguna')}**")
        st.caption(f"Peran: {peran.replace('_', ' ').title()}")
        st.divider()
        
        # Menu Navigasi
        menu_items = [
            ("🏠", "Beranda", "dashboard"),
            ("📊", "Analisis & Laporan", "analisis"),
            ("📁", "Unggah Berkas", "upload"),
        ]
        
        if peran in ["admin", "super_admin"]:
            menu_items += [
                ("👥", "Manajemen Tim", "tim"),
                ("📋", "Log Audit", "audit"),
            ]
            
        menu_items += [
            ("💎", "Paket Langganan", "langganan"),
            ("👤", "Profil Akun", "profil"),
        ]
        
        if peran == "super_admin":
            menu_items.append(("⚙️", "Super Admin", "superadmin"))
            
        for icon, label, page_key in menu_items:
            is_active = current_page == page_key
            btn_type = "primary" if is_active else "secondary"
            if st.button(f"{icon} {label}", key=f"nav_{page_key}", use_container_width=True, type=btn_type):
                st.session_state["page"] = page_key
                st.rerun()
                
        st.divider()
        if st.button("🚪 Keluar / Logout", use_container_width=True):
            from src.auth.session import clear_session
            try:  # cabut refresh token di DB, bukan hanya menghapus sesi browser
                from src.database import get_db
                from src.services.auth_service import logout
                with get_db() as db:
                    logout(db, user.get("id"), user.get("refresh_token"))
            except Exception as e:  # logout lokal tetap jalan; catat kegagalan pencabutan token
                print(f"[LOGOUT] Gagal mencabut refresh token: {type(e).__name__}")
            clear_session()
            st.session_state["page"] = "login"
            st.rerun()

