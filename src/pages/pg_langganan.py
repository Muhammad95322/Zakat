"""Halaman Manajemen Paket Langganan dan Kapasitas Akun."""
import streamlit as st
from src.database import get_db
from src.auth.session import get_tenant_id
from src.services.tenant_service import get_tenant, get_tenant_stats, PAKET_LIMITS

def _pesan_kontak() -> str:
    from src.config import settings
    if settings.KONTAK_PENJUALAN:
        return f"Untuk perubahan paket, hubungi: **{settings.KONTAK_PENJUALAN}**."
    return ("Kontak penjualan belum dikonfigurasi oleh pengelola platform (KONTAK_PENJUALAN). "
            "Hubungi administrator platform Anda.")


def show():
    st.title("💎 Paket Langganan & Kapasitas")
    tenant_id = get_tenant_id()
    if not tenant_id:
        st.info("Akun Super Administrator.")
        return

    with get_db() as db:
        tenant = get_tenant(db, tenant_id)
        stats = get_tenant_stats(db, tenant_id)

    curr_paket = tenant.paket if tenant else "basic"
    st.warning(
        "ℹ️ **Halaman ini hanya informasi paket.** Belum ada pembayaran atau penagihan online di aplikasi ini; "
        "harga bersifat indikatif. Perubahan paket dilakukan manual oleh Super Administrator setelah "
        "kesepakatan di luar aplikasi."
    )
    st.success(f"Paket Anda Saat Ini: **{curr_paket.upper()}**")
    
    # Perbandingan 3 Paket
    c1, c2, c3 = st.columns(3)
    
    with c1:
        st.markdown("""
        ### 🌱 Basic
        **Rp 0 / bulan**
        - Hingga 2 Anggota Tim
        - Penyimpanan 100 MB
        - Maksimal 10 File Unggahan
        - Analisis Dasar & KPI
        - ❌ RFM & Peramalan
        - ❌ Ekspor PDF / Excel
        """)
        if curr_paket == "basic":
            st.button("Paket Aktif", disabled=True, key="p_basic")
            
    with c2:
        st.markdown("""
        ### 🚀 Pro
        **Rp 299.000 / bulan**
        - Hingga 10 Anggota Tim
        - Penyimpanan 2 GB
        - Maksimal 100 File Unggahan
        - Analisis Lengkap + RFM Muzaki
        - Proyeksi Peramalan 12 Bulan
        - Ekspor Laporan PDF & Excel Resmi
        - Log Audit 30 Hari
        """)
        if curr_paket == "pro":
            st.button("Paket Aktif", disabled=True, key="p_pro")
        else:
            if st.button("Tingkatkan ke Pro", type="primary", key="up_pro"):
                st.info(_pesan_kontak())
                
    with c3:
        st.markdown("""
        ### 👑 Enterprise
        **Rp 999.000 / bulan**
        - Pengguna Tanpa Batas
        - Penyimpanan 20 GB
        - File Unggahan Tanpa Batas
        - Seluruh Fitur Pro + White-Label
        - Log Audit 1 Tahun
        - Dukungan Dedicated 24/7
        """)
        if curr_paket == "enterprise":
            st.button("Paket Aktif", disabled=True, key="p_ent")
        else:
            if st.button("Hubungi Enterprise", key="up_ent"):
                st.info(_pesan_kontak())

