"""Tes peramalan: data kosong/pendek, backtest bergulir, pemilihan metode, kejujuran MAPE."""
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


def _acak_kasar(n, seed=0, mulai="2021-01"):
    """Deret sangat berisik (lognormal sigma 1) -> semua metode MAPE tinggi."""
    rng = np.random.default_rng(seed)
    periode = pd.period_range(mulai, periods=n, freq="M")
    return pd.DataFrame({"periode_str": periode.astype(str), "total_dana": rng.lognormal(18, 1.0, n)})


def _dari_nilai(nilai, mulai="2021-01"):
    periode = pd.period_range(mulai, periods=len(nilai), freq="M")
    return pd.DataFrame({"periode_str": periode.astype(str), "total_dana": np.asarray(nilai, dtype=float)})


def _mape(aktual, pred):
    aktual, pred = np.asarray(aktual, float), np.maximum(np.asarray(pred, float), 0)
    return float(np.mean(np.abs((aktual - pred) / aktual)) * 100)


def _baris(meta, kode):
    return next(b for b in meta["perbandingan"] if b["kode"] == kode)


def _tgl(data):
    return pd.DatetimeIndex(pd.to_datetime(data["periode_str"]))


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

    @pytest.mark.parametrize("n", [3, 4, 5, 6])
    def test_terlalu_pendek_untuk_backtest_bergulir(self, n):
        df, meta = forecast_donations(_bulanan(n), periods=6)
        assert len(df) == 6
        assert meta["metode"] == METODE_RATA_BERGERAK  # perilaku lama: metode sederhana
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


class TestTitikAwal:
    @pytest.mark.parametrize("n, h", [(6, 0), (7, 3), (8, 4), (9, 5), (10, 6), (36, 6), (120, 6)])
    def test_horizon(self, n, h):
        assert fc.horizon_backtest(n) == h

    @pytest.mark.parametrize("n, harapan", [
        (6, []),
        (7, [3, 4]),
        (10, [3, 4]),
        (18, list(range(3, 13))),
        (36, list(range(19, 31))),
        (120, list(range(103, 115))),
    ])
    def test_titik_awal(self, n, harapan):
        titik = fc.titik_awal_backtest(n)
        assert titik == harapan
        h = fc.horizon_backtest(n)
        assert all(t + h <= n for t in titik)  # tanpa jendela terpotong
        assert len(titik) <= fc.MAKS_TITIK_AWAL

    def test_syarat_latih_per_titik_awal(self):
        _, meta = forecast_donations(_bulanan(36))
        assert _baris(meta, "tren_linier")["titik_awal"] == list(range(19, 31))
        hw = _baris(meta, "holt_winters")
        if hw["n_jendela"]:  # statsmodels tersedia
            # butuh >= 24 bulan latih -> titik 24..30; titik yang gagal konvergen dihitung terpisah
            assert set(hw["titik_awal"]) <= set(range(24, 31))
            assert hw["n_jendela"] + hw["n_gagal"] == 7

    def test_metode_kurang_dari_dua_titik_awal_tidak_diuji(self):
        # n=18: titik 3..12; tren+musiman butuh t >= 12 -> hanya 1 titik
        _, meta = forecast_donations(_bulanan(18))
        b = _baris(meta, "tren_musiman")
        assert b["mape"] is None and b["n_jendela"] == 0
        assert "minimal 2 titik awal" in b["status"]
        assert _baris(meta, "rata_bergerak")["n_jendela"] == 10
        assert "24 bulan" in _baris(meta, "naif_musiman")["status"]

    def test_hanya_sebagian_metode_cukup(self):
        _, meta = forecast_donations(_bulanan(24))  # titik 7..18
        assert _baris(meta, "tren_musiman")["n_jendela"] == 7
        assert _baris(meta, "naif_musiman")["n_jendela"] == 7
        assert _baris(meta, "holt_winters")["n_jendela"] == 0


