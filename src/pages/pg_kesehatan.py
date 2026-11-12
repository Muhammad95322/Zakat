"""Halaman kesehatan untuk operator (publik, tanpa rahasia): ?page=kesehatan

Render memakai /_stcore/health (bawaan Streamlit) untuk liveness. Halaman ini untuk manusia: status basis
data & penyimpanan, kesiapan email, dan diagnosis IP (untuk memastikan PROXY_TEPERCAYA benar setelah deploy).
Tidak menampilkan nilai rahasia, host, nama pengguna DB, atau data lembaga.
"""
import streamlit as st

from src.services.kesehatan import status_kesehatan


def show():
    st.title("🩺 Status Layanan")
    hasil = status_kesehatan()
    ikon = {True: "✅", False: "❌", None: "➖"}
    for nama, (ok, ket) in hasil["periksa"].items():
        st.write(f"{ikon[ok]} **{nama}**: {ket}")
    st.caption(f"Versi {hasil['versi']} | lingkungan {hasil['lingkungan']}")
    with st.expander("Diagnosis IP (untuk admin platform setelah deploy)"):
        st.write(f"IP Anda menurut aplikasi: `{hasil['ip']['terdeteksi']}`")
        st.write(f"Koneksi langsung dari: `{hasil['ip']['peer']}` | proxy tepercaya: "
                 f"`{hasil['ip']['proxy_tepercaya'] or '(tidak ada)'}`")
        st.caption("IP yang terdeteksi harus sama dengan IP publik Anda (cek di situs 'what is my ip'). Bila yang "
                   "tampil adalah IP proxy/Cloudflare, atur PROXY_TEPERCAYA. Lihat docs/PANDUAN_DEPLOY.md.")
