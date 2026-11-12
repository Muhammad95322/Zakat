"""Impor tahan format: angka, tanggal, judul kolom, struktur sheet, CSV, kategori (semua data sintetis)."""
import importlib.util
import io
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from src.cleaning import clean_data
from src.kategori import ATURAN_JENIS_DANA, ATURAN_KANAL, normalisasi_satu
from src.loader import DataFileError, baca_berkas
from src.pemetaan import deteksi_pemetaan
from src.pipeline import periksa_berkas, siapkan_data
from src.tanggal_impor import parse_kolom, parse_satu
from src.utils import parse_angka_indonesia

AKAR = Path(__file__).parent.parent


def _modul(nama):
    spec = importlib.util.spec_from_file_location(nama, AKAR / "scripts" / f"{nama}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nama] = mod
    spec.loader.exec_module(mod)
    return mod


def _xlsx(baris, gabung=()):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in baris:
        ws.append(r)
    for g in gabung:
        ws.merge_cells(g)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Nominal
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("teks, harapan", [
    ("Rp 1.500.000,-", 1_500_000.0),
    ("Rp. 1.500.000,00", 1_500_000.0),
    ("1,500,000", 1_500_000.0),
    ("1,500,000.50", 1_500_000.5),
    ("1.500.000", 1_500_000.0),
    ("1500000.50", 1_500_000.5),
    ("1500000,50", 1_500_000.5),
    ("  1 500 000 ", 1_500_000.0),
    ("1 500 000", 1_500_000.0),
    ("IDR 250.000", 250_000.0),
    ("-50.000", -50_000.0),
    ("(50.000)", -50_000.0),
    ("50.000-", -50_000.0),
    ("0", 0.0),
])
def test_nominal_beragam(teks, harapan):
    assert parse_angka_indonesia(teks) == pytest.approx(harapan)


@pytest.mark.parametrize("teks", ["1.2.3", "lima ratus ribu", "Rp", "12a", "--", float("nan"), True])
def test_nominal_tidak_valid_tanpa_exception(teks):
    assert parse_angka_indonesia(teks) is None


# ---------------------------------------------------------------------------
# Tanggal
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nilai, harapan", [
    ("2024-01-12", "2024-01-12"),
    ("2024/01/12 14:30:00", "2024-01-12"),
    ("12/01/2024", "2024-01-12"),
    ("12-01-24", "2024-01-12"),
    ("12.01.2024", "2024-01-12"),
    ("12 Januari 2024", "2024-01-12"),
    ("12 Agustus 2023", "2023-08-12"),
    ("12-Jan-24", "2024-01-12"),
    ("12-Agu-24", "2024-08-12"),
    ("Jumat, 12 Jan 2024", "2024-01-12"),
    ("Jan 12, 2024", "2024-01-12"),
    (45303, "2024-01-12"),
    ("45303", "2024-01-12"),
    (20240112, "2024-01-12"),
    (datetime(2024, 1, 12), "2024-01-12"),
])
def test_tanggal_beragam(nilai, harapan):
    assert parse_satu(nilai).strftime("%Y-%m-%d") == harapan


@pytest.mark.parametrize("nilai", ["31/02/2024", "kemarin", "2024-13-45", "1", "12", "Total", 1500000.0, "1/1/1800"])
def test_tanggal_tidak_valid(nilai):
    assert parse_satu(nilai) is None


def test_urutan_bulan_hari_dideteksi_per_kolom():
    hasil, info = parse_kolom(pd.Series(["01/31/2024", "02/15/2024", "03/05/2024"], dtype=object))
    assert hasil.dt.strftime("%Y-%m-%d").tolist() == ["2024-01-31", "2024-02-15", "2024-03-05"]
    assert info["urutan"].startswith("bulan/hari")


def test_urutan_campur_nilai_tidak_cocok_dibuang():
    hasil, info = parse_kolom(pd.Series(["31/01/2024", "01/31/2024", "05/04/2024"], dtype=object))
    assert "PERINGATAN" in info["urutan"]
    assert hasil.isna().sum() == 1


def test_bug_lokal_excel_diperbaiki():
    # tanggal asli dd/mm; Excel ber-lokal AS mengubah yang berhari <= 12 menjadi sel tanggal tertukar
    asli = pd.date_range("2024-01-01", periods=60, freq="5D")
    sel = [datetime(d.year, d.day, d.month) if d.day <= 12 else d.strftime("%d/%m/%Y") for d in asli]
    hasil, info = parse_kolom(pd.Series(sel, dtype=object))
    assert (hasil.values == asli.values).all()
    assert info["tertukar_diperbaiki"] > 0


