"""Beranda Zakat Insight."""
import streamlit as st

from src.auth.session import get_current_user, get_tenant_id, get_user_role
from src.components.tema import angka_id, judul_bagian, judul_halaman, ukuran_mb
from src.database import get_db
from src.services.tenant_service import get_tenant, get_tenant_stats
from src.services.upload_service import get_uploads

_PERAN = {"super_admin": "Super admin", "admin": "Admin", "staf": "Staf", "pembaca": "Pembaca"}
_STATUS = {"siap": ("siap", "Siap"), "processing": ("proses", "Diproses")}


def show():
    from html import escape  # data pengguna masuk ke HTML (unsafe_allow_html) -> wajib di-escape

    user = get_current_user()
    tenant_id = get_tenant_id()
    role = get_user_role()

    with get_db() as db:
        tenant = get_tenant(db, tenant_id) if tenant_id else None
        stats = get_tenant_stats(db, tenant_id) if tenant_id else {}
        uploads = get_uploads(db, tenant_id) if tenant_id else []

    nama_user = (user.get("nama_lengkap") if user else None) or "Pengguna"
    nama_lembaga = tenant.nama if tenant else "Administrator pusat"
    judul_halaman(f"Selamat datang, {nama_user}", f"{nama_lembaga} · masuk sebagai {_PERAN.get(role, '-')}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Paket aktif", stats.get("paket", "basic").capitalize() if stats else "Admin")
    c2.metric("Berkas tersimpan", angka_id(len(uploads)))
    c3.metric("Penyimpanan terpakai",
              f"{ukuran_mb(stats.get('storage_mb', 0))} dari {ukuran_mb(stats.get('max_storage_mb', 100))}" if stats else "-")

    if not uploads:
        judul_bagian("Mulai dengan satu berkas",
                     "Unggah laporan penghimpunan (Excel atau CSV) atau pakai data contoh untuk mencoba.")
        if st.button("Unggah berkas pertama", type="primary", icon=":material/upload_file:"):
            st.session_state["page"] = "upload"
            st.rerun()
        return

    judul_bagian("Berkas terbaru", "Pilih berkas untuk langsung membuka analisisnya.")
    for u in uploads[:5]:
        kelas, teks = _STATUS.get(u.status, ("galat", "Bermasalah"))
        k1, k2, k3 = st.columns([5, 1.4, 1.6], vertical_alignment="center")
        k1.markdown(
            f'<div class="zi-baris"><b>{escape(u.nama_file_asli)}</b><br>'
            f'<span class="zi-meta">Diunggah {u.created_at.strftime("%d/%m/%Y")}</span></div>',
            unsafe_allow_html=True,
        )
        k2.markdown(f'<span class="zi-status {kelas}">{teks}</span>', unsafe_allow_html=True)
        if k3.button("Buka analisis", key=f"dash_buka_{u.id}", use_container_width=True):
            st.session_state["selected_upload_id"] = u.id
            st.session_state["page"] = "analisis"
            st.rerun()
