"""Tes peramalan: data kosong, pendek, 12-24 bulan, >= 24 bulan, dan kejujuran MAPE."""
import sys

import numpy as np
import pandas as pd
import pytest

from src import forecasting as fc
from src.forecasting import (
    METODE_HOLT_WINTERS,
    METODE_RATA_BERGERAK,
    METODE_TIDAK_CUKUP,
    METODE_TREN_LINIER,
    METODE_TREN_MUSIMAN,
    forecast_donations,
    format_mape,
)

ANGKA_KARANGAN_LAMA = {18.5, 12.4, 14.2, 50.0}


def _bulanan(n, seed=0, mulai="2021-01"):
    rng = np.random.default_rng(seed)
    periode = pd.period_range(mulai, periods=n, freq="M")
    t = np.arange(n)
    musiman = 1 + 0.4 * np.sin(2 * np.pi * (t % 12) / 12)
    nilai = (100_000_000 + 1_000_000 * t) * musiman * rng.normal(1, 0.05, n)
    return pd.DataFrame({"periode_str": periode.astype(str), "total_dana": nilai})


def _mape_manual(y, pred):
    y, pred = np.asarray(y, float), np.maximum(np.asarray(pred, float), 0)
    return round(float(np.mean(np.abs((y - pred) / y)) * 100), 2)


def _cek_tidak_karangan(meta):
    assert meta["mape"] is None or meta["mape"] not in ANGKA_KARANGAN_LAMA


class TestDataKosongDanPendek:
    def test_data_kosong(self):
        df, meta = forecast_donations(pd.DataFrame())
        assert df.empty
        assert meta["mape"] is None
        assert meta["metode"] == METODE_TIDAK_CUKUP
        assert format_mape(meta) == "tidak tersedia"

    def test_dua_bulan(self):
        df, meta = forecast_donations(_bulanan(2))
        assert df.empty and meta["mape"] is None

    def test_lima_bulan_tanpa_backtest(self):
        df, meta = forecast_donations(_bulanan(5), periods=6)
        assert len(df) == 6
        assert meta["metode"] == METODE_RATA_BERGERAK
        assert meta["mape"] is None
        assert "terlalu pendek" in meta["mape_keterangan"]

    def test_delapan_bulan_backtest_manual(self):
        data = _bulanan(8)
        df, meta = forecast_donations(data)
        y = data["total_dana"].to_numpy()
        # 3 bulan latih (minimal) -> 5 bulan uji; prediksi = rata-rata 3 bulan latih terakhir
        n_uji = 5
        pred = np.full(n_uji, y[:3].mean())
        assert meta["bulan_uji"] == n_uji
        assert meta["mape"] == pytest.approx(_mape_manual(y[-n_uji:], pred))
        assert df["proyeksi"].iloc[0] == pytest.approx(y[-3:].mean())
        _cek_tidak_karangan(meta)

    def test_input_tidak_dimodifikasi(self):
        data = _bulanan(15)
        kolom = list(data.columns)
        forecast_donations(data)
        assert list(data.columns) == kolom


class TestDuaBelasSampaiDuaPuluhEmpat:
    def test_dua_belas_bulan_mape_tidak_tersedia(self):
        df, meta = forecast_donations(_bulanan(12))
        assert meta["metode"] == METODE_TREN_MUSIMAN
        assert len(df) == 12
        assert meta["mape"] is None

    def test_delapan_belas_bulan_backtest(self):
        data = _bulanan(18)
        _, meta = forecast_donations(data)
        assert meta["metode"] == METODE_TREN_MUSIMAN
        assert meta["bulan_uji"] == 6
        y = data["total_dana"].to_numpy()
        bulan = pd.to_datetime(data["periode_str"]).dt.month.tolist()
        pred, _ = fc._pred_tren_musiman(y[:-6], bulan[:-6], bulan[-6:])
        assert meta["mape"] == pytest.approx(_mape_manual(y[-6:], pred))
        _cek_tidak_karangan(meta)

    def test_mape_berubah_mengikuti_data(self):
        _, m1 = forecast_donations(_bulanan(18, seed=1))
        _, m2 = forecast_donations(_bulanan(18, seed=2))
        assert m1["mape"] != m2["mape"]


class TestDuaPuluhEmpatKeAtas:
    def test_holt_winters_dipakai(self):
        pytest.importorskip("statsmodels")
        df, meta = forecast_donations(_bulanan(36))
        assert meta["metode"] == METODE_HOLT_WINTERS
        assert not meta["fallback"]
        assert len(df) == 12
        assert (df["batas_bawah"] <= df["proyeksi"]).all()
        assert (df["proyeksi"] <= df["batas_atas"]).all()
        assert meta["bulan_uji"] == 6
        assert isinstance(meta["mape"], float)
        _cek_tidak_karangan(meta)

    def test_dua_puluh_empat_bulan_mape_tidak_tersedia(self):
        pytest.importorskip("statsmodels")
        _, meta = forecast_donations(_bulanan(24))
        assert meta["mape"] is None

    def test_mape_tidak_dibatasi_50_persen(self):
        pytest.importorskip("statsmodels")
        data = _bulanan(36)
        # Lonjakan ekstrem di periode uji -> galat besar harus dilaporkan apa adanya
        data.loc[data.index[-6:], "total_dana"] *= 10
        _, meta = forecast_donations(data)
        assert meta["mape"] is not None and meta["mape"] > 50

    def test_statsmodels_tidak_terpasang(self, monkeypatch):
        for mod in [m for m in sys.modules if m == "statsmodels" or m.startswith("statsmodels.")]:
            monkeypatch.delitem(sys.modules, mod)
        monkeypatch.setitem(sys.modules, "statsmodels", None)
        df, meta = forecast_donations(_bulanan(36))
        assert meta["metode"] == METODE_TREN_LINIER
        assert meta["fallback"] is True
        assert "statsmodels" in meta["fallback_alasan"]
        assert "PERINGATAN" in meta["warning"]
        assert len(df) == 12
        _cek_tidak_karangan(meta)

    def test_model_gagal_konvergen(self, monkeypatch):
        def _gagal(*a, **k):
            raise fc._ModelGagal("model tidak konvergen (simulasi)")
        monkeypatch.setitem(fc._METODE, "holt_winters", (_gagal, METODE_HOLT_WINTERS))
        _, meta = forecast_donations(_bulanan(36))
        assert meta["metode"] == METODE_TREN_LINIER
        assert "konvergen" in meta["fallback_alasan"]


def test_format_mape():
    assert format_mape({"mape": 12.345}) == "12.35%"
    assert format_mape({"mape": None}) == "tidak tersedia"
    assert format_mape(None) == "tidak tersedia"


def test_tidak_ada_angka_hardcode_di_sumber():
    import inspect
    sumber = inspect.getsource(fc)
    for angka in ("18.5", "12.4", "14.2", "min(50"):
        assert angka not in sumber
