"""Modul peramalan (forecasting) penghimpunan ZIS dengan interval kepercayaan.

Prinsip modul ini: angka yang ditampilkan harus jujur.

* MAPE dihitung dari backtest nyata: beberapa bulan terakhir disisihkan sebagai
  data uji, model dilatih pada sisanya dengan metode yang sama, lalu galat
  persentase absolut rata-rata dihitung pada data uji. Jika data terlalu pendek
  untuk backtest, ``mape`` bernilai ``None`` (ditampilkan "tidak tersedia").
* Label metode selalu menyebut metode yang benar-benar dipakai.
* Jika statsmodels tidak terpasang atau model Holt-Winters gagal/ tidak
  konvergen, fallback dipakai dan alasannya dilaporkan di ``meta["fallback_alasan"]``.
"""
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Label metode (dipakai juga oleh tes untuk memastikan label jujur)
METODE_TIDAK_CUKUP = "Tidak ada peramalan (data kurang dari 3 bulan)"
METODE_RATA_BERGERAK = "Rata-rata bergerak 3 bulan terakhir"
METODE_TREN_MUSIMAN = "Tren linier + faktor musiman bulanan"
METODE_HOLT_WINTERS = "Holt-Winters (tren & musiman aditif, statsmodels)"
METODE_TREN_LINIER = "Tren linier sederhana"

# Jumlah minimal bulan data latih per metode
_MIN_LATIH = {
    "rata_bergerak": 3,
    "tren_musiman": 12,
    "holt_winters": 24,
    "tren_linier": 3,
}
_MAKS_BULAN_UJI = 6
_MIN_BULAN_UJI = 3

MAPE_TIDAK_TERSEDIA = "tidak tersedia"


class _ModelGagal(Exception):
    """Model statistik gagal dilatih atau tidak konvergen."""


def format_mape(meta: Optional[Dict[str, Any]]) -> str:
    """Format nilai MAPE untuk UI/laporan; "tidak tersedia" jika None."""
    if not meta or meta.get("mape") is None:
        return MAPE_TIDAK_TERSEDIA
    return f"{meta['mape']:.2f}%"


# ---------------------------------------------------------------------------
# Metode-metode peramalan. Semua mengembalikan (prediksi, residual_in_sample).
# ---------------------------------------------------------------------------
def _pred_rata_bergerak(y: np.ndarray, bulan: List[int], bulan_depan: List[int]) -> Tuple[np.ndarray, np.ndarray]:
    baseline = float(np.mean(y[-3:]))
    residual = y - np.mean(y)
    return np.full(len(bulan_depan), baseline), residual


def _pred_tren_linier(y: np.ndarray, bulan: List[int], bulan_depan: List[int]) -> Tuple[np.ndarray, np.ndarray]:
    n = len(y)
    x = np.arange(n)
    slope, intercept = np.polyfit(x, y, 1)
    xf = np.arange(n, n + len(bulan_depan))
    pred = intercept + slope * xf
    residual = y - (intercept + slope * x)
    return pred, residual


def _pred_tren_musiman(y: np.ndarray, bulan: List[int], bulan_depan: List[int]) -> Tuple[np.ndarray, np.ndarray]:
    n = len(y)
    x = np.arange(n)
    slope, intercept = np.polyfit(x, y, 1)
    trend_in = intercept + slope * x
    overall_mean = float(np.mean(y))
    df = pd.DataFrame({"bulan": bulan, "y": y})
    month_means = df.groupby("bulan")["y"].mean()
    faktor = {
        m: (float(month_means[m]) / overall_mean if (m in month_means.index and overall_mean) else 1.0)
        for m in range(1, 13)
    }
    fitted = trend_in * np.array([faktor[m] for m in bulan])
    xf = np.arange(n, n + len(bulan_depan))
    pred = (intercept + slope * xf) * np.array([faktor[m] for m in bulan_depan])
    return pred, y - fitted


