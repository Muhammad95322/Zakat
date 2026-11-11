"""Alur muat -> validasi -> bersihkan data dengan pesan kesalahan ramah pengguna."""
from typing import Any, Dict, List, Tuple

import pandas as pd

from src.cleaning import clean_data
from src.loader import DataFileError, load_file, validasi_kolom_wajib


def siapkan_data(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Muat berkas, validasi kolom wajib, lalu bersihkan.

    Returns:
        dict berisi df_himpun, log_himpun, summary_himpun, df_salur, log_salur

    Raises:
        DataFileError: pesan yang aman dan jelas untuk ditampilkan ke pengguna.
    """
    dfs = load_file(file_bytes, filename)
    raw_himpun = dfs.get("Penghimpunan", pd.DataFrame())
    validasi_kolom_wajib(raw_himpun, "Penghimpunan")

    df_himpun, log_himpun, summary = clean_data(raw_himpun, "Penghimpunan")
    if df_himpun.empty:
        alasan = "; ".join(f"{l['aksi']}: {l['jumlah_baris']} baris" for l in log_himpun) or "-"
        raise DataFileError(
            "Tidak ada baris penghimpunan yang valid setelah pembersihan. Periksa bahwa kolom "
            "'jumlah' berisi angka (contoh: 1500000, 1.500.000, 'Rp 2,5 jt') dan kolom "
            f"'tanggal' berisi tanggal yang valid. Rincian: {alasan}."
        )

    df_salur, log_salur = pd.DataFrame(), []
    raw_salur = dfs.get("Penyaluran", pd.DataFrame())
    if not raw_salur.empty:
        try:
            validasi_kolom_wajib(raw_salur, "Penyaluran")
            df_salur, log_salur, _ = clean_data(raw_salur, "Penyaluran")
        except DataFileError as e:
            # Penyaluran bersifat opsional: abaikan dengan catatan, jangan gagalkan analisis
            log_salur = [{"aksi": "Sheet Penyaluran Diabaikan", "jumlah_baris": len(raw_salur), "keterangan": str(e)}]

    return {
        "df_himpun": df_himpun,
        "log_himpun": log_himpun,
        "summary_himpun": summary,
        "df_salur": df_salur,
        "log_salur": log_salur,
    }