class TestPemilihanMetode:
    def test_terpilih_adalah_rata_rata_terkecil_pada_jendela_bersama(self):
        _, meta = forecast_donations(_bulanan(36))
        diuji = [b for b in meta["perbandingan"] if b["tersedia"]]
        bersama = sorted(set.intersection(*(set(b["mape_per_jendela"]) for b in diuji)))
        assert meta["jendela_bersama"] == bersama and len(bersama) >= 2
        rata = {b["kode"]: np.mean([b["mape_per_jendela"][t] for t in bersama]) for b in diuji}
        terkecil = min(diuji, key=lambda b: (round(rata[b["kode"]], 2), fc._urutan(b["kode"])))
        assert meta["kode_metode"] == terkecil["kode"]
        assert meta["mape"] == terkecil["mape"]  # yang tampil: rata-rata seluruh jendela metode itu
        assert [b["kode"] for b in meta["perbandingan"] if b["terpilih"]] == [terkecil["kode"]]

    def test_statistik_per_metode(self):
        _, meta = forecast_donations(_bulanan(36))
        for b in meta["perbandingan"]:
            if not b["tersedia"]:
                continue
            nilai = np.array(list(b["mape_per_jendela"].values()))
            assert b["n_jendela"] == len(nilai)
            assert b["mape"] == pytest.approx(round(nilai.mean(), 2))
            assert b["mape_median"] == pytest.approx(round(float(np.median(nilai)), 2))
            assert b["mape_terburuk"] == pytest.approx(round(nilai.max(), 2))
            assert b["mape_std"] == pytest.approx(round(nilai.std(ddof=1), 2))

    def test_rata_bergerak_dihitung_manual(self):
        data = _bulanan(36)
        y = data["total_dana"].to_numpy()
        harapan = np.mean([_mape(y[t:t + 6], np.full(6, y[t - 3:t].mean())) for t in range(19, 31)])
        _, meta = forecast_donations(data)
        assert _baris(meta, "rata_bergerak")["mape"] == pytest.approx(round(harapan, 2))

    def test_mape_berubah_mengikuti_data(self):
        _, m1 = forecast_donations(_bulanan(18, seed=1))
        _, m2 = forecast_donations(_bulanan(18, seed=2))
        assert m1["mape"] != m2["mape"]

    def test_proyeksi_dari_metode_terpilih_dilatih_ulang_pada_seluruh_data(self):
        data = _bulanan(36)
        df, meta = forecast_donations(data)
        y = data["total_dana"].to_numpy()
        tgl = _tgl(data)
        tgl_depan = pd.date_range(tgl[-1] + pd.DateOffset(months=1), periods=12, freq="MS")
        pred, _ = fc._METODE[meta["kode_metode"]].fungsi(y, tgl, tgl_depan)
        assert np.allclose(df["proyeksi"], np.maximum(pred, 0))

    def test_tabel_perbandingan(self):
        _, meta = forecast_donations(_bulanan(36))
        tabel = tabel_perbandingan(meta)
        for kolom in ("Metode", "Rata-rata MAPE", "Terburuk", "Jendela dinilai", "Gagal", "Status"):
            assert kolom in tabel.columns
        assert (tabel["Status"] == "TERPILIH").sum() == 1


class TestPemilihanManual:
    """Data 8 bulan -> horizon 4, titik awal t = 3 dan 4. Hanya rata-rata bergerak dan
    tren linier yang punya >= 2 titik awal, sehingga rata-rata MAPE-nya bisa dihitung manual."""

    def test_tren_linier_menang(self):
        y = [100 + 10 * i for i in range(8)]  # garis lurus sempurna
        _, meta = forecast_donations(_dari_nilai(y))
        # MA t=3: prediksi 110 vs 130,140,150,160; t=4: prediksi 120 vs 140,150,160,170
        mape_t3 = np.mean([20 / 130, 30 / 140, 40 / 150, 50 / 160]) * 100
        mape_t4 = np.mean([20 / 140, 30 / 150, 40 / 160, 50 / 170]) * 100
        ma = _baris(meta, "rata_bergerak")
        assert ma["mape_per_jendela"] == {3: pytest.approx(round(mape_t3, 2)), 4: pytest.approx(round(mape_t4, 2))}
        assert ma["mape"] == pytest.approx(round((round(mape_t3, 2) + round(mape_t4, 2)) / 2, 2), abs=0.01)
        assert _baris(meta, "tren_linier")["mape"] == pytest.approx(0.0, abs=1e-6)
        assert meta["kode_metode"] == "tren_linier"
        assert [b["kode"] for b in meta["perbandingan"] if b["tersedia"]] == ["rata_bergerak", "tren_linier"]

    def test_rata_bergerak_menang(self):
        y = [110, 100, 120, 110, 110, 110, 110, 110]
        _, meta = forecast_donations(_dari_nilai(y))
        # t=3: MA 110 (tepat); linier slope 5, intercept 105 -> 120,125,130,135 vs 110
        # t=4: MA 110 (tepat); linier slope 2, intercept 107 -> 115,117,119,121 vs 110
        lin_t3 = np.mean([10, 15, 20, 25]) / 110 * 100
        lin_t4 = np.mean([5, 7, 9, 11]) / 110 * 100
        lin = _baris(meta, "tren_linier")
        assert lin["mape_per_jendela"][3] == pytest.approx(round(lin_t3, 2))
        assert lin["mape_per_jendela"][4] == pytest.approx(round(lin_t4, 2))
        assert _baris(meta, "rata_bergerak")["mape"] == pytest.approx(0.0)
        assert meta["kode_metode"] == "rata_bergerak"

    def test_seri_dipecah_oleh_kesederhanaan(self):
        _, meta = forecast_donations(_dari_nilai([100] * 8))
        assert _baris(meta, "rata_bergerak")["mape"] == _baris(meta, "tren_linier")["mape"] == 0
        assert meta["kode_metode"] == "rata_bergerak"


