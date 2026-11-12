"""Halaman login Zakat Insight."""
import streamlit as st


def show():
    st.set_page_config(page_title="Login - Zakat Insight", page_icon="🕌", layout="centered")

    # Custom CSS tema hijau-teal
    st.markdown("""
    <style>
    .stButton > button { background-color: #0d9488; color: white; border-radius: 8px; width: 100%; }
    .stButton > button:hover { background-color: #0f766e; }
    .login-header { text-align: center; padding: 2rem 0 1rem; }
    .error-box { background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; padding: 1rem; }
    .warning-box { background: #fffbeb; border: 1px solid #fcd34d; border-radius: 8px; padding: 1rem; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            '<div class="login-header"><h1>🕌 Zakat Insight</h1>'
            '<p>Platform Analitik Lembaga Zakat</p></div>',
            unsafe_allow_html=True,
        )

        with st.form("form_login"):
            email = st.text_input("Email", placeholder="admin@lembaga.id")
            password = st.text_input("Kata Sandi", type="password")
            submit = st.form_submit_button("Masuk", use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Lupa kata sandi?", use_container_width=True, type="secondary"):
                st.session_state["page"] = "reset_password"
                st.rerun()
        with col_b:
            if st.button("Daftar lembaga baru", use_container_width=True, type="secondary"):
                st.session_state["page"] = "register"
                st.rerun()

        if submit:
            if not email or not password:
                st.error("Email dan kata sandi wajib diisi.")
                return

            # Import dengan lazy untuk menghindari error jika modul belum ada
            try:
                from src.database import get_db
                from src.services.auth_service import login
                from src.auth.session import set_current_user
                from src.middleware.rate_limiter import RateLimiter
                from src.middleware.ip_klien import ip_dan_ua
                from src.services import batas_laju
                from src.services.audit_service import catat_log

                ip, ua = ip_dan_ua()
                with get_db() as db:
                    boleh_ip, tunggu_ip = batas_laju.periksa(db, "login", ip)
                if not boleh_ip:
                    st.error(batas_laju.pesan_terlalu_sering(tunggu_ip))
                    return

                limiter = RateLimiter()
                is_allowed, wait_secs = limiter.check_rate_limit(
                    f"login:{email}", max_attempts=5, window_seconds=900
                )

                if not is_allowed:
                    menit = wait_secs // 60
                    st.error(
                        f"⚠️ Terlalu banyak percobaan gagal. Coba lagi dalam {menit} menit."
                    )
                    return

                with get_db() as db:
                    result = login(db, email, password, ip=ip, ua=ua)
                    if result:
                        access_token, refresh_token = result
                        # Decode token untuk dapat info user
                        from src.auth.jwt_handler import decode_token

                        user_data = decode_token(access_token)
                        if user_data:
                            set_current_user(
                                {
                                    "id": user_data.get("sub"),
                                    "email": email,
                                    "nama_lengkap": user_data.get("nama", ""),
                                    "peran": user_data.get("peran", ""),
                                    "tenant_id": user_data.get("tenant_id", ""),
                                    "access_token": access_token,
                                    "refresh_token": refresh_token,
                                }
                            )
                            st.session_state["page"] = "dashboard"
                            st.rerun()
                    else:
                        limiter.record_failure(f"login:{email}")
                        batas_laju.catat(db, "login", ip, ua=ua)
                        catat_log(db, None, "login_gagal", ip=ip, ua=ua)  # tanpa email & sandi
                        st.error(
                            "❌ Email atau kata sandi salah. Periksa kembali dan coba lagi."
                        )
            except ImportError:
                st.error("Sistem sedang dalam pemeliharaan. Silakan coba beberapa saat lagi.")

        with st.expander("Belum menerima email verifikasi?"):
            with st.form("form_kirim_ulang_verifikasi"):
                email_v = st.text_input("Email akun", key="email_kirim_ulang")
                kirim_v = st.form_submit_button("Kirim ulang email verifikasi")
            if kirim_v and email_v.strip():
                from src.database import get_db
                from src.middleware.ip_klien import ip_dan_ua
                from src.services import batas_laju
                from src.services.auth_service import kirim_ulang_verifikasi
                ip, ua = ip_dan_ua()
                with get_db() as db:
                    boleh, tunggu = batas_laju.periksa_dan_catat(db, "verifikasi", ip, ua=ua)
                    if not boleh:
                        st.error(batas_laju.pesan_terlalu_sering(tunggu))
                    else:
                        kirim_ulang_verifikasi(db, email_v, ip=ip, ua=ua)
                        st.success("Jika email tersebut terdaftar dan belum terverifikasi, tautan verifikasi baru "
                                   "sedang dikirim. Periksa juga folder spam.")
