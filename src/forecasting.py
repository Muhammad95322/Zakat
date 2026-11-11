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
_MIN_BULAN_DATA = 3
# Alias kompatibilitas nama lama
_MAKS_BULAN_UJI = HORIZON_UJI
_MIN_BULAN_UJI = _MIN_HORIZON

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

    galat_relatif: List[float] = []
    alasan_gagal: List[str] = []
    for t in titik_valid:
        try:
            pred = _prediksi_backtest(kandidat, y, tgl, t, h)
        except ImportError as exc:
            baris["status"] = f"tidak tersedia: pustaka statsmodels tidak dapat diimpor ({exc})"
            baris["gangguan"] = True
            return baris
        except _ModelGagal as exc:
            baris["n_gagal"] += 1
            alasan_gagal.append(str(exc))
            continue
        except _TidakMemenuhiSyarat:
            continue  # titik awal ini tidak memenuhi syarat metode (bukan kegagalan)
        aktual = y[t:t + h]
        mape = _hitung_mape(aktual, pred)
        if mape is None:
            continue  # semua aktual 0: MAPE tak terdefinisi untuk jendela ini
        baris["mape_per_jendela"][t] = round(mape, 2)
        mask = pred > 0
        galat_relatif.extend(((aktual[mask] - pred[mask]) / pred[mask]).tolist())

    baris["titik_awal"] = sorted(baris["mape_per_jendela"])
    baris["n_jendela"] = len(baris["titik_awal"])
    baris["_galat_relatif"] = galat_relatif
    baris["_alasan_gagal"] = alasan_gagal
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


def _urutan(kode: str) -> int:
    return [k.kode for k in _KANDIDAT].index(kode)


def cek_stabilitas(pertama: Dict[str, Any], kedua: Dict[str, Any]) -> Optional[str]:
    """Catatan bila selisih rata-rata MAPE dua metode teratas kecil dibanding sebarannya.

    Sebaran = simpangan baku selisih MAPE per jendela pada titik awal yang sama
    (berpasangan); bila titik awal bersama < 2, dipakai SD terbesar kedua metode.
    Pilihan dianggap tidak stabil bila |selisih rata-rata| < sebaran tersebut.
    """
    selisih_rata = abs(kedua["mape"] - pertama["mape"])
    bersama = sorted(set(pertama["mape_per_jendela"]) & set(kedua["mape_per_jendela"]))
    if len(bersama) >= 2:
        d = np.array([kedua["mape_per_jendela"][t] - pertama["mape_per_jendela"][t] for t in bersama])
        sebaran = float(d.std(ddof=1))
        menang = int((d > 0).sum())
        rincian = (f"{pertama['metode']} lebih baik di {menang} dari {len(bersama)} jendela bersama; "
                   f"SD selisih per jendela {sebaran:.2f} poin")
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
    tersedia = sorted(
        (b for b in perbandingan if b["tersedia"]),
        key=lambda b: (b["mape"], _urutan(b["kode"])),
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
        lain = [b for b in tersedia if b is not terpilih]
        dasar = (
            f"Dipilih karena rata-rata MAPE backtest bergulir terkecil ({mape:.2f}%) "
            f"dari {len(tersedia)} metode yang dapat diuji"
        )
        if lain:
            dasar += "; pembanding: " + ", ".join(f"{b['metode']} {b['mape']:.2f}%" for b in lain)
        dasar += "."
        beda_jendela = [b for b in lain if b["titik_awal"] != terpilih["titik_awal"]]
        if beda_jendela:
            dasar += (
                f" Catatan: rata-rata {terpilih['metode']} dihitung pada {terpilih['n_jendela']} jendela "
                f"(bulan latih {terpilih['titik_awal'][0]}-{terpilih['titik_awal'][-1]}), sedangkan "
                + ", ".join(f"{b['metode']} pada {b['n_jendela']} jendela" for b in beda_jendela)
                + "; jendela yang berbeda membuat perbandingan tidak sepenuhnya setara."
            )
        if lain:
            catatan_stabilitas = cek_stabilitas(terpilih, lain[0])
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
        for k in ("gangguan", "nonaktif", "_galat_relatif", "_alasan_gagal"):
            b.pop(k, None)

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
            r["SD"] = b["mape_std"] if numerik else ("-" if b["mape_std"] is None else f"{b['mape_std']:.2f}")
        r["Jendela"] = b["n_jendela"]
        if lengkap:
            r["Gagal"] = b["n_gagal"]
        r["Status"] = status(b)
        hasil.append(r)
    return pd.DataFrame(hasil)
