"""Tes penanda Ramadan/Idulfitri dan kandidat tren + Ramadan."""
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from src import forecasting as fc
from src.kalender_hijriah import PERKIRAAN_RAMADAN, TAHUN_AKHIR, TAHUN_AWAL, cek_cakupan, fitur_ramadan


def _bulan(mulai, n):
    return pd.date_range(mulai, periods=n, freq="MS")


def test_tabel_konsisten():
    for mulai, syawal in PERKIRAAN_RAMADAN:
        assert 29 <= (syawal - mulai).days <= 30          # Ramadan 29/30 hari
    awal = [m for m, _ in PERKIRAAN_RAMADAN]
    selisih = [(b - a).days for a, b in zip(awal, awal[1:])]
    assert all(352 <= d <= 356 for d in selisih)          # tahun Hijriah ~354 hari


def test_porsi_ramadan_per_tahun_berjumlah_satu():
    f = fitur_ramadan(_bulan("2022-01", 36))
    for tahun in (2022, 2023, 2024):
        assert f.loc[str(tahun), "porsi_ramadan"].sum() == pytest.approx(1.0)
        assert f.loc[str(tahun), "idulfitri"].sum() == 1


def test_fitur_bulan_tertentu():
    f = fitur_ramadan(_bulan("2024-02", 4))  # Feb..Mei 2024; Ramadan 12 Mar - 9 Apr, Idulfitri 10 Apr
    assert f.loc["2024-02-01", "porsi_ramadan"] == 0
    assert f.loc["2024-03-01", "porsi_ramadan"] == pytest.approx(20 / 29)
    assert f.loc["2024-04-01", "porsi_ramadan"] == pytest.approx(9 / 29)
    assert f.loc["2024-04-01", "idulfitri"] == 1
    assert f.loc["2024-03-01", "idulfitri"] == 0


def test_cakupan():
    assert cek_cakupan(_bulan(f"{TAHUN_AWAL}-01", 12)) is None
    pesan = cek_cakupan(_bulan(f"{TAHUN_AKHIR}-06", 12))
    assert pesan and str(TAHUN_AKHIR + 1) in pesan


def _data(nilai, mulai):
    periode = pd.period_range(mulai, periods=len(nilai), freq="M")
    return pd.DataFrame({"periode_str": periode.astype(str), "total_dana": np.asarray(nilai, float)})


def _baris(meta, kode):
    return next(b for b in meta["perbandingan"] if b["kode"] == kode)


def test_dinonaktifkan_di_luar_tabel():
    _, meta = fc.forecast_donations(_data(np.linspace(100, 200, 30), "2012-01"))
    b = _baris(meta, "tren_ramadan")
    assert b["mape"] is None
    assert b["status"].startswith("dinonaktifkan: tabel perkiraan Ramadan hanya mencakup")
    assert "dinonaktifkan" in meta["warning"]


def test_dinonaktifkan_bila_proyeksi_melewati_tabel():
    _, meta = fc.forecast_donations(_data(np.linspace(100, 200, 24), "2029-01"))
    assert "2031" in _baris(meta, "tren_ramadan")["status"]


def test_pola_ramadan_murni_dipilih_dan_tepat():
    """Data = 100 + 2t + 300*porsi_ramadan persis -> regresi Ramadan MAPE ~0 dan terpilih."""
    tgl = _bulan("2021-01", 40)  # uji: 6 bulan terakhir mencakup Ramadan 2024 (Mar-Apr)
    f = fitur_ramadan(tgl)
    y = 100 + 2 * np.arange(40) + 300 * f["porsi_ramadan"].to_numpy()
    _, meta = fc.forecast_donations(_data(y, "2021-01"))
    assert _baris(meta, "tren_ramadan")["mape"] == pytest.approx(0, abs=1e-6)
    assert meta["kode_metode"] == "tren_ramadan"


def test_tanpa_ramadan_di_data_latih():
    tgl = _bulan("2023-05", 12)  # Mei 2023 - Apr 2024; uji 6 bln terakhir -> latih Mei-Okt 2023 tanpa Ramadan
    y = np.linspace(100, 150, 12)
    with pytest.raises(fc._TidakMemenuhiSyarat):
        fc._pred_tren_ramadan(y[:6], tgl[:6], tgl[6:])
