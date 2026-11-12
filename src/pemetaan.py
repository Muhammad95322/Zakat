"""Deteksi pemetaan kolom berkas lembaga -> kolom standar Zakat Insight, beserta tingkat keyakinan.

Status hasil deteksi:

- ``tersimpan``: pemetaan yang pernah dikonfirmasi lembaga ini cocok dengan kolom berkas.
- ``otomatis``: tanggal & jumlah ditemukan dari judul kolom dengan yakin, dan isinya terbaca.
- ``ragu``: kolom wajib ditemukan, tetapi hanya dari isi kolom, ada beberapa kandidat,
  atau sebagian besar isinya tidak terbaca. UI wajib meminta konfirmasi (wizard).
- ``gagal``: kolom wajib tidak ditemukan. UI menampilkan wizard; tanpa wizard, berkas ditolak.
"""
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from src.tanggal_impor import deteksi_urutan, parse_satu
from src.utils import parse_angka_indonesia

KOLOM_LOKASI = "__lokasi__"

# bidang standar -> (sinonim judul, token yang membatalkan kecocokan sebagian)
BIDANG: Dict[str, Tuple[List[str], List[str]]] = {
    "tanggal": ([
        "tanggal", "tgl", "date", "waktu", "tanggal transaksi", "tgl transaksi", "tgl trx", "trans date",
        "transaction date", "tanggal terima", "tanggal setor", "tanggal bayar", "tanggal donasi",
        "tanggal penyaluran", "tgl salur", "tanggal masuk", "hari tanggal", "tanggal kwitansi", "tgl kwitansi",
        "tgl_transaksi",
    ], ["lahir", "input", "cetak", "update", "dibuat", "hari"]),
    "jumlah": ([
        "jumlah", "nominal", "amount", "total", "nilai", "besar donasi", "uang", "jumlah uang", "jumlah donasi",
        "nominal donasi", "setoran", "besaran", "jumlah zakat", "nilai transaksi", "rupiah", "jml", "jumlah dana",
        "nominal transaksi", "jumlah bayar", "donation amount", "value",
    ], ["penerima", "jiwa", "orang", "kk", "transaksi ke", "item", "qty", "kali", "mustahik", "donatur",
        "muzaki", "muzakki", "hari", "jenis", "tipe", "kategori", "sumber", "id", "kode", "no"]),
    "id_muzaki": ([
        "id muzaki", "id donatur", "muzaki id", "donatur id", "no anggota", "id anggota", "kode muzaki",
        "kode donatur", "no muzaki", "nomor muzaki", "no donatur", "nomor donatur", "npwz", "id muzakki",
        "kode muzakki", "id",
    ], ["transaksi", "trx", "kwitansi", "kuitansi", "bukti", "referensi", "ref", "nota", "invoice", "faktur"]),
    # nomor unik per transaksi: dasar pembuangan duplikat (tanpa kolom ini, baris identik dipertahankan)
    "id_transaksi": ([
        "id transaksi", "no transaksi", "nomor transaksi", "kode transaksi", "trx id", "id trx", "no trx",
        "transaction id", "no bukti", "nomor bukti", "bukti", "no kwitansi", "nomor kwitansi", "kwitansi",
        "no kuitansi", "kuitansi", "no referensi", "nomor referensi", "referensi", "no ref", "ref",
        "reference", "no invoice", "invoice", "no faktur", "faktur", "no nota", "nomor nota", "nota",
        "receipt", "no resi", "nomor setoran", "no setoran",
    ], ["donatur", "muzaki", "muzakki", "anggota", "rekening", "hp", "telepon", "tanggal", "tgl", "jumlah",
        "nominal"]),
    "nama_muzaki": ([
        "nama muzaki", "nama donatur", "nama", "donatur", "muzaki", "nama lengkap", "muzakki", "nama muzakki",
        "penyetor", "nama penyetor", "atas nama", "donor", "nama donor",
    ], ["id", "kode", "no", "nomor", "program", "kampanye", "petugas", "amil", "bank", "kota", "jenis",
        "jumlah", "nominal"]),
    "jenis_dana": ([
        "jenis dana", "tipe dana", "dana", "kategori dana", "jenis zis", "program zis", "jenis", "kategori",
        "jenis donasi", "jenis zakat", "peruntukan", "jenis penerimaan", "akad", "jenis_dana", "fund type", "fund",
        "donation type", "type", "category",
    ], ["transaksi", "arus", "kelamin", "bayar", "pembayaran", "kanal", "jumlah", "nominal", "sumber", "kas",
        "mutasi"]),
    "kanal": ([
        "kanal", "metode", "channel", "kanal bayar", "metode bayar", "metode pembayaran", "cara bayar", "via",
        "media", "media pembayaran", "jalur", "sarana", "cara pembayaran", "payment method", "method",
    ], []),
    "kabupaten_kota": ([
        "kabupaten kota", "kabupaten", "kota", "kab kota", "wilayah", "daerah", "lokasi", "domisili", "cabang",
        "area", "region", "kota kabupaten", "kab", "kabupaten_kota", "city", "regency", "district",
    ], ["kantor layanan"]),
    "kampanye": ([
        "kampanye", "program kampanye", "campaign", "kegiatan", "nama kampanye",
    ], []),
    "program": ([
        "program", "bidang program", "pilar", "pilar program", "sektor", "bidang", "program penyaluran",
    ], ["zis", "kampanye"]),
    "asnaf": ([
        "asnaf", "golongan", "kategori asnaf", "mustahik asnaf", "senf",
    ], []),
    "jenis_dana_sumber": ([
        "jenis dana sumber", "sumber dana", "dana sumber", "asal dana",
    ], []),
    "jumlah_penerima": ([
        "jumlah penerima", "penerima manfaat", "total penerima", "kuota penerima", "jiwa", "jumlah mustahik",
        "jumlah jiwa", "jml penerima",
    ], []),
    # kolom khusus lembar gabungan penghimpunan + penyaluran
    "arus": ([
        "jenis transaksi", "tipe transaksi", "arus", "arus dana", "arus kas", "jenis arus", "mutasi",
        "kategori transaksi", "masuk keluar", "keterangan arus", "d k", "debet kredit",
    ], []),
    "masuk": ([
        "masuk", "penerimaan", "pemasukan", "uang masuk", "dana masuk", "debet", "debit", "penghimpunan",
    ], ["tanggal", "tgl", "jenis", "sumber"]),
    "keluar": ([
        "keluar", "pengeluaran", "uang keluar", "dana keluar", "kredit", "penyaluran",
    ], ["tanggal", "tgl", "jenis", "program"]),
}

