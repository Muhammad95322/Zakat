"""Halaman Analisis Interaktif ZIS Komprehensif dengan Visualisasi dan Ekspor."""
import logging
import os
import re
import streamlit as st
import pandas as pd
from pathlib import Path

from src.database import get_db
from src.auth.session import get_tenant_id, get_current_user
from src.services.upload_service import get_upload, get_uploads
from src.services.tenant_service import get_tenant
from src.loader import DataFileError
from src.pipeline import siapkan_data
from src.components.kualitas import tampilkan_kualitas
from src.services.pemetaan_service import daftar_pemetaan
from src.analysis import (
    get_summary_stats, get_trend_analysis, get_composition_analysis,
    get_distribution_analysis, get_statistical_tests
)
from src.rfm import segment_rfm
from src.forecasting import (
    forecast_donations, format_mape_lengkap, ringkasan_catatan_metode, ringkasan_koreksi_bias,
    tabel_bias_koreksi, tabel_perbandingan,
)
from src.charts import (
    chart_trend_bulanan, chart_komposisi_donut, chart_bar_wilayah,
    chart_lorenz, chart_forecasting
)
from src.report_excel import generate_excel_report
from src.report_pdf import generate_pdf_report
from src.utils import format_rupiah, format_tanggal
from src.components.tema import angka_id, judul_bagian, judul_halaman

logger = logging.getLogger(__name__)