class TestHoltWinters:
    def test_holt_winters_diuji(self):
        pytest.importorskip("statsmodels")
        _, meta = forecast_donations(_bulanan(36))
        hw = _baris(meta, "holt_winters")
        assert isinstance(hw["mape"], float)
        assert hw["mape"] not in ANGKA_KARANGAN_LAMA
        assert not meta["fallback"]

    def test_mape_tidak_dibatasi_50_persen(self):
        _, meta = forecast_donations(_acak_kasar(36))
        assert meta["mape"] is not None and meta["mape"] > 50

    def test_statsmodels_tidak_terpasang(self, monkeypatch):
        for mod in [m for m in sys.modules if m == "statsmodels" or m.startswith("statsmodels.")]:
            monkeypatch.delitem(sys.modules, mod)
        monkeypatch.setitem(sys.modules, "statsmodels", None)
        df, meta = forecast_donations(_bulanan(36))
        hw = _baris(meta, "holt_winters")
        assert hw["mape"] is None and hw["n_jendela"] == 0
        assert "statsmodels tidak dapat diimpor" in hw["status"]
        assert meta["metode"] != METODE_HOLT_WINTERS
        assert meta["fallback"] is True
        assert "statsmodels" in meta["fallback_alasan"]
        assert "PERINGATAN" in meta["warning"]
        assert len(df) == 12


def test_format_mape():
    assert format_mape({"mape": 12.345}) == "12.35%"
    assert format_mape({"mape": None}) == "tidak tersedia"
    assert format_mape(None) == "tidak tersedia"


def test_tidak_ada_angka_hardcode_di_sumber():
    sumber = inspect.getsource(fc)
    for angka in ("18.5", "12.4", "14.2", "min(50"):
        assert angka not in sumber


class TestTanpaKebocoranData:
    def test_prediksi_titik_awal_tidak_bergantung_pada_data_setelah_t(self):
        data = _bulanan(36)
        y = data["total_dana"].to_numpy()
        tgl = _tgl(data)
        rng = np.random.default_rng(7)
        for k in fc._KANDIDAT:
            for t in fc.titik_awal_backtest(36):
                if t < k.min_latih:
                    continue
                try:
                    a = fc._prediksi_backtest(k, y, tgl, t, 6)
                except Exception:
                    continue  # kandidat tak tersedia di lingkungan ini
                y_rusak = y.copy()
                y_rusak[t:] = rng.uniform(1, 1e12, len(y) - t)  # ganti semua nilai di luar y[:t]
                b = fc._prediksi_backtest(k, y_rusak, tgl, t, 6)
                assert np.allclose(a, b), (k.kode, t)

    def test_fungsi_hanya_menerima_y_sampai_t(self, monkeypatch):
        dilihat = []
        data = _bulanan(36)
        y_asli = data["total_dana"].to_numpy()

        def mata_mata(kandidat):
            def f(y, tgl, tgl_depan):
                dilihat.append((kandidat.kode, y.copy(), len(tgl), tgl_depan[0] if len(tgl_depan) else None, tgl[-1]))
                return kandidat.fungsi(y, tgl, tgl_depan)
            return fc.Kandidat(kandidat.kode, kandidat.label, f, kandidat.min_latih,
                               kandidat.min_total, kandidat.syarat_total, kandidat.prasyarat)

        monkeypatch.setattr(fc, "_KANDIDAT", [mata_mata(k) for k in fc._KANDIDAT])
        fc.bandingkan_metode(y_asli, _tgl(data))
        assert dilihat, "tidak ada kandidat yang diuji"
        for kode, y, n_tgl, awal_depan, akhir_latih in dilihat:
            t = len(y)
            assert n_tgl == t, kode
            assert np.array_equal(y, y_asli[:t]), kode           # persis y[:t]
            assert awal_depan == akhir_latih + pd.DateOffset(months=1), kode


