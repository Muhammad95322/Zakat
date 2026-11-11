"""Netralisasi injeksi rumus (CSV/Formula injection) untuk ekspor Excel dan CSV.

Sel teks yang diawali '=', '+', '-', '@', tab, atau carriage return dapat ditafsirkan
sebagai rumus oleh Excel/LibreOffice/Google Sheets. Sel seperti itu (lebih dari satu
karakter; "-" tunggal sebagai pengisi tidak berbahaya) diberi awalan
tanda kutip tunggal (') sehingga ditampilkan sebagai teks biasa. Nilai numerik
(termasuk angka negatif bertipe angka) tidak diubah.
"""
from typing import Any

import pandas as pd

AWALAN_BERBAHAYA = ("=", "+", "-", "@", "\t", "\r")


def netralkan_nilai(v: Any) -> Any:
    if isinstance(v, str) and len(v) > 1 and v.startswith(AWALAN_BERBAHAYA):
        return "'" + v
    return v


def netralkan_df(df: pd.DataFrame) -> pd.DataFrame:
    """Salinan DataFrame dengan semua sel teks dinetralkan (juga nama kolom)."""
    if df is None:
        return df
    hasil = df.copy()
    for kolom in hasil.columns:
        s = hasil[kolom]
        if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
            hasil[kolom] = s.map(netralkan_nilai)
    hasil.columns = [netralkan_nilai(c) for c in hasil.columns]
    return hasil


def ke_csv_aman(df: pd.DataFrame) -> bytes:
    """CSV UTF-8 dengan sel teks yang sudah dinetralkan."""
    return netralkan_df(df).to_csv(index=False).encode("utf-8")
