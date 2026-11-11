"""Halaman Dashboard Utama Zakat Insight."""
import streamlit as st
from src.database import get_db
from src.auth.session import get_current_user, get_tenant_id, get_user_role
from src.services.tenant_service import get_tenant, get_tenant_stats
from src.services.upload_service import get_uploads

def show():
    user = get_current_user()
    tenant_id = get_tenant_id()
    role = get_user_role()
    
    with get_db() as db:
        tenant = get_tenant(db, tenant_id) if tenant_id else None
        stats = get_tenant_stats(db, tenant_id) if tenant_id else {}
        uploads = get_uploads(db, tenant_id) if tenant_id else []

    from html import escape  # data pengguna masuk ke HTML (unsafe_allow_html) -> wajib di-escape
    nama_user = escape(user.get("nama_lengkap", "Pengguna") if user else "Pengguna")
    nama_lembaga = escape(tenant.nama if tenant else "Administrator Pusat")

    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #0d9488 0%, #115e59 100%); padding: 25px; border-radius: 12px; color: white; margin-bottom: 25px;">
        <h2 style="margin: 0; color: white;">Selamat Datang, {nama_user}! 👋</h2>
        <p style="margin: 5px 0 0 0; opacity: 0.9; font-size: 1.1em;">{nama_lembaga} &bull; Peran: <b>{role.replace('_', ' ').title() if role else '-'}</b></p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Paket Aktif", stats.get("paket", "Basic").upper() if stats else "ADMIN")
    c2.metric("Berkas Diunggah", f"{len(uploads)} File")
    c3.metric("Kapasitas Penyimpanan", f"{stats.get('storage_mb', 0)} / {stats.get('max_storage_mb', 100)} MB" if stats else "-")

    st.divider()

    col_act1, col_act2 = st.columns(2)
    with col_act1:
        st.markdown("### 📊 Analisis Cerdas ZIS")
        st.write("Buka dashboard visualisasi lengkap, segmentasi muzaki, peramalan tren, dan ekspor laporan resmi.")
        if st.button("🚀 Buka Halaman Analisis", type="primary", use_container_width=True):
            st.session_state["page"] = "analisis"
            st.rerun()

    with col_act2:
        st.markdown("### 📁 Kelola & Unggah Berkas")
        st.write("Unggah laporan transaksi Excel/CSV baru, gunakan data sintetis uji coba, atau kelola riwayat file.")
        if st.button("📤 Buka Manajemen Berkas", use_container_width=True):
            st.session_state["page"] = "upload"
            st.rerun()
            
    if uploads:
        st.divider()
        st.markdown("### 🕒 Berkas Terbaru")
        for u in uploads[:3]:
            st.write(f"- 📄 **{u.nama_file_asli}** &bull; {u.created_at.strftime('%d/%m/%Y')} &bull; Status: `{u.status}`")

