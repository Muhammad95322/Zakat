"""Pembersihan data transaksi ZIS: alasan pembuangan per baris, tanggal & nominal multi-format,
normalisasi ejaan kategori, dan deteksi outlier.

Setiap baris yang dibuang mendapat SATU alasan (yang pertama berlaku, urutan: kosong, baris total,
duplikat, nominal, tanggal) sehingga jumlah per alasan bisa dijumlahkan menjadi total yang dibuang.
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.kategori import ATURAN_JENIS_DANA, ATURAN_KANAL, KOSONG, normalisasi_kolom
from src.pemetaan import KOLOM_LOKASI, deteksi_pemetaan, terapkan_pemetaan
from src.tanggal_impor import FORMAT_DITERIMA, parse_kolom, parse_satu
from src.utils import parse_angka_indonesia


def parse_tanggal_fleksibel(val: Any) -> Optional[datetime]:
    """Parse satu nilai tanggal (hari/bulan untuk format numerik). None bila tidak dikenali."""
    return parse_satu(val)


# kunci alasan -> (aksi di log, penjelasan untuk pengguna)
ALASAN = {
    "kosong": ("Hapus Baris Kosong", "baris tanpa isi"),
    "total": ("Hapus Baris Total/Subtotal", "baris total/subtotal (bukan transaksi)"),
    "duplikat": ("Hapus Duplikat", "duplikat persis baris lain"),
    "jumlah_kosong": ("Hapus Nominal Invalid (kosong)", "nominal kosong"),
    "jumlah_teks": ("Hapus Nominal Invalid (bukan angka)", "nominal bukan angka"),
    "jumlah_nol": ("Hapus Nominal Nol", "nominal Rp 0"),
    "jumlah_negatif": ("Hapus Nominal Negatif", "nominal negatif (koreksi/pengembalian)"),
    "tanggal_kosong": ("Hapus Tanggal Tidak Valid (kosong)", "tanggal kosong"),
    "tanggal_salah": ("Hapus Tanggal Tidak Valid (tidak dikenali)", "tanggal tidak dikenali"),
}

_RE_TOTAL = re.compile(
    r"^\s*(grand\s*)?(sub\s*-?\s*)?(total|jumlah|jml)(\s+(keseluruhan|seluruhnya|akhir|semua|"
    r"penerimaan|penghimpunan|penyaluran|bulan\b.*|tahun\b.*|per\b.*|\d{4}))?\s*:?\s*$",
    re.IGNORECASE,
)

_MAKS_CONTOH = 5

_RE_RIBU = re.compile(r"\bribu(an)?\b|\brb\b|\(\s*(rp\.?\s*)?000\s*\)|\brp\.?\s*000\b|x\s*1\.?000\b|\brp\s*k\b")
_RE_JUTA = re.compile(r"\bjuta(an)?\b|\bjt\b|x\s*1\.?000\.?000\b")


def pengali_satuan(judul: str) -> Tuple[float, str]:
    """Satuan nominal yang dinyatakan di judul kolom: 'Jumlah (Rp ribu)' -> (1000, 'ribu')."""
    j = str(judul or "").lower()
    if _RE_JUTA.search(j):
        return 1_000_000.0, "juta"
    if _RE_RIBU.search(j):
        return 1_000.0, "ribu"
    return 1.0, ""


def _teks(v: Any) -> str:
    s = str(v)
    return s if len(s) <= 40 else s[:37] + "..."


def clean_data(
    df: pd.DataFrame,
    sheet_type: str = "Penghimpunan",
    sudah_dipetakan: bool = False,
    nama_asli: Optional[Dict[str, str]] = None,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]], Dict[str, Any]]:
    """Membersihkan DataFrame data transaksi ZIS.

    Args:
        df: tabel mentah. Bila ``sudah_dipetakan`` False, kolom dipetakan otomatis dari judulnya.
        nama_asli: {kolom standar: judul asli di berkas} untuk pesan yang menunjuk kolom asli.

    Returns:
        (df_clean, cleaning_log, summary). ``summary`` berisi jumlah per alasan, contoh baris,
        kategori yang tidak dikenali, dan info format tanggal.
    """
    awal_count = len(df)
    df = df.copy()
    if KOLOM_LOKASI not in df.columns:
        df[KOLOM_LOKASI] = [f"baris {i + 2}" for i in range(len(df))]  # baris 1 = judul kolom
    if not sudah_dipetakan:
        det = deteksi_pemetaan(df, sheet_type)
        df, nama_asli = terapkan_pemetaan(df, det.pemetaan)
    nama_asli = dict(nama_asli or {})
    kol = lambda b: nama_asli.get(b, b)  # noqa: E731
    data_cols = [c for c in df.columns if c != KOLOM_LOKASI]
    df = df.reset_index(drop=True)

    alasan = pd.Series(pd.NA, index=df.index, dtype=object)
    contoh: Dict[str, List[str]] = {}

    def tandai(mask: pd.Series, kunci: str, nilai: Optional[pd.Series] = None) -> None:
        mask = mask & alasan.isna()
        if not mask.any():
            return
        alasan[mask] = kunci
        idx = mask[mask].index[:_MAKS_CONTOH]
        contoh[kunci] = [
            df.at[i, KOLOM_LOKASI] + (f" ({_teks(nilai[i])!r})" if nilai is not None and pd.notna(nilai[i]) else "")
            for i in idx
        ]

    # 1. baris kosong
    kosong = df[data_cols].apply(lambda s: s.isna() | (s.astype(str).str.strip() == "")).all(axis=1) \
        if data_cols else pd.Series(True, index=df.index)
    tandai(kosong, "kosong")

    # 2. nominal & tanggal diparse lebih dulu (dipakai deteksi baris total)
    jumlah = df["jumlah"].map(parse_angka_indonesia) if "jumlah" in df.columns else None
    pengali, satuan = pengali_satuan(kol("jumlah"))
    if jumlah is not None and pengali != 1:
        jumlah = jumlah * pengali
    info_tanggal: Dict[str, Any] = {}
    if "tanggal" in df.columns:
        tanggal, info_tanggal = parse_kolom(df["tanggal"])
    else:
        tanggal = None

    # 3. baris total/subtotal: ada sel teks "Total"/"Jumlah"/"Subtotal" dan tidak bertanggal valid
    teks_cols = [c for c in data_cols if c != "jumlah"]
    if teks_cols and len(df):
        label_total = pd.Series(False, index=df.index)
        for c in teks_cols:
            s = df[c]
            label_total |= s.map(lambda v: isinstance(v, str) and bool(_RE_TOTAL.match(v)))
        tanpa_tanggal = tanggal.isna() if tanggal is not None else pd.Series(True, index=df.index)
        tandai(label_total & tanpa_tanggal, "total")

    # 4. duplikat persis (di semua kolom data, tanpa memandang posisi baris)
    if data_cols and len(df):
        tandai(df[data_cols].astype(str).duplicated(), "duplikat")
    duplikat_count = int((alasan == "duplikat").sum())

    # 5. nominal
    if jumlah is not None:
        mentah = df["jumlah"]
        kosong_j = mentah.isna() | (mentah.astype(str).str.strip().isin(["", "-", "nan", "None"]))
        tandai(kosong_j, "jumlah_kosong")
        tandai(jumlah.isna(), "jumlah_teks", mentah)
        tandai(jumlah == 0, "jumlah_nol", mentah)
        tandai(jumlah < 0, "jumlah_negatif", mentah)

    # 6. tanggal
    if tanggal is not None:
        mentah = df["tanggal"]
        kosong_t = mentah.isna() | (mentah.astype(str).str.strip() == "")
        tandai(kosong_t, "tanggal_kosong")
        tandai(tanggal.isna(), "tanggal_salah", mentah)

    simpan = alasan.isna()
    df_clean = df[simpan].copy()
    if jumlah is not None:
        df_clean["jumlah"] = jumlah[simpan].astype(float)
    if tanggal is not None:
        df_clean["tanggal"] = pd.to_datetime(tanggal[simpan])

    hitung = alasan.value_counts().to_dict()
    cleaning_log: List[Dict[str, Any]] = []
    if jumlah is not None and pengali != 1:
        cleaning_log.append({"aksi": "Konversi Satuan Nominal", "jumlah_baris": int(simpan.sum()),
                             "keterangan": f"Judul kolom '{kol('jumlah')}' menyatakan satuan {satuan} rupiah: "
                                           f"semua nominal dikali {int(pengali):,}.".replace(",", ".")})
    rincian_alasan: Dict[str, int] = {}
    for kunci, (aksi, label) in ALASAN.items():
        n = int(hitung.get(kunci, 0))
        if not n:
            continue
        rincian_alasan[kunci] = n
        if kunci.startswith("jumlah"):
            ket = f"Dihapus {n} baris: {label} di kolom '{kol('jumlah')}'."
        elif kunci.startswith("tanggal"):
            ket = (f"Dihapus {n} baris: {label} di kolom '{kol('tanggal')}'. "
                   f"Format yang diterima: {FORMAT_DITERIMA}.")
        elif kunci == "duplikat":
            ket = f"Dihapus {n} baris transaksi yang persis sama di semua kolom."
        else:
            ket = f"Dihapus {n} baris: {label}."
        if contoh.get(kunci):
            ket += " Contoh: " + "; ".join(contoh[kunci]) + "."
        cleaning_log.append({"aksi": aksi, "jumlah_baris": n, "keterangan": ket})

    # 7. normalisasi kategori
    tak_dikenal: Dict[str, Dict[str, int]] = {}
    for kolom_kat, aturan in (("jenis_dana", ATURAN_JENIS_DANA), ("kanal", ATURAN_KANAL),
                              ("jenis_dana_sumber", ATURAN_JENIS_DANA)):
        if kolom_kat in df_clean.columns:
            df_clean[kolom_kat], td = normalisasi_kolom(df_clean[kolom_kat], aturan)
            if td and kolom_kat != "jenis_dana_sumber":
                tak_dikenal[kolom_kat] = td

    # 8. kolom teks kosong
    df_clean = df_clean.drop(columns=[KOLOM_LOKASI]).reset_index(drop=True)
    str_cols = [
        c for c in df_clean.columns
        if pd.api.types.is_object_dtype(df_clean[c]) or pd.api.types.is_string_dtype(df_clean[c])
    ]
    for c in str_cols:
        df_clean[c] = df_clean[c].map(lambda v: KOSONG if v is None or (isinstance(v, float) and np.isnan(v))
                                      else str(v).strip()).astype(object)
        df_clean.loc[df_clean[c] == "", c] = KOSONG

    # 9. outlier (IQR)
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
                "keterangan": f"Ditemukan {outlier_count} donasi bernilai sangat besar (> Rp {int(upper_limit):,}). "
                              "Data tetap disimpan untuk analisis komprehensif."
            })

    akhir_count = len(df_clean)
    dibuang_count = awal_count - akhir_count
    summary = {
        "awal": awal_count,
        "akhir": akhir_count,
        "dibuang": dibuang_count,
        "persen_dibuang": round((dibuang_count / awal_count * 100), 2) if awal_count > 0 else 0,
        "duplikat": duplikat_count,
        "outlier": outlier_count,
        "alasan": rincian_alasan,
        "contoh": contoh,
        "kategori_tak_dikenal": tak_dikenal,
        "info_tanggal": info_tanggal,
        "nama_asli": nama_asli,
        "satuan_nominal": satuan,
    }
    return df_clean, cleaning_log, summary
