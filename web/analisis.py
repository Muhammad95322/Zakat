"""Menyusun isi layar analisis dari fungsi yang sudah ada. Tidak ada logika analisis baru di sini.

Satu-satunya hitungan tambahan adalah perbandingan "12 bulan terakhir vs 12 bulan sebelumnya", yaitu
penjumlahan kolom ``total_dana`` dari ``get_trend_analysis`` untuk menjawab "naik atau turun".
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from src.analysis import get_composition_analysis, get_summary_stats, get_trend_analysis
from src.forecasting import BATAS_MAPE_ANDAL, format_mape_lengkap, forecast_donations, ringkasan_koreksi_bias
from src.loader import DataFileError
from src.pipeline import siapkan_data
from web.format import BULAN_PENDEK, bulan_tahun
from web.grafik import figur_proyeksi, figur_tren

logger = logging.getLogger("zakat.web.analisis")

DIMENSI_FILTER = [("wilayah", "kabupaten_kota", "Kabupaten/kota"), ("dana", "jenis_dana", "Jenis dana"),
                  ("kanal", "kanal", "Kanal")]
DIMENSI_RINCIAN = [("jenis_dana", "Jenis dana"), ("kanal", "Kanal"), ("kabupaten_kota", "Kabupaten/kota")]


class BerkasTidakBisaDianalisis(Exception):
    """Pesan aman untuk pengguna (tanpa jejak tumpukan)."""


@dataclass
class Perubahan:
    """Kalimat naik/turun. ``sebelumnya`` None berarti tidak dibandingkan; ``catatan`` menjelaskan sebabnya."""
    sekarang: float
    sebelumnya: Optional[float]
    label_kini: str
    label_lalu: str
    catatan: Optional[str] = None

    @property
    def persen(self) -> Optional[float]:
        if not self.sebelumnya or self.sebelumnya <= 0:
            return None
        return (self.sekarang - self.sebelumnya) / self.sebelumnya * 100

    @property
    def arah(self) -> str:
        if self.sebelumnya is None:
            return "tanpa"
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
    pesan_filter: List[str] = field(default_factory=list)
    tahun: Optional[int] = None


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
    """Tanpa filter tahun: k bulan terakhir vs k bulan sebelumnya (k = 12 bila data >= 24 bulan)."""
    n = len(monthly)
    if n >= 24:
        k = 12
    elif n >= 6:
        k = n // 2
    else:
        return None
    akhir = monthly.tail(k)
    sebelum = monthly.iloc[n - 2 * k:n - k]
    rentang = f"{bulan_tahun(akhir['periode_str'].iloc[0])} sampai {bulan_tahun(akhir['periode_str'].iloc[-1])}"
    return Perubahan(float(akhir["total_dana"].sum()), float(sebelum["total_dana"].sum()),
                     f"{k} bulan terakhir ({rentang})", f"{k} bulan sebelumnya")


def _rentang_bulan(b0: int, b1: int, tahun: int) -> str:
    if b0 == 1 and b1 == 12:
        return str(tahun)
    if b0 == b1:
        return f"{BULAN_PENDEK[b0 - 1]} {tahun}"
    return f"{BULAN_PENDEK[b0 - 1]} sampai {BULAN_PENDEK[b1 - 1]} {tahun}"


def perubahan_tahun(df_tanpa_tahun: pd.DataFrame, tahun: int) -> Optional[Perubahan]:
    """Tahun terpilih vs tahun sebelumnya pada RENTANG BULAN YANG SAMA.

    Rentang = bulan pertama s.d. bulan terakhir yang berdata di tahun terpilih (mis. tahun berjalan baru
    Jan-Okt). Tahun sebelumnya hanya dibandingkan bila datanya mencakup seluruh rentang itu; bila tidak,
    kalimatnya mengatakan apa adanya dan tidak ada persentase.
    """
    tgl = df_tanpa_tahun["tanggal"]
    kini = df_tanpa_tahun[tgl.dt.year == tahun]
    if kini.empty:
        return None
    b0, b1 = int(kini["tanggal"].dt.month.min()), int(kini["tanggal"].dt.month.max())
    label_kini = _rentang_bulan(b0, b1, tahun)
    total_kini = float(kini["jumlah"].sum())
    lalu = df_tanpa_tahun[tgl.dt.year == tahun - 1]
    if lalu.empty:
        return Perubahan(total_kini, None, label_kini, str(tahun - 1),
                         f"Belum ada data {tahun - 1} di berkas ini untuk dibandingkan.")
    l0, l1 = int(lalu["tanggal"].dt.month.min()), int(lalu["tanggal"].dt.month.max())
    if l0 > b0 or l1 < b1:
        return Perubahan(total_kini, None, label_kini, str(tahun - 1),
                         f"Data {tahun - 1} di berkas ini hanya mencakup {_rentang_bulan(l0, l1, tahun - 1)}, "
                         f"jadi tidak dibandingkan dengan {label_kini}.")
    bulan = lalu["tanggal"].dt.month
    total_lalu = float(lalu[(bulan >= b0) & (bulan <= b1)]["jumlah"].sum())
    return Perubahan(total_kini, total_lalu, label_kini, _rentang_bulan(b0, b1, tahun - 1))


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
    andal = not (meta.get("peringatan_keandalan") or meta.get("fallback")
                 or (meta.get("mape") is not None and meta["mape"] > BATAS_MAPE_ANDAL))
    return {"ada": total is not None, "total": total, "andal": andal, "rentang": rentang, "metode": meta.get("metode"),
            "mape": meta.get("mape"), "mape_teks": format_mape_lengkap(meta), "peringatan": peringatan,
            "catatan": catatan, "warning": meta.get("warning", "")}


def analisis(hasil: Dict[str, Any], filter_diminta: Dict[str, Optional[str]]) -> HasilAnalisis:
    df = hasil["df_himpun"]
    opsi, aktif, pesan = [], {}, []
    df_f = df
    for param, kolom, judul in DIMENSI_FILTER:
        pilihan = _opsi(df, kolom)
        nilai = (filter_diminta.get(param) or "").strip()
        if nilai and nilai not in pilihan:
            pesan.append(f"Pilihan {judul.lower()} di alamat halaman tidak ada di berkas ini, jadi semua "
                         f"{judul.lower()} ditampilkan.")
            nilai = ""  # nilai yang tidak ada di data diabaikan (tidak pernah dipakai mentah-mentah)
        if nilai:
            df_f = df_f[df_f[kolom].astype(str) == nilai]
        aktif[param] = nilai
        opsi.append({"param": param, "judul": judul, "pilihan": pilihan, "nilai": nilai})

    # Tahun: pilihan dari seluruh berkas (bukan dari hasil filter lain), terbaru dulu
    tahun_ada = sorted({int(t) for t in df["tanggal"].dropna().dt.year.unique()}, reverse=True) \
        if "tanggal" in df.columns else []
    diminta = (filter_diminta.get("tahun") or "").strip()
    tahun = int(diminta) if diminta.isdigit() and int(diminta) in tahun_ada else None
    if diminta and tahun is None:
        pesan.append("Tahun di alamat halaman tidak ada di berkas ini, jadi semua tahun ditampilkan.")
    aktif["tahun"] = str(tahun) if tahun else ""
    opsi.append({"param": "tahun", "judul": "Tahun", "pilihan": [str(t) for t in tahun_ada],
                 "nilai": aktif["tahun"], "semua": "Semua tahun"})

    df_tanpa_tahun = df_f  # proyeksi selalu dari seluruh riwayat dengan filter lain yang aktif
    if tahun:
        df_f = df_f[df_f["tanggal"].dt.year == tahun]

    kualitas = hasil.get("kualitas") or {}
    if df_f.empty:
        return HasilAnalisis(opsi, aktif, get_summary_stats(df_f), "", None, [], None, None, {"ada": False},
                             kualitas, kosong=True, pesan_filter=pesan, tahun=tahun)

    stats = get_summary_stats(df_f)
    trend = get_trend_analysis(df_f)
    monthly = trend.get("monthly", pd.DataFrame())
    comp = get_composition_analysis(df_f)
    riwayat = get_trend_analysis(df_tanpa_tahun).get("monthly", pd.DataFrame()) if tahun else monthly
    forecast_df, meta = forecast_donations(riwayat, 12)
    periode = ""
    if not monthly.empty:
        periode = f"{bulan_tahun(monthly['periode_str'].iloc[0])} sampai {bulan_tahun(monthly['periode_str'].iloc[-1])}"
    proyeksi = _proyeksi(forecast_df, meta)
    proyeksi["seluruh_riwayat"] = bool(tahun)
    return HasilAnalisis(
        filter_opsi=opsi, filter_aktif=aktif, stats=stats, periode=periode,
        perubahan=perubahan_tahun(df_tanpa_tahun, tahun) if tahun else _perubahan(monthly),
        rincian=_rincian(comp), figur_tren=figur_tren(monthly),
        figur_proyeksi=figur_proyeksi(riwayat, forecast_df, meta), proyeksi=proyeksi,
        kualitas=kualitas, catatan_tren=trend.get("interpretasi", ""),
        peringatan_data=list(kualitas.get("peringatan") or []), pesan_filter=pesan, tahun=tahun,
    )
