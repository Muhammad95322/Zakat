"""Uji Pembersihan Data, Parsing Rupiah Indonesia, dan Normalisasi."""
import pandas as pd
import pytest
from src.utils import format_rupiah, parse_angka_indonesia
from src.cleaning import clean_data

class TestDataCleaning:
    def test_parsing_angka_indonesia(self):
        assert parse_angka_indonesia("1.500.000") == 1500000.0
        assert parse_angka_indonesia("Rp 2,5 jt") == 2500000.0
        assert parse_angka_indonesia("500 rb") == 500000.0
        assert parse_angka_indonesia("Rp 1 M") == 1000000000.0
        assert parse_angka_indonesia(125000) == 125000.0

    def test_format_rupiah(self):
        assert format_rupiah(1500000) == "Rp 1.500.000"
        assert format_rupiah(1500000, singkat=True) == "Rp 1,5 jt"
        assert format_rupiah(2000000000, singkat=True) == "Rp 2 M"
        assert format_rupiah(0) == "Rp 0"

    def test_pembersihan_duplikat_dan_invalid(self):
        data = [
            {"tanggal": "2024-01-01", "id_muzaki": "M-1", "nama_muzaki": "Budi", "jenis_dana": "Zakat Mal", "kanal": "qris", "kabupaten_kota": "Bantul", "jumlah": "1.000.000"},
            {"tanggal": "2024-01-01", "id_muzaki": "M-1", "nama_muzaki": "Budi", "jenis_dana": "Zakat Mal", "kanal": "qris", "kabupaten_kota": "Bantul", "jumlah": "1.000.000"}, # duplikat
            {"tanggal": "2024-01-02", "id_muzaki": "M-2", "nama_muzaki": "Siti", "jenis_dana": "infak", "kanal": "transfer", "kabupaten_kota": "Sleman", "jumlah": "-50.000"}, # negatif
            {"tanggal": "2024-01-03", "id_muzaki": "M-3", "nama_muzaki": "Ali", "jenis_dana": "Sedekah", "kanal": "tunai", "kabupaten_kota": "Kota Yogyakarta", "jumlah": "200.000"}
        ]
        df_raw = pd.DataFrame(data)
        df_clean, logs, summary = clean_data(df_raw, "Penghimpunan")
        
        # 4 baris -> 1 duplikat terbuang, 1 negatif terbuang -> sisa 2
        assert len(df_clean) == 2
        assert summary["duplikat"] == 1
        assert df_clean["jenis_dana"].iloc[0] == "Zakat Maal" # Koreksi typo 'Zakat Mal'
        assert df_clean["kanal"].iloc[0] == "QRIS" # Standardisasi casing 'QRIS'