class TestPeringatanKeandalan:
    def test_mape_terpilih_di_atas_50_persen(self):
        _, meta = forecast_donations(_acak_kasar(36))
        assert meta["mape"] > 50
        assert meta["peringatan_keandalan"] is not None
        assert "belum dapat diandalkan" in meta["peringatan_keandalan"]
        assert meta["peringatan_keandalan"] in meta["warning"]

    def test_tidak_ada_peringatan_bila_di_bawah_50(self):
        _, meta = forecast_donations(_bulanan(36))
        assert meta["mape"] < 50
        assert meta["peringatan_keandalan"] is None

    def test_tidak_ada_peringatan_bila_mape_tidak_tersedia(self):
        _, meta = forecast_donations(_bulanan(4))
        assert meta["mape"] is None and meta["peringatan_keandalan"] is None


class TestSelangDariGalatBacktest:
    def test_hitung_selang_manual(self):
        galat = [i / 10 - 0.5 for i in range(11)]  # -0.5 .. 0.5
        bawah, atas = fc.hitung_selang(np.array([100.0, 200.0]), galat)
        # kuantil 10% = -0.4, 90% = 0.4 (interpolasi linier)
        assert np.allclose(bawah, [60, 120])
        assert np.allclose(atas, [140, 280])

    def test_selang_tidak_pernah_negatif(self):
        bawah, atas = fc.hitung_selang(np.array([100.0, 0.0, -5.0]), [-3.0, -2.5, -2.0] * 4)
        assert (bawah >= 0).all() and (atas >= bawah).all()

    def test_selang_proporsional_terhadap_proyeksi(self):
        df, meta = forecast_donations(_bulanan(36))
        assert meta["selang_tersedia"] is True
        assert meta["selang_label"] == fc.LABEL_SELANG
        rasio_bawah = df["batas_bawah"] / df["proyeksi"]
        rasio_atas = df["batas_atas"] / df["proyeksi"]
        assert np.allclose(rasio_bawah, rasio_bawah.iloc[0])  # kuantil galat yang sama tiap bulan
        assert np.allclose(rasio_atas, rasio_atas.iloc[0])
        assert (df["batas_bawah"] >= 0).all()
        assert (df["batas_atas"] >= df["batas_bawah"]).all()

    def test_tren_sempurna_selang_nol(self):
        df, meta = forecast_donations(_dari_nilai([100 + 10 * i for i in range(12)]))
        assert meta["kode_metode"] == "tren_linier" and meta["selang_tersedia"]
        assert np.allclose(df["batas_bawah"], df["proyeksi"]) and np.allclose(df["batas_atas"], df["proyeksi"])

    def test_galat_terlalu_sedikit_selang_tidak_tersedia(self):
        df, meta = forecast_donations(_bulanan(7))  # H=3, 2 titik awal -> 6 galat < 10
        assert meta["mape"] is not None
        assert meta["selang_tersedia"] is False
        assert "butuh minimal 10" in meta["selang_keterangan"]
        assert df["batas_bawah"].isna().all() and df["batas_atas"].isna().all()
        assert meta["selang_keterangan"] in meta["warning"]

    def test_tanpa_backtest_selang_tidak_tersedia(self):
        df, meta = forecast_donations(_bulanan(5))
        assert meta["selang_tersedia"] is False
        assert "Selang tidak tersedia" in meta["selang_keterangan"]
        assert df["batas_bawah"].isna().all()

    def test_grafik_tanpa_selang_tetap_jalan(self):
        from src.charts import chart_forecasting
        from src.report_charts import chart_peramalan_png
        data = _bulanan(5)
        df, meta = forecast_donations(data)
        assert chart_peramalan_png(data, df, meta["selang_label"]).startswith(b"\x89PNG")
        fig = chart_forecasting(data, df, meta["selang_label"])
        assert all(tr.name != fc.LABEL_SELANG for tr in fig.data)


