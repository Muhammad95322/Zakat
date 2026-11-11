"""Tes laporan PDF: grafik tersisip, catatan metode, dan MAPE 'tidak tersedia'."""
import io
import re

import pandas as pd
import pytest

from src.analysis import get_composition_analysis, get_summary_stats, get_trend_analysis
from src.cleaning import clean_data
from src.forecasting import forecast_donations
from src.report_pdf import generate_pdf_report
from src.sample_data import generate_sample_data


@pytest.fixture(scope="module")
def analisis():
    h, _ = generate_sample_data(1500, 100)
    c, _, _ = clean_data(h)
    trend = get_trend_analysis(c)
    comp = get_composition_analysis(c)
    return get_summary_stats(c), trend, comp


def _teks_pdf(pdf_bytes):
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return reader, "\n".join(p.extract_text() or "" for p in reader.pages)


def _jumlah_gambar(pdf_bytes):
    return len(re.findall(rb"/Subtype\s*/Image", pdf_bytes))


def test_pdf_dengan_grafik(analisis):
    stats, trend, comp = analisis
    fdf, meta = forecast_donations(trend["monthly"])
    pdf = generate_pdf_report("Lembaga Uji", stats, None, None,
                              trend["monthly"], comp["jenis_dana"], fdf, meta)
    assert pdf.startswith(b"%PDF")
    assert 20_000 < len(pdf) < 5_000_000
    assert _jumlah_gambar(pdf) == 3
    reader, teks = _teks_pdf(pdf)
    assert len(reader.pages) >= 2
    assert "Grafik Utama" in teks
    assert "MAPE backtest" in teks
    assert meta["metode"].split(" (")[0] in teks


def test_pdf_mape_tidak_tersedia(analisis):
    stats, trend, comp = analisis
    pendek = trend["monthly"].iloc[:5].reset_index(drop=True)
    fdf, meta = forecast_donations(pendek)
    assert meta["mape"] is None
    pdf = generate_pdf_report("Lembaga Uji", stats, None, None, pendek, comp["jenis_dana"], fdf, meta)
    _, teks = _teks_pdf(pdf)
    assert "tidak tersedia" in re.sub(r"\s+", " ", teks)


def test_pdf_tanpa_grafik_tetap_kompatibel(analisis):
    stats, _, _ = analisis
    pdf = generate_pdf_report("Lembaga Uji", stats)
    assert pdf.startswith(b"%PDF")
    assert _jumlah_gambar(pdf) == 0


def test_pdf_karakter_non_latin(analisis):
    stats, _, _ = analisis
    pdf = generate_pdf_report("Lembaga “Al-Ikhlas” — ≥ 2", {**stats, "interpretasi": "Tes \U0001F31F"})
    assert pdf.startswith(b"%PDF")


def test_pdf_dengan_peringatan_penyaluran(analisis):
    """Regresi: beberapa multi_cell berturut-turut (peringatan penyaluran) tidak boleh error."""
    stats, trend, comp = analisis
    dist = {"status": "ready", "total_salur": 1_000_000, "rasio": 60.0, "saldo": 500_000,
            "warnings": ["Peringatan pertama yang cukup panjang.", "Peringatan kedua."]}
    pdf = generate_pdf_report("Lembaga Uji", stats, dist, None, trend["monthly"], comp["jenis_dana"])
    _, teks = _teks_pdf(pdf)
    assert "Peringatan kedua" in teks
