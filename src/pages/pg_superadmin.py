"""Panel Super Administrator untuk manajemen seluruh lembaga (tenants)."""
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from src.database import get_db
from src.auth.session import get_user_role
from src.services.tenant_service import get_all_tenants, set_paket, nonaktifkan_tenant
from src.models.user import User
from src.models.upload import Upload

def show():
    if get_user_role() != "super_admin":
        st.error("⛔ Akses Terbatas untuk Super Administrator.")
        return

    st.title("⚙️ Panel Super Administrator")
    tab_tenants, tab_stats = st.tabs(["🏢 Daftar Seluruh Lembaga", "📈 Statistik Platform"])

    with tab_tenants:
        with get_db() as db:
            tenants = get_all_tenants(db)
            
        st.markdown(f"Total Lembaga Terdaftar: **{len(tenants)}**")
        for t in tenants:
            with st.expander(f"🏛️ {t.nama} (Paket: {t.paket.upper()})"):
                st.write(f"- Slug: `{t.slug}` | Email Kontak: `{t.email_kontak}`")
                st.write(f"- Status: {'🟢 Aktif' if t.is_active else '🔴 Nonaktif'}")
                
                c_p1, c_p2 = st.columns(2)
                with c_p1:
                    new_paket = st.selectbox(
                        "Ubah Paket:",
                        ["basic", "pro", "enterprise"],
                        index=["basic", "pro", "enterprise"].index(t.paket),
                        key=f"sel_p_{t.id}"
                    )
                    if st.button("Simpan Paket", key=f"btn_p_{t.id}"):
                        with get_db() as db:
                            set_paket(db, t.id, new_paket, date.today(), date.today() + timedelta(days=365))
                            st.success("Paket diperbarui.")
                            st.rerun()
                with st.popover("🗑️ Hapus permanen"):
                    st.warning("Menghapus lembaga, semua pengguna, unggahan (termasuk berkas), dan log auditnya. "
                               "Tidak dapat dibatalkan. Buat backup lebih dulu.")
                    konfirmasi = st.text_input(f"Ketik slug `{t.slug}` untuk konfirmasi", key=f"konf_{t.id}")
                    if st.button("Hapus lembaga ini", key=f"hapus_{t.id}", type="primary"):
                        from src.auth.session import get_current_user
                        from src.services.data_pribadi import hapus_lembaga
                        try:
                            with get_db() as db:
                                hasil = hapus_lembaga(db, t.id, get_current_user(), konfirmasi)
                            st.success(f"Lembaga dihapus: {hasil}")
                            st.rerun()
                        except (ValueError, PermissionError) as e:
                            st.error(str(e))
                with c_p2:
                    if t.is_active:
                        if st.button("Nonaktifkan Lembaga", key=f"btn_non_{t.id}"):
                            with get_db() as db:
                                nonaktifkan_tenant(db, t.id)
                                st.warning("Lembaga dinonaktifkan.")
                                st.rerun()

    with tab_stats:
        with get_db() as db:
            tot_user = db.query(User).count()
            tot_upload = db.query(Upload).count()
            
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Lembaga", len(tenants))
        c2.metric("Total Pengguna", tot_user)
        c3.metric("Total File Diunggah", tot_upload)