def test_sel_tanggal_normal_tidak_dibalik():
    asli = pd.date_range("2024-01-01", periods=60, freq="3D")
    sel = [d.to_pydatetime() for d in asli] + ["15/03/2024"] * 3
    hasil, info = parse_kolom(pd.Series(sel, dtype=object))
    assert (hasil.iloc[:60].values == asli.values).all()
    assert "tertukar_diperbaiki" not in info


# ---------------------------------------------------------------------------
# Kategori
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("asli, standar", [
    ("infaq", "Infak"), ("INFAK", "Infak"), ("shodaqoh", "Sedekah"), ("Shadaqah", "Sedekah"),
    ("Infaq/Shodaqoh", "Infak/Sedekah"), ("zakat mal", "Zakat Maal"), ("zakat harta", "Zakat Maal"),
    ("fithrah", "Zakat Fitrah"), ("zakat penghasilan", "Zakat Profesi"), ("waqaf", "Wakaf"),
    ("DSKL", "Dana Sosial Keagamaan Lainnya"),
])
def test_ejaan_jenis_dana(asli, standar):
    assert normalisasi_satu(asli, ATURAN_JENIS_DANA) == (standar, True)


@pytest.mark.parametrize("asli, standar", [
    ("TF", "Transfer Bank"), ("trf BSI", "Transfer Bank"), ("cash", "Tunai"), ("QR", "QRIS"),
    ("counter", "Kantor Layanan"), ("website", "Mitra/Online"), ("GoPay", "Dompet Digital"),
])
def test_ejaan_kanal(asli, standar):
    assert normalisasi_satu(asli, ATURAN_KANAL) == (standar, True)


def test_kategori_tak_dikenal_dipertahankan_dan_dilaporkan():
    assert normalisasi_satu("kurban", ATURAN_JENIS_DANA) == ("Kurban", False)
    assert normalisasi_satu("Zakat", ATURAN_JENIS_DANA) == ("Zakat", False)  # tidak ditebak maal/fitrah
    df = pd.DataFrame({"tanggal": ["2024-01-01", "2024-01-02", "2024-01-03"],
                       "jenis_dana": ["infaq", "Kurban", "kurban"], "jumlah": [1000, 2000, 3000]})
    out, _, ringkas = clean_data(df)
    assert out["jenis_dana"].tolist() == ["Infak", "Kurban", "Kurban"]
    assert ringkas["kategori_tak_dikenal"] == {"jenis_dana": {"Kurban": 1, "kurban": 1}}


# ---------------------------------------------------------------------------
# Judul kolom & pemetaan
# ---------------------------------------------------------------------------
def test_judul_beragam_terpetakan():
    df = pd.DataFrame(columns=["  TGL ", "Jumlah (Rp)", "Donatur", "Jenis Dana", "Metode Pembayaran", "Kabupaten/Kota"])
    df.loc[0] = ["12/01/2024", "1.500.000", "Ani", "infaq", "TF", "Sleman"]
    d = deteksi_pemetaan(df)
    assert d.status == "otomatis"
    assert d.pemetaan == {"tanggal": "  TGL ", "jumlah": "Jumlah (Rp)", "nama_muzaki": "Donatur",
                          "jenis_dana": "Jenis Dana", "kanal": "Metode Pembayaran", "kabupaten_kota": "Kabupaten/Kota"}


def test_jumlah_penerima_bukan_nominal():
    df = pd.DataFrame({"Tanggal": ["2024-01-01"] * 3, "Jumlah Penerima": [3, 4, 5], "Jumlah (Rp)": [1e6, 2e6, 3e6]})
    assert deteksi_pemetaan(df).pemetaan["jumlah"] == "Jumlah (Rp)"


def test_dua_kandidat_nominal_ragu():
    df = pd.DataFrame({"Tanggal": ["2024-01-01"] * 3, "Nominal": [1e6, 2e6, 3e6], "Total": [1e6, 2e6, 3e6]})
    d = deteksi_pemetaan(df)
    assert d.status == "ragu" and "beberapa kandidat" in " ".join(d.alasan)


def test_judul_tak_dikenal_ditebak_dari_isi_tetapi_ragu():
    df = pd.DataFrame({"Kapan": ["12/01/2024", "13/01/2024", "14/01/2024"], "Siapa": ["A", "B", "C"],
                       "Berapa": ["1.500.000", "250.000", "100.000"]})
    d = deteksi_pemetaan(df)
    assert d.status == "ragu"
    assert d.pemetaan == {"tanggal": "Kapan", "jumlah": "Berapa"}


def test_kolom_wajib_hilang_gagal():
    df = pd.DataFrame({"Nama": ["A", "B"], "Kota": ["X", "Y"]})
    assert deteksi_pemetaan(df).status == "gagal"


