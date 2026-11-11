"""Generator ekspor laporan Excel rapi multi-sheet."""
import io
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def generate_excel_report(
    df_clean: pd.DataFrame,
    summary_stats: dict,
    rfm_df: pd.DataFrame = None,
    forecast_df: pd.DataFrame = None,
    cleaning_log: list = None,
    forecast_meta: dict = None,
) -> bytes:
    """Menghasilkan file Excel berformat rapi dan siap didownload."""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Sheet 1: Data Bersih
        df_clean.to_excel(writer, sheet_name="Data Bersih", index=False)
        
        # Sheet 2: Ringkasan KPI
        kpi_rows = [
            {"Metrik": "Total Penghimpunan", "Nilai": summary_stats.get("total_dana", 0)},
            {"Metrik": "Total Transaksi", "Nilai": summary_stats.get("total_transaksi", 0)},
            {"Metrik": "Jumlah Muzaki Unik", "Nilai": summary_stats.get("muzaki_unik", 0)},
            {"Metrik": "Rata-rata Donasi", "Nilai": summary_stats.get("rata_rata", 0)},
            {"Metrik": "Median Donasi", "Nilai": summary_stats.get("median", 0)},
            {"Metrik": "Donasi Terbesar", "Nilai": summary_stats.get("terbesar", 0)},
        ]
        pd.DataFrame(kpi_rows).to_excel(writer, sheet_name="Ringkasan KPI", index=False)
        
        # Sheet 3: Segmentasi RFM (jika ada)
        if rfm_df is not None and not rfm_df.empty:
            rfm_df.to_excel(writer, sheet_name="Segmentasi RFM", index=False)
            
        # Sheet 4: Proyeksi Peramalan (jika ada)
        if forecast_df is not None and not forecast_df.empty:
            forecast_df.to_excel(writer, sheet_name="Proyeksi Dana", index=False)
            
        # Sheet 4b: Perbandingan metode peramalan (jika ada)
        if forecast_meta and forecast_meta.get("perbandingan"):
            from src.forecasting import tabel_perbandingan
            tabel = tabel_perbandingan(forecast_meta, lengkap=True, numerik=True).rename(columns={
                "Rata-rata MAPE": "Rata-rata MAPE (%)", "Median": "Median MAPE (%)",
                "Terburuk": "MAPE Terburuk (%)", "SD": "SD MAPE (poin)",
                "Rata-rata (jendela bersama)": "Rata-rata MAPE jendela bersama (%)",
            })
            tabel.to_excel(writer, sheet_name="Perbandingan Metode", index=False)
            ringkas = pd.DataFrame([
                {"Butir": "Metode terpilih", "Nilai": forecast_meta.get("metode")},
                {"Butir": "Rata-rata MAPE backtest bergulir (%)", "Nilai": forecast_meta.get("mape")},
                {"Butir": "SD MAPE (poin)", "Nilai": forecast_meta.get("mape_std")},
                {"Butir": "MAPE terbaik (%)", "Nilai": forecast_meta.get("mape_terbaik")},
                {"Butir": "MAPE terburuk (%)", "Nilai": forecast_meta.get("mape_terburuk")},
                {"Butir": "Jumlah jendela", "Nilai": forecast_meta.get("n_jendela")},
                {"Butir": "Horizon uji (bulan)", "Nilai": forecast_meta.get("bulan_uji")},
                {"Butir": "Dasar pemilihan", "Nilai": forecast_meta.get("dasar_pemilihan")},
                {"Butir": "Catatan stabilitas", "Nilai": forecast_meta.get("catatan_stabilitas") or "-"},
                {"Butir": "Peringatan keandalan", "Nilai": forecast_meta.get("peringatan_keandalan") or "-"},
            ])
            ringkas.to_excel(writer, sheet_name="Ringkasan Peramalan", index=False)

        # Sheet 5: Log Pembersihan
        if cleaning_log:
            pd.DataFrame(cleaning_log).to_excel(writer, sheet_name="Log Pembersihan", index=False)
            
        # Format styling pada workbook
        wb = writer.book
        header_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
        header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        
        for ws in wb.worksheets:
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
            
            # Auto-fit column widths
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 80)
                
    output.seek(0)
    return output.getvalue()