BIDANG_HIMPUN = ["tanggal", "jumlah", "id_muzaki", "nama_muzaki", "jenis_dana", "kanal", "kabupaten_kota",
                 "kampanye", "id_transaksi"]
BIDANG_SALUR = ["tanggal", "jumlah", "program", "asnaf", "jenis_dana_sumber", "kabupaten_kota",
                "jumlah_penerima", "id_transaksi"]
BIDANG_GABUNGAN = ["arus", "masuk", "keluar"]
WAJIB = ["tanggal", "jumlah"]

# bidang yang ditawarkan di wizard UI (urutan tampilan) dan labelnya
BIDANG_WIZARD = {
    "tanggal": "Tanggal transaksi (wajib)",
    "jumlah": "Jumlah / nominal (wajib)",
    "jenis_dana": "Jenis dana",
    "kanal": "Kanal / metode bayar",
    "kabupaten_kota": "Wilayah (kabupaten/kota)",
    "nama_muzaki": "Nama donatur",
    "id_muzaki": "ID donatur",
}

LABEL_BIDANG = {
    "tanggal": "tanggal", "jumlah": "jumlah", "id_muzaki": "ID donatur", "nama_muzaki": "nama donatur",
    "id_transaksi": "ID transaksi",
    "jenis_dana": "jenis dana", "kanal": "kanal", "kabupaten_kota": "wilayah", "kampanye": "kampanye",
    "program": "program", "asnaf": "asnaf", "jenis_dana_sumber": "sumber dana",
    "jumlah_penerima": "jumlah penerima", "arus": "jenis transaksi (masuk/keluar)",
    "masuk": "nominal masuk", "keluar": "nominal keluar",
}

_KATA_SATUAN = {"rp", "idr", "rupiah", "dd", "mm", "yyyy", "yy", "rp.", "x", "1000", "ribu"}


def normalisasi_judul(s: Any) -> str:
    """'  Jumlah (Rp) ' -> 'jumlah'; 'Kabupaten/Kota' -> 'kabupaten kota'."""
    tok = [t for t in re.split(r"[^a-z0-9]+", str(s).strip().lower()) if t]
    tok = [t for t in tok if t not in _KATA_SATUAN] or tok
    return " ".join(tok)


_SINONIM_NORM = {b: [normalisasi_judul(x) for x in sin] for b, (sin, _) in BIDANG.items()}


