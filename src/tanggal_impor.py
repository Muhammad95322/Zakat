"""Parsing tanggal dari berkas lembaga yang formatnya beragam.

Format yang dikenali (boleh bercampur dalam satu kolom):

- objek tanggal Excel/pandas (sel berformat tanggal)
- ISO ``2024-01-12`` / ``2024/01/12`` (opsional dengan jam)
- numerik ``12/01/2024``, ``12-01-24``, ``12.01.2024`` (urutan hari/bulan dideteksi per kolom)
- nama bulan Indonesia/Inggris: ``12 Januari 2024``, ``12-Jan-24``, ``Jumat, 12 Jan 2024``, ``Jan 12, 2024``
- nomor seri Excel (``45303`` atau ``45303.5``) dan ``20240112``

Nilai yang tidak dikenali menjadi NaT; tidak ada exception yang lolos ke pemanggil.
"""
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import pandas as pd

BULAN = {
    "jan": 1, "januari": 1, "january": 1,
    "feb": 2, "februari": 2, "pebruari": 2, "february": 2, "peb": 2,
    "mar": 3, "maret": 3, "march": 3,
    "apr": 4, "april": 4,
    "mei": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6,
    "jul": 7, "juli": 7, "july": 7,
    "agu": 8, "agt": 8, "ags": 8, "agus": 8, "agust": 8, "agustus": 8, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oktober": 10, "oct": 10, "october": 10,
    "nov": 11, "nopember": 11, "november": 11, "nop": 11,
    "des": 12, "desember": 12, "dec": 12, "december": 12,
}

FORMAT_DITERIMA = ("2024-01-31, 31/01/2024, 31-01-24, 31 Januari 2024, 31-Jan-24, "
                   "atau sel bertipe tanggal/nomor seri Excel")

TAHUN_MIN, TAHUN_MAKS = 1950, 2100
_EXCEL_NOL = datetime(1899, 12, 30)

_JAM = r"(?:[ T]+\d{1,2}[:.]\d{2}(?:[:.]\d{2}(?:\.\d+)?)?(?:\s*[ap]m)?(?:Z|[+-]\d{2}:?\d{2})?)?"
_RE_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})" + _JAM + "$")
_RE_NUM = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})" + _JAM + "$")
_RE_NAMA = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]+([a-z]+)\.?[\s\-/.,]+(\d{2}|\d{4})" + _JAM + "$")
_RE_NAMA_AS = re.compile(r"^([a-z]+)\.?[\s\-/.]+(\d{1,2})(?:st|nd|rd|th)?,?[\s\-/.]+(\d{4})" + _JAM + "$")
_RE_HARI = re.compile(r"^(senin|selasa|rabu|kamis|jumat|jum'at|sabtu|minggu|ahad|"
                      r"mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+")
_RE_ANGKA = re.compile(r"^\d+(?:\.\d+)?$")


def _tahun(y: str) -> int:
    t = int(y)
    if len(y) == 2:
        t += 2000 if t < 70 else 1900
    return t


def _buat(y: int, m: int, d: int) -> Optional[datetime]:
    if not (TAHUN_MIN <= y <= TAHUN_MAKS):
        return None
    try:
        return datetime(y, m, d)
    except ValueError:
        return None


def _dari_angka(x: float) -> Optional[datetime]:
    """Nomor seri Excel (1954..2119) atau yyyymmdd."""
    if 20000 <= x <= 80000:
        return _EXCEL_NOL + timedelta(days=float(x))
    if float(x).is_integer() and 19500101 <= x <= 21001231:
        s = str(int(x))
        return _buat(int(s[:4]), int(s[4:6]), int(s[6:]))
    return None


def _jenis(s: str) -> str:
    """Kelompokkan teks tanggal untuk statistik dan deteksi urutan."""
    if _RE_ISO.match(s):
        return "iso"
    if _RE_NUM.match(s):
        return "numerik"
    if _RE_NAMA.match(s) or _RE_NAMA_AS.match(s):
        return "nama_bulan"
    if _RE_ANGKA.match(s):
        return "seri_excel"
    return "lain"


def _parse_teks(s: str, bulan_dulu: bool) -> Optional[datetime]:
    s = _RE_HARI.sub("", s.strip().lower())
    if not s:
        return None
    m = _RE_ISO.match(s)
    if m:
        return _buat(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _RE_NUM.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), _tahun(m.group(3))
        return _buat(y, a, b) if bulan_dulu else _buat(y, b, a)
    m = _RE_NAMA.match(s)
    if m and m.group(2) in BULAN:
        return _buat(_tahun(m.group(3)), BULAN[m.group(2)], int(m.group(1)))
    m = _RE_NAMA_AS.match(s)
    if m and m.group(1) in BULAN:
        return _buat(int(m.group(3)), BULAN[m.group(1)], int(m.group(2)))
    if _RE_ANGKA.match(s):
        return _dari_angka(float(s))
    return None