def show():
    tenant_id = get_tenant_id()
    if not tenant_id:
        st.warning("Pilih lembaga terlebih dahulu.")
        return
        
    with get_db() as db:
        tenant = get_tenant(db, tenant_id)
        uploads = get_uploads(db, tenant_id)
        
    if not uploads:
        judul_halaman("Analisis & laporan")
        st.info("Belum ada data untuk dianalisis. Unggah berkas transaksi atau muat data contoh.")
        if st.button("Unggah berkas", type="primary", icon=":material/upload_file:"):
            st.session_state["page"] = "upload"
            st.rerun()
        return
        
    judul_halaman("Analisis & laporan", tenant.nama if tenant else "")

    # Pilih berkas + filter (semua di bagian atas halaman)
    upload_options = {u.id: f"{u.nama_file_asli} ({u.created_at.strftime('%d/%m/%Y')})" for u in uploads}
    default_id = st.session_state.get("selected_upload_id", uploads[0].id)
    if default_id not in upload_options:
        default_id = uploads[0].id

    c_sel, c_f1, c_f2, c_f3 = st.columns([2.2, 1.2, 1.2, 1.2])
    with c_sel:
        selected_id = st.selectbox(
            "Berkas transaksi",
            options=list(upload_options.keys()),
            format_func=lambda x: upload_options[x],
            index=list(upload_options.keys()).index(default_id)
        )
    st.session_state["selected_upload_id"] = selected_id

    # Ambil file
    with get_db() as db:
        upload_record = get_upload(db, selected_id, tenant_id)
        pemetaan_lembaga = daftar_pemetaan(db, tenant_id)
        
    from src.services.upload_service import baca_berkas_unggahan
    try:
        file_bytes = baca_berkas_unggahan(upload_record) if upload_record else None
    except FileNotFoundError:
        file_bytes = None
    except Exception:
        logger.exception("Gagal membaca berkas dari penyimpanan")
        st.error("Penyimpanan berkas sedang tidak dapat diakses. Coba lagi beberapa saat lagi.")
        return
    if file_bytes is None:
        st.error("File fisik tidak ditemukan pada media penyimpanan.")
        return
        
    # Muat, validasi, dan bersihkan data; tampilkan pesan ramah jika berkas bermasalah
    try:
        hasil = siapkan_data(file_bytes, upload_record.nama_file_asli, pemetaan_lembaga=pemetaan_lembaga)
    except DataFileError as e:
        st.error(f"Berkas tidak dapat dianalisis. {e}")
        return
    except Exception as e:  # jangan tampilkan stack trace ke pengguna
        logger.exception("Gagal memproses berkas %s", upload_record.nama_file_asli)
        st.error(
            "Terjadi kesalahan tak terduga saat memproses berkas. "
            "Pastikan berkas sesuai template, lalu coba lagi."
        )
        return
    df_himpun_clean = hasil["df_himpun"]
    log_himpun = hasil["log_himpun"]
    summary_clean = hasil["summary_himpun"]
    df_salur_clean = hasil["df_salur"]
    log_salur = hasil["log_salur"]
    kualitas = hasil["kualitas"]
    tampilkan_kualitas(kualitas, terbuka=bool(kualitas.get("peringatan")))
    
    # Filter global (di atas, sejajar dengan pemilih berkas)
    def _opsi(kolom):
        return ["Semua"] + sorted(df_himpun_clean[kolom].dropna().unique().tolist()) if kolom in df_himpun_clean.columns else ["Semua"]

    with c_f1:
        pilih_wilayah = st.selectbox("Kabupaten / kota", _opsi("kabupaten_kota"))
    with c_f2:
        pilih_dana = st.selectbox("Jenis dana", _opsi("jenis_dana"))
    with c_f3:
        pilih_kanal = st.selectbox("Kanal", _opsi("kanal"))

    df_filtered = df_himpun_clean.copy()
    if pilih_wilayah != "Semua":
        df_filtered = df_filtered[df_filtered["kabupaten_kota"] == pilih_wilayah]
    if pilih_dana != "Semua":
        df_filtered = df_filtered[df_filtered["jenis_dana"] == pilih_dana]
    if pilih_kanal != "Semua":
        df_filtered = df_filtered[df_filtered["kanal"] == pilih_kanal]

    # Kalkulasi Metrik
    stats = get_summary_stats(df_filtered)
    trend = get_trend_analysis(df_filtered)
    comp = get_composition_analysis(df_filtered)
    dist_stats = get_distribution_analysis(df_filtered, df_salur_clean)
    stat_test = get_statistical_tests(df_filtered)
    rfm_df, rfm_meta = segment_rfm(df_filtered)
    forecast_df, forecast_meta = forecast_donations(trend.get("monthly", pd.DataFrame()), 12)

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Ringkasan", "Tren", "Komposisi", "Muzaki", "Penyaluran", "Proyeksi", "Laporan"
    ])

    # RINGKASAN
    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total penghimpunan", format_rupiah(stats["total_dana"], singkat=True))
        c2.metric("Transaksi", angka_id(stats["total_transaksi"]))
        c3.metric("Muzaki", angka_id(stats["muzaki_unik"]))
        c4.metric("Rata-rata per donasi", format_rupiah(stats["rata_rata"], singkat=True))

        st.info(stats["interpretasi"])

        if not trend["monthly"].empty:
            st.plotly_chart(chart_trend_bulanan(trend["monthly"]), use_container_width=True, key="chart_analisis_1")

        with st.expander("Hasil pembersihan data"):
            st.write(f"Baris awal **{angka_id(summary_clean['awal'])}**, baris bersih **{angka_id(summary_clean['akhir'])}**. "
                     f"Duplikat dihapus **{angka_id(summary_clean['duplikat'])}**, donasi outlier **{angka_id(summary_clean['outlier'])}**.")
            if log_himpun:
                st.dataframe(pd.DataFrame(log_himpun), use_container_width=True)

    # TREN
    with tab2:
        judul_bagian("Tren dan pola musiman")
        st.info(trend["interpretasi"])
        if not trend["monthly"].empty:
            st.plotly_chart(chart_trend_bulanan(trend["monthly"]), use_container_width=True, key="chart_analisis_2")
            st.dataframe(trend["monthly"].rename(columns={
                "periode_str": "Bulan", "total_dana": "Total dana (Rp)",
                "jumlah_transaksi": "Transaksi", "mom_growth": "Pertumbuhan bulanan (%)"
            }), use_container_width=True, hide_index=True)

    # KOMPOSISI
    with tab3:
        judul_bagian("Dari mana dana berasal", "Sebaran dana menurut jenis, kanal, dan wilayah.")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if "jenis_dana" in comp:
                st.plotly_chart(chart_komposisi_donut(comp["jenis_dana"], "jenis_dana", "Jenis dana"), use_container_width=True, key="chart_analisis_3")
        with col_d2:
            if "kanal" in comp:
                st.plotly_chart(chart_komposisi_donut(comp["kanal"], "kanal", "Kanal pembayaran"), use_container_width=True, key="chart_analisis_4")

        if "kabupaten_kota" in comp:
            st.plotly_chart(chart_bar_wilayah(comp["kabupaten_kota"]), use_container_width=True, key="chart_analisis_5")

        if "penjelasan" in stat_test:
            st.caption(f"Uji signifikansi statistik: {stat_test['penjelasan']}")

    # MUZAKI
    with tab4:
        judul_bagian("Segmen donatur", "Pengelompokan muzaki menurut kebaruan, frekuensi, dan nilai donasi (RFM).")
        if rfm_df.empty:
            st.info("Data belum cukup untuk mengelompokkan muzaki.")
        else:
            st.info(rfm_meta.get("interpretasi_gini", ""))

            c_rfm1, c_rfm2 = st.columns([1, 1])
            with c_rfm1:
                seg_counts = pd.DataFrame(list(rfm_meta["segmen_counts"].items()), columns=["Segmen", "Jumlah muzaki"])
                st.dataframe(seg_counts, use_container_width=True, hide_index=True)
            with c_rfm2:
                st.plotly_chart(chart_lorenz(rfm_meta["lorenz_x"], rfm_meta["lorenz_y"], rfm_meta["gini_index"]), use_container_width=True, key="chart_analisis_6")

            judul_bagian("Daftar muzaki")
            st.dataframe(rfm_df[["nama", "terakhir_donasi", "frequency", "monetary", "segmen"]].rename(columns={
                "nama": "Nama muzaki", "terakhir_donasi": "Donasi terakhir",
                "frequency": "Frekuensi", "monetary": "Total donasi (Rp)", "segmen": "Segmen"
            }), use_container_width=True, hide_index=True)

    # PENYALURAN
    with tab5:
        judul_bagian("Penyaluran dan kas dana")
        if dist_stats.get("status") == "ready":
            c_s1, c_s2, c_s3 = st.columns(3)
            c_s1.metric("Dana tersalurkan", format_rupiah(dist_stats["total_salur"], singkat=True))
            c_s2.metric("Rasio penyaluran", f"{str(dist_stats['rasio']).replace('.', ',')}%")
            c_s3.metric("Perkiraan saldo kas", format_rupiah(dist_stats["saldo"], singkat=True))

            for w in dist_stats.get("warnings", []):
                st.warning(w)

            if not dist_stats["program_breakdown"].empty:
                judul_bagian("Alokasi per program")
                st.dataframe(dist_stats["program_breakdown"].rename(columns={
                    "program": "Program", "total_dana": "Total dana (Rp)", "penerima": "Penerima manfaat"
                }), use_container_width=True, hide_index=True)
        else:
            st.info(dist_stats.get("pesan", "Data penyaluran belum diunggah."))

    # PROYEKSI
    with tab6:
        judul_bagian("Proyeksi 12 bulan ke depan",
                     "Perkiraan penerimaan berdasarkan pola historis. Pakai sebagai gambaran, bukan target.")
        mape_teks = format_mape_lengkap(forecast_meta)
        nilai_mape, _, rincian_mape = mape_teks.partition(" (")
        m1, m2 = st.columns([1, 2])
        m1.metric("Perkiraan galat (MAPE)", nilai_mape.replace(".", ","))
        m2.markdown(
            f"<div class='zi-meta' style='padding-top:1.1rem'>Metode: <b>{forecast_meta.get('metode')}</b>. "
            "MAPE dihitung dari uji mundur bergulir: makin kecil, makin dekat proyeksi dengan kenyataan."
            + (f"<br>Rincian: {rincian_mape.rstrip(')').replace('.', ',')}." if rincian_mape else "") + "</div>",
            unsafe_allow_html=True)
        if forecast_meta.get("peringatan_keandalan"):
            st.warning(forecast_meta["peringatan_keandalan"])
        if forecast_meta.get("fallback"):
            st.warning(forecast_meta.get("fallback_alasan"))
        konsistensi = (forecast_meta.get("konsistensi_selang") or {}).get("peringatan")
        if konsistensi:
            st.warning(konsistensi)

        if not forecast_df.empty:
            st.plotly_chart(chart_forecasting(trend["monthly"], forecast_df, forecast_meta.get("selang_label"),
                                              (forecast_meta.get("koreksi_bias") or {}).get("dipakai", False)),
                            use_container_width=True, key="chart_analisis_7")
            if forecast_meta.get("selang_keterangan"):
                st.caption(forecast_meta["selang_keterangan"])
            st.dataframe(forecast_df.rename(columns={
                "periode": "Bulan", "proyeksi": "Proyeksi donasi (Rp)",
                "batas_bawah": "Batas bawah (Rp)", "batas_atas": "Batas atas (Rp)",
                "status_selang": "Status selang",
                "proyeksi_tanpa_koreksi": "Proyeksi tanpa koreksi (Rp)",
                "proyeksi_di_dalam_selang": "Proyeksi di dalam selang"
            }), use_container_width=True, hide_index=True)

        # Rincian teknis dikumpulkan di satu tempat agar halaman tetap tenang
        with st.expander("Rincian metode dan catatan"):
            if forecast_meta.get("catatan_stabilitas"):
                st.info(forecast_meta["catatan_stabilitas"])
            if forecast_meta.get("koreksi_bias"):
                st.info(ringkasan_koreksi_bias(forecast_meta))
            if forecast_meta.get("mape_keterangan"):
                st.caption(forecast_meta["mape_keterangan"])
            if forecast_meta.get("dasar_pemilihan"):
                st.caption(f"Dasar pemilihan: {forecast_meta['dasar_pemilihan']}")
            tabel_metode = tabel_perbandingan(forecast_meta, lengkap=True)
            if not tabel_metode.empty:
                st.markdown("**Perbandingan MAPE semua metode**")
                st.dataframe(tabel_metode, use_container_width=True, hide_index=True)
                st.caption(f"Catatan metode: {ringkasan_catatan_metode(forecast_meta)}")
            tabel_bias = tabel_bias_koreksi(forecast_meta)
            if not tabel_bias.empty:
                st.markdown("**Bias uji mundur dan faktor koreksi per bulan**")
                st.dataframe(tabel_bias, use_container_width=True, hide_index=True)
            # Catatan umum = bagian awal warning sebelum PERINGATAN/CATATAN (sudah ditampilkan terpisah)
            catatan_umum = re.split(r"(?:PERINGATAN|CATATAN): ", forecast_meta.get("warning", ""))[0].strip()
            if catatan_umum:
                st.info(catatan_umum)

    # LAPORAN
    with tab7:
        judul_bagian("Unduh laporan", "Siap dibawa ke rapat pimpinan, dewan pengawas syariah, atau donatur.")

        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            pdf_bytes = generate_pdf_report(
                nama_lembaga=tenant.nama if tenant else "Lembaga Zakat",
                summary_stats=stats,
                distribution_stats=dist_stats,
                rfm_summary=rfm_meta,
                monthly_df=trend.get("monthly"),
                composition_df=comp.get("jenis_dana"),
                forecast_df=forecast_df,
                forecast_meta=forecast_meta,
                kualitas=kualitas,
            )
            st.download_button(
                "Unduh laporan eksekutif (PDF)",
                data=pdf_bytes,
                file_name=f"Laporan_Eksekutif_ZIS_{tenant.slug if tenant else 'zakat'}.pdf",
                mime="application/pdf",
                type="primary",
                icon=":material/picture_as_pdf:",
                use_container_width=True
            )

        with col_exp2:
            excel_bytes = generate_excel_report(
                df_clean=df_filtered,
                summary_stats=stats,
                rfm_df=rfm_df,
                forecast_df=forecast_df,
                cleaning_log=log_himpun,
                forecast_meta=forecast_meta,
                kualitas=kualitas,
            )
            st.download_button(
                "Unduh data lengkap (Excel)",
                data=excel_bytes,
                file_name=f"Data_Analitik_ZIS_{tenant.slug if tenant else 'zakat'}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/table_view:",
                use_container_width=True
            )
