"""Modul peramalan (forecasting) penghimpunan ZIS dengan pemilihan metode lewat backtest.

Prinsip modul ini: angka yang ditampilkan harus jujur.

* Metode tidak dipilih berdasarkan panjang data, melainkan lewat backtest:
  beberapa bulan terakhir disisihkan sebagai data uji, setiap metode kandidat
  yang memenuhi syarat data dilatih HANYA pada bulan latih, lalu diuji pada
  bulan uji yang sama. Metode dengan MAPE terkecil dipilih, kemudian dilatih
  ulang pada seluruh data untuk membuat proyeksi.
* Jika data terlalu pendek untuk backtest, dipakai metode sederhana
  (rata-rata bergerak) dan ``mape`` bernilai ``None`` ("tidak tersedia").
* Tabel perbandingan semua kandidat disimpan di ``meta["perbandingan"]``.
* Jika semua MAPE > 50%, ``meta["peringatan_keandalan"]`` berisi peringatan.
* Jika statsmodels tidak terpasang atau Holt-Winters gagal/tidak konvergen,
  kandidat itu dicatat tidak tersedia beserta alasannya di ``meta["fallback_alasan"]``.
"""
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Label metode (dipakai juga oleh tes untuk memastikan label jujur)
METODE_TIDAK_CUKUP = "Tidak ada peramalan (data kurang dari 3 bulan)"
METODE_RATA_BERGERAK = "Rata-rata bergerak 3 bulan terakhir"
METODE_TREN_LINIER = "Tren linier sederhana"
METODE_TREN_MUSIMAN = "Tren linier + faktor musiman bulanan"
METODE_NAIF_MUSIMAN = "Naif musiman (nilai bulan yang sama tahun lalu)"
METODE_HOLT_WINTERS = "Holt-Winters (tren & musiman aditif, statsmodels)"
METODE_TREN_RAMADAN = "Tren linier + penanda Ramadan/Idulfitri (kalender Hijriah)"

MAPE_TIDAK_TERSEDIA = "tidak tersedia"
BATAS_MAPE_ANDAL = 50.0
_MAKS_BULAN_UJI = 6
_MIN_BULAN_UJI = 3
_MIN_BULAN_DATA = 3

Prediktor = Callable[[np.ndarray, pd.DatetimeIndex, pd.DatetimeIndex], Tuple[np.ndarray, np.ndarray]]


class _ModelGagal(Exception):
    """Model statistik gagal dilatih atau tidak konvergen."""


class _TidakMemenuhiSyarat(Exception):
    """Kandidat tidak dapat dipakai untuk data ini (alasan dijelaskan di pesan)."""


def format_mape(meta: Optional[Dict[str, Any]]) -> str:
    """Format nilai MAPE untuk UI/laporan; "tidak tersedia" jika None."""
    if not meta or meta.get("mape") is None:
        return MAPE_TIDAK_TERSEDIA
    return f"{meta['mape']:.2f}%"


# ---------------------------------------------------------------------------
# Metode-metode peramalan.
# Semua menerima (y_latih, tanggal_latih, tanggal_target) dan mengembalikan
# (prediksi untuk tanggal_target, residual in-sample). Tidak ada fungsi yang
# melihat nilai aktual di luar y_latih -> tidak ada kebocoran data.
# ---------------------------------------------------------------------------
def _pred_rata_bergerak(y, tgl, tgl_depan):
    baseline = float(np.mean(y[-3:]))
    return np.full(len(tgl_depan), baseline), y - np.mean(y)


def _pred_tren_linier(y, tgl, tgl_depan):
    n = len(y)
    x = np.arange(n)
    slope, intercept = np.polyfit(x, y, 1)
    xf = np.arange(n, n + len(tgl_depan))
    return intercept + slope * xf, y - (intercept + slope * x)


def _pred_tren_musiman(y, tgl, tgl_depan):
    n = len(y)
    x = np.arange(n)
    slope, intercept = np.polyfit(x, y, 1)
    trend_in = intercept + slope * x
    overall_mean = float(np.mean(y))
    bulan = [d.month for d in tgl]
    month_means = pd.Series(y).groupby(bulan).mean()
    faktor = {
        m: (float(month_means[m]) / overall_mean if (m in month_means.index and overall_mean) else 1.0)
        for m in range(1, 13)
    }
    fitted = trend_in * np.array([faktor[m] for m in bulan])
    xf = np.arange(n, n + len(tgl_depan))
    pred = (intercept + slope * xf) * np.array([faktor[d.month] for d in tgl_depan])
    return pred, y - fitted