def parse_satu(val: Any, bulan_dulu: bool = False) -> Optional[datetime]:
    """Parse satu nilai tanggal; None bila tidak dikenali."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, pd.Timestamp):
        d = val.to_pydatetime()
        return d if TAHUN_MIN <= d.year <= TAHUN_MAKS else None
    if isinstance(val, datetime):
        return val if TAHUN_MIN <= val.year <= TAHUN_MAKS else None
    if isinstance(val, date):
        return _buat(val.year, val.month, val.day)
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return _dari_angka(float(val))
    try:
        return _parse_teks(str(val), bulan_dulu)
    except Exception:  # nilai aneh apa pun -> tidak dikenali, bukan crash
        return None


def deteksi_urutan(unik) -> Tuple[bool, str]:
    """Tentukan urutan d/m vs m/d dari nilai numerik seperti 12/01/2024 dalam satu kolom.

    Bukti hari-dulu: komponen pertama > 12. Bukti bulan-dulu: komponen kedua > 12.
    Bawaan Indonesia: hari-dulu.
    """
    hari, bulan = 0, 0
    for v in unik:
        if not isinstance(v, str):
            continue
        m = _RE_NUM.match(v.strip().lower())
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            hari += a > 12
            bulan += b > 12
    if bulan and not hari:
        return True, f"bulan/hari (ditemukan {bulan} nilai dengan komponen kedua > 12)"
    if hari and bulan:
        return False, (f"hari/bulan; PERINGATAN: kolom mencampur urutan hari/bulan ({hari} nilai) dan "
                       f"bulan/hari ({bulan} nilai), nilai yang tidak cocok dianggap tidak valid")
    if hari:
        return False, "hari/bulan"
    return False, "hari/bulan (diasumsikan; tidak ada nilai yang membedakan)"


def _tertukar_lokal_excel(unik, bulan_dulu: bool) -> bool:
    """Deteksi bug lokal Excel: berkas dd/mm/yyyy dibuka di Excel berlokal bulan/hari.

    Gejalanya khas: nilai dengan hari <= 12 berubah menjadi sel tanggal (hari & bulan tertukar),
    sedangkan nilai dengan hari > 12 tetap teks dd/mm/yyyy. Syarat ketat agar berkas normal tidak
    ikut "dibetulkan": >= 10 sel tanggal berbeda tanpa jam yang SEMUA berhari <= 12, dan >= 3 teks
    dd/mm dengan komponen pertama > 12, tanpa satu pun teks bergaya bulan/hari.
    """
    if bulan_dulu:
        return False
    objek = [v for v in unik if isinstance(v, (datetime, pd.Timestamp))]
    if len(objek) < 10 or any(v.day > 12 or v.hour or v.minute for v in objek):
        return False
    hari_besar, bulan_besar = 0, 0
    for v in unik:
        if isinstance(v, str):
            m = _RE_NUM.match(v.strip().lower())
            if m:
                hari_besar += int(m.group(1)) > 12
                bulan_besar += int(m.group(2)) > 12
    return hari_besar >= 3 and bulan_besar == 0


def parse_kolom(seri: pd.Series) -> Tuple[pd.Series, Dict[str, Any]]:
    """Parse satu kolom tanggal. Mengembalikan (Series datetime64, info)."""
    info: Dict[str, Any] = {"urutan": "-", "jenis_format": {}}
    if pd.api.types.is_datetime64_any_dtype(seri):
        hasil = pd.to_datetime(seri, errors="coerce")
        hasil = hasil.where((hasil.dt.year >= TAHUN_MIN) & (hasil.dt.year <= TAHUN_MAKS))
        info["jenis_format"] = {"sel tanggal": int(hasil.notna().sum())}
        return hasil, info
    unik = pd.unique(seri.dropna())
    bulan_dulu, info["urutan"] = deteksi_urutan(unik)
    tukar = _tertukar_lokal_excel(unik, bulan_dulu)
    if tukar:
        info["tertukar_diperbaiki"] = int(seri.map(lambda v: isinstance(v, (datetime, pd.Timestamp))).sum())
    peta, jenis = {}, {}
    for v in unik:
        if tukar and isinstance(v, (datetime, pd.Timestamp)):
            peta[v] = _buat(v.year, v.day, v.month)  # kembalikan hari/bulan yang ditukar Excel
            jenis["sel tanggal (diperbaiki)"] = jenis.get("sel tanggal (diperbaiki)", 0) + 1
            continue
        peta[v] = parse_satu(v, bulan_dulu)
        k = "sel tanggal" if isinstance(v, (datetime, date, pd.Timestamp)) else (
            "seri_excel" if isinstance(v, (int, float)) else _jenis(str(v).strip().lower()))
        jenis[k] = jenis.get(k, 0) + 1
    info["jenis_format"] = jenis
    hasil = pd.to_datetime(seri.map(peta), errors="coerce")
    return hasil, info


_JUDUL_TAHUN = {"tahun", "thn", "year"}
_JUDUL_BULAN = {"bulan", "bln", "month"}
_JUDUL_HARI = {"tanggal", "tgl", "hari", "day", "tanggal hari"}


def _norm(s: Any) -> str:
    return " ".join(t for t in re.split(r"[^a-z0-9]+", str(s).lower()) if t)


def _bulan(v: Any) -> Optional[int]:
    if v is None or (isinstance(v, float) and v != v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v) if float(v).is_integer() and 1 <= v <= 12 else None
    s = _norm(v)
    if s.isdigit():
        return int(s) if 1 <= int(s) <= 12 else None
    return BULAN.get(s.split(" ")[0]) if s else None


def _bulat(v: Any, lo: int, hi: int) -> Optional[int]:
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() and lo <= f <= hi else None


def gabung_tahun_bulan(df: pd.DataFrame, kolom_lokasi: str = "__lokasi__") -> Tuple[pd.DataFrame, Optional[str]]:
    """Bentuk kolom tanggal dari kolom 'Tahun' + 'Bulan' (+ 'Tanggal'/'Hari' berisi angka hari).

    Hanya dilakukan bila tidak ada kolom lain yang sudah berisi tanggal lengkap. Kolom hari yang
    berjudul 'Tanggal'/'Tgl' diganti nama menjadi '<judul> (hari)' agar tidak dipetakan sebagai tanggal.
    """
    kolom = [c for c in df.columns if c != kolom_lokasi]
    norm = {c: _norm(c) for c in kolom}
    k_tahun = next((c for c in kolom if norm[c] in _JUDUL_TAHUN), None)
    k_bulan = next((c for c in kolom if norm[c] in _JUDUL_BULAN), None)
    if not k_tahun or not k_bulan or df.empty:
        return df, None
    k_hari = next((c for c in kolom if norm[c] in _JUDUL_HARI), None)
    sampel = df.head(200)
    for c in kolom:
        if c in (k_tahun, k_bulan, k_hari):
            continue
        s = sampel[c].dropna()
        teks = s[~s.map(lambda v: isinstance(v, (int, float)) or bool(re.fullmatch(r"\s*\d+\s*", str(v))))]
        if len(teks) and sum(parse_satu(v) is not None for v in teks) / max(len(s), 1) >= 0.8:
            return df, None  # sudah ada kolom tanggal lengkap
    if k_hari is not None:
        hari_ok = sampel[k_hari].dropna().map(lambda v: _bulat(v, 1, 31) is not None)
        if len(hari_ok) == 0 or hari_ok.mean() < 0.8:
            k_hari = None
    th = df[k_tahun].map(lambda v: _bulat(v, TAHUN_MIN, TAHUN_MAKS))
    bl = df[k_bulan].map(_bulan)
    hr = df[k_hari].map(lambda v: _bulat(v, 1, 31)) if k_hari else pd.Series(1, index=df.index)
    if th.notna().mean() < 0.8 or bl.notna().mean() < 0.8:
        return df, None

    def _satu(y, m, d):
        if y is None or m is None or d is None or pd.isna(y) or pd.isna(m) or pd.isna(d):
            return None
        t = _buat(int(y), int(m), int(d))
        return t.strftime("%Y-%m-%d") if t else None

    nama_baru = "Tanggal (gabungan tahun-bulan)"
    out = df.copy()
    if k_hari is not None and norm[k_hari] in ("tanggal", "tgl", "tanggal hari"):
        out = out.rename(columns={k_hari: f"{k_hari} (hari)"})
    out.insert(0, nama_baru, [_satu(y, m, d) for y, m, d in zip(th, bl, hr)])
    catatan = (f"Tanggal transaksi dibentuk dari kolom {', '.join(repr(x) for x in (k_tahun, k_bulan, k_hari) if x)}"
               + ("" if k_hari else "; berkas tidak memuat hari, dipakai tanggal 1 tiap bulan") + ".")
    return out, catatan
