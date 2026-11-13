"""Halaman Unggah Data Transaksi ZIS, wizard pemetaan kolom, dan Riwayat File Multi-Tenant."""
import io
import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from src.auth.session import get_current_user, get_tenant_id, has_permission
from src.components.kualitas import tampilkan_kualitas
from src.components.tema import judul_bagian, judul_halaman, ukuran_mb
from src.database import get_db
from src.loader import DataFileError
from src.pemetaan import BIDANG_WIZARD
from src.pipeline import periksa_berkas, siapkan_data
from src.sample_data import generate_sample_data
from src.services.pemetaan_service import daftar_pemetaan, simpan_pemetaan
from src.services.unggahan_kembar import cari_unggahan_kembar
from src.services.tenant_service import get_tenant_stats
from src.services.upload_service import get_uploads, hapus_upload, simpan_upload

logger = logging.getLogger(__name__)

KUNCI_TERTUNDA = "impor_tertunda"
KUNCI_KUALITAS = "impor_kualitas_terakhir"
TIDAK_ADA = "(tidak ada)"
PESAN_TAK_TERDUGA = ("Terjadi kesalahan tak terduga saat membaca berkas. Pastikan berkas berformat .xlsx atau .csv "
                     "berisi tabel transaksi, lalu coba lagi.")


def _simpan(isi: bytes, nama: str, tenant_id: str, user: dict, pemetaan=None, berkas=None, kolom=None) -> None:
    """Bersihkan + simpan berkas; simpan pemetaan pilihan pengguna untuk unggahan berikutnya."""
    with get_db() as db:
        lembaga = daftar_pemetaan(db, tenant_id)
    try:
        hasil = siapkan_data(isi, nama, pemetaan=pemetaan, pemetaan_lembaga=lembaga, berkas=berkas)
    except DataFileError as e:
        st.error(str(e))
        return
    except Exception:
        logger.exception("Gagal memproses berkas unggahan %s", nama)
        st.error(PESAN_TAK_TERDUGA)
        return
    with get_db() as db:
        kembar = cari_unggahan_kembar(db, tenant_id, isi)
        info_kembar = ({"nama": kembar.nama_file_asli, "waktu": kembar.created_at.strftime("%d/%m/%Y %H:%M")}
                       if kembar is not None else None)
        res, msg = simpan_upload(db, tenant_id, user["id"], isi, nama, hasil_siap=hasil)
        if not res:
            st.error(msg)
            return
        if pemetaan:
            simpan_pemetaan(db, tenant_id, user["id"], kolom or [], pemetaan)
    st.session_state.pop(KUNCI_TERTUNDA, None)
    st.session_state[KUNCI_KUALITAS] = {"nama": nama, "isi": isi, "kualitas": hasil["kualitas"],
                                        "kolom": hasil["kolom"], "pemetaan": hasil["pemetaan"]["pemetaan"],
                                        "kembar": info_kembar,
                                        "pesan": msg + (" Pemetaan kolom disimpan untuk unggahan berikutnya."
                                                        if pemetaan else "")}
    st.rerun()


def _atur_duplikat(tenant_id: str, user: dict, terakhir: dict, kunci: str, nilai: bool) -> None:
    """Simpan pilihan duplikat (buang_duplikat_persis / id_transaksi_unik) bersama pemetaan kolom, lalu hitung
    ulang laporan kualitas berkas terakhir."""
    lap = terakhir["kualitas"]
    opsi = {"buang_duplikat_persis": bool(lap.get("buang_duplikat_persis")),
            "id_transaksi_unik": bool(lap.get("id_transaksi_unik")), kunci: nilai}
    with get_db() as db:
        simpan_pemetaan(db, tenant_id, user["id"], terakhir["kolom"], terakhir["pemetaan"], opsi=opsi)
        lembaga = daftar_pemetaan(db, tenant_id)
    try:
        hasil = siapkan_data(terakhir["isi"], terakhir["nama"], pemetaan_lembaga=lembaga)
        terakhir["kualitas"] = hasil["kualitas"]
    except Exception:
        logger.exception("Gagal menghitung ulang laporan kualitas")
    pesan = {("buang_duplikat_persis", True): "Pilihan disimpan: duplikat persis DIBUANG untuk berkas dengan "
                                              "susunan kolom ini.",
             ("buang_duplikat_persis", False): "Pilihan disimpan: baris identik DIPERTAHANKAN.",
             ("id_transaksi_unik", True): "Pilihan disimpan: ID transaksi dianggap UNIK; baris ber-ID sama dibuang.",
             ("id_transaksi_unik", False): "Pilihan disimpan: baris ber-ID sama dengan isi berbeda DIPERTAHANKAN."}
    terakhir["pesan"] = pesan[(kunci, nilai)]
    st.rerun()


