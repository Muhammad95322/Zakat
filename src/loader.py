"""Loader berkas Excel/CSV ZIS yang toleran terhadap format lembaga yang beragam.

Yang ditangani:

- CSV: pemisah koma/titik koma/tab/pipa (dideteksi), encoding UTF-8, UTF-8 dengan BOM,
  Windows-1252 (fallback Latin-1), baris judul/keterangan di atas header.
- Excel (.xlsx): judul & baris kosong di atas header (baris header dideteksi), sel digabung
  vertikal (nilai diisi ke semua baris gabungan, kecuali angka agar nominal tidak terhitung ganda),
  kolom & baris kosong, sheet petunjuk/sampul, satu sheet per tahun (digabung bila strukturnya sama).

Setiap tabel yang dikembalikan membawa kolom ``__lokasi__`` (mis. "baris 12" atau
"sheet '2023' baris 12") agar pesan galat bisa menunjuk baris di berkas asli.
Semua kegagalan dilaporkan sebagai :class:`DataFileError` berbahasa Indonesia.
"""
import contextlib
import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.pemetaan import (
    BIDANG, KOLOM_LOKASI, WAJIB, deteksi_pemetaan, normalisasi_judul, skor_baris_judul, skor_judul,
    tanda_kolom,
)
from src.tanggal_impor import gabung_tahun_bulan, parse_satu
from src.utils import parse_angka_indonesia

# Kompatibilitas: kamus sinonim lama (dipakai pesan galat & dokumentasi)
COLUMN_SYNONYMS = {b: list(sin) for b, (sin, _) in BIDANG.items()}

# Kolom minimum agar analisis bisa dijalankan
KOLOM_WAJIB = {
    "Penghimpunan": ["tanggal", "jumlah"],
    "Penyaluran": ["tanggal", "jumlah"],
}

KATA_SHEET_HIMPUN = ["himpun", "masuk", "donasi", "terima", "collection", "inflow", "pemasukan"]
KATA_SHEET_SALUR = ["salur", "keluar", "mustahik", "distribusi", "outflow", "tasaruf", "tasyaruf",
                    "pendayagunaan"]
KATA_SHEET_ABAIKAN = ["petunjuk", "keterangan", "instruksi", "readme", "cover", "sampul", "panduan",
                      "rekap", "ringkasan", "summary", "pivot", "grafik", "chart", "referensi", "master"]

_BATAS_CARI_JUDUL = 30


class DataFileError(ValueError):
    """Kesalahan isi/format berkas data yang aman ditampilkan ke pengguna."""


def _normalisasi_string(s: str) -> str:
    """Normalisasi string nama kolom untuk pencocokan (kompatibilitas)."""
    return re.sub(r"[^a-zA-Z0-9]", "_", str(s).strip().lower())


def deteksi_kolom(df: pd.DataFrame, expected_cols: list) -> Tuple[Dict[str, str], list]:
    """Mencocokkan judul kolom dengan kolom standar (berdasarkan judul saja).

    Returns:
        (mapping {nama_kolom_asli: nama_kolom_standar}, kolom standar yang tidak ditemukan)
    """
    from src.pemetaan import _cocokkan_judul
    kolom = [c for c in df.columns if c != KOLOM_LOKASI]
    pem, _, _ = _cocokkan_judul(kolom, [c for c in expected_cols if c in BIDANG])
    return {k: b for b, k in pem.items()}, [c for c in expected_cols if c not in pem]


def validasi_kolom_wajib(df: pd.DataFrame, sheet_type: str = "Penghimpunan") -> None:
    """Pastikan kolom wajib ada (judul atau isi kolom). Raises DataFileError yang menjelaskan."""
    hasil = deteksi_pemetaan(df, sheet_type)
    hilang = hasil.kolom_wajib_hilang()
    if hilang and not (hilang == ["jumlah"] and "masuk" in hasil.pemetaan):
        raise DataFileError(pesan_kolom_hilang(df, hilang, sheet_type))


