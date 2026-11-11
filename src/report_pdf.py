"""Generator laporan eksekutif PDF profesional menggunakan fpdf2."""
import io
from datetime import datetime
from typing import Optional

import pandas as pd
from fpdf import FPDF

from src.forecasting import format_mape, tabel_perbandingan
from src.utils import format_rupiah, format_tanggal


def _aman(teks) -> str:
    """Font inti PDF hanya mendukung Latin-1; ganti karakter lain agar tidak error."""
    return str(teks).replace("\u2014", "-").replace("\u2013", "-").replace("\u2265", ">=").replace(
        "\u2264", "<=").encode("latin-1", "replace").decode("latin-1")


def _sisip_grafik(pdf: FPDF, png: Optional[bytes], judul: str) -> bool:
    if not png:
        return False
    from PIL import Image
    with Image.open(io.BytesIO(png)) as im:
        w_px, h_px = im.size
    lebar = 185.0
    tinggi = lebar * h_px / w_px
    if pdf.get_y() + tinggi > pdf.h - pdf.b_margin:
        pdf.add_page()
    pdf.image(io.BytesIO(png), x=12, w=lebar, alt_text=judul)
    pdf.ln(4)
    return True

class ZakatPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(100, 116, 139)
            self.cell(0, 8, "Zakat Insight - Laporan Analitik ZIS Lembaga", border=0, align="L")
            self.cell(0, 8, f"Hal {self.page_no()}", border=0, align="R", new_x="LMARGIN", new_y="NEXT")
            self.line(10, 18, 200, 18)
            self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, "Dokumen ini dibuat otomatis oleh Zakat Insight | Rahasia & Khusus Lembaga", align="C")


def _bagian_pemilihan_metode(pdf: FPDF, meta: dict) -> None:
    """Tulis metode terpilih, MAPE-nya, dan tabel perbandingan semua kandidat."""
    if pdf.get_y() > pdf.h - 90:
        pdf.add_page()
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(15, 118, 110)
    pdf.cell(0, 8, "Pemilihan Metode Peramalan", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 5, _aman(
        f"Metode terpilih: {meta.get('metode')} | MAPE backtest: {format_mape(meta)}. "
        f"{meta.get('dasar_pemilihan', '')}"
    ), new_x="LMARGIN", new_y="NEXT")
    if meta.get("peringatan_keandalan"):
        pdf.set_text_color(180, 83, 9)
        pdf.multi_cell(0, 5, _aman("PERINGATAN: " + meta["peringatan_keandalan"]), new_x="LMARGIN", new_y="NEXT")
    if meta.get("fallback_alasan"):
        pdf.set_text_color(180, 83, 9)
        pdf.multi_cell(0, 5, _aman("PERINGATAN: " + meta["fallback_alasan"]), new_x="LMARGIN", new_y="NEXT")
    tabel = tabel_perbandingan(meta)
    if not tabel.empty:
        pdf.ln(1)
        pdf.set_text_color(51, 65, 85)
        pdf.set_font("Helvetica", "", 7.5)
        with pdf.table(col_widths=(62, 22, 14, 12, 80), text_align=("LEFT", "RIGHT", "RIGHT", "RIGHT", "LEFT"),
                       line_height=4.2) as t:
            t.row([_aman(c) for c in tabel.columns])
            for _, r in tabel.iterrows():
                t.row([_aman(v) for v in r.tolist()])
    pdf.ln(3)