def _pred_holt_winters(y: np.ndarray, bulan: List[int], bulan_depan: List[int]) -> Tuple[np.ndarray, np.ndarray]:
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
        pred = np.asarray(model.forecast(len(bulan_depan)), dtype=float)
        residual = y - np.asarray(model.fittedvalues, dtype=float)
    except _ModelGagal:
        raise
    except Exception as exc:
        raise _ModelGagal(f"model gagal dilatih ({type(exc).__name__}: {exc})") from exc
    if not np.all(np.isfinite(pred)):
        raise _ModelGagal("model menghasilkan nilai tidak terhingga/NaN")
    return pred, residual


_METODE = {
    "rata_bergerak": (_pred_rata_bergerak, METODE_RATA_BERGERAK),
    "tren_musiman": (_pred_tren_musiman, METODE_TREN_MUSIMAN),
    "holt_winters": (_pred_holt_winters, METODE_HOLT_WINTERS),
    "tren_linier": (_pred_tren_linier, METODE_TREN_LINIER),
}


def _hitung_mape(aktual: np.ndarray, prediksi: np.ndarray) -> Optional[float]:
    """MAPE (%) apa adanya, mengabaikan bulan dengan nilai aktual 0."""
    mask = aktual != 0
    if not np.any(mask):
        return None
    return float(np.mean(np.abs((aktual[mask] - prediksi[mask]) / aktual[mask])) * 100)


def _backtest(kunci: str, y: np.ndarray, bulan: List[int]) -> Tuple[Optional[float], int, str]:
    """Backtest: sisihkan bulan terakhir sebagai data uji.

    Returns:
        (mape atau None, jumlah bulan uji, keterangan)
    """
    n = len(y)
    min_latih = _MIN_LATIH[kunci]
    n_uji = min(_MAKS_BULAN_UJI, n - min_latih)
    if n_uji < _MIN_BULAN_UJI:
        return None, 0, (
            f"MAPE tidak tersedia: data {n} bulan terlalu pendek untuk backtest metode ini "
            f"(butuh minimal {min_latih + _MIN_BULAN_UJI} bulan: {min_latih} bulan latih + "
            f"{_MIN_BULAN_UJI} bulan uji)."
        )
    fungsi, _ = _METODE[kunci]
    y_latih, y_uji = y[:-n_uji], y[-n_uji:]
    try:
        pred, _ = fungsi(y_latih, bulan[:-n_uji], bulan[-n_uji:])
    except (ImportError, _ModelGagal) as exc:
        return None, 0, f"MAPE tidak tersedia: backtest gagal ({exc})."
    pred = np.maximum(pred, 0)
    mape = _hitung_mape(y_uji, pred)
    if mape is None:
        return None, n_uji, "MAPE tidak tersedia: semua nilai aktual pada periode uji bernilai 0."
    return round(mape, 2), n_uji, (
        f"MAPE dihitung dari backtest: {n - n_uji} bulan pertama untuk melatih model, "
        f"{n_uji} bulan terakhir sebagai data uji."
    )


