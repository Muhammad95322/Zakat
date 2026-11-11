"""Tes loader: sinonim kolom, file/sheet kosong, kolom wajib hilang, teks di kolom angka."""
import io

import pandas as pd
import pytest

from src.loader import DataFileError, deteksi_kolom, load_file, validasi_kolom_wajib
from src.pipeline import siapkan_data


def _excel_bytes(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for nama, df in sheets.items():
            df.to_excel(w, sheet_name=nama, index=False)
    return buf.getvalue()


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


DATA_VALID = pd.DataFrame({
    "Tgl": ["2024-01-05", "2024-02-10", "2024-03-15"],
    "ID Donatur": ["M-1", "M-2", "M-1"],
    "Nama Donatur": ["Budi", "Siti", "Budi"],
    "Tipe Dana": ["infaq", "zakat mal", "sedekah"],
    "Metode": ["qris", "transfer", "tunai"],
    "Wilayah": ["Sleman", "Bantul", "Sleman"],
    "Nominal": ["1.500.000", "Rp 2,5 jt", "500 rb"],
})


class TestDeteksiSinonim:
    def test_sinonim_dipetakan_ke_kolom_standar(self):
        expected = ["tanggal", "id_muzaki", "nama_muzaki", "jenis_dana", "kanal", "kabupaten_kota", "jumlah"]
        mapping, missing = deteksi_kolom(DATA_VALID, expected)
        assert missing == []
        assert mapping == {
            "Tgl": "tanggal", "ID Donatur": "id_muzaki", "Nama Donatur": "nama_muzaki",
            "Tipe Dana": "jenis_dana", "Metode": "kanal", "Wilayah": "kabupaten_kota", "Nominal": "jumlah",
        }

    def test_nama_kolom_berspasi_dan_huruf_besar(self):
        df = pd.DataFrame(columns=["  TANGGAL ", "Besar Donasi"])
        mapping, missing = deteksi_kolom(df, ["tanggal", "jumlah"])
        assert missing == []
        assert set(mapping.values()) == {"tanggal", "jumlah"}

    def test_kolom_tidak_dikenal_dilaporkan_hilang(self):
        df = pd.DataFrame(columns=["foo", "bar"])
        _, missing = deteksi_kolom(df, ["tanggal", "jumlah"])
        assert missing == ["tanggal", "jumlah"]


class TestFileKosong:
    def test_bytes_kosong(self):
        with pytest.raises(DataFileError, match="kosong"):
            load_file(b"", "data.xlsx")

    def test_csv_tanpa_isi(self):
        with pytest.raises(DataFileError, match="kosong"):
            load_file(b"\n", "data.csv")

    def test_csv_hanya_header(self):
        with pytest.raises(DataFileError, match="tidak berisi baris data"):
            load_file(b"tanggal,jumlah\n", "data.csv")

    def test_excel_rusak(self):
        with pytest.raises(DataFileError, match="rusak"):
            load_file(b"PK\x03\x04bukan-zip-yang-valid", "data.xlsx")


class TestSheetKosong:
    def test_sheet_penghimpunan_kosong(self):
        konten = _excel_bytes({"Penghimpunan": pd.DataFrame(), "Penyaluran": pd.DataFrame({"a": [1]})})
        with pytest.raises(DataFileError, match="Penghimpunan.*kosong"):
            load_file(konten, "data.xlsx")

    def test_sheet_penghimpunan_hanya_header(self):
        konten = _excel_bytes({"Penghimpunan": pd.DataFrame(columns=["tanggal", "jumlah"])})
        with pytest.raises(DataFileError, match="kosong"):
            load_file(konten, "data.xlsx")

    def test_sheet_penyaluran_kosong_diabaikan(self):
        konten = _excel_bytes({"Penghimpunan": DATA_VALID, "Penyaluran": pd.DataFrame()})
        res = load_file(konten, "data.xlsx")
        assert "Penghimpunan" in res
        assert "Penyaluran" not in res


class TestKolomWajib:
    def test_kolom_jumlah_hilang(self):
        df = DATA_VALID.drop(columns=["Nominal"])
        with pytest.raises(DataFileError) as info:
            validasi_kolom_wajib(df, "Penghimpunan")
        pesan = str(info.value)
        assert "'jumlah'" in pesan
        assert "nominal" in pesan  # sinonim yang diterima disebutkan
        assert "'tanggal'" not in pesan

    def test_lewat_pipeline(self):
        konten = _csv_bytes(DATA_VALID.drop(columns=["Tgl"]))
        with pytest.raises(DataFileError, match="kolom wajib.*'tanggal'"):
            siapkan_data(konten, "data.csv")

    def test_kolom_lengkap_lolos(self):
        validasi_kolom_wajib(DATA_VALID, "Penghimpunan")


class TestTeksDiKolomAngka:
    def test_sebagian_teks_dibuang_dan_dicatat(self):
        df = DATA_VALID.copy()
        df.loc[1, "Nominal"] = "lima ratus ribu"
        hasil = siapkan_data(_csv_bytes(df), "data.csv")
        assert len(hasil["df_himpun"]) == 2
        assert hasil["df_himpun"]["jumlah"].tolist() == [1_500_000.0, 500_000.0]
        aksi = [l["aksi"] for l in hasil["log_himpun"]]
        assert any("Invalid" in a for a in aksi)

    def test_semua_teks_gagal_ramah(self):
        df = DATA_VALID.copy()
        df["Nominal"] = ["abc", "tidak tahu", "-"]
        with pytest.raises(DataFileError, match="Tidak ada baris penghimpunan yang valid"):
            siapkan_data(_csv_bytes(df), "data.csv")

    def test_file_valid_lengkap(self):
        hasil = siapkan_data(_excel_bytes({"Penghimpunan": DATA_VALID}), "data.xlsx")
        assert hasil["df_himpun"]["jumlah"].sum() == 1_500_000 + 2_500_000 + 500_000
        assert hasil["df_salur"].empty


def test_tanggal_invalid_tidak_menggeser_nilai():
    """Regresi: setelah baris invalid dibuang, nilai sisa harus tetap pada barisnya."""
    df = DATA_VALID.copy()
    df.loc[0, "Tgl"] = "bukan tanggal"
    hasil = siapkan_data(_csv_bytes(df), "data.csv")
    out = hasil["df_himpun"]
    assert out["tanggal"].dt.strftime("%Y-%m-%d").tolist() == ["2024-02-10", "2024-03-15"]
    assert out["jumlah"].tolist() == [2_500_000.0, 500_000.0]
