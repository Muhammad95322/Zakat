"""Halaman penerimaan undangan anggota tim - Zakat Insight."""
import streamlit as st


def show():
    st.title("✉️ Terima Undangan")
    token = st.query_params.get("token", "")
    if not token:
        st.error("Tautan undangan tidak valid.")
        return
    st.markdown("Buat akun Anda untuk bergabung dengan lembaga yang mengundang.")
    with st.form("form_terima_undangan"):
        nama = st.text_input("Nama Lengkap *")
        sandi = st.text_input("Kata Sandi *", type="password", help="Minimal 8 karakter, 1 huruf besar, 1 angka")
        konfirmasi = st.text_input("Konfirmasi Kata Sandi *", type="password")
        kirim = st.form_submit_button("Buat Akun", use_container_width=True)
    if kirim:
        if sandi != konfirmasi:
            st.error("Kata sandi dan konfirmasi tidak cocok.")
            return
        from src.database import get_db
        from src.services.auth_service import terima_undangan
        with get_db() as db:
            ok, pesan = terima_undangan(db, token, nama, sandi)
        if ok:
            st.success(f"✅ {pesan} Silakan masuk.")
            if st.button("Masuk", type="primary"):
                st.query_params.clear()
                st.session_state["page"] = "login"
                st.rerun()
        else:
            st.error(f"❌ {pesan}")
