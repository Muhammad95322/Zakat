"""Halaman manajemen tim - Zakat Insight."""
import streamlit as st


def _check_access():
    """Periksa apakah user memiliki akses ke halaman ini."""
    try:
        from src.auth.session import get_user_role
        peran = get_user_role() or ""
    except ImportError:
        user = st.session_state.get("user", {})
        peran = user.get("peran", "") if user else ""
    return peran in ("admin", "super_admin"), peran


def show():
    st.title("👥 Manajemen Tim")

    has_access, peran = _check_access()
    if not has_access:
        st.error("⛔ Akses ditolak. Halaman ini hanya untuk Admin dan Super Admin.")
        return

    try:
        from src.auth.session import get_current_user
        user = get_current_user()
        tenant_id = user.get("tenant_id") if user else None
    except ImportError:
        user = st.session_state.get("user", {})
        tenant_id = user.get("tenant_id") if user else None

    # =========================================================
    # Section 1: Daftar Anggota Tim
    # =========================================================
    st.subheader("👥 Anggota Tim")

    try:
        from src.database import get_db
        from src.repositories.user_repo import get_users_by_tenant

        with get_db() as db:
            members = [
                {"id": m.id, "nama_lengkap": m.nama_lengkap, "email": m.email, "peran": m.peran,
                 "is_active": m.is_active}
                for m in (get_users_by_tenant(db, tenant_id) if tenant_id else [])
            ]

        if members:
            for member in members:
                with st.container(border=True):
                    col1, col2, col3, col4, col5 = st.columns([3, 3, 2, 2, 2])
                    with col1:
                        st.markdown(f"**{member.get('nama_lengkap', '-')}**")
                    with col2:
                        st.caption(member.get("email", "-"))
                    with col3:
                        peran_member = member.get("peran", "staf")
                        badge = {"admin": "🟠", "staf": "🔵", "pembaca": "⚪"}.get(
                            peran_member, "⚪"
                        )
                        st.markdown(f"{badge} {peran_member.replace('_', ' ').title()}")
                    with col4:
                        status_icon = "✅" if member.get("is_active") else "❌"
                        st.markdown(f"{status_icon} {'Aktif' if member.get('is_active') else 'Nonaktif'}")
                    with col5:
                        # Tombol ubah peran
                        new_role = st.selectbox(
                            "Peran",
                            ["admin", "staf", "pembaca"],
                            index=["admin", "staf", "pembaca"].index(
                                peran_member if peran_member in ["admin", "staf", "pembaca"] else "staf"
                            ),
                            key=f"role_{member.get('id')}",
                            label_visibility="collapsed",
                        )
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("Ubah", key=f"ubah_{member.get('id')}", use_container_width=True):
                                try:
                                    from src.repositories.user_repo import update_user_role
                                    with get_db() as db2:
                                        update_user_role(db2, member.get("id"), new_role, oleh=user)
                                    st.success("Peran diperbarui!")
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Gagal: {ex}")
                        with c2:
                            if st.button("Nonaktifkan", key=f"deact_{member.get('id')}", use_container_width=True, type="secondary"):
                                st.session_state[f"confirm_deact_{member.get('id')}"] = True

                        if not member.get("is_active") and member.get("id") != (user or {}).get("id"):
                            if st.button("Hapus data", key=f"hapus_{member.get('id')}", use_container_width=True):
                                try:
                                    from src.services.data_pribadi import hapus_pengguna
                                    with get_db() as db4:
                                        hapus_pengguna(db4, member.get("id"), oleh=user)
                                    st.success("Data pengguna dihapus; unggahannya tetap milik lembaga.")
                                    st.rerun()
                                except (ValueError, PermissionError) as ex:
                                    st.error(str(ex))

                        if st.session_state.get(f"confirm_deact_{member.get('id')}"):
                            st.warning(
                                f"Yakin nonaktifkan **{member.get('nama_lengkap')}**?"
                            )
                            cc1, cc2 = st.columns(2)
                            with cc1:
                                if st.button("Ya, Nonaktifkan", key=f"yes_deact_{member.get('id')}", type="primary"):
                                    try:
                                        from src.repositories.user_repo import deactivate_user
                                        with get_db() as db3:
                                            deactivate_user(db3, member.get("id"), oleh=user)
                                        st.session_state.pop(f"confirm_deact_{member.get('id')}", None)
                                        st.success("Pengguna dinonaktifkan.")
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"Gagal: {ex}")
                            with cc2:
                                if st.button("Batal", key=f"no_deact_{member.get('id')}"):
                                    st.session_state.pop(f"confirm_deact_{member.get('id')}", None)
                                    st.rerun()
        else:
            st.info("Belum ada anggota tim yang terdaftar.")

    except ImportError as e:
        st.warning("Data tim belum tersedia.")

    st.divider()

    # =========================================================
    # Section 2: Undang Anggota Baru
    # =========================================================
    st.subheader("✉️ Undang Anggota Baru")

    with st.form("form_undang"):
        col1, col2 = st.columns(2)
        with col1:
            email_undang = st.text_input("Email *", placeholder="karyawan@lembaga.id")
        with col2:
            peran_undang = st.selectbox("Peran *", ["staf", "admin", "pembaca"])
        kirim = st.form_submit_button("Kirim Undangan", use_container_width=True)

    if kirim:
        if not email_undang.strip():
            st.error("Email wajib diisi.")
        else:
            try:
                from src.database import get_db
                from src.services.auth_service import kirim_undangan

                with get_db() as db:
                    undangan = kirim_undangan(db, tenant_id=tenant_id, email=email_undang.strip(), peran=peran_undang,
                                              oleh=user)
                if getattr(undangan, "email_terkirim", True):
                    st.success(f"✅ Undangan terkirim ke **{email_undang}** dengan peran **{peran_undang}**.")
                else:
                    st.warning("⚠️ Undangan dibuat, tetapi email undangan GAGAL dikirim (server email tidak dapat "
                               "dihubungi atau menolak). Batalkan undangan ini di tabel di bawah lalu coba lagi "
                               "nanti, atau hubungi admin platform.")
            except (ValueError, PermissionError) as e:
                st.error(f"❌ {e}")
            except ImportError as e:
                st.error("Sistem sedang dalam pemeliharaan.")

    # Tabel Undangan Tertunda
    st.subheader("📋 Undangan Tertunda")
    try:
        from src.database import get_db
        from src.services.auth_service import get_pending_invitations

        with get_db() as db:
            invitations = get_pending_invitations(db, tenant_id) if tenant_id else []

        if invitations:
            for inv in invitations:
                col1, col2, col3, col4, col5 = st.columns([3, 2, 3, 3, 2])
                with col1:
                    st.markdown(inv.get("email", "-"))
                with col2:
                    st.markdown(inv.get("peran", "-"))
                with col3:
                    st.caption(f"Dikirim: {inv.get('created_at', '-')}")
                with col4:
                    st.caption(f"Berakhir: {inv.get('expires_at', '-')}")
                with col5:
                    if st.button("Batalkan", key=f"cancel_inv_{inv.get('id')}"):
                        try:
                            from src.services.auth_service import cancel_invitation
                            with get_db() as db2:
                                cancel_invitation(db2, inv.get("id"), tenant_id, oleh=user)
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Gagal: {ex}")
        else:
            st.info("Tidak ada undangan yang tertunda.")

    except ImportError as e:
        st.info("Data undangan belum tersedia.")
