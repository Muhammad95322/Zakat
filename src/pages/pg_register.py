"""Halaman registrasi lembaga baru - Zakat Insight."""
import re
import streamlit as st


def _validate_password(password: str) -> list[str]:
    """Validasi kekuatan password, kembalikan list pesan error."""
    errors = []
    if len(password) < 8:
        errors.append("Minimal 8 karakter")
    if not re.search(r"[A-Z]", password):
        errors.append("Minimal 1 huruf besar")
    if not re.search(r"\d", password):
        errors.append("Minimal 1 angka")
    return errors


def show():
    st.set_page_config(
        page_title="Daftar Lembaga - Zakat Insight", page_icon="🕌", layout="centered"
    )

    st.markdown("""
    <style>
    .stButton > button { border-radius: 8px; width: 100%; }
    .reg-header { text-align: center; padding: 2rem 0 1rem; }
    .req-list { background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px;
                padding: 0.75rem 1rem; font-size: 0.85rem; color: #166534; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            '<div class="reg-header"><h1>🕌 Zakat Insight</h1>'
            "<h3>Daftar Lembaga Baru</h3></div>",
            unsafe_allow_html=True,
        )

        with st.form("form_register"):
            nama_lembaga = st.text_input("Nama Lembaga *", placeholder="Yayasan Zakat Nusantara")
            nama_admin = st.text_input("Nama Administrator *", placeholder="Ahmad Fauzi")
            email_admin = st.text_input("Email Administrator *", placeholder="admin@lembaga.id")

            st.markdown(
                '<div class="req-list">🔒 Syarat kata sandi: minimal 8 karakter, '
                "1 huruf besar, 1 angka</div>",
                unsafe_allow_html=True,
            )
            password = st.text_input("Kata Sandi *", type="password")
            konfirmasi_password = st.text_input("Konfirmasi Kata Sandi *", type="password")
            setuju = st.checkbox(
                "Saya menyetujui [syarat & ketentuan](https://zakatinsight.id/terms) "
                "dan [kebijakan privasi](https://zakatinsight.id/privacy)"
            )

            submit = st.form_submit_button("Daftar Sekarang", use_container_width=True)

        if submit:
            # Validasi frontend
            errors = []
            if not nama_lembaga.strip():
                errors.append("Nama lembaga wajib diisi.")
            if not nama_admin.strip():
                errors.append("Nama administrator wajib diisi.")
            if not email_admin.strip():
                errors.append("Email administrator wajib diisi.")
            elif not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email_admin):
                errors.append("Format email tidak valid.")
            if not password:
                errors.append("Kata sandi wajib diisi.")
            else:
                pw_errors = _validate_password(password)
                if pw_errors:
                    errors.append("Kata sandi tidak memenuhi syarat: " + ", ".join(pw_errors) + ".")
            if password and konfirmasi_password and password != konfirmasi_password:
                errors.append("Kata sandi dan konfirmasi tidak cocok.")
            if not setuju:
                errors.append("Anda harus menyetujui syarat & ketentuan untuk mendaftar.")

            if errors:
                for err in errors:
                    st.error(err)
            else:
                try:
                    from src.database import get_db
                    from src.services.auth_service import register_tenant

                    with get_db() as db:
                        result = register_tenant(
                            db,
                            nama_lembaga=nama_lembaga.strip(),
                            nama_admin=nama_admin.strip(),
                            email=email_admin.strip().lower(),
                            password=password,
                        )
                        if result:
                            st.success(
                                f"✅ Email verifikasi telah dikirim ke **{email_admin}**. "
                                "Silakan cek inbox Anda."
                            )
                            st.info(
                                "Setelah email diverifikasi, Anda dapat masuk ke akun Anda."
                            )
                            if st.button("Kembali ke Login"):
                                st.session_state["page"] = "login"
                                st.rerun()
                        else:
                            st.error(
                                "❌ Pendaftaran gagal. Email mungkin sudah terdaftar atau "
                                "terjadi kesalahan sistem."
                            )
                except ImportError as e:
                    st.error(
                        "Sistem sedang dalam pemeliharaan. Silakan coba beberapa saat lagi."
                    )
                    st.caption(f"Detail teknis: {e}")

        st.divider()
        st.markdown(
            "<p style='text-align:center'>Sudah punya akun? </p>", unsafe_allow_html=True
        )
        if st.button("Masuk ke Akun Anda", use_container_width=True, type="secondary"):
            st.session_state["page"] = "login"
            st.rerun()