def generate_pdf_report(
    nama_lembaga: str,
    summary_stats: dict,
    distribution_stats: dict = None,
    rfm_summary: dict = None,
    monthly_df: Optional[pd.DataFrame] = None,
    composition_df: Optional[pd.DataFrame] = None,
    forecast_df: Optional[pd.DataFrame] = None,
    forecast_meta: Optional[dict] = None,
) -> bytes:
    """Menghasilkan file PDF ringkasan eksekutif.

    Parameter grafik (monthly_df, composition_df, forecast_df, forecast_meta)
    opsional; bila diisi, laporan memuat halaman grafik dan catatan metode peramalan.
    """
    pdf = ZakatPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # 1. Halaman Cover / Header
    pdf.set_fill_color(13, 148, 136) # Teal
    pdf.rect(10, 10, 190, 35, "F")
    
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(15, 16)
    pdf.cell(0, 10, "LAPORAN EKSEKUTIF ANALITIK ZIS")
    
    pdf.set_font("Helvetica", "", 12)
    pdf.set_xy(15, 26)
    pdf.cell(0, 10, _aman(f"Lembaga: {nama_lembaga} | Tanggal Cetak: {format_tanggal(datetime.now())}"))
    
    pdf.ln(30)
    pdf.set_text_color(30, 41, 59)
    
    # 2. Ringkasan Eksekutif
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(15, 118, 110)
    pdf.cell(0, 10, "1. Ringkasan Eksekutif", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 6, _aman(summary_stats.get("interpretasi", "Belum ada catatan interpretasi.")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # 3. Tabel Indikator Kinerja Utama (KPI)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(15, 118, 110)
    pdf.cell(0, 10, "2. Indikator Kinerja Utama (KPI)", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(241, 245, 249)
    pdf.cell(95, 8, "Indikator", border=1, fill=True)
    pdf.cell(95, 8, "Nilai Capaian", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    
    kpis = [
        ("Total Penghimpunan", format_rupiah(summary_stats.get("total_dana", 0))),
        ("Total Transaksi", f"{summary_stats.get('total_transaksi', 0):,} transaksi"),
        ("Muzaki Unik Terdaftar", f"{summary_stats.get('muzaki_unik', 0):,} donatur"),
        ("Rata-Rata Donasi per Transaksi", format_rupiah(summary_stats.get("rata_rata", 0))),
        ("Median Donasi", format_rupiah(summary_stats.get("median", 0))),
        ("Donasi Terbesar Tunggal", format_rupiah(summary_stats.get("terbesar", 0))),
    ]
    
    pdf.set_font("Helvetica", "", 10)
    for k, v in kpis:
        pdf.cell(95, 8, k, border=1)
        pdf.cell(95, 8, v, border=1, new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(5)
    
    # 4. Ringkasan Penyaluran & Saldo (Jika ada)
    if distribution_stats and distribution_stats.get("status") == "ready":
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(0, 10, "3. Ringkasan Penyaluran & Kas Dana", new_x="LMARGIN", new_y="NEXT")
        
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(51, 65, 85)
        salur_text = (
            f"Total dana yang disalurkan mencapai {format_rupiah(distribution_stats.get('total_salur', 0))} "
            f"dengan rasio penyaluran sebesar {distribution_stats.get('rasio', 0)}%. "
            f"Estimasi saldo kas belum tersalurkan adalah {format_rupiah(distribution_stats.get('saldo', 0))}."
        )
        pdf.multi_cell(0, 6, _aman(salur_text), new_x="LMARGIN", new_y="NEXT")
        
        for w in distribution_stats.get("warnings", []):
            pdf.set_text_color(180, 83, 9)
            pdf.multi_cell(0, 5, _aman(f"- {w}"), new_x="LMARGIN", new_y="NEXT")
            
        pdf.ln(5)
        
    # 5. Grafik Utama (tren, komposisi, peramalan)
    from src.report_charts import chart_komposisi_png, chart_peramalan_png, chart_tren_png
    grafik = [
        (chart_tren_png(monthly_df) if monthly_df is not None else None, "Tren penghimpunan bulanan"),
        (chart_komposisi_png(composition_df) if composition_df is not None else None, "Komposisi per jenis dana"),
        (chart_peramalan_png(monthly_df, forecast_df) if forecast_df is not None else None, "Proyeksi penghimpunan"),
    ]
    if any(png for png, _ in grafik):
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(0, 10, "Grafik Utama", new_x="LMARGIN", new_y="NEXT")
        for png, judul in grafik:
            _sisip_grafik(pdf, png, judul)
        pdf.set_text_color(30, 41, 59)

    # 6. Pemilihan Metode Peramalan (tabel perbandingan MAPE backtest)
    if forecast_meta and forecast_meta.get("kode_metode"):
        _bagian_pemilihan_metode(pdf, forecast_meta)

    # 7. Catatan Metode & Asumsi
    if pdf.get_y() > pdf.h - 80:
        pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(15, 118, 110)
    pdf.cell(0, 8, "Catatan Metodologi & Kepatuhan Fikih:", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 116, 139)
    metode_text = (
        "1. Analisis outlier menggunakan metode IQR (Interquartile Range) dengan faktor 3x untuk mendeteksi transaksi bernilai besar.\n"
        "2. Segmentasi muzaki menggunakan kuantil RFM (Recency, Frequency, Monetary) terkalibrasi per periode.\n"
        "3. Laporan ini merupakan instrumen transparansi tata kelola ZIS internal lembaga.\n"
        "4. Total dana dihitung dari transaksi yang lolos pembersihan (duplikat persis, nominal nol/negatif/"
        "bukan angka, dan tanggal tidak valid dibuang); outlier tetap dihitung.\n"
        "5. Koefisien Gini dihitung dari total donasi per muzaki (0 = merata, 1 = sangat timpang)."
    )
    if forecast_meta:
        metode_text += (
            f"\n6. Peramalan: metode {forecast_meta.get('metode', '-')}, berdasarkan "
            f"{forecast_meta.get('n_bulan', '-')} bulan data historis. Interval ~95% = proyeksi +/- 1,96 x "
            f"simpangan baku residual model (asumsi galat kira-kira normal dan pola historis berlanjut).\n"
            f"7. Estimasi galat (MAPE backtest): {format_mape(forecast_meta)}. "
            f"{forecast_meta.get('mape_keterangan', '')} {forecast_meta.get('dasar_pemilihan', '')}"
        )
        if forecast_meta.get("peringatan_keandalan"):
            metode_text += f"\n8. PERINGATAN: {forecast_meta.get('peringatan_keandalan')}"
        if forecast_meta.get("fallback"):
            metode_text += f"\n9. PERINGATAN: {forecast_meta.get('fallback_alasan')}"
    pdf.multi_cell(0, 4, _aman(metode_text), new_x="LMARGIN", new_y="NEXT")
    
    return bytes(pdf.output())

