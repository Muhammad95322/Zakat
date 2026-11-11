"""Modul pembersihan otomatis data ZIS dengan laporan transparan dan deteksi outlier."""
import re
from datetime import datetime, date
from typing import Dict, Any, Tuple, List, Optional
import pandas as pd
import numpy as np

from src.utils import parse_angka_indonesia
from src.loader import deteksi_kolom

STANDAR_JENIS_DANA = {
    "fitrah": "Zakat Fitrah",
    "zakat fitrah": "Zakat Fitrah",
    "maal": "Zakat Maal",
    "mal": "Zakat Maal",
    "zakat maal": "Zakat Maal",
    "zakat mal": "Zakat Maal",
    "profesi": "Zakat Profesi",
    "zakat profesi": "Zakat Profesi",
    "penghasilan": "Zakat Profesi",
    "infak": "Infak",
    "infaq": "Infak",
    "sedekah": "Sedekah",
    "shodaqoh": "Sedekah",
    "wakaf": "Wakaf",
    "waqaf": "Wakaf",
    "dska": "Dana Sosial Keagamaan Lainnya",
    "dsakl": "Dana Sosial Keagamaan Lainnya"
}

STANDAR_KANAL = {
    "transfer": "Transfer Bank",
    "bank": "Transfer Bank",
    "transfer bank": "Transfer Bank",
    "tunai": "Tunai",
    "cash": "Tunai",
    "qris": "QRIS",
    "kantor": "Kantor Layanan",
    "kantor layanan": "Kantor Layanan",
    "online": "Mitra/Online",
    "mitra": "Mitra/Online"
}

def parse_tanggal_fleksibel(val: Any) -> Optional[datetime]:
    """Parse berbagai format tanggal fleksibel."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.to_pydatetime()
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
        
    s = str(val).strip()
    if not s:
        return None
        
    # Format ISO atau yyyy-mm-dd
    for fmt in [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d",
        "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"
    ]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
            
    # Coba dateutil jika ada
    try:
        import dateutil.parser
        return dateutil.parser.parse(s)
    except Exception:
        return None


def clean_data(df: pd.DataFrame, sheet_type: str = "Penghimpunan") -> Tuple[pd.DataFrame, List[Dict[str, Any]], Dict[str, Any]]:
    """Membersihkan DataFrame data transaksi ZIS.
    
    Returns:
        (df_clean, cleaning_log, summary_dict)
    """
    awal_count = len(df)
    cleaning_log = []
    
    # 1. Pemetaan Kolom
    if sheet_type == "Penghimpunan":
        expected = ["tanggal", "id_muzaki", "nama_muzaki", "jenis_dana", "kanal", "kabupaten_kota", "jumlah"]
    else:
        expected = ["tanggal", "program", "asnaf", "jenis_dana_sumber", "kabupaten_kota", "jumlah_penerima", "jumlah"]
        
    col_map, missing = deteksi_kolom(df, expected)
    df_mapped = df.rename(columns=col_map).copy()
    
    # 2. Hapus duplikat persis
    duplikat_mask = df_mapped.duplicated()
    duplikat_count = int(duplikat_mask.sum())
    if duplikat_count > 0:
        cleaning_log.append({
            "aksi": "Hapus Duplikat",
            "jumlah_baris": duplikat_count,
            "keterangan": f"Dihapus {duplikat_count} baris transaksi yang persis sama di semua kolom."
        })
    df_clean = df_mapped[~duplikat_mask].copy().reset_index(drop=True)
    
    # 3. Normalisasi Kolom 'jumlah'
    if "jumlah" in df_clean.columns:
        parsed_jumlah = df_clean["jumlah"].apply(parse_angka_indonesia)
        invalid_jumlah = parsed_jumlah.isna() | (parsed_jumlah <= 0)
        invalid_count = int(invalid_jumlah.sum())
        
        if invalid_count > 0:
            cleaning_log.append({
                "aksi": "Hapus Nilai Nol / Negatif / Invalid",
                "jumlah_baris": invalid_count,
                "keterangan": f"Dihapus {invalid_count} baris dengan nominal donasi Rp 0, bernilai negatif, atau bukan angka."
            })
            df_clean = df_clean[~invalid_jumlah].copy().reset_index(drop=True)
            df_clean["jumlah"] = parsed_jumlah[~invalid_jumlah].astype(float).to_numpy()
        else:
            df_clean["jumlah"] = parsed_jumlah.astype(float)
            
    # 4. Normalisasi Kolom 'tanggal'
    if "tanggal" in df_clean.columns:
        parsed_dates = df_clean["tanggal"].apply(parse_tanggal_fleksibel)
        invalid_date = parsed_dates.isna()
        invalid_date_count = int(invalid_date.sum())
        
        if invalid_date_count > 0:
            cleaning_log.append({
                "aksi": "Hapus Tanggal Tidak Valid",
                "jumlah_baris": invalid_date_count,
                "keterangan": f"Dihapus {invalid_date_count} baris yang tidak memiliki tanggal transaksi valid."
            })
            df_clean = df_clean[~invalid_date].copy().reset_index(drop=True)
            df_clean["tanggal"] = pd.to_datetime(parsed_dates[~invalid_date]).to_numpy()
        else:
            df_clean["tanggal"] = pd.to_datetime(parsed_dates)
            
    # 5. Normalisasi Kategori (jenis_dana & kanal)
    if "jenis_dana" in df_clean.columns:
        def _clean_jenis(val):
            s = str(val).strip().lower()
            return STANDAR_JENIS_DANA.get(s, str(val).strip().title())
        df_clean["jenis_dana"] = df_clean["jenis_dana"].apply(_clean_jenis)
        
    if "kanal" in df_clean.columns:
        def _clean_kanal(val):
            s = str(val).strip().lower()
            return STANDAR_KANAL.get(s, str(val).strip().title())
        df_clean["kanal"] = df_clean["kanal"].apply(_clean_kanal)

    # 6. Tangani missing string
    str_cols = df_clean.select_dtypes(include=["object"]).columns
    for c in str_cols:
        df_clean[c] = df_clean[c].fillna("Tidak Diketahui").astype(str).str.strip()
        df_clean.loc[df_clean[c] == "", c] = "Tidak Diketahui"
        
    # 7. Deteksi Outlier (IQR)
    outlier_count = 0
    df_clean["is_outlier"] = False
    if "jumlah" in df_clean.columns and len(df_clean) >= 10:
        q1 = df_clean["jumlah"].quantile(0.25)
        q3 = df_clean["jumlah"].quantile(0.75)
        iqr = q3 - q1
        upper_limit = q3 + (3 * iqr)
        outlier_mask = df_clean["jumlah"] > upper_limit
        outlier_count = int(outlier_mask.sum())
        df_clean["is_outlier"] = outlier_mask
        if outlier_count > 0:
            cleaning_log.append({
                "aksi": "Deteksi Outlier",
                "jumlah_baris": outlier_count,
                "keterangan": f"Ditemukan {outlier_count} donasi bernilai sangat besar (> Rp {int(upper_limit):,}). Data tetap disimpan untuk analisis komprehensif."
            })
            
    akhir_count = len(df_clean)
    dibuang_count = awal_count - akhir_count
    persen_dibuang = round((dibuang_count / awal_count * 100), 2) if awal_count > 0 else 0
    
    summary = {
        "awal": awal_count,
        "akhir": akhir_count,
        "dibuang": dibuang_count,
        "persen_dibuang": persen_dibuang,
        "duplikat": duplikat_count,
        "outlier": outlier_count
    }
    
    return df_clean, cleaning_log, summary

