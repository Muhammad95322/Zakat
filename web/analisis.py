"""Menyusun isi layar analisis dari fungsi yang sudah ada. Tidak ada logika analisis baru di sini.

Satu-satunya hitungan tambahan adalah perbandingan "12 bulan terakhir vs 12 bulan sebelumnya", yaitu
penjumlahan kolom ``total_dana`` dari ``get_trend_analysis`` untuk menjawab "naik atau turun".
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from src.analysis import get_composition_analysis, get_summary_stats, get_trend_analysis
from src.forecasting import format_mape_lengkap, forecast_donations, ringkasan_koreksi_bias
from src.loader import DataFileError
from src.pipeline import siapkan_data
from web.format import bulan_tahun
from web.grafik import figur_proyeksi, figur_tren

logger = logging.getLogger("zakat.web.analisis")

DIMENSI_FILTER = [("wilayah", "kabupaten_kota", "Kabupaten/kota"), ("dana", "jenis_dana", "Jenis dana"),
                  ("kanal", "kanal", "Kanal")]
DIMENSI_RINCIAN = [("jenis_dana", "Jenis dana"), ("kanal", "Kanal"), ("kabupaten_kota", "Kabupaten/kota")]


class BerkasTidakBisaDianalisis(Exception):
    """Pesan aman untuk pengguna (tanpa jejak tumpukan)."""


@dataclass
class Perubahan:
    n_bulan: int
    sekarang: float
    sebelumnya: float
    awal: str
    akhir: str

    @property
    def persen(self) -> Optional[float]:
        if self.sebelumnya <= 0:
            return None
        return (self.sekarang - self.sebelumnya) / self.sebelumnya * 100

    @property
    def arah(self) -> str:
        p = self.persen
        if p is None:
            return "baru"
        if abs(p) < 0.5:
            return "tetap"
        return "naik" if p > 0 else "turun"


@dataclass
class HasilAnalisis:
    filter_opsi: List[Dict[str, Any]]
    filter_aktif: Dict[str, str]
    stats: Dict[str, Any]
    periode: str
    perubahan: Optional[Perubahan]
    rincian: List[Dict[str, Any]]
    figur_tren: Optional[Dict]
    figur_proyeksi: Optional[Dict]
    proyeksi: Dict[str, Any]
    kualitas: Dict[str, Any]
    catatan_tren: str = ""
    kosong: bool = False
    peringatan_data: List[str] = field(default_factory=list)


def siapkan(file_bytes: bytes, nama_file: str, pemetaan_lembaga) -> Dict[str, Any]:
    try:
        return siapkan_data(file_bytes, nama_file, pemetaan_lembaga=pemetaan_lembaga)
    except DataFileError as e:
        raise BerkasTidakBisaDianalisis(str(e)) from None
    except Exception:
        logger.exception("gagal memproses berkas untuk analisis web")
        raise BerkasTidakBisaDianalisis(
            "Terjadi kesalahan tak terduga saat memproses berkas. Pastikan berkas sesuai template, "
            "lalu coba unggah ulang.") from None


def _opsi(df: pd.DataFrame, kolom: str) -> List[str]:
    if kolom not in df.columns:
        return []
    return sorted(str(v) for v in df[kolom].dropna().unique())


def _perubahan(monthly: pd.DataFrame) -> Optional[Perubahan]:
    n = len(monthly)
    if n >= 24:
        k = 12
    elif n >= 6:
        k = n // 2
    else:
        return None
    akhir = monthly.tail(k)
    sebelum = monthly.iloc[n - 2 * k:n - k]
    return Perubahan(k, float(akhir["total_dana"].sum()), float(sebelum["total_dana"].sum()),
                     bulan_tahun(akhir["periode_str"].iloc[0]), bulan_tahun(akhir["periode_str"].iloc[-1]))


def _rincian(comp: Dict[str, Any], batas: int = 5) -> List[Dict[str, Any]]:
    hasil = []
    for kolom, judul in DIMENSI_RINCIAN:
        df = comp.get(kolom)
        if df is None or getattr(df, "empty", True):
            continue
        df = df.sort_values("total", ascending=False)
        baris = [{"nama": str(r[kolom]), "total": float(r["total"]), "persen": float(r["persentase"]),
                  "transaksi": int(r["transaksi"])} for _, r in df.head(batas).iterrows()]
        sisa = df.iloc[batas:]
        if not sisa.empty:
            baris.append({"nama": f"{len(sisa)} lainnya", "total": float(sisa["total"].sum()),
                          "persen": float(sisa["persentase"].sum()), "transaksi": int(sisa["transaksi"].sum()),
                          "lainnya": True})
        maks = max(b["persen"] for b in baris) or 1
        for b in baris:
            b["lebar"] = round(b["persen"] / maks * 100, 1)
        hasil.append({"judul": judul, "baris": baris})
    return hasil


def _proyeksi(forecast_df: pd.DataFrame, meta: Dict[str, Any]) -> Dict[str, Any]:
    peringatan = []
    if meta.get("peringatan_keandalan"):
        peringatan.append(meta["peringatan_keandalan"])
    if meta.get("fallback") and meta.get("fallback_alasan"):
        peringatan.append(meta["fallback_alasan"])
    konsistensi = (meta.get("konsistensi_selang") or {}).get("peringatan")
    if konsistensi:
        peringatan.append(konsistensi)
    catatan = [c for c in (meta.get("catatan_stabilitas"), ringkasan_koreksi_bias(meta),
                           meta.get("mape_keterangan"), meta.get("selang_keterangan")) if c]
    total = float(forecast_df["proyeksi"].sum()) if forecast_df is not None and not forecast_df.empty else None
    rentang = None
    if forecast_df is not None and not forecast_df.empty:
        rentang = f"{bulan_tahun(forecast_df['periode'].iloc[0])} sampai {bulan_tahun(forecast_df['periode'].iloc[-1])}"
    return {"ada": total is not None, "total": total, "rentang": rentang, "metode": meta.get("metode"),
            "mape": meta.get("mape"), "mape_teks": format_mape_lengkap(meta), "peringatan": peringatan,
            "catatan": catatan, "warning": meta.get("warning", "")}


def analisis(hasil: Dict[str, Any], filter_diminta: Dict[str, Optional[str]]) -> HasilAnalisis:
    df = hasil["df_himpun"]
    opsi, aktif = [], {}
    df_f = df
    for param, kolom, judul in DIMENSI_FILTER:
        pilihan = _opsi(df, kolom)
        nilai = filter_diminta.get(param) or ""
        if nilai not in pilihan:
            nilai = ""  # nilai yang tidak ada di data diabaikan (tidak pernah dipakai mentah-mentah)
        if nilai:
            df_f = df_f[df_f[kolom].astype(str) == nilai]
        aktif[param] = nilai
        opsi.append({"param": param, "judul": judul, "pilihan": pilihan, "nilai": nilai})

    kualitas = hasil.get("kualitas") or {}
    if df_f.empty:
        return HasilAnalisis(opsi, aktif, get_summary_stats(df_f), "", None, [], None, None, {"ada": False},
                             kualitas, kosong=True)

    stats = get_summary_stats(df_f)
    trend = get_trend_analysis(df_f)
    monthly = trend.get("monthly", pd.DataFrame())
    comp = get_composition_analysis(df_f)
    forecast_df, meta = forecast_donations(monthly, 12)
    periode = ""
    if not monthly.empty:
        periode = f"{bulan_tahun(monthly['periode_str'].iloc[0])} sampai {bulan_tahun(monthly['periode_str'].iloc[-1])}"
    return HasilAnalisis(
        filter_opsi=opsi, filter_aktif=aktif, stats=stats, periode=periode, perubahan=_perubahan(monthly),
        rincian=_rincian(comp), figur_tren=figur_tren(monthly),
        figur_proyeksi=figur_proyeksi(monthly, forecast_df, meta), proyeksi=_proyeksi(forecast_df, meta),
        kualitas=kualitas, catatan_tren=trend.get("interpretasi", ""),
        peringatan_data=list(kualitas.get("peringatan") or []),
    )
