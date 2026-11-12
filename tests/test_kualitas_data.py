"""Laporan kualitas data: angka konsisten, peringatan < 24 bulan, masuk PDF & Excel (data sintetis)."""
import io

import openpyxl
import pandas as pd
import pytest

from src.analysis import get_summary_stats
from src.kualitas_data import BULAN_MINIMUM_PERAMALAN, tabel_kualitas
from src.pipeline import siapkan_data
from src.report_excel import generate_excel_report
from src.report_pdf import generate_pdf_report


def _csv(baris):
    return ("\n".join(";".join(map(str, r)) for r in baris) + "\n").encode("utf-8")


def _data(bulan: int, kotor: bool = True):
    tgl = pd.date_range("2022-01-15", periods=bulan, freq="MS") + pd.Timedelta(days=14)
    baris = [["Tanggal", "Jenis Dana", "Kanal", "Nominal"]]
    for i, t in enumerate(tgl):
        baris.append([t.strftime("%d/%m/%Y"), ["infaq", "zakat mal", "Kurban"][i % 3], "TF", f"{(i + 1) * 1000}"])
    if kotor:
        baris += [["31/02/2024", "infaq", "TF", "1000"],      # tanggal salah
                  [tgl[0].strftime("%d/%m/%Y"), "infaq", "TF", "0"],  # nominal nol
                  [tgl[0].strftime("%d/%m/%Y"), "infaq", "TF", "-500"],  # negatif
                  ["TOTAL", "", "", "999999"]]                   # baris total
    return _csv(baris)


def test_angka_laporan_konsisten():
    lap = siapkan_data(_data(30), "a.csv")["kualitas"]
    assert lap["baris_dibaca"] == 34 and lap["baris_valid"] == 30
    assert lap["baris_dibuang"] == sum(d["jumlah"] for d in lap["dibuang"]) == 4
    assert lap["persen_valid"] == pytest.approx(88.2)
    alasan = {d["alasan"]: d["jumlah"] for d in lap["dibuang"]}
    assert alasan == {"baris total/subtotal (bukan transaksi)": 1, "nominal Rp 0": 1,
                      "nominal negatif (koreksi/pengembalian)": 1, "tanggal tidak dikenali": 1}
    assert lap["rentang_bulan"] == 30 and lap["bulan_berdata"] == 30
    assert lap["kategori_tak_dikenal"] == {"jenis_dana": {"Kurban": 10}}
    assert any("Kurban" in w for w in lap["peringatan"])


@pytest.mark.parametrize("bulan, terbatas", [(12, True), (BULAN_MINIMUM_PERAMALAN - 1, True),
                                             (BULAN_MINIMUM_PERAMALAN, False), (36, False)])
def test_peringatan_kurang_24_bulan(bulan, terbatas):
    lap = siapkan_data(_data(bulan, kotor=False), "a.csv")["kualitas"]
    assert lap["peramalan_terbatas"] is terbatas
    assert any("kurang dari 24 bulan" in w for w in lap["peringatan"]) is terbatas


def test_tabel_kualitas_lengkap():
    t = tabel_kualitas(siapkan_data(_data(30), "a.csv")["kualitas"])
    butir = t["Butir"].str.strip().tolist()
    for b in ("Baris data dibaca", "Baris valid", "Baris dibuang", "Rentang tanggal", "Pemetaan kolom",
              "Format berkas", "Tidak dikenali: jenis dana"):
        assert b in butir
    assert any(x.startswith("Dibuang: tanggal tidak dikenali") for x in butir)
    assert "baris 2" not in " ".join(t["Nilai"])  # contoh menunjuk baris yang benar-benar dibuang
    assert "baris 32 ('31/02/2024')" in " ".join(t["Nilai"])


def test_masuk_pdf_dan_excel():
    hasil = siapkan_data(_data(12), "a.csv")
    stats = get_summary_stats(hasil["df_himpun"])
    pdf = generate_pdf_report("Lembaga Uji", stats, kualitas=hasil["kualitas"])
    pypdf = pytest.importorskip("pypdf")
    teks = " ".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    teks = " ".join(teks.split())
    assert "Kualitas Data Masukan" in teks and "kurang dari 24 bulan" in teks
    xlsx = generate_excel_report(hasil["df_himpun"], stats, kualitas=hasil["kualitas"])
    kd = pd.read_excel(io.BytesIO(xlsx), sheet_name="Kualitas Data")
    assert list(kd.columns) == ["Butir", "Nilai"]
    assert (kd["Butir"] == "PERINGATAN").any()


def test_laporan_tanpa_kualitas_tetap_jalan():
    hasil = siapkan_data(_data(12), "a.csv")
    stats = get_summary_stats(hasil["df_himpun"])
    assert generate_pdf_report("L", stats).startswith(b"%PDF")
    assert "Kualitas Data" not in pd.read_excel(io.BytesIO(generate_excel_report(hasil["df_himpun"], stats)),
                                                sheet_name=None)


def test_kategori_berawalan_rumus_dinetralkan_di_excel():
    baris = [["Tanggal", "Jenis Dana", "Nominal"], ["01/01/2024", '=HYPERLINK("http://contoh.invalid")', "1000"],
             ["02/01/2024", "infaq", "2000"]]
    hasil = siapkan_data(_csv(baris), "a.csv")
    xlsx = generate_excel_report(hasil["df_himpun"], get_summary_stats(hasil["df_himpun"]), kualitas=hasil["kualitas"])
    ws = openpyxl.load_workbook(io.BytesIO(xlsx))["Kualitas Data"]
    assert all(c.data_type != "f" for row in ws.iter_rows() for c in row)
