"""Halaman Manajemen Paket Langganan dan Kapasitas Akun."""
import streamlit as st
from src.components.tema import judul_halaman
from src.database import get_db
from src.auth.session import get_tenant_id
from src.services.tenant_service import get_tenant, get_tenant_stats, PAKET_LIMITS

def _pesan_kontak() -> str:
    from src.config import settings
    if settings.KONTAK_PENJUALAN:
        return f"Untuk perubahan paket, hubungi: **{settings.KONTAK_PENJUALAN}**."
    return ("Kontak penjualan belum dikonfigurasi oleh pengelola platform (KONTAK_PENJUALAN). "
            "Hubungi administrator platform Anda.")


def _paket(nama, harga, per, fitur, aktif):
    baris = "".join(f'<li class="{"" if ok else "tidak"}">{teks}</li>' for teks, ok in fitur)
    st.markdown(
        f'<div class="zi-paket {"aktif" if aktif else ""}"><h3>{nama}</h3>'
        f'<div class="zi-harga">{harga} <small>{per}</small></div><ul>{baris}</ul></div>',
        unsafe_allow_html=True)


def show():
    judul_halaman("Paket langganan", "Bandingkan paket dan lihat kapasitas yang tersedia untuk lembaga Anda.")
    tenant_id = get_tenant_id()
    if not tenant_id:
        st.info("Akun Super Administrator.")
        return

    with get_db() as db:
        tenant = get_tenant(db, tenant_id)
        stats = get_tenant_stats(db, tenant_id)

    curr_paket = tenant.paket if tenant else "basic"
    st.info(
        "**Halaman ini hanya informasi paket.** Belum ada pembayaran atau penagihan online di aplikasi ini; "
        "harga bersifat indikatif. Perubahan paket dilakukan manual oleh Super Administrator setelah "
        "kesepakatan di luar aplikasi."
    )
    st.markdown(f"Paket Anda saat ini: **{curr_paket.capitalize()}**")

    c1, c2, c3 = st.columns(3, gap="large")

    with c1:
        _paket("Basic", "Rp 0", "per bulan", [
            ("Hingga 2 anggota tim", True), ("Penyimpanan 100 MB", True), ("Maksimal 10 berkas", True),
            ("Analisis dasar dan KPI", True), ("RFM dan peramalan", False), ("Ekspor PDF dan Excel", False)],
            curr_paket == "basic")
        if curr_paket == "basic":
            st.button("Paket aktif", disabled=True, key="p_basic", use_container_width=True)

    with c2:
        _paket("Pro", "Rp 299.000", "per bulan", [
            ("Hingga 10 anggota tim", True), ("Penyimpanan 2 GB", True), ("Maksimal 100 berkas", True),
            ("Analisis lengkap dan RFM muzaki", True), ("Proyeksi 12 bulan", True),
            ("Ekspor laporan PDF dan Excel", True), ("Log audit 30 hari", True)],
            curr_paket == "pro")
        if curr_paket == "pro":
            st.button("Paket aktif", disabled=True, key="p_pro", use_container_width=True)
        elif st.button("Tingkatkan ke Pro", type="primary", key="up_pro", use_container_width=True):
            st.info(_pesan_kontak())

    with c3:
        _paket("Enterprise", "Rp 999.000", "per bulan", [
            ("Pengguna tanpa batas", True), ("Penyimpanan 20 GB", True), ("Berkas tanpa batas", True),
            ("Semua fitur Pro dan white-label", True), ("Log audit 1 tahun", True), ("Dukungan khusus", True)],
            curr_paket == "enterprise")
        if curr_paket == "enterprise":
            st.button("Paket aktif", disabled=True, key="p_ent", use_container_width=True)
        elif st.button("Hubungi kami untuk Enterprise", key="up_ent", use_container_width=True):
            st.info(_pesan_kontak())