def _gagal_di(kode, titik_gagal):
    """Bungkus kandidat agar melempar _ModelGagal pada titik awal (panjang latih) tertentu."""
    asli = fc._METODE[kode]

    def f(y, tgl, tgl_depan):
        if len(y) in titik_gagal:
            raise fc._ModelGagal(f"simulasi gagal konvergen pada t={len(y)}")
        return asli.fungsi(y, tgl, tgl_depan)

    return fc.Kandidat(asli.kode, asli.label, f, asli.min_latih, asli.min_total, asli.syarat_total, asli.prasyarat)


def _pasang(monkeypatch, pengganti):
    baru = [pengganti if k.kode == pengganti.kode else k for k in fc._KANDIDAT]
    monkeypatch.setattr(fc, "_KANDIDAT", baru)
    monkeypatch.setattr(fc, "_METODE", {k.kode: k for k in baru})


class TestTidakAndal:
    # Data garis lurus 12 bulan: H=6, titik awal 3..6 (4 titik); tren linier MAPE 0 (terbaik)
    DATA = [100 + 10 * i for i in range(12)]

    def test_gagal_lebih_dari_sepertiga_tidak_andal_dan_tidak_terpilih(self, monkeypatch):
        _pasang(monkeypatch, _gagal_di("tren_linier", {3, 4}))  # gagal 2 dari 4 (> 1/3)
        _, meta = forecast_donations(_dari_nilai(self.DATA))
        lin = _baris(meta, "tren_linier")
        assert lin["andal"] is False and lin["tersedia"] is False and not lin["terpilih"]
        assert lin["n_gagal"] == 2 and lin["n_jendela"] == 2
        assert lin["mape"] == pytest.approx(0.0)  # statistik tetap ditampilkan...
        assert meta["kode_metode"] != "tren_linier"  # ...tetapi tidak dipilih walau MAPE terkecil
        assert lin["status"].startswith("tidak andal: gagal di 2 dari 4 titik awal")
        assert "simulasi gagal konvergen" in lin["status"]
        assert meta["fallback"] and "tidak andal" in meta["fallback_alasan"]

    def test_gagal_tepat_sepertiga_masih_boleh_terpilih(self, monkeypatch):
        data = [100 + 10 * i for i in range(14)]  # titik 3..8 (6 titik)
        _pasang(monkeypatch, _gagal_di("tren_linier", {3, 4}))  # 2 dari 6 = tepat 1/3
        _, meta = forecast_donations(_dari_nilai(data))
        lin = _baris(meta, "tren_linier")
        assert lin["andal"] is True and lin["tersedia"] is True
        assert "gagal di 2 dari 6" in lin["status"]
        assert meta["kode_metode"] == "tren_linier"

    def test_holt_winters_gagal_konvergen_semua_titik(self, monkeypatch):
        def selalu_gagal(*a, **k):
            raise fc._ModelGagal("model tidak konvergen (simulasi)")
        asli = fc._METODE["holt_winters"]
        _pasang(monkeypatch, fc.Kandidat(asli.kode, asli.label, selalu_gagal, asli.min_latih))
        _, meta = forecast_donations(_bulanan(36))
        hw = _baris(meta, "holt_winters")
        assert hw["andal"] is False and hw["n_gagal"] == 7 and hw["mape"] is None
        assert meta["metode"] != METODE_HOLT_WINTERS
        assert "konvergen" in meta["fallback_alasan"]