def test_nominal_dalam_ribuan_dikonversi():
    isi = _xlsx([["Tanggal", "Jumlah (Rp ribu)"], ["2024-01-01", 1500], ["2024-01-02", 250.5]])
    hasil = siapkan_data(isi, "a.xlsx")
    assert hasil["df_himpun"]["jumlah"].tolist() == [1_500_000.0, 250_500.0]
    assert any("satuan ribu" in w for w in hasil["kualitas"]["peringatan"])


# ---------------------------------------------------------------------------
# Struktur berkas
# ---------------------------------------------------------------------------
def test_judul_laporan_sel_gabung_dan_baris_total():
    baris = [["LAPORAN PENERIMAAN ZIS 2024", None, None], [None, None, None],
             ["Tanggal", "Donatur", "Nominal"],
             [datetime(2024, 1, 5), "Ani", 100000], [None, "Budi", 200000], [None, "Cici", 300000],
             [datetime(2024, 1, 6), "Dedi", 50000],
             [None, None, None], ["TOTAL", None, 650000]]
    isi = _xlsx(baris, gabung=["A1:C1", "A4:A6"])
    hasil = siapkan_data(isi, "a.xlsx")
    df = hasil["df_himpun"]
    assert df["jumlah"].sum() == 650000
    assert df["tanggal"].dt.day.tolist() == [5, 5, 5, 6]
    lap = hasil["kualitas"]
    assert lap["sumber"]["baris_judul"] == 3
    assert {d["alasan"] for d in lap["dibuang"]} == {"baris total/subtotal (bukan transaksi)"}
    assert "baris 9" in lap["dibuang"][0]["contoh"]


def test_sel_gabung_nominal_tidak_digandakan():
    baris = [["Tanggal", "Donatur", "Nominal"], ["2024-01-05", "Ani", 100000], ["2024-01-06", "Budi", None]]
    hasil = siapkan_data(_xlsx(baris, gabung=["C2:C3"]), "a.xlsx")
    assert hasil["df_himpun"]["jumlah"].sum() == 100000


def test_sheet_petunjuk_dilewati_dan_sheet_per_tahun_digabung():
    wb = openpyxl.Workbook()
    wb.active.title = "Petunjuk"
    wb.active.append(["Isi satu transaksi per baris"])
    for th in (2023, 2024):
        ws = wb.create_sheet(str(th))
        ws.append(["Tanggal", "Nominal"])
        ws.append([f"{th}-03-01", 1000])
        ws.append([f"{th}-04-01", 2000])
    buf = io.BytesIO()
    wb.save(buf)
    hasil = siapkan_data(buf.getvalue(), "a.xlsx")
    assert len(hasil["df_himpun"]) == 4
    assert hasil["info"]["sheet_penghimpunan"] == ["sheet '2023'", "sheet '2024'"]


def test_sheet_gabungan_dipisah():
    baris = [["Tanggal", "Jenis Transaksi", "Nominal"], ["2024-01-01", "Penerimaan", 100000],
             ["2024-01-02", "Penyaluran", 40000], ["2024-01-03", "Masuk", 50000], ["2024-01-04", "Lain-lain", 1]]
    hasil = siapkan_data(_xlsx(baris), "a.xlsx")
    assert hasil["df_himpun"]["jumlah"].tolist() == [100000.0, 50000.0]
    assert hasil["df_salur"]["jumlah"].tolist() == [40000.0]
    assert hasil["kualitas"]["dibuang"][0]["alasan"] == "jenis transaksi bukan masuk/keluar"


def test_buku_kas_masuk_keluar():
    baris = [["Tgl", "Uraian", "Masuk", "Keluar"], ["2024-01-01", "Donasi", "100.000", None],
             ["2024-01-02", "Bantuan", None, "40.000"], ["Jumlah", None, "100.000", "40.000"]]
    hasil = siapkan_data(_xlsx(baris), "a.xlsx")
    assert hasil["df_himpun"]["jumlah"].tolist() == [100000.0]
    assert hasil["df_salur"]["jumlah"].tolist() == [40000.0]


