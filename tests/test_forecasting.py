"""Tes peramalan: data kosong/pendek, pemilihan metode lewat backtest, kejujuran MAPE."""
import inspect
import sys

import numpy as np
import pandas as pd
import pytest

from src import forecasting as fc
from src.forecasting import (
    METODE_HOLT_WINTERS,
    METODE_RATA_BERGERAK,
    METODE_TIDAK_CUKUP,
    forecast_donations,
    format_mape,
    tabel_perbandingan,
)

ANGKA_KARANGAN_LAMA = {18.5, 12.4, 14.2, 50.0}


def _bulanan(n, seed=0, mulai="2021-01"):
    rng = np.random.default_rng(seed)
    periode = pd.period_range(mulai, periods=n, freq="M")
    t = np.arange(n)
    musiman = 1 + 0.4 * np.sin(2 * np.pi * (t % 12) / 12)
    nilai = (100_000_000 + 1_000_000 * t) * musiman * rng.normal(1, 0.05, n)
    return pd.DataFrame({"periode_str": periode.astype(str), "total_dana": nilai})


def _dari_nilai(nilai, mulai="2021-01"):
    periode = pd.period_range(mulai, periods=len(nilai), freq="M")
    return pd.DataFrame({"periode_str": periode.astype(str), "total_dana": np.asarray(nilai, dtype=float)})


def _mape_manual(y, pred):
    y, pred = np.asarray(y, float), np.maximum(np.asarray(pred, float), 0)
    return round(float(np.mean(np.abs((y - pred) / y)) * 100), 2)


def _baris(meta, kode):
    return next(b for b in meta["perbandingan"] if b["kode"] == kode)


class TestDataKosongDanPendek:
    def test_data_kosong(self):
        df, meta = forecast_donations(pd.DataFrame())
        assert df.empty
        assert meta["mape"] is None
        assert meta["metode"] == METODE_TIDAK_CUKUP
        assert meta["perbandingan"] == []
        assert format_mape(meta) == "tidak tersedia"

    def test_none(self):
        df, meta = forecast_donations(None)
        assert df.empty and meta["mape"] is None

    def test_dua_bulan(self):
        df, meta = forecast_donations(_bulanan(2))
        assert df.empty and meta["mape"] is None

    @pytest.mark.parametrize("n", [3, 4, 5])
    def test_terlalu_pendek_untuk_backtest(self, n):
        df, meta = forecast_donations(_bulanan(n), periods=6)
        assert len(df) == 6
        assert meta["metode"] == METODE_RATA_BERGERAK  # metode sederhana yang sudah ada
        assert meta["mape"] is None
        assert format_mape(meta) == "tidak tersedia"
        assert "terlalu pendek" in meta["mape_keterangan"]
        assert meta["perbandingan"] == []
        assert meta["peringatan_keandalan"] is None

    def test_input_tidak_dimodifikasi(self):
        data = _bulanan(15)
        salinan = data.copy()
        forecast_donations(data)
        pd.testing.assert_frame_equal(data, salinan)


class TestJendelaBacktest:
    @pytest.mark.parametrize("n, uji", [(5, 0), (6, 3), (8, 5), (9, 6), (36, 6)])
    def test_jumlah_bulan_uji(self, n, uji):
        assert fc.jumlah_bulan_uji(n) == uji

    def test_semua_kandidat_diuji_pada_bulan_yang_sama(self):
        _, meta = forecast_donations(_bulanan(36))
        diuji = [b for b in meta["perbandingan"] if b["mape"] is not None]
        assert len(diuji) >= 4
        assert {(b["bulan_latih"], b["bulan_uji"]) for b in diuji} == {(30, 6)}

    def test_syarat_data_per_kandidat(self):
        _, meta = forecast_donations(_bulanan(18))
        assert _baris(meta, "rata_bergerak")["mape"] is not None
        assert _baris(meta, "tren_musiman")["mape"] is not None      # 12 bulan latih cukup
        assert _baris(meta, "naif_musiman")["mape"] is None          # butuh data >= 24 bulan
        assert "24 bulan" in _baris(meta, "naif_musiman")["status"]
        assert _baris(meta, "holt_winters")["mape"] is None          # butuh 24 bulan latih
        assert "tidak diuji" in _baris(meta, "holt_winters")["status"]

    def test_naif_musiman_ikut_bila_24_bulan(self):
        _, meta = forecast_donations(_bulanan(24))
        assert _baris(meta, "naif_musiman")["mape"] is not None


