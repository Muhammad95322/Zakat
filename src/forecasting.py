"""Modul peramalan (forecasting) penghimpunan ZIS dengan pemilihan metode lewat backtest.

Prinsip modul ini: angka yang ditampilkan harus jujur.

* Metode dipilih lewat backtest BERGULIR (rolling origin): untuk setiap titik
  awal t (maksimal 12 titik terbaru, langkah 1 bulan) metode dilatih HANYA pada
  y[:t], memprediksi horizon tetap H bulan, lalu MAPE dihitung terhadap
  y[t:t+H]. Metode dengan rata-rata MAPE lintas titik awal terkecil dipilih,
  kemudian dilatih ulang pada seluruh data untuk membuat proyeksi.
* Jika data terlalu pendek untuk backtest, dipakai metode sederhana
  (rata-rata bergerak) dan ``mape`` bernilai ``None`` ("tidak tersedia").
* Tabel perbandingan semua kandidat disimpan di ``meta["perbandingan"]``.
* Jika semua MAPE > 50%, ``meta["peringatan_keandalan"]`` berisi peringatan.
* Jika statsmodels tidak terpasang atau Holt-Winters gagal/tidak konvergen,
  kandidat itu dicatat tidak tersedia beserta alasannya di ``meta["fallback_alasan"]``.
"""
import logging
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
HORIZON_UJI = 6          # horizon backtest bawaan (bulan)
_MIN_HORIZON = 3         # horizon terpendek yang masih dipakai untuk data pendek
MAKS_TITIK_AWAL = 12     # jumlah titik awal (terbaru) yang diuji
MIN_TITIK_AWAL = 2       # minimal titik awal valid agar metode dianggap teruji
BATAS_PORSI_GAGAL = 1 / 3  # gagal di lebih dari porsi ini -> "tidak andal"
LEVEL_SELANG = 0.80        # selang proyeksi empiris dari galat backtest
MIN_SAMPEL_SELANG = 6      # minimal galat backtest PER LANGKAH HORIZON agar selang langkah itu dihitung
MAKS_HORIZON_SELANG = 12   # backtest selang menjangkau sampai 12 bulan ke depan (= horizon proyeksi bawaan)
LABEL_SELANG = f"Selang {LEVEL_SELANG:.0%} (dari galat backtest)"
MAKS_TITIK_AWAL_RINCI = 36  # titik awal per langkah untuk uji bertingkat koreksi bias (lebih panjang dari 12)
AMBANG_ARAH_BIAS = 0.05     # |median rasio - 1| < 5% dianggap tidak bias berarti
MIN_RASIO_KOREKSI = 6       # minimal rasio per langkah horizon agar faktor koreksi dihitung
BATAS_FAKTOR_KOREKSI = (0.5, 2.0)  # faktor di luar rentang ini dianggap tidak wajar -> tidak dipakai
MIN_EVAL_KOREKSI = 12       # minimal pasangan evaluasi pada uji bertingkat
AMBANG_PERBAIKAN_KOREKSI = 0.10  # koreksi dipakai hanya bila MAPE evaluasi turun >= 10% relatif
_MIN_BULAN_DATA = 3
# Alias kompatibilitas nama lama
_MAKS_BULAN_UJI = HORIZON_UJI
_MIN_BULAN_UJI = _MIN_HORIZON

Prediktor = Callable[[np.ndarray, pd.DatetimeIndex, pd.DatetimeIndex], Tuple[np.ndarray, np.ndarray]]


class _ModelGagal(Exception):
    """Model statistik gagal dilatih atau tidak konvergen."""


class _TidakMemenuhiSyarat(Exception):
    """Kandidat tidak dapat dipakai untuk data ini (alasan dijelaskan di pesan)."""


def versi_lingkungan() -> Dict[str, str]:
    """Versi Python dan pustaka numerik yang memengaruhi angka peramalan."""
    import platform

    versi = {"python": platform.python_version()}
    for nama in ("numpy", "scipy", "pandas", "statsmodels"):
        try:
            modul = __import__(nama)
            versi[nama] = str(getattr(modul, "__version__", "?"))
        except Exception:
            versi[nama] = "tidak dapat diimpor"
    return versi


def format_mape(meta: Optional[Dict[str, Any]]) -> str:
    """Format nilai MAPE untuk UI/laporan; "tidak tersedia" jika None."""
    if not meta or meta.get("mape") is None:
        return MAPE_TIDAK_TERSEDIA
    return f"{meta['mape']:.2f}%"


def format_mape_lengkap(meta: Optional[Dict[str, Any]]) -> str:
    """Rata-rata MAPE lintas titik awal beserta sebarannya, mis.
    "26.86% (rata-rata 12 jendela; SD 5.61; rentang 18.40-37.15%)"."""
    dasar = format_mape(meta)
    if dasar == MAPE_TIDAK_TERSEDIA:
        return dasar
    bagian = [f"rata-rata {meta.get('n_jendela', 0)} jendela"]
    if meta.get("mape_std") is not None:
        bagian.append(f"SD {meta['mape_std']:.2f}")
    if meta.get("mape_terbaik") is not None and meta.get("mape_terburuk") is not None:
        bagian.append(f"rentang {meta['mape_terbaik']:.2f}-{meta['mape_terburuk']:.2f}%")
    return f"{dasar} ({'; '.join(bagian)})"


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
        # jenis & pesan exception hanya ke log server; status yang tampil ke pengguna tetap bahasa awam
        logging.getLogger("zakat.peramalan").info("model gagal dilatih", extra={"galat": type(exc).__name__})
        raise _ModelGagal("model gagal dilatih (perhitungan numerik tidak stabil pada data ini)") from exc
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


def horizon_backtest(n: int) -> int:
    """Horizon H backtest untuk data n bulan (0 = backtest bergulir tidak mungkin).

    H = 6 bila data cukup; untuk data pendek H diperpendek (minimal 3) agar
    masih ada >= 2 titik awal dengan >= 3 bulan latih: H <= n - 3 - 1.
    """
    h = min(HORIZON_UJI, n - _MIN_BULAN_DATA - (MIN_TITIK_AWAL - 1))
    return h if h >= _MIN_HORIZON else 0


