"""Halaman Analisis Interaktif ZIS Komprehensif dengan Visualisasi dan Ekspor."""
import logging
import os
import streamlit as st
import pandas as pd
from pathlib import Path

from src.database import get_db
from src.auth.session import get_tenant_id, get_current_user
from src.services.upload_service import get_upload, get_uploads
from src.services.tenant_service import get_tenant
from src.loader import DataFileError
from src.pipeline import siapkan_data
from src.analysis import (
    get_summary_stats, get_trend_analysis, get_composition_analysis,
    get_distribution_analysis, get_statistical_tests
)
from src.rfm import segment_rfm
from src.forecasting import forecast_donations, format_mape, tabel_perbandingan
from src.charts import (
    chart_trend_bulanan, chart_komposisi_donut, chart_bar_wilayah,
    chart_lorenz, chart_forecasting
)
from src.report_excel import generate_excel_report
from src.report_pdf import generate_pdf_report
from src.utils import format_rupiah, format_tanggal

logger = logging.getLogger(__name__)


def show():
    tenant_id = get_tenant_id()
    if not tenant_id:
        st.warning("Silakan pilih lembaga terlebih dahulu.")
        return
        
    with get_db() as db:
        tenant = get_tenant(db, tenant_id)
        uploads = get_uploads(db, tenant_id)
        
    if not uploads:
        st.info("Belum ada data transaksi yang diunggah. Silakan buka menu 'Upload Data' untuk mengunggah file atau memuat data contoh.")
        if st.button("📁 Buka Menu Upload"):
            st.session_state["page"] = "upload"
            st.rerun()
        return
        
    # Pilih file yang dianalisis
    upload_options = {u.id: f"{u.nama_file_asli} ({u.created_at.strftime('%d/%m/%Y')})" for u in uploads}
    default_id = st.session_state.get("selected_upload_id", uploads[0].id)
    if default_id not in upload_options:
        default_id = uploads[0].id
        
    c_sel, _ = st.columns([2, 1])
    with c_sel:
        selected_id = st.selectbox(
            "Pilih Berkas Transaksi:",
            options=list(upload_options.keys()),
            format_func=lambda x: upload_options[x],
            index=list(upload_options.keys()).index(default_id)
        )
    st.session_state["selected_upload_id"] = selected_id
    
    # Ambil file
    with get_db() as db:
        upload_record = get_upload(db, selected_id, tenant_id)
        
    if not upload_record or not os.path.exists(upload_record.storage_path):
        st.error("File fisik tidak ditemukan pada media penyimpanan.")
        return
        
    with open(upload_record.storage_path, "rb") as f:
        file_bytes = f.read()
        
    # Muat, validasi, dan bersihkan data; tampilkan pesan ramah jika berkas bermasalah
    try:
        hasil = siapkan_data(file_bytes, upload_record.nama_file_asli)
    except DataFileError as e:
        st.error(f"❌ Berkas tidak dapat dianalisis. {e}")
        return
    except Exception as e:  # jangan tampilkan stack trace ke pengguna
        logger.exception("Gagal memproses berkas %s", upload_record.nama_file_asli)
        st.error(
            "❌ Terjadi kesalahan tak terduga saat memproses berkas. "
            "Pastikan berkas sesuai template, lalu coba lagi."
        )
        return
    df_himpun_clean = hasil["df_himpun"]
    log_himpun = hasil["log_himpun"]
    summary_clean = hasil["summary_himpun"]
    df_salur_clean = hasil["df_salur"]
    log_salur = hasil["log_salur"]
    
    # Sidebar Filters Global
    st.sidebar.markdown("### 🔍 Filter Analisis")
    
    # Filter Wilayah
    wilayah_list = ["Semua"] + sorted(df_himpun_clean["kabupaten_kota"].dropna().unique().tolist()) if "kabupaten_kota" in df_himpun_clean.columns else ["Semua"]
    pilih_wilayah = st.sidebar.selectbox("Kabupaten / Kota:", wilayah_list)
    
    # Filter Jenis Dana
    dana_list = ["Semua"] + sorted(df_himpun_clean["jenis_dana"].dropna().unique().tolist()) if "jenis_dana" in df_himpun_clean.columns else ["Semua"]
    pilih_dana = st.sidebar.selectbox("Jenis Dana:", dana_list)
    
    # Filter Kanal
    kanal_list = ["Semua"] + sorted(df_himpun_clean["kanal"].dropna().unique().tolist()) if "kanal" in df_himpun_clean.columns else ["Semua"]
    pilih_kanal = st.sidebar.selectbox("Kanal Donasi:", kanal_list)
    
    # Terapkan filter ke DataFrame analisis
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

    # Navigasi Tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Ringkasan & KPI",
        "📈 Tren & Musiman",
        "🥧 Komposisi",
        "👥 Analisis Muzaki (RFM)",
        "🤝 Penyaluran Dana",
        "🔮 Proyeksi & Prediksi",
        "📑 Laporan & Ekspor"
    ])

    # TAB 1: Ringkasan & KPI
    with tab1:
        st.markdown(f"## Ringkasan Kinerja Lembaga: {tenant.nama if tenant else ''}")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Penghimpunan", format_rupiah(stats["total_dana"], singkat=True))
        c2.metric("Total Transaksi", f"{stats['total_transaksi']:,}")
        c3.metric("Muzaki Terdaftar", f"{stats['muzaki_unik']:,}")
        c4.metric("Rata-Rata Donasi", format_rupiah(stats["rata_rata"], singkat=True))
        
        st.info(f"💡 **Interpretasi Hasil:** {stats['interpretasi']}")
        
        if not trend["monthly"].empty:
            st.plotly_chart(chart_trend_bulanan(trend["monthly"]), use_container_width=True, key="chart_analisis_1")
            
        # Kualitas Data Box
        with st.expander("🔍 Laporan Kualitas Data Hasil Pembersihan"):
            st.write(f"- Baris Awal: **{summary_clean['awal']:,}** | Baris Bersih: **{summary_clean['akhir']:,}**")
            st.write(f"- Duplikat Dihapus: **{summary_clean['duplikat']:,}** | Donasi Outlier: **{summary_clean['outlier']:,}**")
            if log_himpun:
                st.dataframe(pd.DataFrame(log_himpun), use_container_width=True)

    # TAB 2: Tren & Musiman
    with tab2:
        st.markdown("### Analisis Tren Waktu & Pola Musiman")
        st.info(f"📅 {trend['interpretasi']}")
        if not trend["monthly"].empty:
            st.plotly_chart(chart_trend_bulanan(trend["monthly"]), use_container_width=True, key="chart_analisis_2")
            st.dataframe(trend["monthly"].rename(columns={
                "periode_str": "Bulan", "total_dana": "Total Dana (Rp)",
                "jumlah_transaksi": "Transaksi", "mom_growth": "Pertumbuhan MoM (%)"
            }), use_container_width=True)

    # TAB 3: Komposisi
    with tab3:
        st.markdown("### Komposisi Donasi Berdasarkan Dimensi")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if "jenis_dana" in comp:
                st.plotly_chart(chart_komposisi_donut(comp["jenis_dana"], "jenis_dana", "Sebaran Jenis Dana ZIS"), use_container_width=True, key="chart_analisis_3")
        with col_d2:
            if "kanal" in comp:
                st.plotly_chart(chart_komposisi_donut(comp["kanal"], "kanal", "Kanal Metode Pembayaran"), use_container_width=True, key="chart_analisis_4")
                
        if "kabupaten_kota" in comp:
            st.plotly_chart(chart_bar_wilayah(comp["kabupaten_kota"]), use_container_width=True, key="chart_analisis_5")
            
        if "penjelasan" in stat_test:
            st.caption(f"🧪 **Uji Signifikansi Statistik:** {stat_test['penjelasan']}")

    # TAB 4: Muzaki & RFM
    with tab4:
        st.markdown("### Segmentasi Perilaku Donatur (RFM) & Pemerataan Dana")
        if not rfm_df.empty:
            st.info(f"⚖️ {rfm_meta.get('interpretasi_gini', '')}")
            
            c_rfm1, c_rfm2 = st.columns([1, 1])
            with c_rfm1:
                seg_counts = pd.DataFrame(list(rfm_meta["segmen_counts"].items()), columns=["Segmen", "Jumlah Muzaki"])
                st.dataframe(seg_counts, use_container_width=True)
            with c_rfm2:
                st.plotly_chart(chart_lorenz(rfm_meta["lorenz_x"], rfm_meta["lorenz_y"], rfm_meta["gini_index"]), use_container_width=True, key="chart_analisis_6")
                
            st.markdown("#### Daftar Donatur & Kategori")
            st.dataframe(rfm_df[["nama", "terakhir_donasi", "frequency", "monetary", "segmen"]].rename(columns={
                "nama": "Nama Muzaki", "terakhir_donasi": "Terakhir Donasi",
                "frequency": "Frekuensi", "monetary": "Total Donasi (Rp)", "segmen": "Kategori Segmen"
            }), use_container_width=True)

    # TAB 5: Penyaluran Dana
    with tab5:
        st.markdown("### Tata Kelola Penyaluran & Kas Dana")
        if dist_stats.get("status") == "ready":
            c_s1, c_s2, c_s3 = st.columns(3)
            c_s1.metric("Dana Tersalurkan", format_rupiah(dist_stats["total_salur"], singkat=True))
            c_s2.metric("Rasio Penyaluran", f"{dist_stats['rasio']}%")
            c_s3.metric("Estimasi Saldo Kas", format_rupiah(dist_stats["saldo"], singkat=True))
            
            for w in dist_stats.get("warnings", []):
                st.warning(w)
                
            if not dist_stats["program_breakdown"].empty:
                st.markdown("#### Alokasi per Program Penyaluran")
                st.dataframe(dist_stats["program_breakdown"].rename(columns={
                    "program": "Program", "total_dana": "Total Dana (Rp)", "penerima": "Penerima Manfaat"
                }), use_container_width=True)
        else:
            st.info(dist_stats.get("pesan", "Data penyaluran belum diunggah."))

    # TAB 6: Proyeksi & Prediksi
    with tab6:
        st.markdown("### Proyeksi Penerimaan 12 Bulan ke Depan")
        st.caption(f"Metode: **{forecast_meta.get('metode')}** | Estimasi Galat (MAPE backtest): **{format_mape(forecast_meta)}**")
        if forecast_meta.get("peringatan_keandalan"):
            st.warning(f"⚠️ {forecast_meta['peringatan_keandalan']}")
        if forecast_meta.get("fallback"):
            st.warning(f"⚠️ {forecast_meta.get('fallback_alasan')}")
        if forecast_meta.get("mape_keterangan"):
            st.caption(forecast_meta["mape_keterangan"])
        if forecast_meta.get("dasar_pemilihan"):
            st.caption(f"Dasar pemilihan: {forecast_meta['dasar_pemilihan']}")
        tabel_metode = tabel_perbandingan(forecast_meta)
        if not tabel_metode.empty:
            with st.expander("📊 Perbandingan MAPE backtest semua metode", expanded=True):
                st.dataframe(tabel_metode, use_container_width=True, hide_index=True)
        catatan_lain = [c for c in forecast_meta.get("warning", "").split("PERINGATAN: ")[0:1] if c.strip()]
        if catatan_lain:
            st.info(catatan_lain[0].strip())
            
        if not forecast_df.empty:
            st.plotly_chart(chart_forecasting(trend["monthly"], forecast_df), use_container_width=True, key="chart_analisis_7")
            st.dataframe(forecast_df.rename(columns={
                "periode": "Bulan", "proyeksi": "Proyeksi Donasi (Rp)",
                "batas_bawah": "Batas Bawah (Rp)", "batas_atas": "Batas Atas (Rp)"
            }), use_container_width=True)

    # TAB 7: Laporan & Ekspor
    with tab7:
        st.markdown("### 📥 Unduh Laporan Resmi")
        st.write("Unduh laporan siap presentasi untuk pimpinan, dewan pengawas syariah, atau donatur lembaga:")
        
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
            )
            st.download_button(
                "📑 Unduh Laporan Eksekutif PDF",
                data=pdf_bytes,
                file_name=f"Laporan_Eksekutif_ZIS_{tenant.slug if tenant else 'zakat'}.pdf",
                mime="application/pdf",
                type="primary",
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
            )
            st.download_button(
                "📊 Unduh Laporan Lengkap Excel",
                data=excel_bytes,
                file_name=f"Data_Analitik_ZIS_{tenant.slug if tenant else 'zakat'}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