class TestPemilihanMetode:
    def test_terpilih_adalah_mape_terkecil(self):
        _, meta = forecast_donations(_bulanan(36))
        diuji = [b for b in meta["perbandingan"] if b["mape"] is not None]
        terkecil = min(diuji, key=lambda b: b["mape"])
        assert meta["kode_metode"] == terkecil["kode"]
        assert meta["mape"] == terkecil["mape"]
        assert [b["kode"] for b in meta["perbandingan"] if b["terpilih"]] == [terkecil["kode"]]

    def test_mape_rata_bergerak_dihitung_manual(self):
        data = _bulanan(8)
        y = data["total_dana"].to_numpy()
        _, meta = forecast_donations(data)
        # 8 bulan -> 5 bulan uji, 3 bulan latih; prediksi = rata-rata 3 bulan latih
        assert _baris(meta, "rata_bergerak")["mape"] == pytest.approx(_mape_manual(y[-5:], np.full(5, y[:3].mean())))

    def test_mape_tren_musiman_dihitung_manual(self):
        data = _bulanan(18)
        y = data["total_dana"].to_numpy()
        tgl = pd.to_datetime(data["periode_str"])
        pred, _ = fc._pred_tren_musiman(y[:-6], tgl[:-6], tgl[-6:])
        _, meta = forecast_donations(data)
        assert _baris(meta, "tren_musiman")["mape"] == pytest.approx(_mape_manual(y[-6:], pred))

    def test_mape_berubah_mengikuti_data(self):
        _, m1 = forecast_donations(_bulanan(18, seed=1))
        _, m2 = forecast_donations(_bulanan(18, seed=2))
        assert m1["mape"] != m2["mape"]

    def test_proyeksi_dari_metode_terpilih_dilatih_ulang_pada_seluruh_data(self):
        data = _bulanan(36)
        df, meta = forecast_donations(data)
        y = data["total_dana"].to_numpy()
        tgl = pd.to_datetime(data["periode_str"])
        tgl_depan = pd.date_range(tgl.iloc[-1] + pd.DateOffset(months=1), periods=12, freq="MS")
        pred, _ = fc._METODE[meta["kode_metode"]].fungsi(y, pd.DatetimeIndex(tgl), tgl_depan)
        assert np.allclose(df["proyeksi"], np.maximum(pred, 0))
        assert (df["batas_bawah"] <= df["proyeksi"]).all()
        assert (df["proyeksi"] <= df["batas_atas"]).all()

    def test_tabel_perbandingan(self):
        _, meta = forecast_donations(_bulanan(36))
        tabel = tabel_perbandingan(meta)
        assert list(tabel.columns) == ["Metode", "MAPE backtest", "Bulan latih", "Bulan uji", "Status"]
        assert (tabel["Status"] == "TERPILIH").sum() == 1
        assert meta["metode"] in meta["dasar_pemilihan"] or "MAPE backtest terkecil" in meta["dasar_pemilihan"]


class TestHoltWinters:
    def test_holt_winters_diuji(self):
        pytest.importorskip("statsmodels")
        _, meta = forecast_donations(_bulanan(36))
        hw = _baris(meta, "holt_winters")
        assert isinstance(hw["mape"], float)
        assert hw["mape"] not in ANGKA_KARANGAN_LAMA
        assert not meta["fallback"]

    def test_mape_tidak_dibatasi_50_persen(self):
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
        hw = _baris(meta, "holt_winters")
        assert hw["mape"] is None
        assert "statsmodels tidak dapat diimpor" in hw["status"]
        assert meta["metode"] != METODE_HOLT_WINTERS
        assert meta["fallback"] is True
        assert "statsmodels" in meta["fallback_alasan"]
        assert "PERINGATAN" in meta["warning"]
        assert len(df) == 12

    def test_model_gagal_konvergen(self, monkeypatch):
        def _gagal(*a, **k):
            raise fc._ModelGagal("model tidak konvergen (simulasi)")
        asli = fc._METODE["holt_winters"]
        monkeypatch.setitem(fc._METODE, "holt_winters", fc.Kandidat(asli.kode, asli.label, _gagal, asli.min_latih))
        monkeypatch.setattr(fc, "_KANDIDAT", [fc._METODE[k.kode] for k in fc._KANDIDAT])
        _, meta = forecast_donations(_bulanan(36))
        assert meta["metode"] != METODE_HOLT_WINTERS
        assert "konvergen" in meta["fallback_alasan"]
        assert _baris(meta, "holt_winters")["mape"] is None


def test_format_mape():
    assert format_mape({"mape": 12.345}) == "12.35%"
    assert format_mape({"mape": None}) == "tidak tersedia"
    assert format_mape(None) == "tidak tersedia"


def test_tidak_ada_angka_hardcode_di_sumber():
    sumber = inspect.getsource(fc)
    for angka in ("18.5", "12.4", "14.2", "min(50"):
        assert angka not in sumber
