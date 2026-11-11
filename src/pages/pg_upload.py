"""Halaman Unggah Data Transaksi ZIS dan Riwayat File Multi-Tenant."""
import streamlit as st
from pathlib import Path
from src.database import get_db
from src.auth.session import get_tenant_id, get_current_user, has_permission
from src.services.upload_service import simpan_upload, get_uploads, hapus_upload
from src.services.tenant_service import get_tenant_stats
from src.sample_data import generate_sample_data
from src.loader import load_file
from src.cleaning import clean_data
import pandas as pd
import io

def show():
    st.title("📁 Pengelolaan Data Transaksi ZIS")
    tenant_id = get_tenant_id()
    user = get_current_user()
    
    if not tenant_id:
        st.warning("Anda masuk sebagai Super Administrator tanpa lembaga tertaut.")
        return

    with get_db() as db:
        stats = get_tenant_stats(db, tenant_id)
        
    # 1. Info Kuota & Kapasitas
    st.markdown("### 📊 Status Kapasitas Penyimpanan")
    col1, col2, col3 = st.columns(3)
    storage_mb = stats.get("storage_mb", 0)
    max_storage = stats.get("max_storage_mb", 100)
    upload_count = stats.get("upload_count", 0)
    max_uploads = stats.get("max_uploads", 10)
    paket = stats.get("paket", "basic").upper()
    
    with col1:
        st.metric("Paket Langganan", paket)
    with col2:
        st.metric("Penyimpanan", f"{storage_mb} / {max_storage} MB")
        pct_storage = min(1.0, storage_mb / max_storage) if max_storage > 0 else 0
        st.progress(pct_storage)
    with col3:
        st.metric("Jumlah Berkas", f"{upload_count} / {max_uploads} file")
        pct_upload = min(1.0, upload_count / max_uploads) if max_uploads > 0 else 0
        st.progress(pct_upload)
        
    st.divider()

    # 2. Form Unggah File Baru (hanya admin/staf)
    if has_permission("staf"):
        st.markdown("### 📤 Unggah File Baru")
        col_up, col_helper = st.columns([2, 1])
        
        with col_up:
            uploaded_file = st.file_uploader(
                "Pilih berkas Excel (.xlsx, .xls) atau CSV:",
                type=["xlsx", "xls", "csv"],
                help="Ukuran file maksimal sesuai paket (maks 50MB)"
            )
            
            if uploaded_file is not None:
                if st.button("Simpan dan Proses Berkas", type="primary"):
                    bytes_data = uploaded_file.getvalue()
                    with get_db() as db:
                        res, msg = simpan_upload(db, tenant_id, user["id"], bytes_data, uploaded_file.name)
                        if res:
                            st.success(f"✅ {msg}")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
                            
        with col_helper:
            st.markdown("**Bantuan & Data Uji:**")
            
            # Tombol data contoh sintetis
            if st.button("🎲 Muat Data Contoh Sintetis"):
                with st.spinner("Membuat 2.000 transaksi sintetis realistis..."):
                    df_h, df_s = generate_sample_data(2000, 500)
                    out_buffer = io.BytesIO()
                    with pd.ExcelWriter(out_buffer, engine="openpyxl") as writer:
                        df_h.to_excel(writer, sheet_name="Penghimpunan", index=False)
                        df_s.to_excel(writer, sheet_name="Penyaluran", index=False)
                    out_buffer.seek(0)
                    with get_db() as db:
                        res, msg = simpan_upload(db, tenant_id, user["id"], out_buffer.getvalue(), "data_contoh_zis_3tahun.xlsx")
                        if res:
                            st.success("✅ Data contoh sintetis berhasil dimuat!")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
                            
            # Download template
            sample_tmpl = Path("data/template/template_zakat.xlsx")
            if sample_tmpl.exists():
                with open(sample_tmpl, "rb") as f:
                    st.download_button(
                        "📥 Unduh Template Excel",
                        data=f.read(),
                        file_name="template_zis.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
    else:
        st.info("ℹ️ Peran Anda adalah Pembaca. Anda dapat melihat riwayat dan analitik, namun tidak dapat mengunggah berkas baru.")

    st.divider()

    # 3. Riwayat Unggahan
    st.markdown("### 📋 Riwayat Berkas Tersimpan")
    with get_db() as db:
        files = get_uploads(db, tenant_id)
        
    if not files:
        st.info("Belum ada berkas transaksi yang diunggah. Silakan unggah berkas atau gunakan data contoh di atas.")
        return

    for item in files:
        with st.container():
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            with c1:
                st.markdown(f"**📄 {item.nama_file_asli}**")
                st.caption(f"Diunggah: {item.created_at.strftime('%d/%m/%Y %H:%M')} | Ukuran: {round(item.ukuran_bytes/1024, 1)} KB")
            with c2:
                status_color = "🟢 Siap" if item.status == "siap" else ("🟡 Proses" if item.status == "processing" else "🔴 Error")
                st.write(status_color)
            with c3:
                if st.button("📊 Analisis", key=f"btn_anl_{item.id}", type="primary"):
                    st.session_state["selected_upload_id"] = item.id
                    st.session_state["page"] = "analisis"
                    st.rerun()
            with c4:
                if has_permission("admin"):
                    if st.button("🗑️ Hapus", key=f"btn_del_{item.id}"):
                        with get_db() as db:
                            if hapus_upload(db, item.id, tenant_id, user["id"]):
                                st.success("Berkas dihapus.")
                                st.rerun()
            st.divider()