def pesan_kolom_hilang(df: pd.DataFrame, hilang: List[str], sheet_type: str = "Penghimpunan") -> str:
    detail = "; ".join(
        f"'{c}' (nama judul yang dikenali: {', '.join(COLUMN_SYNONYMS.get(c, [c])[:8])}, dst.)" for c in hilang
    )
    ada = ", ".join(repr(str(c)) for c in df.columns if c != KOLOM_LOKASI) or "(tidak ada)"
    from src.tanggal_impor import BULAN
    n_bulan = sum(str(c).strip().lower().split(" ")[0] in BULAN for c in df.columns)
    rekap = (" Berkas ini tampak berupa REKAP dengan bulan sebagai kolom; Zakat Insight membutuhkan data per "
             "transaksi (satu baris per donasi dengan kolom tanggal dan nominal)." if n_bulan >= 3 else "")
    return (f"Sheet {sheet_type} tidak memiliki kolom wajib: {detail}. Kolom yang ditemukan: {ada}.{rekap} "
            "Pilih kolomnya lewat formulir pemetaan kolom saat mengunggah, ubah judul kolom, "
            "atau gunakan template Excel.")


def _batas_baris() -> int:
    from src.config import settings
    return settings.MAX_BARIS


def _cek_baris(n: int, nama: str) -> None:
    if n > _batas_baris():
        raise DataFileError(f"{nama} memiliki lebih dari {_batas_baris():,} baris. "
                            "Bagi berkas menjadi beberapa bagian.".replace(",", "."))


