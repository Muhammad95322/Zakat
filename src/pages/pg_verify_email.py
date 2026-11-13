"""Halaman verifikasi email - Zakat Insight."""
import streamlit as st
from src.components.tema import kepala_publik


def show():
    st.set_page_config(
        page_title="Verifikasi Email - Zakat Insight", page_icon=":material/bar_chart_4_bars:", layout="centered"
    )


    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        kepala_publik('Verifikasi email', '')

        # Baca token dari query params
        params = st.query_params
        token = params.get("token", "")

        if not token:
            st.markdown(
                '<div class="error-box">Token verifikasi tidak ditemukan.<br>'
                "Pastikan Anda mengklik tautan dari email verifikasi.</div>",
                unsafe_allow_html=True,
            )
            st.write("")
            if st.button("Kembali ke Login", use_container_width=True):
                st.session_state["page"] = "login"
                st.rerun()
            return

        # Proses verifikasi
        with st.spinner("Memverifikasi email Anda..."):
            try:
                from src.database import get_db
                from src.services.auth_service import verifikasi_email

                with get_db() as db:
                    success = verifikasi_email(db, token)

                if success:
                    st.markdown(
                        '<div class="success-box">'
                        "<strong>Email berhasil diverifikasi!</strong><br><br>"
                        "Akun Anda sudah aktif. Silakan masuk menggunakan email dan kata sandi Anda."
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    st.write("")
                    if st.button("Masuk Sekarang", use_container_width=True, type="primary"):
                        st.session_state["page"] = "login"
                        st.rerun()
                else:
                    st.markdown(
                        '<div class="error-box">'
                        "<strong>Verifikasi gagal.</strong><br><br>"
                        "Token tidak valid atau sudah kedaluwarsa. "
                        "Silakan daftar ulang atau hubungi administrator."
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    st.write("")
                    if st.button("Kembali ke Login", use_container_width=True):
                        st.session_state["page"] = "login"
                        st.rerun()

            except ImportError as e:
                st.error(
                    "Sistem sedang dalam pemeliharaan. Silakan coba beberapa saat lagi."
                )
                if st.button("Kembali ke Login", use_container_width=True):
                    st.session_state["page"] = "login"
                    st.rerun()
