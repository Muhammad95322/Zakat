"""Tes segmentasi RFM dan koefisien Gini dengan kasus yang bisa dihitung manual."""
import numpy as np
import pandas as pd
import pytest

from src.rfm import calculate_gini, segment_rfm


class TestGini:
    def test_semua_donasi_sama_gini_nol(self):
        gini, x, y = calculate_gini(pd.Series([250_000] * 10))
        assert gini == 0.0
        assert np.allclose(x, y)  # kurva Lorenz = garis kesetaraan

    def test_satu_donatur_dari_dua(self):
        # [0, 10]: Lorenz (0,0)-(0.5,0)-(1,1); luas = 0.25; Gini = (0.5-0.25)/0.5 = 0.5
        gini, _, _ = calculate_gini(pd.Series([0, 10]))
        assert gini == pytest.approx(0.5)

    def test_kasus_manual_1_2_3_4(self):
        # Lorenz y: 0, .1, .3, .6, 1 pada x: 0,.25,.5,.75,1
        # luas trapesium = .25*(0+.1+.1+.3+.3+.6+.6+1)/2 = .375 -> Gini = (.5-.375)/.5 = .25
        gini, _, _ = calculate_gini(pd.Series([4, 1, 3, 2]))
        assert gini == pytest.approx(0.25)

    def test_kosong_dan_nol(self):
        assert calculate_gini(pd.Series([], dtype=float))[0] == 0.0
        assert calculate_gini(pd.Series([0, 0, 0]))[0] == 0.0

    def test_nan_diabaikan(self):
        assert calculate_gini(pd.Series([5, np.nan, 5]))[0] == 0.0


def _transaksi(baris):
    return pd.DataFrame(
        [{"id_muzaki": i, "nama_muzaki": f"Donatur {i}", "tanggal": pd.Timestamp(t), "jumlah": j} for i, t, j in baris]
    )


class TestRFM:
    def test_agregasi_frequency_monetary_recency(self):
        df = _transaksi([
            ("A", "2024-01-01", 100), ("A", "2024-03-01", 200), ("A", "2024-06-30", 300),
            ("B", "2024-06-01", 1000),
            ("C", "2023-06-30", 50),
        ])
        rfm, summary = segment_rfm(df)
        rfm = rfm.set_index("id_muzaki")
        assert rfm.loc["A", "frequency"] == 3
        assert rfm.loc["A", "monetary"] == 600
        assert rfm.loc["A", "recency_days"] == 0
        assert rfm.loc["B", "recency_days"] == 29
        assert rfm.loc["C", "recency_days"] == 366  # 2024 kabisat
        assert summary["total_muzaki"] == 3

    def test_skor_frekuensi_manual(self):
        baris = [("X", f"2024-01-{d:02d}", 10) for d in range(1, 11)]  # 10x -> skor 5
        baris += [("Y", "2024-01-05", 10), ("Y", "2024-01-06", 10)]     # 2x -> skor 2
        baris += [("Z", "2024-01-05", 10)]                              # 1x -> skor 1
        rfm, _ = segment_rfm(_transaksi(baris))
        skor = rfm.set_index("id_muzaki")["f_score"].to_dict()
        assert skor == {"X": 5, "Y": 2, "Z": 1}

    def test_data_kecil_skor_netral(self):
        # < 5 muzaki: r_score & m_score bernilai 3
        rfm, _ = segment_rfm(_transaksi([("A", "2024-01-01", 10), ("B", "2024-01-02", 20)]))
        assert set(rfm["r_score"]) == {3}
        assert set(rfm["m_score"]) == {3}

    def test_segmen_setia_dan_hilang(self):
        baris = []
        # Setia: sangat baru dan sering (>= 5 transaksi)
        baris += [("SETIA", f"2024-12-{d:02d}", 100_000) for d in range(20, 26)]
        # Pasif: sekali, sudah lama
        baris += [("LAMA", "2022-01-01", 50_000)]
        # Pengisi agar kuantil terbentuk (>= 5 muzaki)
        baris += [(f"P{i}", f"2024-0{i}-15", 10_000 * i) for i in range(1, 5)]
        rfm, summary = segment_rfm(_transaksi(baris))
        seg = rfm.set_index("id_muzaki")["segmen"].to_dict()
        assert "Setia" in seg["SETIA"]
        assert "Pasif" in seg["LAMA"]
        assert sum(summary["segmen_counts"].values()) == len(rfm)

    def test_gini_ringkasan_merata(self):
        df = _transaksi([(c, "2024-01-01", 100) for c in "ABCDEF"])
        _, summary = segment_rfm(df)
        assert summary["gini_index"] == 0.0

    def test_pareto_manual(self):
        # Satu donatur menyumbang 90% -> 1 dari 4 muzaki (25%) menyumbang >= 80%
        df = _transaksi([("A", "2024-01-01", 900), ("B", "2024-01-01", 50), ("C", "2024-01-01", 30), ("D", "2024-01-01", 20)])
        _, summary = segment_rfm(df)
        assert summary["pareto_pct"] == 25.0

    def test_data_kosong(self):
        rfm, summary = segment_rfm(pd.DataFrame())
        assert rfm.empty and summary == {}
