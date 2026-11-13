"""Halaman profil pengguna - Zakat Insight."""
import re
import streamlit as st
from src.components.tema import judul_halaman


def show():
    judul_halaman("Profil akun", "Kelola nama dan kata sandi Anda.")

    # Ambil info user dari session
    try:
        from src.auth.session import get_current_user, get_user_role
        user = get_current_user()
        peran = get_user_role() or ""
    except ImportError:
        user = st.session_state.get("user", {})
        peran = user.get("peran", "") if user else ""

    if not user:
        st.error("Sesi tidak valid. Silakan login kembali.")
        if st.button("Login"):
            st.session_state["page"] = "login"
            st.rerun()
        return

    # --- Informasi Akun ---
    st.subheader("Informasi akun")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Nama Lengkap:** {user.get('nama_lengkap', '-')}")
        st.markdown(f"**Email:** {user.get('email', '-')}")
        st.markdown(f"**Peran:** {peran.replace('_', ' ').title() if peran else '-'}")
    with col2:
        st.markdown(f"**Lembaga:** {user.get('nama_lembaga', '-')}")
        st.markdown(f"**Bergabung Sejak:** {user.get('created_at', '-')}")
        st.markdown(f"**Status:** {'Aktif' if user.get('is_active', True) else 'Nonaktif'}")

    st.divider()

    # --- Ubah Nama Lengkap ---
    st.subheader("Ubah nama")
    with st.form("form_ubah_nama"):
        nama_baru = st.text_input(
            "Nama Lengkap Baru", value=user.get("nama_lengkap", "")
        )
        simpan_nama = st.form_submit_button("Simpan Nama")

    if simpan_nama:
        if not nama_baru.strip():
            st.error("Nama lengkap tidak boleh kosong.")
        else:
            try:
                from src.database import get_db
                from src.repositories.user_repo import update_user_name
                from src.auth.session import update_session_user

                with get_db() as db:
                    success = update_user_name(db, user["id"], nama_baru.strip())
                if success:
                    update_session_user({"nama_lengkap": nama_baru.strip()})
                    st.success("Nama berhasil diperbarui.")
                else:
                    st.error("Gagal memperbarui nama. Coba lagi.")
            except ImportError as e:
                st.error("Sistem sedang dalam pemeliharaan.")

    st.divider()

    # --- Ubah Kata Sandi ---
    st.subheader("Ubah kata sandi")
    with st.form("form_ubah_password"):
        password_lama = st.text_input("Kata Sandi Saat Ini *", type="password")
        password_baru = st.text_input(
            "Kata Sandi Baru *",
            type="password",
            help="Minimal 8 karakter, 1 huruf besar, 1 angka",
        )
        konfirmasi_baru = st.text_input("Konfirmasi Kata Sandi Baru *", type="password")
        simpan_pw = st.form_submit_button("Ubah Kata Sandi")

    if simpan_pw:
        errors = []
        if not password_lama:
            errors.append("Kata sandi saat ini wajib diisi.")
        if not password_baru:
            errors.append("Kata sandi baru wajib diisi.")
        else:
            if len(password_baru) < 8:
                errors.append("Kata sandi baru minimal 8 karakter.")
            if not re.search(r"[A-Z]", password_baru):
                errors.append("Kata sandi baru harus memiliki minimal 1 huruf besar.")
            if not re.search(r"\d", password_baru):
                errors.append("Kata sandi baru harus memiliki minimal 1 angka.")
        if password_baru and konfirmasi_baru and password_baru != konfirmasi_baru:
            errors.append("Kata sandi baru dan konfirmasi tidak cocok.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            try:
                from src.database import get_db
                from src.services.auth_service import change_password

                with get_db() as db:
                    success = change_password(
                        db, user["id"], password_lama, password_baru
                    )
                if success:
                    # sesi_versi naik -> terbitkan token baru untuk sesi ini; sesi lain berakhir
                    from src.services.auth_service import token_akses_baru
                    from src.auth.session import update_session_user
                    with get_db() as db:
                        update_session_user({"access_token": token_akses_baru(db, user["id"])})
                    st.success("Kata sandi berhasil diubah. Sesi di perangkat lain telah diakhiri.")
                else:
                    st.error(
                        "Kata sandi saat ini tidak benar. Periksa kembali dan coba lagi."
                    )
            except ImportError as e:
                st.error("Sistem sedang dalam pemeliharaan.")

    st.divider()

    # --- Sesi Aktif ---
    st.subheader("Sesi aktif")
    st.info(
        "Sesi aktif saat ini tercatat dari session state browser Anda. "
        "Logout untuk mengakhiri sesi."
    )
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**Token:** `...{user.get('access_token', '')[-8:] if user.get('access_token') else 'N/A'}`")
    with col_b:
        st.markdown(f"**Email:** {user.get('email', '-')}")
