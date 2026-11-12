"""Helper utilities untuk Zakat Insight: format rupiah, tanggal, dan kalkulasi umum."""
from datetime import datetime, date
import math
import re
from typing import Any, Optional, Union

def format_rupiah(nominal: Union[int, float], singkat: bool = False) -> str:
    """Format angka ke Rupiah Indonesia.
    
    Args:
        nominal: Nilai uang dalam rupiah
        singkat: Jika True, gunakan singkatan jt / M / T
    
    Examples:
        format_rupiah(1500000) -> "Rp 1.500.000"
        format_rupiah(1500000, singkat=True) -> "Rp 1,5 jt"
        format_rupiah(2000000000, singkat=True) -> "Rp 2 M"
        format_rupiah(0) -> "Rp 0"
    """
    if nominal is None:
        return "Rp 0"
    
    is_negatif = nominal < 0
    abs_nominal = abs(nominal)
    
    if singkat:
        if abs_nominal >= 1_000_000_000_000:
            val = abs_nominal / 1_000_000_000_000
            formatted = f"{val:.1f}".replace(".", ",").rstrip("0").rstrip(",")
            res = f"Rp {formatted} T"
        elif abs_nominal >= 1_000_000_000:
            val = abs_nominal / 1_000_000_000
            formatted = f"{val:.1f}".replace(".", ",").rstrip("0").rstrip(",")
            res = f"Rp {formatted} M"
        elif abs_nominal >= 1_000_000:
            val = abs_nominal / 1_000_000
            formatted = f"{val:.1f}".replace(".", ",").rstrip("0").rstrip(",")
            res = f"Rp {formatted} jt"
        elif abs_nominal >= 1_000:
            val = abs_nominal / 1_000
            formatted = f"{val:.1f}".replace(".", ",").rstrip("0").rstrip(",")
            res = f"Rp {formatted} rb"
        else:
            res = f"Rp {int(abs_nominal)}"
    else:
        # Standard Indonesian format with dot as thousand separator
        formatted = f"{int(round(abs_nominal)):,}".replace(",", ".")
        res = f"Rp {formatted}"
        
    return f"-{res}" if is_negatif else res


def format_tanggal(tgl: Union[datetime, date, str]) -> str:
    """Format tanggal ke standar Bahasa Indonesia: DD Bulan YYYY."""
    if not tgl:
        return "-"
    
    if isinstance(tgl, str):
        try:
            tgl = datetime.fromisoformat(tgl.replace("Z", "+00:00"))
        except Exception:
            return str(tgl)
            
    nama_bulan = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]
    
    return f"{tgl.day} {nama_bulan[tgl.month]} {tgl.year}"


_RE_SPASI = re.compile(r"[\s   ']+")
_RE_PENGALI = re.compile(r"^(?P<angka>[\d.,]+)(?P<satuan>jt|juta|rb|ribu|k|m|miliar|milyar|t|triliun)$")
_PENGALI = {"jt": 1e6, "juta": 1e6, "rb": 1e3, "ribu": 1e3, "k": 1e3,
            "m": 1e9, "miliar": 1e9, "milyar": 1e9, "t": 1e12, "triliun": 1e12}
_RE_ANGKA_AKHIR = re.compile(r"^\d+(\.\d+)?$")


def _normalisasi_pemisah(teks: str) -> str:
    """Ubah '1.500.000,50' / '1,500,000.50' / '1.500' menjadi notasi float Python."""
    titik, koma = teks.count("."), teks.count(",")
    if titik and koma:
        # pemisah yang muncul terakhir adalah desimal
        if teks.rfind(",") > teks.rfind("."):
            return teks.replace(".", "").replace(",", ".")
        return teks.replace(",", "")
    for sep, n in ((".", titik), (",", koma)):
        if not n:
            continue
        bagian = teks.split(sep)
        if n > 1:
            # beberapa pemisah: harus pemisah ribuan yang konsisten (kelompok 3 digit)
            if all(len(b) == 3 for b in bagian[1:]) and 1 <= len(bagian[0]) <= 3:
                return teks.replace(sep, "")
            return ""  # bukan angka yang valid, mis. '1.2.3'
        # satu pemisah: 3 digit di belakang = ribuan (gaya Indonesia), selain itu desimal
        if len(bagian[1]) == 3 and bagian[0] not in ("", "0"):
            return teks.replace(sep, "")
        return teks.replace(sep, ".")
    return teks


def parse_angka_indonesia(val: Any) -> Optional[float]:
    """Parse berbagai representasi nominal (gaya Indonesia maupun internasional) ke float.

    Diterima, antara lain: ``1500000``, ``1.500.000``, ``1,500,000``, ``1500000.50``,
    ``1.500.000,50``, ``Rp 1.500.000,-``, ``IDR 1 500 000``, ``Rp 2,5 jt``, ``500 rb``,
    ``1,5 M``, ``-50.000``, ``(50.000)`` (negatif gaya akuntansi), ``50.000-``.
    Mengembalikan None untuk nilai kosong/bukan angka; tidak pernah melempar exception.
    """
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else f
    try:
        import numpy as np
        if isinstance(val, np.generic):
            return parse_angka_indonesia(val.item())
    except Exception:  # pragma: no cover - numpy selalu tersedia
        pass
    teks = str(val).strip().lower()
    if not teks or teks in ("nan", "none", "null", "-", "--"):
        return None
    negatif = False
    if teks.startswith("(") and teks.endswith(")"):
        negatif, teks = True, teks[1:-1]
    teks = teks.replace("rp.", "").replace("rp", "").replace("idr", "")
    teks = _RE_SPASI.sub("", teks)
    # akhiran gaya kuitansi: '1.500.000,-' / '1.500.000.-' / '1.500.000,00'
    for akhir in (",-", ".-", ",--", "=-", "=", ",00-"):
        if teks.endswith(akhir):
            teks = teks[: -len(akhir)]
    if teks.startswith("-"):
        negatif, teks = not negatif, teks[1:]
    elif teks.startswith("+"):
        teks = teks[1:]
    if teks.endswith("-"):  # '50.000-' (format kredit)
        negatif, teks = not negatif, teks[:-1]
    pengali = 1.0
    m = _RE_PENGALI.match(teks)
    if m:
        pengali, teks = _PENGALI[m.group("satuan")], m.group("angka")
    teks = _normalisasi_pemisah(teks)
    if not _RE_ANGKA_AKHIR.match(teks):
        return None
    hasil = float(teks) * pengali
    return -hasil if negatif else hasil