def _tampilkan_duplikat(tenant_id: str, user: dict, terakhir: dict) -> None:
    lap = terakhir["kualitas"]
    if terakhir.get("kembar"):
        k = terakhir["kembar"]
        st.warning(f"Berkas ini identik byte demi byte dengan unggahan '{k['nama']}' ({k['waktu']}). "
                   "Kemungkinan unggahan ganda; hapus salah satunya di Riwayat bila tidak disengaja.")
    if lap.get("kolom_id_transaksi"):
        if lap.get("id_berbagi"):
            st.warning(f"{lap['id_berbagi']} baris berbagi ID transaksi yang sama tetapi isinya berbeda "
                       "(mis. satu kwitansi untuk beberapa pos); semuanya dipertahankan.")
            st.caption("Bawaan: semua baris dipertahankan agar donasi sah tidak hilang. Pilih tombol di bawah HANYA "
                       "bila di lembaga Anda satu nomor bukti PASTI satu transaksi; baris ber-ID sama selain yang "
                       "pertama akan DIBUANG walau nominal/jenis dananya berbeda.")
            if st.button("Anggap ID transaksi unik, buang baris ber-ID sama", key="btn_id_unik"):
                _atur_duplikat(tenant_id, user, terakhir, "id_transaksi_unik", True)
        elif lap.get("id_transaksi_unik"):
            st.info("ID transaksi dianggap unik untuk berkas dengan susunan kolom ini (pilihan lembaga): baris "
                    "ber-ID sama dibuang.")
            if st.button("Pertahankan baris ber-ID sama", key="btn_id_tidak_unik"):
                _atur_duplikat(tenant_id, user, terakhir, "id_transaksi_unik", False)
    if lap.get("identik_dipertahankan"):
        st.warning(f"{lap['identik_dipertahankan']} baris identik dipertahankan karena tidak ada ID transaksi; "
                   "periksa apakah ada unggahan ganda.")
        st.caption("Dua donasi yang sama pada hari yang sama bisa saja sah. Buang hanya bila Anda yakin baris "
                   "itu terunggah dua kali. Pilihan ini disimpan bersama pemetaan kolom lembaga.")
        if st.button(f"Buang {lap.get('salinan_identik', 0)} baris duplikat persis",
                     key="btn_buang_duplikat"):
            _atur_duplikat(tenant_id, user, terakhir, "buang_duplikat_persis", True)
    elif lap.get("buang_duplikat_persis"):
        st.info("Duplikat persis dibuang untuk berkas dengan susunan kolom ini (pilihan lembaga).")
        if st.button("Pertahankan baris identik", key="btn_pertahankan_duplikat"):
            _atur_duplikat(tenant_id, user, terakhir, "buang_duplikat_persis", False)


def _proses_unggahan(isi: bytes, nama: str, tenant_id: str, user: dict) -> None:
    st.session_state.pop(KUNCI_KUALITAS, None)
    st.session_state.pop(KUNCI_TERTUNDA, None)
    with get_db() as db:
        lembaga = daftar_pemetaan(db, tenant_id)
    try:
        periksa = periksa_berkas(isi, nama, lembaga)
    except DataFileError as e:
        st.error(str(e))
        return
    except Exception:
        logger.exception("Gagal membaca berkas unggahan %s", nama)
        st.error(PESAN_TAK_TERDUGA)
        return
    if periksa.perlu_wizard:
        st.session_state[KUNCI_TERTUNDA] = {"isi": isi, "nama": nama, "periksa": periksa}
        st.rerun()
    _simpan(isi, nama, tenant_id, user, berkas=periksa.berkas)


def _wizard(tenant_id: str, user: dict) -> None:
    t = st.session_state[KUNCI_TERTUNDA]
    p = t["periksa"]
    judul_bagian("Cocokkan kolom berkas")
    st.warning(f"Kolom pada berkas **{t['nama']}** tidak dapat dipastikan otomatis. "
               + " ".join(p.deteksi.alasan) + " Pilih kolom yang sesuai, lalu simpan.")
    st.caption("Pratinjau 5 baris pertama (judul kolom sesuai berkas):")
    st.dataframe(p.pratinjau.astype(str).replace({"None": "", "nan": ""}), hide_index=True, width="stretch")
    opsi = [TIDAK_ADA] + p.kolom
    pilihan = {}
    kol = st.columns(2)
    for i, (bidang, label) in enumerate(BIDANG_WIZARD.items()):
        saran = p.deteksi.pemetaan.get(bidang)
        with kol[i % 2]:
            pilihan[bidang] = st.selectbox(label, opsi, index=opsi.index(saran) if saran in opsi else 0,
                                           key=f"wiz_{p.tanda[:10]}_{bidang}")
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Simpan pemetaan dan proses", type="primary", key="wiz_simpan"):
            pem = {b: (k if k != TIDAK_ADA else None) for b, k in pilihan.items()}
            _simpan(t["isi"], t["nama"], tenant_id, user, pemetaan=pem, berkas=p.berkas, kolom=p.kolom)
    with c2:
        if st.button("Batal", key="wiz_batal"):
            st.session_state.pop(KUNCI_TERTUNDA, None)
            st.rerun()


