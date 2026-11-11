"""Halaman verifikasi email - Zakat Insight."""
import streamlit as st


def show():
    st.set_page_config(
        page_title="Verifikasi Email - Zakat Insight", page_icon="🕌", layout="centered"
    )

    st.markdown("""
    <style>
    .verify-header { text-align: center; padding: 2rem 0 1rem; }
    .success-box { background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px;
                   padding: 1.5rem; text-align: center; }
    .error-box { background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px;
                 padding: 1.5rem; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            '<div class="verify-header"><h1>🕌 Zakat Insight</h1>'
            "<h3>Verifikasi Email</h3></div>",
            unsafe_allow_html=True,
        )

        # Baca token dari query params
        params = st.query_params
        token = params.get("token", "")

        if not token:
            st.markdown(
                '<div class="error-box">❌ Token verifikasi tidak ditemukan.<br>'
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
                        "✅ <strong>Email berhasil diverifikasi!</strong><br><br>"
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
                        "❌ <strong>Verifikasi gagal.</strong><br><br>"
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
                st.caption(f"Detail teknis: {e}")
                if st.button("Kembali ke Login", use_container_width=True):
                    st.session_state["page"] = "login"
                    st.rerun()