def test_tahun_bulan_terpisah():
    baris = [["Tahun", "Bulan", "Penerimaan Zakat (Rp)"], [2024, "Januari", 1000000], [2024, 2, 2000000]]
    hasil = siapkan_data(_xlsx(baris), "a.xlsx")
    assert hasil["df_himpun"]["tanggal"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-01", "2024-02-01"]
    assert any("tanggal 1 tiap bulan" in c for c in hasil["info"]["catatan"])


@pytest.mark.parametrize("pemisah, encoding, bom", [
    (",", "utf-8", False), (";", "utf-8", False), ("\t", "utf-8", False), (";", "utf-8", True), (";", "cp1252", False),
])
def test_csv_pemisah_dan_encoding(pemisah, encoding, bom):
    teks = pemisah.join(["Tanggal", "Donatur", "Kota", "Nominal"]) + "\r\n"
    teks += pemisah.join(["12/01/2024", "André", "Sleman – DIY", "1.500.000"]) + "\r\n"
    teks += pemisah.join(["13/01/2024", "Zoë", "Bantul", "250.000"]) + "\r\n"
    isi = (b"\xef\xbb\xbf" if bom else b"") + teks.encode(encoding)
    b = baca_berkas(isi, "a.csv")
    df = b.tabel["Penghimpunan"]
    assert list(df.columns[:4]) == ["Tanggal", "Donatur", "Kota", "Nominal"]
    assert df["Donatur"].tolist() == ["André", "Zoë"]
    assert df["Kota"].iloc[0] == "Sleman – DIY"
    assert siapkan_data(isi, "a.csv")["df_himpun"]["jumlah"].sum() == 1_750_000


def test_csv_desimal_koma_tidak_dikira_pemisah():
    isi = b"Tanggal;Nominal\n12/01/2024;1500000,50\n13/01/2024;250000,25\n"
    assert siapkan_data(isi, "a.csv")["df_himpun"]["jumlah"].tolist() == [1500000.5, 250000.25]


def test_lokasi_baris_di_pesan_galat():
    isi = b"Keterangan ekspor\n\nTanggal,Nominal\nkemarin,1000\n31/02/2024,2000\n"
    with pytest.raises(DataFileError) as e:
        siapkan_data(isi, "a.csv")
    pesan = str(e.value)
    assert "baris 4 ('kemarin')" in pesan and "baris 5 ('31/02/2024')" in pesan
    assert "kolom 'Tanggal'" in pesan and "31 Januari 2024" in pesan  # apa yang diharapkan


def test_xls_lama_ditolak_jelas():
    with pytest.raises(DataFileError, match=r"\.xls"):
        siapkan_data(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100, "lama.xls")


def test_periksa_berkas_memberi_pratinjau_5_baris():
    baris = [["Kapan", "Berapa"]] + [[f"2024-01-{i:02d}", i * 1000] for i in range(1, 11)]
    p = periksa_berkas(_xlsx(baris), "a.xlsx")
    assert p.perlu_wizard and len(p.pratinjau) == 5 and p.kolom == ["Kapan", "Berapa"]


# ---------------------------------------------------------------------------
# Variasi dari generator: hasil impor dicocokkan dengan kunci jawaban
# ---------------------------------------------------------------------------
GAGAL_TERDOKUMENTASI = {
    # mm/dd/yyyy dengan SEMUA hari <= 12: secara isi tidak bisa dibedakan dari dd/mm/yyyy.
    # Dibaca sebagai dd/mm dan laporan kualitas memberi peringatan; lihat docs/HASIL_UJI_IMPOR.md.
    "v45_tgl_mdy_ambigu",
}


@pytest.fixture(scope="module")
def hasil_variasi(tmp_path_factory):
    gen = _modul("buat_data_kotor")
    ukur = _modul("ukur_impor")
    d = tmp_path_factory.mktemp("kotor")
    gen.tulis_semua(d, besar=False)
    return ukur.ukur(d), ukur


def test_variasi_jumlah_puluhan_dan_berbeda(hasil_variasi):
    hasil, _ = hasil_variasi
    assert len(hasil) >= 50
    assert len({r["kode"] for r in hasil}) == len(hasil)


def test_variasi_tidak_ada_exception_mentah(hasil_variasi):
    hasil, _ = hasil_variasi
    assert [r for r in hasil if "EXCEPTION" in r["catatan"]] == []


def test_variasi_rusak_ditolak_dengan_pesan_jelas(hasil_variasi):
    hasil, _ = hasil_variasi
    tolak = [r for r in hasil if r["kode"].startswith("t")]
    assert tolak and all(r["kategori"] == "ditolak" for r in tolak), [r for r in tolak if r["kategori"] != "ditolak"]


def test_variasi_wajar_terbaca_benar_kecuali_yang_terdokumentasi(hasil_variasi):
    hasil, ukur = hasil_variasi
    gagal = {r["kode"]: r["catatan"] for r in hasil if r["kategori"] == "GAGAL"}
    assert set(gagal) == GAGAL_TERDOKUMENTASI, gagal
    r = ukur.ringkas(hasil)
    assert r["otomatis"] + r["wizard"] + r["ditolak"] + r["GAGAL"] == r["N"]


def test_variasi_besar_100rb_baris(tmp_path):
    gen = _modul("buat_data_kotor")
    ukur = _modul("ukur_impor")
    semua = gen.semua_variasi(besar=True)
    for v in [x for x in semua if "besar" in x["kode"]]:
        r = ukur.nilai_variasi(v, v["isi"])
        assert r["kategori"] == "otomatis", r
