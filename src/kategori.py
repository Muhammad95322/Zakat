"""Normalisasi ejaan kategori (jenis dana, kanal) dari berkas lembaga yang beragam.

Aturan berupa kata kunci pada teks yang sudah dinormalisasi (huruf kecil, tanpa tanda baca),
diperiksa berurutan; aturan pertama yang cocok menang. Nilai yang tidak cocok dengan aturan
mana pun dipertahankan (huruf kapital di awal kata) dan dilaporkan sebagai "tidak dikenali"
di laporan kualitas data, bukan ditebak.
"""
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

KOSONG = "Tidak Diketahui"

# (kata kunci yang SEMUA harus ada, kategori standar). Diperiksa berurutan.
ATURAN_JENIS_DANA: List[Tuple[Tuple[str, ...], str]] = [
    (("fitr",), "Zakat Fitrah"),
    (("fithr",), "Zakat Fitrah"),
    (("profesi",), "Zakat Profesi"),
    (("penghasilan",), "Zakat Profesi"),
    (("pendapatan",), "Zakat Profesi"),
    (("zakat", "harta"), "Zakat Maal"),
    (("maal",), "Zakat Maal"),
    (("mal",), "Zakat Maal"),
    (("infa", "sedekah"), "Infak/Sedekah"),
    (("infa", "shodaq"), "Infak/Sedekah"),
    (("infa", "shadaq"), "Infak/Sedekah"),
    (("infa", "sodaq"), "Infak/Sedekah"),
    (("infa", "sadaq"), "Infak/Sedekah"),
    (("infa", "sedeqah"), "Infak/Sedekah"),
    (("is",), "Infak/Sedekah"),
    (("infa",), "Infak"),           # infak, infaq, infaaq
    (("sedekah",), "Sedekah"),
    (("sedeqah",), "Sedekah"),
    (("shodaq",), "Sedekah"),       # shodaqoh, shodaqah
    (("shadaq",), "Sedekah"),
    (("sodaq",), "Sedekah"),
    (("sadaq",), "Sedekah"),
    (("wakaf",), "Wakaf"),
    (("waqaf",), "Wakaf"),
    (("waqf",), "Wakaf"),
    (("dskl",), "Dana Sosial Keagamaan Lainnya"),
    (("dska",), "Dana Sosial Keagamaan Lainnya"),
    (("dsakl",), "Dana Sosial Keagamaan Lainnya"),
    (("sosial", "keagamaan"), "Dana Sosial Keagamaan Lainnya"),
    (("fidyah",), "Fidyah"),
    (("fidiah",), "Fidyah"),
    (("kafarat",), "Kafarat"),
    (("kaffarat",), "Kafarat"),
]

ATURAN_KANAL: List[Tuple[Tuple[str, ...], str]] = [
    (("qris",), "QRIS"),
    (("qr",), "QRIS"),
    (("gopay",), "Dompet Digital"),
    (("ovo",), "Dompet Digital"),
    (("dana", "dompet"), "Dompet Digital"),
    (("shopeepay",), "Dompet Digital"),
    (("linkaja",), "Dompet Digital"),
    (("e", "wallet"), "Dompet Digital"),
    (("ewallet",), "Dompet Digital"),
    (("dompet",), "Dompet Digital"),
    (("transfer",), "Transfer Bank"),
    (("trf",), "Transfer Bank"),
    (("tf",), "Transfer Bank"),
    (("bank",), "Transfer Bank"),
    (("rekening",), "Transfer Bank"),
    (("va",), "Transfer Bank"),
    (("virtual", "account"), "Transfer Bank"),
    (("bsi",), "Transfer Bank"),
    (("bca",), "Transfer Bank"),
    (("bri",), "Transfer Bank"),
    (("bni",), "Transfer Bank"),
    (("mandiri",), "Transfer Bank"),
    (("muamalat",), "Transfer Bank"),
    (("debit",), "Transfer Bank"),
    (("autodebet",), "Transfer Bank"),
    (("tunai",), "Tunai"),
    (("cash",), "Tunai"),
    (("kas",), "Tunai"),
    (("jemput",), "Jemput Zakat"),
    (("kantor",), "Kantor Layanan"),
    (("counter",), "Kantor Layanan"),
    (("konter",), "Kantor Layanan"),
    (("gerai",), "Kantor Layanan"),
    (("loket",), "Kantor Layanan"),
    (("upz",), "Kantor Layanan"),
    (("online",), "Mitra/Online"),
    (("daring",), "Mitra/Online"),
    (("website",), "Mitra/Online"),
    (("web",), "Mitra/Online"),
    (("aplikasi",), "Mitra/Online"),
    (("app",), "Mitra/Online"),
    (("mitra",), "Mitra/Online"),
    (("marketplace",), "Mitra/Online"),
    (("kitabisa",), "Mitra/Online"),
]

KATEGORI_STANDAR = {
    "jenis_dana": sorted({k for _, k in ATURAN_JENIS_DANA}),
    "kanal": sorted({k for _, k in ATURAN_KANAL}),
}


def _token(s: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def _cocok(token: List[str], kunci: Tuple[str, ...]) -> bool:
    """Setiap kata kunci harus menjadi awalan salah satu token (kunci <=3 huruf: token persis)."""
    for k in kunci:
        if len(k) <= 3:
            if k not in token:
                return False
        elif not any(t.startswith(k) or (len(k) >= 5 and k in t) for t in token):
            return False
    return True


def normalisasi_satu(val, aturan) -> Tuple[str, bool]:
    """(nilai standar, dikenali?)"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return KOSONG, True
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "-", "null"):
        return KOSONG, True
    tok = _token(s)
    gabung = "".join(tok)
    for kunci, standar in aturan:
        if _cocok(tok, kunci) or (len(kunci) == 1 and len(kunci[0]) >= 5 and kunci[0] in gabung):
            return standar, True
    return " ".join(w.capitalize() for w in s.split()), False


def normalisasi_kolom(seri: pd.Series, aturan) -> Tuple[pd.Series, Dict[str, int]]:
    """Normalisasi satu kolom; kembalikan (seri baru, {nilai_asli_tak_dikenal: jumlah_baris})."""
    hitung = seri.astype(object).where(seri.notna(), None).value_counts(dropna=False)
    peta: Dict[object, str] = {}
    tak_dikenal: Dict[str, int] = {}
    for v, n in hitung.items():
        standar, dikenali = normalisasi_satu(v, aturan)
        peta[v] = standar
        if not dikenali:
            tak_dikenal[str(v).strip()] = tak_dikenal.get(str(v).strip(), 0) + int(n)
    hasil = seri.astype(object).map(lambda v: peta.get(v, KOSONG) if v is not None and not (
        isinstance(v, float) and pd.isna(v)) else KOSONG)
    return hasil, dict(sorted(tak_dikenal.items(), key=lambda kv: -kv[1]))


def kategori_baku(nama: str) -> Optional[List[str]]:
    return KATEGORI_STANDAR.get(nama)