# ---------------------------------------------------------------------------
# Tabel mentah (list baris) -> DataFrame dengan judul kolom yang terdeteksi
# ---------------------------------------------------------------------------
def _kosong(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    return isinstance(v, str) and not v.strip()


def _tampak_data(v: Any) -> bool:
    """Sel yang tampak seperti data (angka/tanggal), bukan judul kolom."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)) or hasattr(v, "year"):
        return True
    s = str(v).strip()
    return parse_angka_indonesia(s) is not None or parse_satu(s) is not None


def _huruf_kolom(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cari_baris_judul(baris: List[Sequence[Any]]) -> Optional[int]:
    """Indeks baris judul kolom di antara baris teratas; None bila berkas tanpa judul kolom."""
    terbaik, skor_terbaik = None, 0
    for i, r in enumerate(baris[:_BATAS_CARI_JUDUL]):
        isi = [v for v in r if not _kosong(v)]
        if len(isi) < 2 or any(_tampak_data(v) for v in isi):
            continue  # baris judul tidak berisi tanggal/angka; baris seperti itu adalah data
        unik = list(dict.fromkeys(str(v).strip() for v in isi if isinstance(v, str)))
        skor = skor_baris_judul(unik)
        if skor > skor_terbaik:
            terbaik, skor_terbaik = i, skor
    if terbaik is not None and skor_terbaik >= 2:
        return terbaik
    # tidak ada judul yang dikenal: baris pertama yang semua selnya teks (bukan angka/tanggal)
    for i, r in enumerate(baris[:_BATAS_CARI_JUDUL]):
        isi = [v for v in r if not _kosong(v)]
        if len(isi) >= 2 and not any(_tampak_data(v) for v in isi):
            return i
    return terbaik  # satu judul dikenal (skor 1) lebih baik daripada tidak ada


@dataclass(eq=False)
class Tabel:
    df: pd.DataFrame
    sumber: str
    baris_judul: Optional[int]          # nomor baris (1-based) judul kolom di berkas, None = tanpa judul
    baris_kosong: int = 0
    kolom_kosong: List[str] = field(default_factory=list)


def _bentuk_tabel(baris: List[Sequence[Any]], sumber: str, awalan_lokasi: str = "") -> Optional[Tabel]:
    """Ubah list baris mentah menjadi DataFrame berjudul; None bila tidak ada isi sama sekali."""
    # buang baris kosong di akhir
    while baris and all(_kosong(v) for v in baris[-1]):
        baris.pop()
    if not baris:
        return None
    lebar = max(len(r) for r in baris)
    idx = _cari_baris_judul(baris)
    if idx is None:
        # tanpa judul kolom: mulai dari baris pertama yang berisi
        mulai = next(i for i, r in enumerate(baris) if any(not _kosong(v) for v in r))
        judul = [f"Kolom {_huruf_kolom(i)}" for i in range(lebar)]
        data_mulai = mulai
    else:
        mentah = list(baris[idx]) + [None] * (lebar - len(baris[idx]))
        judul = []
        for i, v in enumerate(mentah):
            if _kosong(v):
                judul.append(f"Kolom {_huruf_kolom(i)}")
            else:
                judul.append(re.sub(r"\s+", " ", str(v)).strip())
        data_mulai = idx + 1
    # judul kembar -> beri akhiran
    terlihat: Dict[str, int] = {}
    for i, j in enumerate(judul):
        if j in terlihat:
            terlihat[j] += 1
            judul[i] = f"{j} ({terlihat[j]})"
        else:
            terlihat[j] = 1

    isi, lokasi, n_kosong = [], [], 0
    for i in range(data_mulai, len(baris)):
        r = baris[i]
        if all(_kosong(v) for v in r):
            n_kosong += 1
            continue
        isi.append(list(r) + [None] * (lebar - len(r)))
        lokasi.append(f"{awalan_lokasi}baris {i + 1}")
    df = pd.DataFrame(isi, columns=judul, dtype=object) if isi else pd.DataFrame(columns=judul, dtype=object)
    # kolom yang seluruh isinya kosong dibuang (judulnya dicatat)
    kolom_kosong = [c for c in df.columns if df[c].map(_kosong).all()] if len(df) else []
    if len(df):
        df = df.drop(columns=kolom_kosong)
    kolom_kosong = [c for c in kolom_kosong if not c.startswith("Kolom ")]
    df[KOLOM_LOKASI] = lokasi
    return Tabel(df=df.reset_index(drop=True), sumber=sumber,
                 baris_judul=None if idx is None else idx + 1, baris_kosong=n_kosong, kolom_kosong=kolom_kosong)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def _dekode(isi: bytes, nama: str) -> Tuple[str, str]:
    sampel = isi[:4096]
    if b"\x00" in sampel:
        raise DataFileError(
            f"Berkas '{nama}' bukan berkas teks CSV (berisi data biner). Bila ini berkas Excel, "
            "simpan dengan ekstensi .xlsx; bila CSV, simpan ulang sebagai 'CSV UTF-8'.")
    if isi.startswith(b"\xef\xbb\xbf"):
        return isi[3:].decode("utf-8", errors="replace"), "UTF-8 (BOM)"
    try:
        return isi.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        pass
    try:
        return isi.decode("cp1252"), "Windows-1252"
    except UnicodeDecodeError:
        return isi.decode("latin-1"), "Latin-1"


def _deteksi_pemisah(teks: str) -> str:
    baris = [b for b in teks.splitlines()[:200] if b.strip()]
    if baris and baris[0].lower().startswith("sep=") and len(baris[0].strip()) == 5:
        return baris[0].strip()[4]
    terbaik, skor_terbaik = ",", (-1, -1)
    for p in [",", ";", "\t", "|"]:
        try:
            jumlah = [len(r) for r in csv.reader(baris, delimiter=p)]
        except csv.Error:
            continue
        if not jumlah:
            continue
        modus = max(set(jumlah), key=jumlah.count)
        konsisten = jumlah.count(modus) / len(jumlah)
        if modus < 2:
            continue
        skor = (int(konsisten >= 0.6), modus if konsisten >= 0.6 else 0, konsisten)
        if skor > skor_terbaik:
            terbaik, skor_terbaik = p, skor
    return terbaik


_NAMA_PEMISAH = {",": "koma", ";": "titik koma", "\t": "tab", "|": "garis tegak"}


def _baca_csv(isi: bytes, nama: str) -> Tuple[Tabel, Dict[str, Any]]:
    teks, enc = _dekode(isi, nama)
    if not teks.strip():
        raise DataFileError(f"Berkas CSV '{nama}' kosong: tidak ada judul kolom maupun data.")
    pemisah = _deteksi_pemisah(teks)
    baris_teks = teks.splitlines()
    if baris_teks and baris_teks[0].lower().startswith("sep="):
        baris_teks[0] = ""
    _cek_baris(len(baris_teks) - 1, f"Berkas CSV '{nama}'")
    try:
        baris = [[v if v.strip() else None for v in r] for r in csv.reader(baris_teks, delimiter=pemisah)]
    except csv.Error as e:
        raise DataFileError(f"Berkas CSV '{nama}' tidak dapat dibaca: {e}. Simpan ulang sebagai CSV.")
    tabel = _bentuk_tabel(baris, "CSV")
    if tabel is None:
        raise DataFileError(f"Berkas CSV '{nama}' kosong: tidak ada judul kolom maupun data.")
    if tabel.df.empty:
        raise DataFileError(f"Berkas CSV '{nama}' tidak berisi baris data (hanya judul kolom).")
    if len([c for c in tabel.df.columns if c != KOLOM_LOKASI]) < 2:
        raise DataFileError(
            f"Berkas CSV '{nama}' hanya terbaca sebagai satu kolom. Pastikan nilai dipisah koma, titik koma, "
            "atau tab, dan setiap baris memiliki jumlah kolom yang sama.")
    return tabel, {"jenis": "CSV", "encoding": enc, "pemisah": _NAMA_PEMISAH.get(pemisah, pemisah)}


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def _ada_sel_gabung(isi: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(isi)) as z:
            for n in z.namelist():
                if n.startswith("xl/worksheets/") and n.endswith(".xml"):
                    with z.open(n) as f:
                        while True:
                            potong = f.read(1 << 20)
                            if not potong:
                                break
                            if b"<mergeCell " in potong or b"<mergeCells" in potong:
                                return True
    except Exception:
        return False
    return False


def _sheet_mentah(isi: bytes, nama: str) -> List[Tuple[str, List[Sequence[Any]], int]]:
    """[(nama sheet, baris mentah, jumlah sel gabung yang diisi)]"""
    if isi[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise DataFileError(
            f"Berkas '{nama}' berformat Excel lama (.xls 97-2003) atau dilindungi kata sandi. Format ini belum "
            "didukung: buka di Excel, hapus kata sandi bila ada, lalu Simpan Sebagai 'Excel Workbook (.xlsx)'.")
    import openpyxl
    gabung = _ada_sel_gabung(isi)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(isi), read_only=not gabung, data_only=True)
    except Exception as e:
        raise DataFileError(
            f"Berkas Excel '{nama}' rusak atau bukan file Excel yang valid ({type(e).__name__}). "
            "Buka dan simpan ulang berkas di Excel, lalu unggah kembali.")
    hasil = []
    batas = _batas_baris() + _BATAS_CARI_JUDUL + 1
    try:
        for ws in wb.worksheets:
            diisi = 0
            if gabung and hasattr(ws, "merged_cells"):
                for rng in list(ws.merged_cells.ranges):
                    v = ws.cell(rng.min_row, rng.min_col).value
                    ws.unmerge_cells(str(rng))
                    if rng.min_col != rng.max_col or v is None:
                        continue  # gabung horizontal (judul): cukup sel kiri atas
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        continue  # jangan gandakan nominal
                    for r in range(rng.min_row + 1, rng.max_row + 1):
                        ws.cell(r, rng.min_col).value = v
                        diisi += 1
            baris = []
            for r in ws.iter_rows(min_row=1, min_col=1, values_only=True):
                baris.append(r)
                if len(baris) > batas:
                    _cek_baris(len(baris), f"Sheet '{ws.title}'")
            hasil.append((ws.title, baris, diisi))
    except DataFileError:
        raise
    except Exception as e:
        raise DataFileError(f"Berkas Excel '{nama}' tidak dapat dibaca ({type(e).__name__}). "
                            "Buka dan simpan ulang berkas di Excel, lalu unggah kembali.")
    finally:
        with contextlib.suppress(Exception):  # menutup berkas tidak boleh menutupi galat aslinya
            wb.close()
    if not hasil:
        raise DataFileError(f"Berkas Excel '{nama}' tidak memiliki sheet.")
    return hasil


def _ada_kata(nama: str, kata: List[str]) -> bool:
    n = nama.lower()
    return any(k in n for k in kata)


def _jenis_dari_isi(tabel: Tabel) -> Optional[str]:
    """'Penghimpunan' / 'Penyaluran' / None (bukan tabel transaksi) dari judul kolomnya."""
    kolom = [c for c in tabel.df.columns if c != KOLOM_LOKASI]
    if tabel.df.empty or len(kolom) < 2:
        return None
    ada = lambda b: any(skor_judul(k, b) >= 0.8 for k in kolom)  # noqa: E731
    punya_tanggal = ada("tanggal")
    punya_nominal = ada("jumlah") or ada("masuk") or ada("keluar")
    if not (punya_tanggal and punya_nominal):
        det = deteksi_pemetaan(tabel.df)
        if det.status == "gagal":
            return None
    salur = sum(ada(b) for b in ("program", "asnaf", "jumlah_penerima"))
    himpun = sum(ada(b) for b in ("id_muzaki", "nama_muzaki", "kanal"))
    return "Penyaluran" if salur > himpun else "Penghimpunan"


@dataclass
class BerkasTerbaca:
    tabel: Dict[str, pd.DataFrame]
    info: Dict[str, Any]


def _gabung_sheet(daftar: List[Tabel]) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """Gabungkan sheet-sheet berstruktur sama (mis. satu sheet per tahun)."""
    pertama = daftar[0]
    tanda = tanda_kolom(pertama.df.columns)
    pakai, lewati = [pertama], []
    for t in daftar[1:]:
        (pakai if tanda_kolom(t.df.columns) == tanda else lewati).append(t)
    if len(pakai) == 1:
        df = pertama.df
    else:
        # samakan nama kolom ke urutan sheet pertama berdasar judul ternormalisasi
        acuan = {normalisasi_judul(c): c for c in pertama.df.columns}
        bagian = [t.df.rename(columns={c: acuan.get(normalisasi_judul(c), c) for c in t.df.columns})
                  for t in pakai]
        df = pd.concat(bagian, ignore_index=True)
    return df, [t.sumber for t in pakai], [t.sumber for t in lewati]


def baca_berkas(file_content: bytes, filename: str) -> BerkasTerbaca:
    """Baca berkas menjadi tabel Penghimpunan (wajib) dan Penyaluran (opsional) beserta info pembacaan."""
    hasil = _baca_berkas(file_content, filename)
    for jenis, df in list(hasil.tabel.items()):
        df2, catatan = gabung_tahun_bulan(df, KOLOM_LOKASI)
        if catatan:
            hasil.tabel[jenis] = df2
            hasil.info.setdefault("catatan", []).append(f"{jenis}: {catatan}")
    return hasil


def _baca_berkas(file_content: bytes, filename: str) -> BerkasTerbaca:
    if not file_content:
        raise DataFileError(f"Berkas '{filename}' kosong (0 byte). Unggah berkas yang berisi data.")
    fn = filename.lower()
    if fn.endswith(".csv") or fn.endswith(".txt"):
        tabel, info = _baca_csv(file_content, filename)
        info.update({"sheet_penghimpunan": ["CSV"], "baris_judul": tabel.baris_judul,
                     "baris_kosong": tabel.baris_kosong, "kolom_kosong": tabel.kolom_kosong, "catatan": []})
        return BerkasTerbaca({"Penghimpunan": tabel.df}, info)

    mentah = _sheet_mentah(file_content, filename)
    banyak = len(mentah) > 1
    tabel_sheet: List[Tuple[str, Optional[Tabel]]] = []
    sel_gabung = 0
    for nama, baris, diisi in mentah:
        sel_gabung += diisi
        awalan = f"sheet '{nama}' " if banyak else ""
        tabel_sheet.append((nama, _bentuk_tabel(list(baris), f"sheet '{nama}'", awalan)))

    catatan: List[str] = []
    himpun_kata = [(n, t) for n, t in tabel_sheet if _ada_kata(n, KATA_SHEET_HIMPUN)]
    salur_kata = [(n, t) for n, t in tabel_sheet if _ada_kata(n, KATA_SHEET_SALUR)
                  and not _ada_kata(n, KATA_SHEET_HIMPUN)]

    # sheet penghimpunan bernama jelas tetapi kosong -> galat eksplisit
    for n, t in himpun_kata:
        if t is None or t.df.empty:
            raise DataFileError(
                f"Sheet '{n}' (data penghimpunan) pada berkas '{filename}' kosong. "
                "Isi sheet tersebut dengan data transaksi atau gunakan template Excel.")

    lain = [(n, t) for n, t in tabel_sheet if (n, t) not in himpun_kata and (n, t) not in salur_kata
            and t is not None and not t.df.empty]
    jenis_lain = {n: _jenis_dari_isi(t) for n, t in lain}
    if himpun_kata:
        himpun = [t for _, t in himpun_kata]
    else:
        himpun = [t for n, t in lain if jenis_lain[n] == "Penghimpunan" and not _ada_kata(n, KATA_SHEET_ABAIKAN)]
        if not himpun:
            himpun = [t for n, t in lain if jenis_lain[n] == "Penghimpunan"]
    if not himpun:
        # tidak ada yang tampak seperti tabel transaksi: pakai sheet pertama yang berisi (wizard memutuskan)
        kandidat = [t for n, t in tabel_sheet if t is not None and not t.df.empty
                    and not _ada_kata(n, KATA_SHEET_SALUR)]
        if not kandidat:
            n0 = mentah[0][0]
            raise DataFileError(
                f"Sheet '{n0}' (data penghimpunan) pada berkas '{filename}' kosong. "
                "Isi sheet tersebut dengan data transaksi atau gunakan template Excel.")
        himpun = kandidat[:1]
    df_himpun, sheet_himpun, dilewati = _gabung_sheet(himpun)
    if len(sheet_himpun) > 1:
        catatan.append(f"{len(sheet_himpun)} sheet berstruktur sama digabung: {', '.join(sheet_himpun)}.")
    if dilewati:
        catatan.append(f"Sheet dengan susunan kolom berbeda tidak ikut dibaca: {', '.join(dilewati)}.")

    res = {"Penghimpunan": df_himpun}
    salur = [t for _, t in salur_kata if t is not None and not t.df.empty] or \
            [t for n, t in lain if jenis_lain[n] == "Penyaluran"]
    sheet_salur = None
    if salur:
        res["Penyaluran"] = salur[0].df
        sheet_salur = salur[0].sumber
    t0 = himpun[0]
    info = {"jenis": "Excel", "sheet_penghimpunan": sheet_himpun, "sheet_penyaluran": sheet_salur,
            "baris_judul": t0.baris_judul, "baris_kosong": sum(t.baris_kosong for t in himpun),
            "kolom_kosong": sorted({k for t in himpun for k in t.kolom_kosong}),
            "sel_gabung_diisi": sel_gabung, "catatan": catatan,
            "sheet_diabaikan": [n for n, t in tabel_sheet if t is not None and not t.df.empty
                                and t not in himpun and t not in salur]}
    return BerkasTerbaca(res, info)


def load_file(file_content: bytes, filename: str) -> Dict[str, pd.DataFrame]:
    """Membaca file Excel atau CSV dan mengembalikan dict of DataFrames.

    Returns:
        dict: {"Penghimpunan": df_himpun, "Penyaluran": df_salur (opsional)}; setiap DataFrame
        membawa kolom ``__lokasi__`` (posisi baris di berkas asli).

    Raises:
        DataFileError: file kosong, rusak, atau sheet penghimpunan kosong.
            Sheet penyaluran yang kosong diabaikan (tidak dikembalikan).
    """
    return baca_berkas(file_content, filename).tabel
