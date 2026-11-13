"""Format angka, tanggal, dan bulan gaya Indonesia untuk templat dan grafik.

Nominal singkat memakai ``src.utils.format_rupiah(singkat=True)`` (rb, jt, M = miliar, T) apa adanya.
"""
from datetime import date, datetime
from typing import Optional, Union

from src.utils import format_rupiah

BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
         "Oktober", "November", "Desember"]
BULAN_PENDEK = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def rupiah(nilai) -> str:
    """Rp 1.500.000"""
    return format_rupiah(nilai or 0)


def rupiah_singkat(nilai) -> str:
    """Rp 1,5 jt / Rp 2 M"""
    return format_rupiah(nilai or 0, singkat=True)


def singkat_tanpa_rp(nilai) -> str:
    """1,5 jt (label sumbu grafik)."""
    return format_rupiah(nilai or 0, singkat=True).replace("Rp ", "", 1)


def bilangan(nilai) -> str:
    """12.345"""
    return f"{int(round(nilai or 0)):,}".replace(",", ".")


def persen(nilai, desimal: int = 1) -> str:
    """12,3%"""
    teks = f"{abs(float(nilai or 0)):.{desimal}f}".replace(".", ",")
    if "," in teks:
        teks = teks.rstrip("0").rstrip(",")
    return f"{teks}%"


def desimal(nilai, digit: int = 1) -> str:
    """2,5 (desimal koma, nol di belakang dibuang)"""
    teks = f"{float(nilai or 0):,.{digit}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if "," in teks:
        teks = teks.rstrip("0").rstrip(",")
    return teks


def bulan_tahun(teks_atau_tgl: Union[str, date, datetime, None], pendek: bool = True) -> str:
    """'2024-10' -> 'Okt 2024'."""
    if teks_atau_tgl is None:
        return "-"
    if isinstance(teks_atau_tgl, (date, datetime)):
        th, bl = teks_atau_tgl.year, teks_atau_tgl.month
    else:
        bagian = str(teks_atau_tgl)[:7].split("-")
        th, bl = int(bagian[0]), int(bagian[1])
    return f"{(BULAN_PENDEK if pendek else BULAN)[bl - 1]} {th}"


def tanggal(tgl: Optional[Union[date, datetime]]) -> str:
    """12 November 2026"""
    if tgl is None:
        return "-"
    return f"{tgl.day} {BULAN[tgl.month - 1]} {tgl.year}"


def tanggal_pendek(tgl: Optional[Union[date, datetime]]) -> str:
    """12 Nov 2026"""
    if tgl is None:
        return "-"
    return f"{tgl.day} {BULAN_PENDEK[tgl.month - 1]} {tgl.year}"


def ukuran_berkas(n_byte: Optional[int]) -> str:
    n = float(n_byte or 0)
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f}".replace(".", ",") + " MB"
    return f"{max(1, round(n / 1024))} KB"


FILTER = {
    "rupiah": rupiah, "rupiah_singkat": rupiah_singkat, "bilangan": bilangan, "persen": persen, "desimal": desimal,
    "bulan_tahun": bulan_tahun, "tanggal": tanggal, "tanggal_pendek": tanggal_pendek, "ukuran_berkas": ukuran_berkas,
}
