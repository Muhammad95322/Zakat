"""Tes parsing angka Indonesia dan format rupiah/tanggal."""
from datetime import date

import pytest

from src.utils import format_rupiah, format_tanggal, parse_angka_indonesia


@pytest.mark.parametrize("teks, harapan", [
    ("1.500.000", 1_500_000.0),
    ("Rp 1.500.000", 1_500_000.0),
    ("Rp1.500.000,50", 1_500_000.5),
    ("Rp 2,5 jt", 2_500_000.0),
    ("2,5 juta", 2_500_000.0),
    ("500 rb", 500_000.0),
    ("500 ribu", 500_000.0),
    ("Rp 1 M", 1_000_000_000.0),
    ("1,5 miliar", 1_500_000_000.0),
    ("250000", 250_000.0),
    ("1.5", 1.5),
    ("1,000,000", 1_000_000.0),
    ("  75.000  ", 75_000.0),
    (125000, 125_000.0),
    (99.5, 99.5),
])
def test_parse_angka_indonesia(teks, harapan):
    assert parse_angka_indonesia(teks) == pytest.approx(harapan)


@pytest.mark.parametrize("teks", [None, "", "   ", "abc", "lima ratus", "-"])
def test_parse_angka_tidak_valid(teks):
    assert parse_angka_indonesia(teks) is None


@pytest.mark.parametrize("nominal, singkat, harapan", [
    (1_500_000, False, "Rp 1.500.000"),
    (0, False, "Rp 0"),
    (None, False, "Rp 0"),
    (999.6, False, "Rp 1.000"),
    (-250_000, False, "-Rp 250.000"),
    (1_500_000, True, "Rp 1,5 jt"),
    (2_000_000_000, True, "Rp 2 M"),
    (3_400_000_000_000, True, "Rp 3,4 T"),
    (500_000, True, "Rp 500 rb"),
    (750, True, "Rp 750"),
])
def test_format_rupiah(nominal, singkat, harapan):
    assert format_rupiah(nominal, singkat=singkat) == harapan


def test_format_tanggal():
    assert format_tanggal(date(2024, 3, 11)) == "11 Maret 2024"
    assert format_tanggal("2024-12-01") == "1 Desember 2024"
    assert format_tanggal(None) == "-"