class TestStabilitas:
    @staticmethod
    def _b(nama, per_jendela):
        nilai = np.array(list(per_jendela.values()), dtype=float)
        return {"metode": nama, "mape": float(nilai.mean()), "mape_std": float(nilai.std(ddof=1)),
                "mape_per_jendela": per_jendela}

    def test_tidak_stabil_bila_pemenang_berganti_antar_jendela(self):
        # A: 10,30,10,30 (rata 20); B: 30,12,30,12 (rata 21): selisih 1, SD selisih per jendela ~20.8
        a = self._b("A", {1: 10, 2: 30, 3: 10, 4: 30})
        b = self._b("B", {1: 30, 2: 12, 3: 30, 4: 12})
        catatan = fc.cek_stabilitas(a, b)
        assert catatan and "tidak stabil" in catatan
        assert "lebih baik di 2 dari 4 jendela yang diuji kedua metode" in catatan

    def test_stabil_bila_selalu_lebih_baik_dengan_selisih_besar(self):
        a = self._b("A", {1: 10, 2: 11, 3: 12, 4: 10})
        b = self._b("B", {1: 30, 2: 32, 3: 31, 4: 33})
        assert fc.cek_stabilitas(a, b) is None

    def test_memakai_jendela_dasar_peringkat(self):
        # Jendela 1-6: A jauh lebih baik; jendela 7-8: A dan B bergantian unggul
        a = self._b("A", {**{t: 10 for t in range(1, 7)}, 7: 10, 8: 30})
        b = self._b("B", {**{t: 60 for t in range(1, 7)}, 7: 30, 8: 12})
        assert fc.cek_stabilitas(a, b) is None  # semua jendela: selisih 37,75 > SD ~23 -> stabil
        catatan = fc.cek_stabilitas(a, b, [7, 8])  # hanya jendela dasar peringkat
        assert catatan and "lebih baik di 1 dari 2 jendela" in catatan

    def test_tanpa_jendela_bersama_pakai_sd_terbesar(self):
        a = self._b("A", {1: 10, 2: 30})
        b = self._b("B", {5: 21, 6: 23})
        assert "SD MAPE terbesar" in fc.cek_stabilitas(a, b)

    def test_catatan_muncul_di_meta_dan_warning(self):
        # Deret zig-zag: rata-rata bergerak & tren linier bergantian unggul antar jendela
        y = [100, 140, 90, 150, 95, 145, 100, 150, 90, 140, 100, 150, 95, 145, 100, 150]
        _, meta = forecast_donations(_dari_nilai(y))
        diuji = sorted((b for b in meta["perbandingan"] if b["tersedia"]), key=lambda b: b["mape"])
        harapan = fc.cek_stabilitas(diuji[0], diuji[1], meta["jendela_bersama"])
        assert harapan is not None, "kasus uji harus tidak stabil"
        assert meta["catatan_stabilitas"] == harapan
        assert "CATATAN: " + harapan in meta["warning"]

    def test_tidak_ada_catatan_bila_hanya_satu_metode(self):
        _, meta = forecast_donations(_bulanan(5))
        assert meta["catatan_stabilitas"] is None


@pytest.mark.parametrize("n", [36, 120])
def test_performa_di_bawah_15_detik(n):
    import time
    mulai = time.perf_counter()
    df, meta = forecast_donations(_bulanan(n))
    assert time.perf_counter() - mulai < 15
    assert len(df) == 12 and meta["n_bulan"] == n



class TestKeadilanJendela:
    @staticmethod
    def _b(kode, per_jendela):
        return {"kode": kode, "metode": kode, "mape": float(np.mean(list(per_jendela.values()))),
                "mape_per_jendela": per_jendela}

    def test_metode_dengan_jendela_lebih_sedikit_tidak_diuntungkan(self):
        # tren_linier: jendela awal sulit (50) & akhir mudah (10) -> rata-rata sendiri 30
        # holt_winters: hanya jendela akhir, 20 -> rata-rata sendiri 20 (tampak lebih baik)
        lin = self._b("tren_linier", {1: 50, 2: 50, 3: 10, 4: 10})
        hw = self._b("holt_winters", {3: 20, 4: 20})
        urut, bersama = fc.urutkan_kandidat([hw, lin])
        assert bersama == [3, 4]
        assert [b["kode"] for b in urut] == ["tren_linier", "holt_winters"]  # 10 vs 20 pada jendela sama
        assert lin["mape_bersama"] == 10 and hw["mape_bersama"] == 20

    def test_jendela_bersama_kurang_dari_dua_pakai_rata_rata_sendiri(self):
        a = self._b("tren_linier", {1: 30, 2: 30})
        b = self._b("rata_bergerak", {2: 40, 3: 40})
        urut, bersama = fc.urutkan_kandidat([b, a])
        assert bersama == []
        assert [x["kode"] for x in urut] == ["tren_linier", "rata_bergerak"]
        assert a["mape_bersama"] is None

    def test_pemecah_seri_kesederhanaan(self):
        a = self._b("tren_linier", {1: 10, 2: 10})
        b = self._b("rata_bergerak", {1: 10, 2: 10})
        urut, _ = fc.urutkan_kandidat([a, b])
        assert urut[0]["kode"] == "rata_bergerak"
