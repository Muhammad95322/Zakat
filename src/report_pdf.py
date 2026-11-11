"""Generator laporan eksekutif PDF profesional menggunakan fpdf2."""
import io
from datetime import datetime
from fpdf import FPDF
from src.utils import format_rupiah, format_tanggal

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


def generate_pdf_report(
    nama_lembaga: str,
    summary_stats: dict,
    distribution_stats: dict = None,
    rfm_summary: dict = None
) -> bytes:
    """Menghasilkan file PDF ringkasan eksekutif."""
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
    pdf.cell(0, 10, f"Lembaga: {nama_lembaga} | Tanggal Cetak: {format_tanggal(datetime.now())}")
    
    pdf.ln(30)
    pdf.set_text_color(30, 41, 59)
    
    # 2. Ringkasan Eksekutif
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(15, 118, 110)
    pdf.cell(0, 10, "1. Ringkasan Eksekutif", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 6, summary_stats.get("interpretasi", "Belum ada catatan interpretasi."))
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
        pdf.multi_cell(0, 6, salur_text)
        
        for w in distribution_stats.get("warnings", []):
            pdf.set_text_color(180, 83, 9)
            pdf.multi_cell(0, 5, f"- {w}")
            
        pdf.ln(5)
        
    # 5. Catatan Metode & Asumsi
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(15, 118, 110)
    pdf.cell(0, 8, "Catatan Metodologi & Kepatuhan Fikih:", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 116, 139)
    metode_text = (
        "1. Analisis outlier menggunakan metode IQR (Interquartile Range) dengan faktor 3x untuk mendeteksi transaksi bernilai besar.\n"
        "2. Segmentasi muzaki menggunakan kuantil RFM (Recency, Frequency, Monetary) terkalibrasi per periode.\n"
        "3. Laporan ini merupakan instrumen transparansi tata kelola ZIS internal lembaga."
    )
    pdf.multi_cell(0, 4, metode_text)
    
    return bytes(pdf.output())

