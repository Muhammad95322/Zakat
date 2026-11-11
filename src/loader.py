"""Loader cerdas untuk file Excel dan CSV ZIS dengan toleransi nama kolom."""
import io
import re
from typing import Dict, Any, Tuple, Optional
import pandas as pd

# Kamus sinonim kolom untuk auto-mapping
COLUMN_SYNONYMS = {
    # Penghimpunan
    "tanggal": ["tanggal", "tgl", "date", "waktu", "tgl_transaksi", "trans_date"],
    "id_muzaki": ["id_muzaki", "id_donatur", "muzaki_id", "donatur_id", "no_anggota", "id_anggota"],
    "nama_muzaki": ["nama_muzaki", "nama_donatur", "nama", "donatur", "muzaki", "nama_lengkap"],
    "jenis_dana": ["jenis_dana", "tipe_dana", "dana", "kategori_dana", "jenis_zis", "program_zis"],
    "kanal": ["kanal", "metode", "channel", "kanal_bayar", "metode_bayar", "cara_bayar", "via"],
    "kabupaten_kota": ["kabupaten_kota", "kabupaten", "kota", "wilayah", "daerah", "lokasi", "domisili"],
    "kampanye": ["kampanye", "program_kampanye", "campaign", "kegiatan", "nama_kampanye"],
    "jumlah": ["jumlah", "nominal", "amount", "total", "nilai", "besar_donasi", "uang"],
    
    # Penyaluran
    "program": ["program", "bidang_program", "pilar", "pilar_program", "sektor"],
    "asnaf": ["asnaf", "golongan", "kategori_asnaf", "mustahik_asnaf"],
    "jenis_dana_sumber": ["jenis_dana_sumber", "sumber_dana", "dana_sumber", "asal_dana"],
    "jumlah_penerima": ["jumlah_penerima", "penerima_manfaat", "total_penerima", "kuota_penerima", "jiwa"]
}

def _normalisasi_string(s: str) -> str:
    """Normalisasi string nama kolom untuk pencocokan."""
    return re.sub(r"[^a-zA-Z0-9]", "_", str(s).strip().lower())

def deteksi_kolom(df: pd.DataFrame, expected_cols: list) -> Tuple[Dict[str, str], list]:
    """Mencocokkan nama kolom DataFrame dengan kolom standar.
    
    Returns:
        (mapping: {nama_kolom_asli: nama_kolom_standar}, missing_cols: [kolom_standar_yg_hilang])
    """
    mapping = {}
    matched_standards = set()
    
    normalized_actual = {_normalisasi_string(col): col for col in df.columns}
    
    for standard_col in expected_cols:
        synonyms = COLUMN_SYNONYMS.get(standard_col, [standard_col])
        found = False
        for syn in synonyms:
            syn_norm = _normalisasi_string(syn)
            if syn_norm in normalized_actual:
                actual_col = normalized_actual[syn_norm]
                mapping[actual_col] = standard_col
                matched_standards.add(standard_col)
                found = True
                break
                
    missing = [c for c in expected_cols if c not in matched_standards]
    return mapping, missing


def load_file(file_content: bytes, filename: str) -> Dict[str, pd.DataFrame]:
    """Membaca file Excel atau CSV dan mengembalikan dict of DataFrames.
    
    Returns:
        dict: {"Penghimpunan": df_himpun, "Penyaluran": df_salur (optional)}
    """
    fn = filename.lower()
    res = {}
    
    if fn.endswith(".csv"):
        # Coba encoding utf-8 dan latin-1
        try:
            df = pd.read_csv(io.BytesIO(file_content), encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(file_content), encoding="latin-1")
        res["Penghimpunan"] = df
    else:
        # Excel (.xlsx / .xls)
        excel_file = pd.ExcelFile(io.BytesIO(file_content))
        sheet_names = excel_file.sheet_names
        
        # Cari sheet yang cocok
        himpun_sheet = None
        salur_sheet = None
        
        for name in sheet_names:
            norm_name = name.lower()
            if any(k in norm_name for k in ["himpun", "masuk", "donasi", "terima", "collection", "inflow"]):
                himpun_sheet = name
            elif any(k in norm_name for k in ["salur", "keluar", "mustahik", "distribusi", "outflow"]):
                salur_sheet = name
                
        if himpun_sheet:
            res["Penghimpunan"] = pd.read_excel(excel_file, sheet_name=himpun_sheet)
        else:
            # Gunakan sheet pertama sebagai Penghimpunan
            res["Penghimpunan"] = pd.read_excel(excel_file, sheet_name=sheet_names[0])
            
        if salur_sheet:
            res["Penyaluran"] = pd.read_excel(excel_file, sheet_name=salur_sheet)
        elif len(sheet_names) > 1 and sheet_names[1] != himpun_sheet:
            res["Penyaluran"] = pd.read_excel(excel_file, sheet_name=sheet_names[1])
            
    return res

