"""Helper utilities untuk Zakat Insight: format rupiah, tanggal, dan kalkulasi umum."""
from datetime import datetime, date
from typing import Union, Optional

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


def parse_angka_indonesia(val: any) -> Optional[float]:
    """Parse berbagai representasi angka string Indonesia ke float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
        
    teks = str(val).strip()
    if not teks:
        return None
        
    # Bersihkan prefix Rp dan spasi
    teks = teks.replace("Rp", "").replace("rp", "").strip()
    
    # Deteksi singkatan juta/ribu/miliar
    multiplier = 1.0
    teks_lower = teks.lower()
    if "jt" in teks_lower or "juta" in teks_lower:
        multiplier = 1_000_000.0
        teks = teks_lower.replace("juta", "").replace("jt", "").strip()
    elif "rb" in teks_lower or "ribu" in teks_lower:
        multiplier = 1_000.0
        teks = teks_lower.replace("ribu", "").replace("rb", "").strip()
    elif "m" in teks_lower or "miliar" in teks_lower or "milyar" in teks_lower:
        multiplier = 1_000_000_000.0
        teks = teks_lower.replace("miliar", "").replace("milyar", "").replace("m", "").strip()
        
    # Tangani pemisah ribuan titik dan desimal koma (misal: "1.500.000,50")
    if "." in teks and "," in teks:
        teks = teks.replace(".", "").replace(",", ".")
    elif "." in teks:
        # Bisa jadi "1.500.000" (ribuan) atau "1.5" (desimal)
        parts = teks.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            teks = teks.replace(".", "")
        else:
            pass # desimal standar
    elif "," in teks:
        parts = teks.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            teks = teks.replace(",", ".")
        else:
            teks = teks.replace(",", "")
            
    try:
        return float(teks) * multiplier
    except ValueError:
        return None