def titik_awal_backtest(n: int) -> List[int]:
    """Titik awal t (jumlah bulan latih) yang horizon penuhnya tersedia.

    Hanya t dengan t + H <= n (tanpa jendela terpotong), maksimal
    MAKS_TITIK_AWAL titik terbaru, langkah 1 bulan, dan t >= 3.
    """
    h = horizon_backtest(n)
    if h == 0:
        return []
    akhir = n - h
    awal = max(_MIN_BULAN_DATA, akhir - MAKS_TITIK_AWAL + 1)
    return list(range(awal, akhir + 1))


def jumlah_bulan_uji(n: int) -> int:
    """Kompatibilitas: horizon backtest (bulan uji per titik awal)."""
    return horizon_backtest(n)


def _prediksi_backtest(kandidat: Kandidat, y: np.ndarray, tgl: pd.DatetimeIndex, t: int, h: int) -> np.ndarray:
    """Latih HANYA pada y[:t] lalu prediksi h bulan berikutnya (tgl[t:t+h])."""
    y_latih = y[:t].copy()  # salinan: fungsi tidak dapat menyentuh data setelah t
    pred, _ = kandidat.fungsi(y_latih, tgl[:t], tgl[t:t + h])
    return np.maximum(np.asarray(pred, dtype=float), 0)


def _ringkas(nilai: List[float]) -> Dict[str, Optional[float]]:
    if not nilai:
        return {"mape": None, "mape_median": None, "mape_terbaik": None, "mape_terburuk": None, "mape_std": None}
    a = np.asarray(nilai, dtype=float)
    return {
        "mape": round(float(a.mean()), 2),
        "mape_median": round(float(np.median(a)), 2),
        "mape_terbaik": round(float(a.min()), 2),
        "mape_terburuk": round(float(a.max()), 2),
        "mape_std": round(float(a.std(ddof=1)), 2) if len(a) > 1 else None,
    }