def _pred_naif_musiman(y, tgl, tgl_depan):
    """Nilai bulan yang sama 12 bulan sebelumnya; horizon > 12 mengulang siklus terakhir."""
    n = len(y)
    if n < 12:
        raise _TidakMemenuhiSyarat("butuh minimal 12 bulan data latih")
    pred = np.array([y[n - 12 + (i % 12)] for i in range(len(tgl_depan))], dtype=float)
    return pred, y[12:] - y[:-12]


def _pred_tren_ramadan(y, tgl, tgl_depan):
    """Regresi y = a + b*t + c*porsi_ramadan + d*idulfitri (kuadrat terkecil).

    Fitur kalender diketahui di muka (bukan dari nilai aktual), jadi aman dari kebocoran.
    """
    from src.kalender_hijriah import fitur_ramadan

    n = len(y)
    f_latih = fitur_ramadan(tgl)
    kolom = [c for c in f_latih.columns if f_latih[c].abs().sum() > 0]
    if "porsi_ramadan" not in kolom:
        raise _TidakMemenuhiSyarat("periode latih tidak mencakup bulan Ramadan")
    f_depan = fitur_ramadan(tgl_depan)

    def _X(t, f):
        return np.column_stack([np.ones(len(t)), t] + [f[c].to_numpy() for c in kolom])

    X = _X(np.arange(n), f_latih)
    koef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = _X(np.arange(n, n + len(tgl_depan)), f_depan) @ koef
    return pred, y - X @ koef


def _prasyarat_kalender(tgl, tgl_depan):
    from src.kalender_hijriah import cek_cakupan

    return cek_cakupan(tgl.append(tgl_depan))


def _pred_holt_winters(y, tgl, tgl_depan):
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except Exception as exc:  # ImportError atau error lain saat import
        raise ImportError(str(exc)) from exc

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = ExponentialSmoothing(
                y,
                seasonal_periods=12,
                trend="add",
                seasonal="add",
                initialization_method="estimated",
            ).fit()
        konvergen_gagal = [w for w in caught if "Convergence" in w.category.__name__]
        if konvergen_gagal:
            raise _ModelGagal(f"model tidak konvergen ({konvergen_gagal[0].message})")
        pred = np.asarray(model.forecast(len(tgl_depan)), dtype=float)
        residual = y - np.asarray(model.fittedvalues, dtype=float)
    except _ModelGagal:
        raise
    except Exception as exc:
        raise _ModelGagal(f"model gagal dilatih ({type(exc).__name__}: {exc})") from exc
    if not np.all(np.isfinite(pred)):
        raise _ModelGagal("model menghasilkan nilai tidak terhingga/NaN")
    return pred, residual


@dataclass(frozen=True)
class Kandidat:
    kode: str
    label: str
    fungsi: Prediktor
    min_latih: int          # minimal bulan data latih
    min_total: int = 0      # minimal panjang data keseluruhan agar kandidat ikut diuji
    syarat_total: str = ""  # penjelasan min_total untuk pengguna
    # Fungsi (tanggal_data, tanggal_proyeksi) -> None atau alasan kandidat dinonaktifkan
    prasyarat: Optional[Callable[[pd.DatetimeIndex, pd.DatetimeIndex], Optional[str]]] = None


# Urutan = urutan kesederhanaan; dipakai sebagai pemecah seri bila MAPE sama.
_KANDIDAT: List[Kandidat] = [
    Kandidat("rata_bergerak", METODE_RATA_BERGERAK, _pred_rata_bergerak, 3),
    Kandidat("tren_linier", METODE_TREN_LINIER, _pred_tren_linier, 3),
    Kandidat("naif_musiman", METODE_NAIF_MUSIMAN, _pred_naif_musiman, 12, 24,
             "hanya diuji bila data >= 24 bulan"),
    Kandidat("tren_musiman", METODE_TREN_MUSIMAN, _pred_tren_musiman, 12),
    Kandidat("tren_ramadan", METODE_TREN_RAMADAN, _pred_tren_ramadan, 12,
             prasyarat=_prasyarat_kalender),
    Kandidat("holt_winters", METODE_HOLT_WINTERS, _pred_holt_winters, 24),
]
_METODE = {k.kode: k for k in _KANDIDAT}
_METODE_SEDERHANA = "rata_bergerak"


