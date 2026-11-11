"""Uji Analisis Statistik, Gini Index, dan Segmentasi RFM."""
import pandas as pd
import numpy as np
import pytest
from src.analysis import get_summary_stats
from src.rfm import calculate_gini, segment_rfm

class TestStatisticalAndRFM:
    def test_gini_calculation(self):
        # Distribusi sempurna merata -> Gini 0
        merata = pd.Series([100, 100, 100, 100])
        gini, _, _ = calculate_gini(merata)
        assert gini == 0.0

        # Distribusi timpang -> Gini mendekati 1
        timpang = pd.Series([1, 1, 1, 1000000])
        gini_t, _, _ = calculate_gini(timpang)
        assert gini_t > 0.5

    def test_rfm_segmentation(self):
        data = [
            {"id_muzaki": "M-1", "nama_muzaki": "Donatur 1", "tanggal": pd.Timestamp("2024-05-01"), "jumlah": 10000000},
            {"id_muzaki": "M-1", "nama_muzaki": "Donatur 1", "tanggal": pd.Timestamp("2024-05-15"), "jumlah": 15000000},
            {"id_muzaki": "M-2", "nama_muzaki": "Donatur 2", "tanggal": pd.Timestamp("2022-01-01"), "jumlah": 50000},
            {"id_muzaki": "M-3", "nama_muzaki": "Donatur 3", "tanggal": pd.Timestamp("2024-05-10"), "jumlah": 200000},
        ]
        df = pd.DataFrame(data)
        rfm_df, summary = segment_rfm(df)
        
        assert len(rfm_df) == 3
        assert "segmen" in rfm_df.columns
        assert summary["total_muzaki"] == 3
        assert "gini_index" in summary

    def test_summary_stats(self):
        df = pd.DataFrame([
            {"jumlah": 100000, "id_muzaki": "M-1"},
            {"jumlah": 200000, "id_muzaki": "M-2"}
        ])
        stats = get_summary_stats(df)
        assert stats["total_dana"] == 300000.0
        assert stats["total_transaksi"] == 2
        assert stats["muzaki_unik"] == 2
        assert stats["rata_rata"] == 150000.0