def forecast_donations(monthly_df: pd.DataFrame, periods: int = 12) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Meramalkan penerimaan donasi bulanan untuk beberapa bulan ke depan.

    Args:
        monthly_df: DataFrame dengan kolom ['periode_str', 'total_dana'] terurut waktu.
        periods: Jumlah bulan proyeksi (default 12)

    Returns:
        (forecast_df, meta). ``meta`` berisi:
          - metode: label metode yang benar-benar dipakai
          - warning: catatan untuk pengguna (string)
          - mape: float (persen) hasil backtest, atau None jika tidak tersedia
          - mape_keterangan: penjelasan cara MAPE dihitung / alasan tidak tersedia
          - bulan_uji: jumlah bulan yang dipakai sebagai data uji backtest
          - fallback: True jika metode cadangan dipakai
          - fallback_alasan: alasan fallback (atau None)
          - n_bulan: jumlah bulan data historis
    """
    n = 0 if monthly_df is None or monthly_df.empty else len(monthly_df)
    if n < 3:
        return pd.DataFrame(), {
            "metode": METODE_TIDAK_CUKUP,
            "warning": "Data historis kurang dari 3 bulan sehingga peramalan tidak dibuat.",
            "mape": None,
            "mape_keterangan": "MAPE tidak tersedia: tidak ada peramalan.",
            "bulan_uji": 0,
            "fallback": False,
            "fallback_alasan": None,
            "n_bulan": n,
        }

    y = monthly_df["total_dana"].to_numpy(dtype=float)

    periode = pd.to_datetime(monthly_df["periode_str"].astype(str), errors="coerce")
    if periode.isna().any():
        # Tanpa tanggal valid, susun bulan berurutan berakhir di bulan ini
        akhir = pd.Timestamp.now().to_period("M").to_timestamp()
        periode = pd.Series(pd.date_range(end=akhir, periods=n, freq="MS"))
    bulan = [int(d.month) for d in periode]
    last_dt = periode.iloc[-1]
    future_dates = [last_dt + pd.DateOffset(months=i) for i in range(1, periods + 1)]
    future_labels = [d.strftime("%Y-%m") for d in future_dates]
    bulan_depan = [d.month for d in future_dates]

    catatan: List[str] = []
    fallback_alasan: Optional[str] = None
    if n < 12:
        kunci = "rata_bergerak"
        catatan.append(
            "Data historis kurang dari 12 bulan: proyeksi berupa rata-rata 3 bulan terakhir "
            "dan pola musiman (mis. Ramadan) belum bisa ditangkap."
        )
    elif n < 24:
        kunci = "tren_musiman"
        catatan.append(
            "Data historis 12-23 bulan: faktor musiman dihitung dari data yang tersedia "
            "sehingga masih kasar."
        )
    else:
        kunci = "holt_winters"
        catatan.append("Data historis >= 24 bulan: proyeksi mempertimbangkan pola musiman tahunan.")

    fungsi, metode = _METODE[kunci]
    try:
        pred, residual = fungsi(y, bulan, bulan_depan)
    except ImportError as exc:
        fallback_alasan = (
            f"Pustaka statsmodels tidak dapat diimpor ({exc}). "
            f"Dipakai metode cadangan '{METODE_TREN_LINIER}' tanpa komponen musiman."
        )
    except _ModelGagal as exc:
        fallback_alasan = (
            f"Model Holt-Winters gagal: {exc}. "
            f"Dipakai metode cadangan '{METODE_TREN_LINIER}' tanpa komponen musiman."
        )
    if fallback_alasan:
        kunci = "tren_linier"
        fungsi, metode = _METODE[kunci]
        pred, residual = fungsi(y, bulan, bulan_depan)
        catatan.append("PERINGATAN: " + fallback_alasan)

    std_err = float(np.std(residual)) if len(residual) > 1 else float(np.mean(y)) * 0.15
    forecast_vals = [max(0.0, float(v)) for v in pred]
    lower_vals = [max(0.0, v - 1.96 * std_err) for v in forecast_vals]
    upper_vals = [v + 1.96 * std_err for v in forecast_vals]

    mape, n_uji, mape_ket = _backtest(kunci, y, bulan)

    df_forecast = pd.DataFrame({
        "periode": future_labels,
        "proyeksi": forecast_vals,
        "batas_bawah": lower_vals,
        "batas_atas": upper_vals,
    })

    meta = {
        "metode": metode,
        "warning": " ".join(catatan),
        "mape": mape,
        "mape_keterangan": mape_ket,
        "bulan_uji": n_uji,
        "fallback": fallback_alasan is not None,
        "fallback_alasan": fallback_alasan,
        "n_bulan": n,
    }
    return df_forecast, meta