def skor_judul(judul: Any, bidang: str) -> float:
    """1.0 = judul persis sinonim; 0.8 = semua kata sinonim ada di judul; 0 = tidak cocok."""
    norm = normalisasi_judul(judul)
    if not norm:
        return 0.0
    if norm in _SINONIM_NORM[bidang]:
        return 1.0
    tok = set(norm.split())
    if tok & set(BIDANG[bidang][1]):
        return 0.0
    for sin in _SINONIM_NORM[bidang]:
        st = set(sin.split())
        if st and st <= tok:
            return 0.8
    return 0.0


def skor_baris_judul(nilai: Iterable[Any]) -> int:
    """Berapa sel dalam satu baris yang tampak seperti judul kolom yang dikenal (untuk deteksi baris judul)."""
    n = 0
    for v in nilai:
        if v is None or (isinstance(v, float) and pd.isna(v)) or not isinstance(v, str):
            continue
        if len(v) > 60:
            continue
        if any(skor_judul(v, b) >= 0.8 for b in BIDANG):
            n += 1
    return n


def _sampel(seri: pd.Series, n: int = 300) -> pd.Series:
    s = seri.dropna()
    s = s[s.astype(str).str.strip() != ""]
    if len(s) > n:
        s = s.iloc[:: max(1, len(s) // n)][:n]
    return s


def rasio_tanggal(seri: pd.Series, terima_angka: bool = True) -> float:
    """Rasio nilai yang terbaca sebagai tanggal (urutan hari/bulan dideteksi per kolom)."""
    s = _sampel(seri)
    if s.empty:
        return 0.0
    bulan_dulu, _ = deteksi_urutan(pd.unique(seri.dropna()))
    ok = 0
    for v in s:
        if not terima_angka and (isinstance(v, (int, float)) or re.fullmatch(r"\s*\d+(\.\d+)?\s*", str(v))):
            continue
        ok += parse_satu(v, bulan_dulu) is not None
    return ok / len(s)


def rasio_angka(seri: pd.Series) -> float:
    s = _sampel(seri)
    if s.empty:
        return 0.0
    return sum(parse_angka_indonesia(v) is not None for v in s) / len(s)


def _tampak_nominal(seri: pd.Series) -> float:
    """Rasio nilai yang terbaca sebagai angka >= 1.000 (nominal rupiah), bukan ID/kode/tanggal."""
    s = _sampel(seri)
    if s.empty:
        return 0.0
    ok = 0
    for v in s:
        if hasattr(v, "year"):
            continue
        a = parse_angka_indonesia(v)
        ok += a is not None and abs(a) >= 1000
    return ok / len(s)


@dataclass
class HasilDeteksi:
    pemetaan: Dict[str, str]                  # bidang standar -> nama kolom asli
    status: str                               # tersimpan | otomatis | ragu | gagal
    alasan: List[str] = field(default_factory=list)
    keyakinan: Dict[str, float] = field(default_factory=dict)
    sumber: Dict[str, str] = field(default_factory=dict)  # bidang -> "judul" | "isi" | "tersimpan" | "pengguna"
    opsi: Dict[str, Any] = field(default_factory=dict)    # pilihan lembaga, mis. buang_duplikat_persis

    def kolom_wajib_hilang(self) -> List[str]:
        return [b for b in WAJIB if b not in self.pemetaan]

    def sebagai_dict(self) -> Dict[str, Any]:
        return {"pemetaan": dict(self.pemetaan), "status": self.status, "alasan": list(self.alasan),
                "keyakinan": dict(self.keyakinan), "sumber": dict(self.sumber), "opsi": dict(self.opsi)}


def _kolom_data(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if c != KOLOM_LOKASI]


def tanda_kolom(kolom: Iterable[Any]) -> str:
    """Sidik jari susunan judul kolom (untuk mencari pemetaan tersimpan)."""
    norm = sorted(normalisasi_judul(c) for c in kolom if c != KOLOM_LOKASI)
    return hashlib.sha256("|".join(norm).encode("utf-8")).hexdigest()


def _cocokkan_judul(kolom: List[str], bidang: List[str]) -> Tuple[Dict[str, str], Dict[str, float], List[str]]:
    """Penugasan rakus: pasangan (kolom, bidang) skor tertinggi lebih dulu, satu kolom satu bidang."""
    pasangan = []
    for i_b, b in enumerate(bidang):
        for i_k, k in enumerate(kolom):
            s = skor_judul(k, b)
            if s > 0:
                pasangan.append((-s, i_b, i_k, b, k))
    pasangan.sort()
    pemetaan, yakin, dipakai = {}, {}, set()
    for neg, _, _, b, k in pasangan:
        if b in pemetaan or k in dipakai:
            continue
        pemetaan[b], yakin[b] = k, -neg
        dipakai.add(k)
    # kandidat kembar: dua kolom tersisa dengan skor sama tinggi untuk bidang wajib
    ragu = []
    for b in WAJIB:
        if b not in pemetaan:
            continue
        kembar = [k for k in kolom if k != pemetaan[b] and k not in dipakai and skor_judul(k, b) >= yakin[b]]
        if kembar:
            ragu.append(f"Kolom {LABEL_BIDANG[b]} punya beberapa kandidat: "
                        f"{', '.join(repr(str(x)) for x in [pemetaan[b], *kembar])}.")
    return pemetaan, yakin, ragu


def deteksi_pemetaan(df: pd.DataFrame, jenis: str = "Penghimpunan") -> HasilDeteksi:
    """Deteksi otomatis pemetaan kolom untuk satu tabel."""
    kolom = _kolom_data(df)
    bidang = (BIDANG_SALUR if jenis == "Penyaluran" else BIDANG_HIMPUN) + BIDANG_GABUNGAN
    pemetaan, yakin, alasan = _cocokkan_judul(kolom, bidang)
    sumber = {b: "judul" for b in pemetaan}

    # lembar gabungan model debet/kredit: kolom masuk/keluar menggantikan kolom jumlah
    if "jumlah" in pemetaan or "masuk" not in pemetaan:
        for b in ("masuk", "keluar"):
            pemetaan.pop(b, None)
            yakin.pop(b, None)
            sumber.pop(b, None)

    # validasi isi kolom yang dipetakan dari judul
    if "tanggal" in pemetaan:
        r = rasio_tanggal(df[pemetaan["tanggal"]])
        if r < 0.6:
            alasan.append(f"Kolom '{pemetaan['tanggal']}' dipetakan sebagai tanggal, tetapi hanya "
                          f"{r:.0%} isinya terbaca sebagai tanggal.")
        elif r < 0.9:
            alasan.append(f"Hanya {r:.0%} isi kolom tanggal '{pemetaan['tanggal']}' terbaca sebagai tanggal.")
    for b in ("jumlah", "masuk"):
        if b in pemetaan:
            r = rasio_angka(df[pemetaan[b]])
            if r < 0.6:
                alasan.append(f"Kolom '{pemetaan[b]}' dipetakan sebagai {LABEL_BIDANG[b]}, tetapi hanya "
                              f"{r:.0%} isinya berupa angka.")
            elif r < 0.9:
                alasan.append(f"Hanya {r:.0%} isi kolom {LABEL_BIDANG[b]} '{pemetaan[b]}' berupa angka.")

    # tebakan dari isi kolom bila judul tidak dikenali
    dipakai = set(pemetaan.values())
    if "tanggal" not in pemetaan:
        cand = sorted(((rasio_tanggal(df[k], terima_angka=False), k) for k in kolom if k not in dipakai),
                      reverse=True)
        if cand and cand[0][0] >= 0.8:
            pemetaan["tanggal"], sumber["tanggal"], yakin["tanggal"] = cand[0][1], "isi", 0.5
            dipakai.add(cand[0][1])
            alasan.append(f"Kolom tanggal ditebak dari isinya: '{cand[0][1]}'.")
    if "jumlah" not in pemetaan and "masuk" not in pemetaan:
        cand = sorted(((_tampak_nominal(df[k]), k) for k in kolom if k not in dipakai), reverse=True)
        if cand and cand[0][0] >= 0.8:
            kembar = [k for r, k in cand[1:] if r >= 0.8]
            pemetaan["jumlah"], sumber["jumlah"], yakin["jumlah"] = cand[0][1], "isi", 0.5
            alasan.append(f"Kolom jumlah ditebak dari isinya: '{cand[0][1]}'"
                          + (f" (kandidat lain: {', '.join(repr(str(k)) for k in kembar)})." if kembar else "."))

    hilang = [b for b in WAJIB if b not in pemetaan and not (b == "jumlah" and "masuk" in pemetaan)]
    if hilang:
        status = "gagal"
        alasan.insert(0, "Kolom wajib tidak ditemukan: " + ", ".join(LABEL_BIDANG[b] for b in hilang) + ".")
    elif alasan or any(sumber.get(b) != "judul" for b in WAJIB if b in pemetaan):
        status = "ragu"
    else:
        status = "otomatis"
    return HasilDeteksi(pemetaan=pemetaan, status=status, alasan=alasan, keyakinan=yakin, sumber=sumber)


def terapkan_tersimpan(df: pd.DataFrame, tersimpan: Iterable[Dict[str, Any]]) -> Optional[HasilDeteksi]:
    """Cari pemetaan tersimpan (terbaru lebih dulu) yang semua kolom sumbernya ada di berkas ini."""
    kolom = set(_kolom_data(df))
    tanda = tanda_kolom(kolom)
    daftar = list(tersimpan or [])
    daftar.sort(key=lambda p: p.get("tanda") != tanda)  # sidik jari sama didahulukan; stabil
    for p in daftar:
        pem = {b: k for b, k in (p.get("pemetaan") or {}).items() if k}
        if not all(b in pem for b in WAJIB):
            continue
        if not set(pem.values()) <= kolom:
            continue
        if rasio_tanggal(df[pem["tanggal"]]) < 0.6 or rasio_angka(df[pem["jumlah"]]) < 0.6:
            continue
        return HasilDeteksi(pemetaan=pem, status="tersimpan",
                            alasan=["Memakai pemetaan kolom yang pernah dikonfirmasi lembaga ini."],
                            keyakinan={b: 1.0 for b in pem}, sumber={b: "tersimpan" for b in pem},
                            opsi=dict(p.get("opsi") or {}))
    return None


def validasi_pemetaan_pengguna(df: pd.DataFrame, pemetaan: Dict[str, Optional[str]]) -> Tuple[Dict[str, str], List[str]]:
    """Periksa pilihan pengguna di wizard. Mengembalikan (pemetaan bersih, daftar galat)."""
    bersih = {b: k for b, k in pemetaan.items() if k}
    galat = []
    kolom = set(_kolom_data(df))
    for b in WAJIB:
        if b not in bersih:
            galat.append(f"Pilih kolom untuk {BIDANG_WIZARD.get(b, b)}.")
    for b, k in bersih.items():
        if k not in kolom:
            galat.append(f"Kolom '{k}' tidak ada di berkas.")
    terpakai: Dict[str, List[str]] = {}
    for b, k in bersih.items():
        terpakai.setdefault(k, []).append(b)
    for k, bs in terpakai.items():
        if len(bs) > 1:
            galat.append(f"Kolom '{k}' dipilih untuk lebih dari satu isian: "
                         f"{', '.join(LABEL_BIDANG.get(b, b) for b in bs)}.")
    if galat:
        return bersih, galat
    r = rasio_tanggal(df[bersih["tanggal"]])
    if r < 0.5:
        contoh = ", ".join(repr(str(v)) for v in _sampel(df[bersih["tanggal"]], 3))
        galat.append(f"Kolom '{bersih['tanggal']}' yang dipilih sebagai tanggal hanya {r:.0%} terbaca sebagai "
                     f"tanggal (contoh isi: {contoh}).")
    r = rasio_angka(df[bersih["jumlah"]])
    if r < 0.5:
        contoh = ", ".join(repr(str(v)) for v in _sampel(df[bersih["jumlah"]], 3))
        galat.append(f"Kolom '{bersih['jumlah']}' yang dipilih sebagai jumlah hanya {r:.0%} berupa angka "
                     f"(contoh isi: {contoh}).")
    return bersih, galat


def terapkan_pemetaan(df: pd.DataFrame, pemetaan: Dict[str, str]) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Ganti nama kolom sumber menjadi nama standar. Kolom lain yang namanya bentrok dengan nama
    standar diberi akhiran " (asli)" agar tidak ikut terbaca sebagai kolom standar.

    Returns:
        (DataFrame baru, {kolom standar: judul asli})
    """
    pem = {b: k for b, k in pemetaan.items() if k and k in df.columns}
    sumber = set(pem.values())
    standar = set(pem)
    ganti = {}
    for c in df.columns:
        if c in sumber or c == KOLOM_LOKASI:
            continue
        if c in BIDANG or c in standar:
            ganti[c] = f"{c} (asli)"
    out = df.rename(columns=ganti)
    out = out.rename(columns={k: b for b, k in pem.items()})
    # satu kolom sumber yang dipetakan ke dua bidang tidak diizinkan oleh validasi; jaga-jaga
    out = out.loc[:, ~out.columns.duplicated()]
    return out, {b: str(k) for b, k in pem.items()}