def show():
    judul_halaman("Unggah berkas", "Simpan laporan transaksi zakat, infak, dan sedekah. Setiap berkas dibersihkan otomatis sebelum dianalisis.")
    tenant_id = get_tenant_id()
    user = get_current_user()
    
    if not tenant_id:
        st.warning("Anda masuk sebagai Super Administrator tanpa lembaga tertaut.")
        return

    with get_db() as db:
        stats = get_tenant_stats(db, tenant_id)
        
    # 1. Info Kuota & Kapasitas
    judul_bagian("Kapasitas paket")
    col1, col2, col3 = st.columns(3)
    storage_mb = stats.get("storage_mb", 0)
    max_storage = stats.get("max_storage_mb", 100)
    upload_count = stats.get("upload_count", 0)
    max_uploads = stats.get("max_uploads", 10)
    paket = stats.get("paket", "basic").upper()
    
    with col1:
        st.metric("Paket", paket.capitalize())
    with col2:
        st.metric("Penyimpanan", f"{ukuran_mb(storage_mb)} dari {ukuran_mb(max_storage)}")
        pct_storage = min(1.0, storage_mb / max_storage) if max_storage > 0 else 0
        st.progress(pct_storage)
    with col3:
        st.metric("Jumlah berkas", f"{upload_count} dari {max_uploads}")
        pct_upload = min(1.0, upload_count / max_uploads) if max_uploads > 0 else 0
        st.progress(pct_upload)

    # 2. Form Unggah File Baru (hanya admin/staf)
    if has_permission("staf"):
        judul_bagian("Berkas baru")
        col_up, col_helper = st.columns([2, 1])
        
        with col_up:
            uploaded_file = st.file_uploader(
                "Pilih berkas Excel (.xlsx, .xls) atau CSV",
                type=["xlsx", "xls", "csv"],
                help="Ukuran maksimal 50 MB, sesuai batas paket."
            )
            
            if uploaded_file is not None:
                if st.button("Simpan dan proses", type="primary", key="btn_proses_unggah"):
                    _proses_unggahan(uploaded_file.getvalue(), uploaded_file.name, tenant_id, user)

            if st.session_state.get(KUNCI_TERTUNDA):
                _wizard(tenant_id, user)

            terakhir = st.session_state.get(KUNCI_KUALITAS)
            if terakhir:
                st.success(f"{terakhir['nama']}: {terakhir['pesan']}")
                _tampilkan_duplikat(tenant_id, user, terakhir)
                tampilkan_kualitas(terakhir["kualitas"], "Laporan kualitas data berkas terakhir", terbuka=True)

        with col_helper:
            st.markdown("**Belum punya berkas?**")
            st.caption("Coba dengan data contoh, atau pakai template agar kolomnya langsung sesuai.")
            
            # Tombol data contoh sintetis
            if st.button("Muat data contoh", icon=":material/science:"):
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
                            st.success("Data contoh berhasil dimuat.")
                            st.rerun()
                        else:
                            st.error(msg)
                            
            # Download template
            sample_tmpl = Path("data/template/template_zakat.xlsx")
            if sample_tmpl.exists():
                with open(sample_tmpl, "rb") as f:
                    st.download_button(
                        "Unduh template Excel",
                        data=f.read(),
                        file_name="template_zis.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
    else:
        st.info("Peran Anda adalah Pembaca. Anda dapat melihat riwayat dan analitik, namun tidak dapat mengunggah berkas baru.")

    st.divider()

    # 3. Riwayat Unggahan
    judul_bagian("Riwayat berkas")
    with get_db() as db:
        files = get_uploads(db, tenant_id)
        
    if not files:
        st.info("Belum ada berkas. Unggah berkas di atas atau muat data contoh.")
        return

    from html import escape
    for item in files:
        kelas, teks = {"siap": ("siap", "Siap"), "processing": ("proses", "Diproses")}.get(item.status, ("galat", "Bermasalah"))
        c1, c2, c3, c4 = st.columns([4, 1.2, 1.5, 1.2], vertical_alignment="center")
        with c1:
            st.markdown(
                f'<div class="zi-baris"><b>{escape(item.nama_file_asli)}</b><br><span class="zi-meta">'
                f'{item.created_at.strftime("%d/%m/%Y %H:%M")} · {round(item.ukuran_bytes/1024, 1)} KB</span></div>',
                unsafe_allow_html=True)
        with c2:
            st.markdown(f'<span class="zi-status {kelas}">{teks}</span>', unsafe_allow_html=True)
        with c3:
            if st.button("Buka analisis", key=f"btn_anl_{item.id}", type="primary", use_container_width=True):
                st.session_state["selected_upload_id"] = item.id
                st.session_state["page"] = "analisis"
                st.rerun()
        with c4:
            if has_permission("admin"):
                if st.button("Hapus", key=f"btn_del_{item.id}", use_container_width=True):
                    with get_db() as db:
                        if hapus_upload(db, item.id, tenant_id, user["id"]):
                            st.success("Berkas dihapus.")
                            st.rerun()
        st.divider()
