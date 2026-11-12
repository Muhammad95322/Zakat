"""Halaman reset password - Zakat Insight."""
import re
import streamlit as st


def show():
    st.set_page_config(
        page_title="Reset Kata Sandi - Zakat Insight", page_icon="🕌", layout="centered"
    )

    st.markdown("""
    <style>
    .stButton > button { border-radius: 8px; width: 100%; }
    .reset-header { text-align: center; padding: 2rem 0 1rem; }
    .info-box { background: #eff6ff; border: 1px solid #93c5fd; border-radius: 8px;
                padding: 1rem; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            '<div class="reset-header"><h1>🕌 Zakat Insight</h1>'
            "<h3>Reset Kata Sandi</h3></div>",
            unsafe_allow_html=True,
        )

        # Cek apakah ada token di URL
        params = st.query_params
        token = params.get("token", "")

        if token:
            # State 2: Ada token → tampilkan form password baru
            _show_new_password_form(token)
        else:
            # State 1: Tidak ada token → form minta email
            _show_request_form()

        st.divider()
        if st.button("Kembali ke Login", use_container_width=True, type="secondary"):
            st.session_state["page"] = "login"
            st.rerun()


def _show_request_form():
    """Form untuk meminta link reset password."""
    st.markdown(
        "Masukkan email yang terdaftar. Kami akan mengirimkan tautan untuk mereset kata sandi Anda."
    )

    with st.form("form_request_reset"):
        email = st.text_input("Email", placeholder="admin@lembaga.id")
        submit = st.form_submit_button("Kirim Tautan Reset", use_container_width=True)

    if submit:
        if not email.strip():
            st.error("Email wajib diisi.")
            return
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email.strip()):
            st.error("Format email tidak valid.")
            return

        try:
            from src.database import get_db
            from src.services.auth_service import request_reset_password

            from src.middleware.ip_klien import ip_dan_ua
            from src.services.batas_laju import pesan_terlalu_sering, periksa_dan_catat

            ip, ua = ip_dan_ua()
            with get_db() as db:
                boleh, tunggu = periksa_dan_catat(db, "reset", ip, ua=ua)
                if not boleh:
                    st.error(pesan_terlalu_sering(tunggu))
                    return
                request_reset_password(db, email.strip().lower(), ip=ip, ua=ua)

            # Pesan & waktu respons SAMA untuk email terdaftar maupun tidak (email dikirim di latar belakang)
            st.success(
                "✅ Jika email tersebut terdaftar, tautan reset kata sandi sedang dikirim. Tautan berlaku 1 jam."
            )
            st.info("Bila email tidak masuk dalam 10 menit, periksa folder spam lalu coba lagi. Bila tetap tidak "
                    "masuk, server email mungkin sedang bermasalah; hubungi admin lembaga Anda.")

        except ImportError as e:
            st.error("Sistem sedang dalam pemeliharaan. Silakan coba beberapa saat lagi.")
            st.caption(f"Detail teknis: {e}")


def _show_new_password_form(token: str):
    """Form untuk mengatur password baru menggunakan token."""
    st.markdown("Masukkan kata sandi baru untuk akun Anda.")

    with st.form("form_new_password"):
        new_password = st.text_input(
            "Kata Sandi Baru *",
            type="password",
            help="Minimal 8 karakter, 1 huruf besar, 1 angka",
        )
        konfirmasi = st.text_input("Konfirmasi Kata Sandi Baru *", type="password")
        submit = st.form_submit_button("Simpan Kata Sandi Baru", use_container_width=True)

    if submit:
        errors = []
        if not new_password:
            errors.append("Kata sandi baru wajib diisi.")
        else:
            if len(new_password) < 8:
                errors.append("Minimal 8 karakter.")
            if not re.search(r"[A-Z]", new_password):
                errors.append("Minimal 1 huruf besar.")
            if not re.search(r"\d", new_password):
                errors.append("Minimal 1 angka.")
        if new_password and konfirmasi and new_password != konfirmasi:
            errors.append("Kata sandi dan konfirmasi tidak cocok.")

        if errors:
            for err in errors:
                st.error(err)
            return

        try:
            from src.database import get_db
            from src.services.auth_service import reset_password

            with get_db() as db:
                from src.middleware.ip_klien import ip_dan_ua
                ip, ua = ip_dan_ua()
                success = reset_password(db, token, new_password, ip=ip, ua=ua)

            if success:
                st.success("✅ Kata sandi berhasil diubah! Silakan masuk dengan kata sandi baru.")
                if st.button("Masuk Sekarang", use_container_width=True, type="primary"):
                    st.session_state["page"] = "login"
                    st.rerun()
            else:
                st.error(
                    "❌ Token tidak valid atau sudah kedaluwarsa. "
                    "Silakan minta tautan reset baru."
                )

        except ImportError as e:
            st.error("Sistem sedang dalam pemeliharaan. Silakan coba beberapa saat lagi.")
            st.caption(f"Detail teknis: {e}")