def _hitung_mape(aktual: np.ndarray, prediksi: np.ndarray) -> Optional[float]:
    """MAPE (%) apa adanya, mengabaikan bulan dengan nilai aktual 0."""
    mask = aktual != 0
    if not np.any(mask):
        return None
    return float(np.mean(np.abs((aktual[mask] - prediksi[mask]) / aktual[mask])) * 100)


def jumlah_bulan_uji(n: int) -> int:
    """Jumlah bulan uji backtest untuk data n bulan (0 = backtest tidak mungkin)."""
    n_uji = min(_MAKS_BULAN_UJI, n - _MIN_BULAN_DATA)
    return n_uji if n_uji >= _MIN_BULAN_UJI else 0


def _prediksi_backtest(kandidat: Kandidat, y: np.ndarray, tgl: pd.DatetimeIndex, n_uji: int) -> np.ndarray:
    """Latih HANYA pada y[:-n_uji] lalu prediksi n_uji bulan berikutnya."""
    y_latih = y[:-n_uji].copy()  # salinan: fungsi tidak dapat menyentuh data uji
    pred, _ = kandidat.fungsi(y_latih, tgl[:-n_uji], tgl[-n_uji:])
    return np.maximum(np.asarray(pred, dtype=float), 0)


def _uji_kandidat(kandidat: Kandidat, y: np.ndarray, tgl: pd.DatetimeIndex, n_uji: int,
                  tgl_depan: pd.DatetimeIndex) -> Dict[str, Any]:
    n = len(y)
    baris = {
        "kode": kandidat.kode,
        "metode": kandidat.label,
        "bulan_latih": n - n_uji,
        "bulan_uji": n_uji,
        "mape": None,
        "status": "",
        "tersedia": False,
        "terpilih": False,
    }
    if kandidat.prasyarat is not None:
        alasan = kandidat.prasyarat(tgl, tgl_depan)
        if alasan:
            baris["status"] = f"dinonaktifkan: {alasan}"
            baris["nonaktif"] = alasan
            return baris
    if n < kandidat.min_total:
        baris["status"] = f"tidak diuji: {kandidat.syarat_total} (data {n} bulan)"
        return baris
    if n - n_uji < kandidat.min_latih:
        baris["status"] = (
            f"tidak diuji: butuh minimal {kandidat.min_latih} bulan latih + {_MIN_BULAN_UJI} bulan uji"
        )
        return baris
    try:
        pred = _prediksi_backtest(kandidat, y, tgl, n_uji)
    except ImportError as exc:
        baris["status"] = f"tidak tersedia: pustaka statsmodels tidak dapat diimpor ({exc})"
        baris["gangguan"] = True
        return baris
    except _ModelGagal as exc:
        baris["status"] = f"tidak tersedia: {exc}"
        baris["gangguan"] = True
        return baris
    except _TidakMemenuhiSyarat as exc:
        baris["status"] = f"tidak diuji: {exc}"
        return baris
    mape = _hitung_mape(y[-n_uji:], pred)
    if mape is None:
        baris["status"] = "MAPE tidak terdefinisi: semua nilai aktual periode uji bernilai 0"
        return baris
    baris["mape"] = round(mape, 2)
    baris["status"] = "diuji"
    baris["tersedia"] = True
    return baris


def bandingkan_metode(y: np.ndarray, tgl: pd.DatetimeIndex,
                      tgl_depan: Optional[pd.DatetimeIndex] = None) -> Tuple[List[Dict[str, Any]], int]:
    """Backtest semua kandidat pada jendela uji yang sama.

    Returns:
        (tabel perbandingan, jumlah bulan uji). Tabel kosong bila backtest tidak mungkin.
    """
    n_uji = jumlah_bulan_uji(len(y))
    if n_uji == 0:
        return [], 0
    if tgl_depan is None:
        tgl_depan = pd.DatetimeIndex([])
    return [_uji_kandidat(k, y, tgl, n_uji, tgl_depan) for k in _KANDIDAT], n_uji


