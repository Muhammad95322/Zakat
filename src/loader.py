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

# Kolom minimum agar analisis bisa dijalankan
KOLOM_WAJIB = {
    "Penghimpunan": ["tanggal", "jumlah"],
    "Penyaluran": ["tanggal", "jumlah"],
}


class DataFileError(ValueError):
    """Kesalahan isi/format berkas data yang aman ditampilkan ke pengguna."""


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


def validasi_kolom_wajib(df: pd.DataFrame, sheet_type: str = "Penghimpunan") -> None:
    """Pastikan kolom wajib ada (dengan toleransi sinonim).

    Raises:
        DataFileError: berisi daftar kolom yang hilang dan nama yang diterima.
    """
    wajib = KOLOM_WAJIB.get(sheet_type, [])
    _, missing = deteksi_kolom(df, wajib)
    if missing:
        detail = "; ".join(
            f"'{c}' (nama yang diterima: {', '.join(COLUMN_SYNONYMS.get(c, [c]))})" for c in missing
        )
        ada = ", ".join(str(c) for c in df.columns) or "(tidak ada)"
        raise DataFileError(
            f"Sheet {sheet_type} tidak memiliki kolom wajib: {detail}. "
            f"Kolom yang ditemukan: {ada}. Sesuaikan judul kolom atau gunakan template Excel."
        )


def _batas_baris() -> int:
    from src.config import settings
    return settings.MAX_BARIS


def _cek_baris(df: pd.DataFrame, nama: str) -> None:
    if len(df) > _batas_baris():
        raise DataFileError(f"{nama} memiliki lebih dari {_batas_baris():,} baris. Bagi berkas menjadi beberapa bagian.")


def _sheet_kosong(df: pd.DataFrame) -> bool:
    return df is None or df.empty or df.dropna(how="all").empty


def load_file(file_content: bytes, filename: str) -> Dict[str, pd.DataFrame]:
    """Membaca file Excel atau CSV dan mengembalikan dict of DataFrames.

    Returns:
        dict: {"Penghimpunan": df_himpun, "Penyaluran": df_salur (optional)}

    Raises:
        DataFileError: file kosong, rusak, atau sheet penghimpunan kosong.
            Sheet penyaluran yang kosong diabaikan (tidak dikembalikan).
    """
    if not file_content:
        raise DataFileError(f"Berkas '{filename}' kosong (0 byte). Unggah berkas yang berisi data.")

    fn = filename.lower()
    res = {}

    if fn.endswith(".csv"):
        df = None
        for enc in ("utf-8", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(file_content), encoding=enc, nrows=_batas_baris() + 1)
                break
            except UnicodeDecodeError:
                continue
            except pd.errors.EmptyDataError:
                raise DataFileError(f"Berkas CSV '{filename}' kosong: tidak ada judul kolom maupun data.")
            except pd.errors.ParserError as e:
                raise DataFileError(f"Berkas CSV '{filename}' tidak dapat dibaca (format baris tidak konsisten): {e}")
        if df is None:
            raise DataFileError(f"Berkas CSV '{filename}' tidak dapat dibaca. Simpan ulang sebagai CSV UTF-8.")
        _cek_baris(df, f"Berkas CSV '{filename}'")
        if _sheet_kosong(df):
            raise DataFileError(f"Berkas CSV '{filename}' tidak berisi baris data.")
        res["Penghimpunan"] = df
        return res

    # Excel (.xlsx / .xls)
    try:
        excel_file = pd.ExcelFile(io.BytesIO(file_content))
    except Exception as e:
        raise DataFileError(
            f"Berkas Excel '{filename}' rusak atau bukan file Excel yang valid ({type(e).__name__}). "
            "Buka dan simpan ulang berkas di Excel, lalu unggah kembali."
        )
    sheet_names = excel_file.sheet_names
    if not sheet_names:
        raise DataFileError(f"Berkas Excel '{filename}' tidak memiliki sheet.")

    # Cari sheet yang cocok
    himpun_sheet = None
    salur_sheet = None

    for name in sheet_names:
        norm_name = name.lower()
        if any(k in norm_name for k in ["himpun", "masuk", "donasi", "terima", "collection", "inflow"]):
            himpun_sheet = name
        elif any(k in norm_name for k in ["salur", "keluar", "mustahik", "distribusi", "outflow"]):
            salur_sheet = name

    def _baca(sheet):
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet, nrows=_batas_baris() + 1)
            _cek_baris(df, f"Sheet '{sheet}'")
            return df
        except DataFileError:
            raise
        except Exception as e:
            raise DataFileError(f"Sheet '{sheet}' pada berkas '{filename}' tidak dapat dibaca ({type(e).__name__}).")

    nama_himpun = himpun_sheet or sheet_names[0]  # default: sheet pertama
    df_himpun = _baca(nama_himpun)
    if _sheet_kosong(df_himpun):
        raise DataFileError(
            f"Sheet '{nama_himpun}' (data penghimpunan) pada berkas '{filename}' kosong. "
            "Isi sheet tersebut dengan data transaksi atau gunakan template Excel."
        )
    res["Penghimpunan"] = df_himpun

    nama_salur = None
    if salur_sheet:
        nama_salur = salur_sheet
    elif len(sheet_names) > 1 and sheet_names[1] != himpun_sheet:
        nama_salur = sheet_names[1]
    if nama_salur:
        df_salur = _baca(nama_salur)
        if not _sheet_kosong(df_salur):
            res["Penyaluran"] = df_salur

    return res