def _uji_kandidat(kandidat: Kandidat, y: np.ndarray, tgl: pd.DatetimeIndex, titik: List[int], h: int,
                  tgl_depan: pd.DatetimeIndex) -> Dict[str, Any]:
    n = len(y)
    baris: Dict[str, Any] = {
        "kode": kandidat.kode,
        "metode": kandidat.label,
        "bulan_uji": h,
        "titik_awal": [],
        "mape_per_jendela": {},
        "n_jendela": 0,
        "n_gagal": 0,
        "n_dilewati": 0,
        "titik_gagal": [],
        "alasan_gagal": [],
        "status": "",
        "tersedia": False,
        "andal": True,
        "terpilih": False,
        **_ringkas([]),
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
    titik_valid = [t for t in titik if t >= kandidat.min_latih]
    if len(titik_valid) < MIN_TITIK_AWAL:
        baris["status"] = (
            f"tidak diuji: butuh minimal {MIN_TITIK_AWAL} titik awal dengan >= {kandidat.min_latih} bulan latih "
            f"dan horizon {h} bulan (tersedia {len(titik_valid)})"
        )
        return baris

    alasan_gagal: List[str] = []
    for t in titik_valid:
        try:
            pred = _prediksi_backtest(kandidat, y, tgl, t, h)
        except ImportError as exc:
            baris["status"] = "tidak tersedia: pustaka statsmodels tidak dapat diimpor"
            baris["gangguan"] = True
            return baris
        except _ModelGagal as exc:
            baris["n_gagal"] += 1
            baris["titik_gagal"].append(t)
            alasan_gagal.append(str(exc))
            continue
        except _TidakMemenuhiSyarat:
            continue  # titik awal ini tidak memenuhi syarat metode (bukan kegagalan)
        aktual = y[t:t + h]
        mape = _hitung_mape(aktual, pred)
        if mape is None:
            baris["n_dilewati"] += 1
            continue  # semua aktual 0: MAPE tak terdefinisi untuk jendela ini (bukan kegagalan)
        baris["mape_per_jendela"][t] = round(mape, 2)

    baris["titik_awal"] = sorted(baris["mape_per_jendela"])
    baris["n_jendela"] = len(baris["titik_awal"])
    baris["_alasan_gagal"] = alasan_gagal
    baris["alasan_gagal"] = list(dict.fromkeys(alasan_gagal))[:3]  # alasan unik (maks 3)
    baris.update(_ringkas(list(baris["mape_per_jendela"].values())))
    n_coba = baris["n_jendela"] + baris["n_gagal"]
    if baris["n_gagal"] and baris["n_gagal"] > BATAS_PORSI_GAGAL * n_coba:
        baris["andal"] = False
        baris["status"] = (
            f"tidak andal: gagal di {baris['n_gagal']} dari {n_coba} titik awal "
            f"(lebih dari sepertiga; contoh alasan: {alasan_gagal[0]})"
        )
        baris["gangguan"] = True
        return baris  # statistik dari jendela yang berhasil tetap ditampilkan, tetapi tidak dipilih
    if baris["n_jendela"] < MIN_TITIK_AWAL:
        detail = f"; gagal di {baris['n_gagal']} titik awal ({alasan_gagal[0]})" if alasan_gagal else ""
        baris["status"] = (
            f"tidak diuji: hanya {baris['n_jendela']} titik awal yang valid (butuh {MIN_TITIK_AWAL}){detail}"
        )
        baris.update(_ringkas([]))
        if alasan_gagal:
            baris["gangguan"] = True
        return baris
    baris["status"] = "diuji" if not baris["n_gagal"] else f"diuji (gagal di {baris['n_gagal']} dari {n_coba} titik awal)"
    baris["tersedia"] = True
    return baris


def bandingkan_metode(y: np.ndarray, tgl: pd.DatetimeIndex,
                      tgl_depan: Optional[pd.DatetimeIndex] = None) -> Tuple[List[Dict[str, Any]], int]:
    """Backtest bergulir semua kandidat.

    Returns:
        (tabel perbandingan, horizon H). Tabel kosong bila backtest bergulir tidak mungkin.
    """
    titik = titik_awal_backtest(len(y))
    if not titik:
        return [], 0
    h = horizon_backtest(len(y))
    if tgl_depan is None:
        tgl_depan = pd.DatetimeIndex([])
    return [_uji_kandidat(k, y, tgl, titik, h, tgl_depan) for k in _KANDIDAT], h


def _hasil_kosong(n: int) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    return pd.DataFrame(), {
        "metode": METODE_TIDAK_CUKUP,
        "kode_metode": None,
        "warning": "Data historis kurang dari 3 bulan sehingga peramalan tidak dibuat.",
        "mape": None,
        "mape_median": None,
        "mape_terburuk": None,
        "mape_std": None,
        "n_jendela": 0,
        "mape_keterangan": "MAPE tidak tersedia: tidak ada peramalan.",
        "bulan_uji": 0,
        "bulan_latih": 0,
        "fallback": False,
        "fallback_alasan": None,
        "peringatan_keandalan": None,
        "catatan_stabilitas": None,
        "jendela_bersama": [],
        "jendela_dikeluarkan": {},
        "lingkungan": versi_lingkungan(),
        "selang_tersedia": False,
        "selang_label": None,
        "selang_keterangan": "Selang tidak tersedia: tidak ada peramalan.",
        "selang_per_bulan": [],
        "bias_per_horizon": [],
        "koreksi_bias": {"dipakai": False, "alasan": "tidak ada peramalan", "uji": {}, "faktor_per_horizon": []},
        "konsistensi_selang": {"n_bulan_selang": 0, "bulan_di_luar": [], "bulan_tidak_sah": [],
                               "di_dalam_selang": [], "peringatan": None},
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


def hitung_selang(proyeksi: np.ndarray, galat_relatif: List[float]) -> Tuple[np.ndarray, np.ndarray]:
    """Selang empiris: proyeksi x (1 + kuantil galat relatif backtest).

    galat relatif = (aktual - prediksi) / prediksi, dikumpulkan dari semua titik
    awal dan semua langkah horizon metode terpilih. Batas bawah tidak pernah < 0.
    """
    g = np.asarray(galat_relatif, dtype=float)
    alfa = (1 - LEVEL_SELANG) / 2
    q_bawah, q_atas = np.quantile(g, [alfa, 1 - alfa])
    proyeksi = np.maximum(np.asarray(proyeksi, dtype=float), 0)
    bawah = np.maximum(proyeksi * (1 + q_bawah), 0)
    atas = np.maximum(proyeksi * (1 + q_atas), bawah)
    return bawah, atas


def _rentang(angka: List[int]) -> str:
    """[1,2,3,5,7,8] -> '1-3, 5, 7-8'."""
    bagian, mulai = [], None
    for i, a in enumerate(angka):
        if mulai is None:
            mulai = a
        if i == len(angka) - 1 or angka[i + 1] != a + 1:
            bagian.append(f"{mulai}" if mulai == a else f"{mulai}-{a}")
            mulai = None
    return ", ".join(bagian)


def rasio_per_horizon_rinci(kandidat: Kandidat, y: np.ndarray, tgl: pd.DatetimeIndex, maks_h: int,
                            maks_titik: int = MAKS_TITIK_AWAL_RINCI) -> Dict[int, List[Tuple[int, float]]]:
    """Rasio aktual/prediksi backtest metode ``kandidat`` per langkah horizon h = 1..maks_h.

    Untuk langkah h dipakai sampai ``maks_titik`` titik awal TERBARU t yang mencapai
    bulan itu (t + h <= n) dan memenuhi syarat data latih metode. Model hanya dilatih
    pada y[:t]. Prediksi <= 0 dilewati. Hasil: {h: [(t, rasio), ...]} terurut menurut t.
    """
    n = len(y)
    paling_awal = max(kandidat.min_latih, n - (maks_titik + maks_h - 1))
    per_h: Dict[int, List[Tuple[int, float]]] = {hh: [] for hh in range(1, maks_h + 1)}
    for t in range(paling_awal, n):
        langkah = min(maks_h, n - t)
        try:
            pred = _prediksi_backtest(kandidat, y, tgl, t, langkah)
        except (ImportError, _ModelGagal, _TidakMemenuhiSyarat):
            continue
        for hh in range(1, langkah + 1):
            p = pred[hh - 1]
            if p > 0:
                per_h[hh].append((t, float(y[t + hh - 1] / p)))
    return {hh: sorted(v)[-maks_titik:] for hh, v in per_h.items()}


def terbaru(rinci: Dict[int, List[Tuple[int, float]]], n: int, k: int = MAKS_TITIK_AWAL) -> Dict[int, List[float]]:
    """Rasio dari k TITIK AWAL terbaru yang mencapai langkah h (t dari n-h-k+1 sampai n-h).

    Dipilih menurut titik awal, bukan jumlah rasio: bila sebagian titik awal dilewati
    (prediksi <= 0 atau model gagal), tidak diganti dengan titik awal yang lebih lama.
    """
    return {hh: [r for t, r in v if t >= n - hh - k + 1] for hh, v in rinci.items()}


def galat_per_horizon(kandidat: Kandidat, y: np.ndarray, tgl: pd.DatetimeIndex,
                      maks_h: int) -> Dict[int, List[float]]:
    """Galat relatif (aktual - prediksi) / prediksi = rasio - 1, maks MAKS_TITIK_AWAL titik awal
    terbaru per langkah horizon (dipakai untuk selang)."""
    rinci = rasio_per_horizon_rinci(kandidat, y, tgl, maks_h, MAKS_TITIK_AWAL)
    return {hh: [r - 1 for r in v] for hh, v in terbaru(rinci, len(y)).items()}


def faktor_koreksi(rasio: List[float]) -> Tuple[float, str]:
    """Faktor koreksi = median rasio aktual/prediksi, dengan syarat jumlah dan rentang wajar.

    Returns:
        (faktor, status). Faktor 1.0 berarti tidak dikoreksi; status menjelaskan alasannya.
    """
    if len(rasio) < MIN_RASIO_KOREKSI:
        return 1.0, f"tidak dikoreksi: hanya {len(rasio)} rasio (butuh {MIN_RASIO_KOREKSI})"
    f = float(np.median(rasio))
    lo, hi = BATAS_FAKTOR_KOREKSI
    if not (lo <= f <= hi):
        return 1.0, f"tidak dikoreksi: faktor {f:.2f} di luar rentang wajar {lo}-{hi}"
    return f, "dikoreksi"


def rasio_belajar(rinci: Dict[int, List[Tuple[int, float]]], hh: int, t_i: int) -> List[float]:
    """Rasio langkah ``hh`` yang AKTUALNYA sudah diketahui pada titik awal t_i
    (t_j + hh <= t_i), maks MAKS_TITIK_AWAL terbaru. Inilah satu-satunya data yang
    boleh dipakai untuk mempelajari faktor koreksi saat menilai jendela t_i."""
    return [r for t_j, r in rinci.get(hh, []) if t_j + hh <= t_i][-MAKS_TITIK_AWAL:]


def faktor_belajar(rinci: Dict[int, List[Tuple[int, float]]], hh: int, t_i: int) -> Tuple[float, str, int]:
    """Faktor koreksi yang dipelajari untuk menilai jendela (t_i, hh), tanpa kebocoran."""
    belajar = rasio_belajar(rinci, hh, t_i)
    f, status = faktor_koreksi(belajar)
    return f, status, len(belajar)


def uji_koreksi_bertingkat(rinci: Dict[int, List[Tuple[int, float]]]) -> Dict[str, Any]:
    """Uji tanpa kebocoran apakah koreksi bias memperbaiki proyeksi.

    Untuk setiap sampel evaluasi (titik awal t_i, langkah h, rasio r_i), faktor dipelajari
    HANYA dari rasio (t_j, h) yang nilai aktualnya sudah diketahui pada t_i, yaitu
    t_j + h <= t_i (maks MAKS_TITIK_AWAL terbaru), dengan aturan ``faktor_koreksi``.
    Sampel tanpa >= MIN_RASIO_KOREKSI rasio belajar dilewati. APE tanpa koreksi =
    |1 - 1/r_i|, dengan koreksi = |1 - f/r_i| (karena aktual = r_i x prediksi).
    """
    ape_tanpa: List[float] = []
    ape_dengan: List[float] = []
    titik_eval: List[int] = []
    n_luar_batas = 0
    for hh, sampel in rinci.items():
        for t_i, r_i in sampel:
            f, status, n_belajar = faktor_belajar(rinci, hh, t_i)
            if n_belajar < MIN_RASIO_KOREKSI:
                continue
            if status != "dikoreksi":
                n_luar_batas += 1
            ape_tanpa.append(abs(1 - 1 / r_i))
            ape_dengan.append(abs(1 - f / r_i))
            titik_eval.append(t_i)
    n_eval = len(ape_tanpa)
    hasil = {
        "n_eval": n_eval,
        "mape_tanpa": round(float(np.mean(ape_tanpa)) * 100, 2) if n_eval else None,
        "mape_dengan": round(float(np.mean(ape_dengan)) * 100, 2) if n_eval else None,
        "n_lebih_baik": int(sum(d < t for d, t in zip(ape_dengan, ape_tanpa))),
        "n_faktor_di_luar_batas": n_luar_batas,
        "titik_awal_eval": [min(titik_eval), max(titik_eval)] if titik_eval else [],
    }
    if n_eval < MIN_EVAL_KOREKSI:
        hasil["dipakai"] = False
        hasil["alasan"] = (
            f"data terlalu sedikit untuk uji bertingkat: {n_eval} pasangan evaluasi "
            f"(butuh {MIN_EVAL_KOREKSI})"
        )
    elif hasil["mape_dengan"] <= (1 - AMBANG_PERBAIKAN_KOREKSI) * hasil["mape_tanpa"]:
        hasil["dipakai"] = True
        hasil["alasan"] = (
            f"MAPE evaluasi turun dari {hasil['mape_tanpa']:.2f}% menjadi {hasil['mape_dengan']:.2f}% "
            f"pada {n_eval} pasangan (perbaikan >= {AMBANG_PERBAIKAN_KOREKSI:.0%})"
        )
    else:
        hasil["dipakai"] = False
        hasil["alasan"] = (
            f"tidak membaik secara nyata: MAPE evaluasi {hasil['mape_tanpa']:.2f}% tanpa koreksi vs "
            f"{hasil['mape_dengan']:.2f}% dengan koreksi pada {n_eval} pasangan "
            f"(butuh perbaikan >= {AMBANG_PERBAIKAN_KOREKSI:.0%})"
        )
    return hasil


def periksa_konsistensi_selang(proyeksi: np.ndarray, bawah: np.ndarray, atas: np.ndarray,
                               bias: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Periksa tiap bulan yang punya selang: 0 <= bawah <= proyeksi <= atas.

    Returns dict berisi jumlah bulan yang punya selang, bulan dengan proyeksi di luar selang,
    bulan dengan selang tidak sah (negatif/terbalik), status per bulan, dan teks peringatan
    (None bila konsisten).
    """
    proyeksi = np.asarray(proyeksi, dtype=float)
    ada = np.isfinite(bawah) & np.isfinite(atas)
    status: List[Optional[bool]] = []
    luar, tidak_sah = [], []
    for i in range(len(proyeksi)):
        if not ada[i]:
            status.append(None)
            continue
        if bawah[i] < 0 or bawah[i] > atas[i]:
            tidak_sah.append(i + 1)
        di_dalam = bool(bawah[i] - 1e-9 <= proyeksi[i] <= atas[i] + 1e-9)
        status.append(di_dalam)
        if not di_dalam:
            luar.append(i + 1)
    pesan = []
    if luar:
        arah = ""
        if bias:
            arah_bulan = [b["arah"] for b in bias if b["langkah"] in luar]
            if arah_bulan:
                dominan = max(set(arah_bulan), key=arah_bulan.count)
                arah = f"; metode cenderung bias ({dominan} menurut backtest)"
        pesan.append(
            f"Proyeksi titik berada di luar selang di {len(luar)} dari {int(ada.sum())} bulan "
            f"(bulan ke-{_rentang(luar)}){arah}. Selang menunjukkan rentang nilai yang lebih mungkin "
            "berdasarkan galat masa lalu; proyeksi titik dari metode ini kemungkinan bias."
        )
    if tidak_sah:
        pesan.append(f"Selang tidak sah (negatif atau terbalik) di bulan ke-{_rentang(tidak_sah)}.")
    return {
        "n_bulan_selang": int(ada.sum()),
        "bulan_di_luar": luar,
        "bulan_tidak_sah": tidak_sah,
        "di_dalam_selang": status,
        "peringatan": " ".join(pesan) if pesan else None,
    }


def ringkas_bias(rasio: Dict[int, List[float]]) -> List[Dict[str, Any]]:
    """Ringkasan bias per langkah horizon dari rasio aktual/prediksi backtest.

    median > 1 berarti metode MEREMEHKAN (aktual lebih besar dari prediksi),
    median < 1 berarti MELEBIHKAN. |median - 1| < AMBANG_ARAH_BIAS: tidak bias berarti.
    """
    hasil = []
    for hh in sorted(rasio):
        r = np.asarray(rasio[hh], dtype=float)
        if len(r) == 0:
            hasil.append({"langkah": hh, "n_rasio": 0, "median_rasio": None, "q10_rasio": None,
                          "q90_rasio": None, "arah": "tidak ada data"})
            continue
        med = float(np.median(r))
        if med > 1 + AMBANG_ARAH_BIAS:
            arah = "meremehkan"
        elif med < 1 - AMBANG_ARAH_BIAS:
            arah = "melebihkan"
        else:
            arah = "tidak bias berarti"
        hasil.append({
            "langkah": hh, "n_rasio": int(len(r)), "median_rasio": round(med, 4),
            "q10_rasio": round(float(np.quantile(r, 0.1)), 4), "q90_rasio": round(float(np.quantile(r, 0.9)), 4),
            "arah": arah,
        })
    return hasil


def selang_per_horizon(proyeksi: np.ndarray, galat: Dict[int, List[float]]) -> Tuple[
        np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    """Selang per bulan proyeksi dari sebaran galat langkah horizon yang sesuai.

    Bulan ke-i memakai galat langkah h = i. Status per bulan: 'tersedia',
    'tidak tersedia' (galat < MIN_SAMPEL_SELANG), atau 'di luar cakupan backtest'
    (tidak ada titik awal yang mencapai langkah itu). Tidak ada ekstrapolasi.
    """
    m = len(proyeksi)
    bawah = np.full(m, np.nan)
    atas = np.full(m, np.nan)
    rincian: List[Dict[str, Any]] = []
    for i in range(m):
        hh = i + 1
        g = galat.get(hh, [])
        if not g:
            status = "di luar cakupan backtest"
        elif len(g) < MIN_SAMPEL_SELANG:
            status = f"tidak tersedia: hanya {len(g)} galat (butuh {MIN_SAMPEL_SELANG})"
        else:
            b, a = hitung_selang(np.array([proyeksi[i]]), g)
            bawah[i], atas[i] = b[0], a[0]
            status = "tersedia"
        rincian.append({"langkah": hh, "n_galat": len(g), "status": status})
    return bawah, atas, rincian


def _urutan(kode: str) -> int:
    return [k.kode for k in _KANDIDAT].index(kode)


def urutkan_kandidat(tersedia: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[int]]:
    """Urutkan kandidat yang dapat dipilih secara adil.

    Rata-rata MAPE tiap metode dihitung pada JENDELA BERSAMA (titik awal yang
    berhasil diuji oleh semua kandidat), karena metode yang butuh data latih
    panjang (mis. Holt-Winters) hanya punya jendela terbaru; membandingkan
    rata-rata pada jendela berbeda membuat perbandingan bias. Bila jendela
    bersama < MIN_TITIK_AWAL, dipakai rata-rata masing-masing metode.
    Pemecah seri: urutan kesederhanaan.

    Returns:
        (kandidat terurut, daftar titik awal bersama). Setiap kandidat diberi
        kunci ``mape_bersama`` (None bila jendela bersama tidak cukup).
    """
    if not tersedia:
        return [], []
    bersama = sorted(set.intersection(*(set(b["mape_per_jendela"]) for b in tersedia)))
    if len(bersama) < MIN_TITIK_AWAL:
        bersama = []
    for b in tersedia:
        b["mape_bersama"] = (
            round(float(np.mean([b["mape_per_jendela"][t] for t in bersama])), 2) if bersama else None
        )
    kunci = (lambda b: (b["mape_bersama"], _urutan(b["kode"]))) if bersama else (
        lambda b: (b["mape"], _urutan(b["kode"])))
    return sorted(tersedia, key=kunci), bersama


def jendela_dikeluarkan_karena_gagal(tersedia: List[Dict[str, Any]], bersama: List[int]) -> Dict[int, List[str]]:
    """Titik awal yang keluar dari jendela bersama karena metode andal GAGAL di sana.

    Aturan (sama untuk semua metode): jendela bersama = titik awal tempat SEMUA
    metode andal berhasil dinilai. Bila satu metode gagal di titik awal t, t
    dikeluarkan dari jendela bersama untuk SEMUA metode (dasar peringkat), tetapi
    rata-rata MAPE yang ditampilkan per metode tetap memakai seluruh jendela yang
    berhasil ia nilai.
    """
    hasil: Dict[int, List[str]] = {}
    for b in tersedia:
        for t in b.get("titik_gagal", []):
            if t not in bersama:
                hasil.setdefault(t, []).append(b["metode"])
    return dict(sorted(hasil.items()))


def ringkasan_catatan_metode(meta: Optional[Dict[str, Any]]) -> str:
    """Satu paragraf singkat: versi pustaka dan kegagalan konvergensi per metode."""
    meta = meta or {}
    v = meta.get("lingkungan") or {}
    bagian = []
    if v:
        bagian.append(
            f"Dihitung dengan Python {v.get('python')}, statsmodels {v.get('statsmodels')}, "
            f"numpy {v.get('numpy')}, scipy {v.get('scipy')}, pandas {v.get('pandas')}."
        )
    for b in meta.get("perbandingan") or []:
        if b.get("n_gagal"):
            coba = b["n_jendela"] + b["n_gagal"]
            alasan = f" ({b['alasan_gagal'][0]})" if b.get("alasan_gagal") else ""
            bagian.append(
                f"{b['metode']}: {b['n_jendela']} dari {coba} titik awal dinilai, "
                f"{b['n_gagal']} gagal{alasan}."
            )
        elif b["status"].startswith("tidak tersedia"):
            bagian.append(f"{b['metode']} {b['status']}.")
    keluar = meta.get("jendela_dikeluarkan") or {}
    if keluar:
        bagian.append(
            "Titik awal (bulan latih) yang dikeluarkan dari jendela bersama untuk semua metode karena ada metode "
            "yang gagal: " + "; ".join(f"{t} ({', '.join(m)})" for t, m in keluar.items()) + "."
        )
    if not any(b.get("n_gagal") for b in meta.get("perbandingan") or []) and meta.get("perbandingan"):
        bagian.append("Tidak ada kegagalan konvergensi pada backtest.")
    bagian.append(ringkasan_koreksi_bias(meta))
    k = (meta.get("konsistensi_selang") or {}).get("peringatan")
    if k:
        bagian.append(k)
    return " ".join(b for b in bagian if b)


def ringkasan_koreksi_bias(meta: Optional[Dict[str, Any]]) -> str:
    """Satu kalimat: koreksi bias dipakai atau tidak, faktor, dan bukti uji bertingkat."""
    kb = (meta or {}).get("koreksi_bias") or {}
    if not kb:
        return ""
    uji = kb.get("uji") or {}
    bukti = ""
    if uji.get("n_eval"):
        bukti = (f" Uji bertingkat (tanpa kebocoran) pada {uji['n_eval']} pasangan: MAPE tanpa koreksi "
                 f"{uji['mape_tanpa']:.2f}%, dengan koreksi {uji['mape_dengan']:.2f}%.")
    if kb.get("dipakai"):
        faktor = [f["faktor"] for f in kb.get("faktor_per_horizon", []) if f["status"] == "dikoreksi"]
        rentang = f" faktor {min(faktor):.2f}-{max(faktor):.2f}" if faktor else ""
        return f"Koreksi bias dipakai ({len(faktor)} langkah horizon dikoreksi,{rentang}): {kb['alasan']}.{bukti}"
    return f"Koreksi bias tidak dipakai: {kb.get('alasan')}.{bukti}"


def tabel_bias_koreksi(meta: Optional[Dict[str, Any]]) -> pd.DataFrame:
    """Tabel per langkah horizon: bias backtest dan faktor koreksi (UI/Excel)."""
    meta = meta or {}
    faktor = {f["langkah"]: f for f in (meta.get("koreksi_bias") or {}).get("faktor_per_horizon", [])}
    baris = []
    for b in meta.get("bias_per_horizon") or []:
        f = faktor.get(b["langkah"], {})
        baris.append({
            "Bulan ke-": b["langkah"],
            "Jumlah rasio": b["n_rasio"],
            "Median aktual/prediksi": b["median_rasio"],
            "Kuantil 10%": b["q10_rasio"],
            "Kuantil 90%": b["q90_rasio"],
            "Arah bias": b["arah"],
            "Faktor dihitung": f.get("faktor_dihitung"),
            "Faktor dipakai": f.get("faktor"),
            "Status faktor": f.get("status"),
        })
    return pd.DataFrame(baris)


def cek_stabilitas(pertama: Dict[str, Any], kedua: Dict[str, Any],
                   jendela: Optional[List[int]] = None) -> Optional[str]:
    """Catatan bila selisih rata-rata MAPE dua metode teratas kecil dibanding sebarannya.

    Sebaran = simpangan baku selisih MAPE per jendela pada titik awal yang sama
    (berpasangan). Jendela yang dipakai = ``jendela`` (dasar peringkat, yaitu
    jendela bersama semua metode) bila diberikan, selain itu titik awal yang
    diuji kedua metode; bila < 2, dipakai SD terbesar kedua metode.
    Pilihan dianggap tidak stabil bila |selisih rata-rata| < sebaran tersebut.
    """
    selisih_rata = abs(kedua["mape"] - pertama["mape"])
    bersama = sorted(set(pertama["mape_per_jendela"]) & set(kedua["mape_per_jendela"]))
    if jendela and len(jendela) >= 2:
        bersama = [t for t in jendela if t in bersama]
    if len(bersama) >= 2:
        d = np.array([kedua["mape_per_jendela"][t] - pertama["mape_per_jendela"][t] for t in bersama])
        selisih_rata = abs(float(d.mean()))  # selisih pada jendela yang sama
        sebaran = float(d.std(ddof=1))
        menang = int((d > 0).sum())
        rincian = (f"{pertama['metode']} lebih baik di {menang} dari {len(bersama)} jendela yang diuji "
                   f"kedua metode; SD selisih per jendela {sebaran:.2f} poin")
    else:
        sebaran = max(v for v in (pertama["mape_std"], kedua["mape_std"], 0.0) if v is not None)
        rincian = f"SD MAPE terbesar {sebaran:.2f} poin"
    if selisih_rata < sebaran:
        return (
            f"Pilihan metode tidak stabil: selisih rata-rata MAPE {pertama['metode']} dan "
            f"{kedua['metode']} hanya {selisih_rata:.2f} poin, lebih kecil dari sebarannya ({rincian}). "
            "Kedua metode praktis setara; metode terpilih bisa berganti bila data bertambah."
        )
    return None


def forecast_donations(monthly_df: pd.DataFrame, periods: int = 12) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Meramalkan penerimaan donasi bulanan dengan metode terbaik hasil backtest bergulir.

    Args:
        monthly_df: DataFrame dengan kolom ['periode_str', 'total_dana'] terurut waktu.
        periods: Jumlah bulan proyeksi (default 12)

    Returns:
        (forecast_df, meta). ``meta`` berisi antara lain:
          - metode / kode_metode: metode terpilih (label jujur)
          - mape: RATA-RATA MAPE lintas titik awal metode terpilih (float, %), atau None
          - mape_median, mape_terburuk, mape_std, n_jendela: sebaran MAPE metode terpilih
          - mape_keterangan: cara MAPE dihitung / alasan tidak tersedia
          - bulan_uji: horizon H; bulan_latih: bulan latih pada titik awal terbaru
          - perbandingan: list dict per kandidat (mape, mape_median, mape_terburuk, mape_std,
            n_jendela, n_gagal, titik_awal, mape_per_jendela, status, andal, terpilih)
          - dasar_pemilihan, peringatan_keandalan, catatan_stabilitas
          - fallback / fallback_alasan: kandidat yang tidak tersedia/tidak andal karena
            statsmodels tidak ada atau model gagal/tidak konvergen
          - warning: gabungan catatan untuk pengguna
          - n_bulan: jumlah bulan data historis
    """
    n = 0 if monthly_df is None or monthly_df.empty else len(monthly_df)
    if n < _MIN_BULAN_DATA:
        return _hasil_kosong(n)

    y = monthly_df["total_dana"].to_numpy(dtype=float)
    tgl = _tanggal_bulanan(monthly_df)
    tgl_depan = pd.date_range(tgl[-1] + pd.DateOffset(months=1), periods=periods, freq="MS")

    perbandingan, h = bandingkan_metode(y, tgl, tgl_depan)
    tersedia, jendela_bersama = urutkan_kandidat([b for b in perbandingan if b["tersedia"]])
    jendela_keluar = jendela_dikeluarkan_karena_gagal(tersedia, jendela_bersama) if jendela_bersama else {}
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
            sebab = "pustaka statsmodels tidak dapat diimpor" if isinstance(exc, ImportError) else str(exc)
            b["status"] = f"lolos backtest tetapi gagal dilatih pada seluruh data: {sebab}"
            catatan.append(f"PERINGATAN: {b['metode']} gagal dilatih pada seluruh data ({sebab}).")

    titik = titik_awal_backtest(n)
    catatan_stabilitas = None
    if terpilih is not None:
        terpilih["terpilih"] = True
        kode = terpilih["kode"]
        mape = terpilih["mape"]
        mape_ket = (
            f"MAPE = rata-rata dari backtest bergulir: {terpilih['n_jendela']} titik awal "
            f"(bulan latih {terpilih['titik_awal'][0]}-{terpilih['titik_awal'][-1]}), "
            f"masing-masing memprediksi {h} bulan ke depan."
        )
        if terpilih["n_gagal"]:
            mape_ket += (
                f" {terpilih['n_gagal']} titik awal lain gagal dilatih dan tidak ikut dihitung "
                f"({terpilih['n_jendela']} dinilai dari {terpilih['n_jendela'] + terpilih['n_gagal']} dicoba)."
            )
        lain = [b for b in tersedia if b is not terpilih]
        if jendela_bersama:
            dasar = (
                f"Dipilih karena rata-rata MAPE terkecil pada {len(jendela_bersama)} jendela bersama "
                f"(bulan latih {jendela_bersama[0]}-{jendela_bersama[-1]}) yang dapat diuji semua "
                f"{len(tersedia)} metode: {terpilih['mape_bersama']:.2f}%"
            )
            if lain:
                dasar += "; pembanding: " + ", ".join(f"{b['metode']} {b['mape_bersama']:.2f}%" for b in lain)
            dasar += (
                f". MAPE yang ditampilkan ({mape:.2f}%) adalah rata-rata seluruh {terpilih['n_jendela']} "
                f"jendela yang dinilai untuk metode terpilih."
            )
            if jendela_keluar:
                dasar += (
                    " Titik awal " + ", ".join(str(t) for t in jendela_keluar)
                    + " dikeluarkan dari jendela bersama untuk semua metode karena ada metode yang gagal di sana."
                )
        else:
            dasar = (
                f"Dipilih karena rata-rata MAPE backtest bergulir terkecil ({mape:.2f}%) "
                f"dari {len(tersedia)} metode yang dapat diuji"
            )
            if lain:
                dasar += "; pembanding: " + ", ".join(f"{b['metode']} {b['mape']:.2f}%" for b in lain)
            dasar += "."
            if any(b["titik_awal"] != terpilih["titik_awal"] for b in lain):
                dasar += (
                    " Catatan: jendela bersama semua metode kurang dari 2, sehingga rata-rata dihitung pada "
                    "jendela masing-masing dan perbandingan tidak sepenuhnya setara."
                )
        if lain:
            catatan_stabilitas = cek_stabilitas(terpilih, lain[0], jendela_bersama)
            if catatan_stabilitas:
                catatan.append("CATATAN: " + catatan_stabilitas)
    else:
        kode = _METODE_SEDERHANA
        pred, residual = _METODE[kode].fungsi(y, tgl, tgl_depan)
        mape = None
        if perbandingan:
            mape_ket = "MAPE tidak tersedia: tidak ada metode yang dapat diuji dengan backtest bergulir pada data ini."
        else:
            mape_ket = (
                f"MAPE tidak tersedia: data {n} bulan terlalu pendek untuk backtest bergulir "
                f"(butuh minimal {_MIN_BULAN_DATA + _MIN_HORIZON + MIN_TITIK_AWAL - 1} bulan)."
            )
        dasar = "Backtest tidak dapat dilakukan, sehingga dipakai metode paling sederhana."
        catatan.append(
            "Proyeksi berupa rata-rata 3 bulan terakhir; akurasinya belum dapat diukur dan pola musiman "
            "(mis. Ramadan) belum tertangkap."
        )

    peringatan_keandalan = None
    if terpilih is not None and mape > BATAS_MAPE_ANDAL:
        peringatan_keandalan = (
            f"Rata-rata MAPE backtest metode terpilih {mape:.2f}% (di atas {BATAS_MAPE_ANDAL:.0f}%). "
            "Proyeksi belum dapat diandalkan untuk perencanaan; gunakan hanya sebagai gambaran kasar."
        )
        catatan.append("PERINGATAN: " + peringatan_keandalan)

    forecast_vals = np.maximum(np.asarray(pred, dtype=float), 0)
    bias_per_horizon: List[Dict[str, Any]] = []
    proyeksi_tanpa_koreksi = forecast_vals.copy()
    koreksi_bias: Dict[str, Any] = {
        "dipakai": False, "alasan": "backtest tidak dapat dilakukan", "uji": {}, "faktor_per_horizon": []}
    if terpilih is None:
        lower_vals = upper_vals = np.full(len(forecast_vals), np.nan)
        rincian_selang = [{"langkah": i + 1, "n_galat": 0, "status": "di luar cakupan backtest"}
                          for i in range(len(forecast_vals))]
        selang_ket = "Selang tidak tersedia: backtest tidak dapat dilakukan sehingga galat proyeksi belum terukur."
    else:
        rinci = rasio_per_horizon_rinci(_METODE[kode], y, tgl, min(periods, MAKS_HORIZON_SELANG))
        rasio_terbaru = terbaru(rinci, n)
        bias_per_horizon = ringkas_bias(rasio_terbaru)
        uji = uji_koreksi_bertingkat(rinci)
        faktor_h = {}
        for hh in sorted(rasio_terbaru):
            f, st = faktor_koreksi(rasio_terbaru[hh])
            faktor_h[hh] = (f if uji["dipakai"] else 1.0, st, len(rasio_terbaru[hh]), f)
        koreksi_bias = {
            "dipakai": uji["dipakai"],
            "alasan": uji["alasan"],
            "uji": {k: v for k, v in uji.items() if k not in ("dipakai", "alasan")},
            "faktor_per_horizon": [
                {"langkah": hh, "faktor": round(f_dipakai, 4), "faktor_dihitung": round(f_hit, 4),
                 "n_rasio": n_r, "status": st}
                for hh, (f_dipakai, st, n_r, f_hit) in faktor_h.items()
            ],
        }
        if uji["dipakai"]:
            proyeksi_tanpa_koreksi = forecast_vals.copy()
            faktor_bulan = np.array([faktor_h.get(i + 1, (1.0,))[0] for i in range(len(forecast_vals))])
            forecast_vals = forecast_vals * faktor_bulan
            # Selang dari galat yang SUDAH dikoreksi: aktual / (f x prediksi) - 1
            galat_h = {hh: [r / faktor_h[hh][0] - 1 for r in v] for hh, v in rasio_terbaru.items()}
        else:
            galat_h = {hh: [r - 1 for r in v] for hh, v in rasio_terbaru.items()}
        lower_vals, upper_vals, rincian_selang = selang_per_horizon(forecast_vals, galat_h)
        ada = [r["langkah"] for r in rincian_selang if r["status"] == "tersedia"]
        luar = [r["langkah"] for r in rincian_selang if r["status"] == "di luar cakupan backtest"]
        kurang = [r["langkah"] for r in rincian_selang if r["status"].startswith("tidak tersedia")]
        alfa = (1 - LEVEL_SELANG) / 2
        if ada:
            selang_ket = (
                f"{LABEL_SELANG}: untuk tiap bulan proyeksi ke-h dipakai kuantil {alfa:.0%} dan {1 - alfa:.0%} "
                f"galat relatif backtest bergulir metode terpilih pada langkah horizon h yang sama "
                f"(maks {MAKS_TITIK_AWAL} titik awal terbaru per langkah). Selang tersedia untuk bulan ke-"
                f"{_rentang(ada)}."
            )
        else:
            selang_ket = "Selang tidak tersedia untuk semua bulan proyeksi."
        if kurang:
            selang_ket += (
                f" Bulan ke-{_rentang(kurang)}: selang tidak tersedia karena galat backtest kurang dari "
                f"{MIN_SAMPEL_SELANG} per langkah."
            )
        if luar:
            selang_ket += (
                f" Bulan ke-{_rentang(luar)}: di luar cakupan backtest (data belum cukup untuk menguji "
                "proyeksi sejauh itu), sehingga tanpa selang."
            )
    konsistensi = periksa_konsistensi_selang(forecast_vals, lower_vals, upper_vals, bias_per_horizon)
    if konsistensi["peringatan"]:
        catatan.append("PERINGATAN: " + konsistensi["peringatan"])
    selang_tersedia = bool(np.isfinite(lower_vals).any())
    if not selang_tersedia or np.isnan(lower_vals).any():
        catatan.append(selang_ket)

    df_forecast = pd.DataFrame({
        "periode": [d.strftime("%Y-%m") for d in tgl_depan],
        "proyeksi": forecast_vals,
        "batas_bawah": lower_vals,
        "batas_atas": upper_vals,
        "status_selang": [r["status"] for r in rincian_selang],
        "proyeksi_tanpa_koreksi": proyeksi_tanpa_koreksi,
        "proyeksi_di_dalam_selang": konsistensi["di_dalam_selang"],
    })

    for b in perbandingan:
        for k in ("gangguan", "nonaktif", "_galat_relatif", "_alasan_gagal"):
            b.pop(k, None)
        b.setdefault("mape_bersama", None)

    pilih = terpilih or {}
    meta = {
        "metode": _METODE[kode].label,
        "kode_metode": kode,
        "warning": " ".join(catatan),
        "mape": mape,
        "mape_median": pilih.get("mape_median"),
        "mape_terbaik": pilih.get("mape_terbaik"),
        "mape_terburuk": pilih.get("mape_terburuk"),
        "mape_std": pilih.get("mape_std"),
        "n_jendela": pilih.get("n_jendela", 0),
        "mape_keterangan": mape_ket,
        "bulan_uji": h if mape is not None else 0,
        "bulan_latih": titik[-1] if (mape is not None and titik) else n,
        "fallback": fallback_alasan is not None,
        "fallback_alasan": fallback_alasan,
        "peringatan_keandalan": peringatan_keandalan,
        "catatan_stabilitas": catatan_stabilitas,
        "jendela_bersama": jendela_bersama,
        "jendela_dikeluarkan": jendela_keluar,
        "lingkungan": versi_lingkungan(),
        "selang_tersedia": selang_tersedia,
        "selang_label": LABEL_SELANG if selang_tersedia else None,
        "selang_keterangan": selang_ket,
        "selang_per_bulan": rincian_selang,
        "bias_per_horizon": bias_per_horizon,
        "koreksi_bias": koreksi_bias,
        "konsistensi_selang": konsistensi,
        "perbandingan": perbandingan,
        "dasar_pemilihan": dasar,
        "n_bulan": n,
    }
    return df_forecast, meta


def _fmt_persen(v: Optional[float]) -> str:
    return MAPE_TIDAK_TERSEDIA if v is None else f"{v:.2f}%"


def tabel_perbandingan(meta: Optional[Dict[str, Any]], lengkap: bool = False,
                       numerik: bool = False) -> pd.DataFrame:
    """Tabel perbandingan MAPE backtest bergulir siap tampil.

    Args:
        lengkap: tambah kolom median, simpangan baku, dan jumlah gagal (UI/Excel).
        numerik: kolom MAPE berupa angka (persen) alih-alih teks (untuk Excel).
    """
    baris = (meta or {}).get("perbandingan") or []

    def fmt(v):
        if numerik:
            return v
        return MAPE_TIDAK_TERSEDIA if v is None else f"{v:.2f}%"

    def status(b):
        return "TERPILIH" if b["terpilih"] else b["status"]

    hasil = []
    for b in baris:
        r = {"Metode": b["metode"], "Rata-rata MAPE": fmt(b["mape"])}
        if lengkap:
            r["Median"] = fmt(b["mape_median"])
        r["Terburuk"] = fmt(b["mape_terburuk"])
        if lengkap:
            r["Rata-rata (jendela bersama)"] = fmt(b.get("mape_bersama"))
        if lengkap:
            r["SD"] = b["mape_std"] if numerik else ("-" if b["mape_std"] is None else f"{b['mape_std']:.2f}")
        r["Jendela dinilai"] = b["n_jendela"]
        r["Gagal"] = b["n_gagal"]
        r["Status"] = status(b)
        hasil.append(r)
    return pd.DataFrame(hasil)