def _hasil_kosong(n: int) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    return pd.DataFrame(), {
        "metode": METODE_TIDAK_CUKUP,
        "kode_metode": None,
        "warning": "Data historis kurang dari 3 bulan sehingga peramalan tidak dibuat.",
        "mape": None,
        "mape_keterangan": "MAPE tidak tersedia: tidak ada peramalan.",
        "bulan_uji": 0,
        "bulan_latih": 0,
        "fallback": False,
        "fallback_alasan": None,
        "peringatan_keandalan": None,
        "perbandingan": [],
        "dasar_pemilihan": "Tidak ada peramalan.",
        "n_bulan": n,
    }


def _tanggal_bulanan(monthly_df: pd.DataFrame) -> pd.DatetimeIndex:
    periode = pd.to_datetime(monthly_df["periode_str"].astype(str), errors="coerce")
    if periode.isna().any():
        # Tanpa tanggal valid, susun bulan berurutan berakhir di bulan ini
        akhir = pd.Timestamp.now().to_period("M").to_timestamp()
        return pd.date_range(end=akhir, periods=len(monthly_df), freq="MS")
    return pd.DatetimeIndex(periode).to_period("M").to_timestamp()


def forecast_donations(monthly_df: pd.DataFrame, periods: int = 12) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Meramalkan penerimaan donasi bulanan dengan metode terbaik hasil backtest.

    Args:
        monthly_df: DataFrame dengan kolom ['periode_str', 'total_dana'] terurut waktu.
        periods: Jumlah bulan proyeksi (default 12)

    Returns:
        (forecast_df, meta). ``meta`` berisi:
          - metode / kode_metode: metode terpilih (label jujur)
          - mape: MAPE backtest metode terpilih (float, %), atau None
          - mape_keterangan: cara MAPE dihitung / alasan tidak tersedia
          - bulan_latih, bulan_uji: ukuran jendela backtest
          - perbandingan: list dict per kandidat (metode, mape, bulan_latih, bulan_uji, status, terpilih)
          - dasar_pemilihan: kalimat penjelasan pemilihan metode
          - peringatan_keandalan: teks bila semua MAPE > 50%, selain itu None
          - fallback / fallback_alasan: True + alasan bila ada kandidat yang tidak tersedia
            karena statsmodels tidak ada atau model gagal/tidak konvergen
          - warning: gabungan catatan untuk pengguna
          - n_bulan: jumlah bulan data historis
    """
    n = 0 if monthly_df is None or monthly_df.empty else len(monthly_df)
    if n < _MIN_BULAN_DATA:
        return _hasil_kosong(n)

    y = monthly_df["total_dana"].to_numpy(dtype=float)
    tgl = _tanggal_bulanan(monthly_df)
    tgl_depan = pd.date_range(tgl[-1] + pd.DateOffset(months=1), periods=periods, freq="MS")

    perbandingan, n_uji = bandingkan_metode(y, tgl, tgl_depan)
    tersedia = sorted(
        (b for b in perbandingan if b["tersedia"]),
        key=lambda b: (b["mape"], [k.kode for k in _KANDIDAT].index(b["kode"])),
    )
    gangguan = [b for b in perbandingan if b.get("gangguan")]

    catatan: List[str] = []
    for b in perbandingan:
        if b.get("nonaktif"):
            catatan.append(f"{b['metode']} dinonaktifkan: {b['nonaktif']}.")
    fallback_alasan = None
    if gangguan:
        fallback_alasan = " ".join(f"{b['metode']} {b['status']}." for b in gangguan) + (
            " Metode dipilih dari kandidat lain yang dapat diuji."
        )
        catatan.append("PERINGATAN: " + fallback_alasan)

    # Pilih metode; latih ulang pada seluruh data. Jika kandidat terbaik gagal
    # pada data penuh (jarang), turun ke kandidat terbaik berikutnya.
    terpilih = None
    pred = residual = None
    for b in tersedia:
        try:
            pred, residual = _METODE[b["kode"]].fungsi(y, tgl, tgl_depan)
            terpilih = b
            break
        except (ImportError, _ModelGagal, _TidakMemenuhiSyarat) as exc:
            b["status"] = f"lolos backtest tetapi gagal dilatih pada seluruh data: {exc}"
            catatan.append(f"PERINGATAN: {b['metode']} gagal dilatih pada seluruh data ({exc}).")

    if terpilih is not None:
        terpilih["terpilih"] = True
        kode = terpilih["kode"]
        mape = terpilih["mape"]
        mape_ket = (
            f"MAPE dihitung dari backtest: {n - n_uji} bulan pertama untuk melatih model, "
            f"{n_uji} bulan terakhir sebagai data uji; semua kandidat diuji pada bulan yang sama."
        )
        lain = [b for b in tersedia if b is not terpilih]
        dasar = f"Dipilih karena MAPE backtest terkecil ({mape:.2f}%) dari {len(tersedia)} metode yang dapat diuji"
        if lain:
            dasar += "; pembanding: " + ", ".join(f"{b['metode']} {b['mape']:.2f}%" for b in lain)
        dasar += "."
    else:
        kode = _METODE_SEDERHANA
        pred, residual = _METODE[kode].fungsi(y, tgl, tgl_depan)
        mape = None
        if perbandingan:
            mape_ket = "MAPE tidak tersedia: tidak ada metode yang dapat diuji dengan backtest pada data ini."
        else:
            mape_ket = (
                f"MAPE tidak tersedia: data {n} bulan terlalu pendek untuk backtest "
                f"(butuh minimal {_MIN_BULAN_DATA + _MIN_BULAN_UJI} bulan)."
            )
        dasar = "Backtest tidak dapat dilakukan, sehingga dipakai metode paling sederhana."
        catatan.append(
            "Proyeksi berupa rata-rata 3 bulan terakhir; akurasinya belum dapat diukur dan pola musiman "
            "(mis. Ramadan) belum tertangkap."
        )

    peringatan_keandalan = None
    if tersedia and all(b["mape"] > BATAS_MAPE_ANDAL for b in tersedia):
        peringatan_keandalan = (
            f"Semua metode yang diuji memiliki MAPE backtest di atas {BATAS_MAPE_ANDAL:.0f}% "
            f"(terkecil {tersedia[0]['mape']:.2f}%). Proyeksi belum dapat diandalkan untuk perencanaan; "
            "gunakan hanya sebagai gambaran kasar."
        )
        catatan.append("PERINGATAN: " + peringatan_keandalan)

    std_err = float(np.std(residual)) if len(residual) > 1 else float(np.mean(y)) * 0.15
    forecast_vals = [max(0.0, float(v)) for v in pred]
    lower_vals = [max(0.0, v - 1.96 * std_err) for v in forecast_vals]
    upper_vals = [v + 1.96 * std_err for v in forecast_vals]

    df_forecast = pd.DataFrame({
        "periode": [d.strftime("%Y-%m") for d in tgl_depan],
        "proyeksi": forecast_vals,
        "batas_bawah": lower_vals,
        "batas_atas": upper_vals,
    })

    for b in perbandingan:
        b.pop("gangguan", None)
        b.pop("nonaktif", None)

    meta = {
        "metode": _METODE[kode].label,
        "kode_metode": kode,
        "warning": " ".join(catatan),
        "mape": mape,
        "mape_keterangan": mape_ket,
        "bulan_uji": n_uji if mape is not None else 0,
        "bulan_latih": (n - n_uji) if mape is not None else n,
        "fallback": fallback_alasan is not None,
        "fallback_alasan": fallback_alasan,
        "peringatan_keandalan": peringatan_keandalan,
        "perbandingan": perbandingan,
        "dasar_pemilihan": dasar,
        "n_bulan": n,
    }
    return df_forecast, meta


def tabel_perbandingan(meta: Optional[Dict[str, Any]]) -> pd.DataFrame:
    """Tabel perbandingan MAPE siap tampil (UI/PDF/Excel)."""
    baris = (meta or {}).get("perbandingan") or []
    return pd.DataFrame([{
        "Metode": b["metode"],
        "MAPE backtest": MAPE_TIDAK_TERSEDIA if b["mape"] is None else f"{b['mape']:.2f}%",
        "Bulan latih": b["bulan_latih"],
        "Bulan uji": b["bulan_uji"],
        "Status": ("TERPILIH" if b["terpilih"] else b["status"]),
    } for b in baris])
