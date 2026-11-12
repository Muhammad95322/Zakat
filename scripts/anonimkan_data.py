"""Anonimkan berkas data ZIS (Excel/CSV) di laptop sendiri, TANPA jaringan, sebelum dibagikan/diuji.

Yang dilakukan (berkas asli TIDAK diubah; hasil ditulis ke data/private/anon/):

- Nama & ID muzaki/mustahik/donatur diganti pseudonim HMAC-SHA256 dengan kunci rahasia lokal.
  Orang yang sama (beda huruf besar/spasi pun) selalu mendapat pseudonim yang sama.
- Kolom data pribadi DIHAPUS: HP/telepon, alamat, email, NIK/KTP/NPWP, nomor rekening, tanggal lahir,
  catatan/keterangan bebas. Dideteksi dari NAMA KOLOM dan dari POLA ISI (nomor HP, NIK 16 digit,
  email, nomor panjang 10-20 digit), serta kolom teks yang memuat nama orang dari kolom nama.
- Tanggal, jumlah, jenis dana, kanal, wilayah, program, asnaf, dan kolom transaksi lain tetap utuh.
  Bila sel di kolom-kolom ini memuat email/HP/NIK/nama orang, HANYA sel itu yang disensor.
- Laporan berisi kolom yang dihapus/dipseudonimkan, jumlah baris, dan peringatan. ISI BARIS TIDAK DICETAK.

Kunci rahasia dibuat sekali (32 byte acak) di luar repo, default ~/.zakat-insight/kunci_anonim
(izin 600). Simpan kunci ini: kunci yang sama = pseudonim yang sama di unggahan berikutnya.
Jangan pernah membagikan kunci bersama hasil anonimisasi.

Pemakaian:
    python scripts/anonimkan_data.py data/private/donasi_2024.xlsx
    python scripts/anonimkan_data.py donasi.csv --hapus-kolom "Nama Petugas"
"""
# Tidak ada impor modul jaringan di berkas ini (diuji: tests/test_anonimkan.py).
import argparse
import csv
import hashlib
import hmac
import io
import os
import re
import secrets
import stat
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

AKAR = Path(__file__).resolve().parent.parent
KELUAR_BAWAAN = AKAR / "data" / "private" / "anon"
KUNCI_BAWAAN = Path.home() / ".zakat-insight" / "kunci_anonim"
SENSOR = "[DISENSOR]"

# ---------------------------------------------------------------------------
# Pola isi
# ---------------------------------------------------------------------------
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# HP Indonesia: 08xx / +62 8xx / 62 8xx, dengan spasi/titik/strip; telepon rumah (0xx) 7-8 digit
RE_HP = re.compile(r"(?<![\d])(?:\+?62[\s.-]?|0)8\d{1,3}(?:[\s.-]?\d){6,9}(?![\d])"
                   r"|(?<![\d])\(?0\d{1,3}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?![\d])")
# NIK 16 digit (boleh dengan pemisah) dan nomor panjang lain (rekening, KK, NPWP 15 digit)
RE_NIK = re.compile(r"(?<![\d])\d(?:[\s.-]?\d){15}(?![\d])")
RE_NOMOR_PANJANG = re.compile(r"(?<![\d])\d(?:[\s.-]?\d){9,19}(?![\d])")
# Sapaan/gelar diikuti kata berhuruf kapital: "Pak Wahyudi", "bu Wati", "H. Ahmad", "Ustadzah Aisyah".
# Kata benda umum yang lazim mengikuti sapaan dalam nama program/tempat tidak dianggap nama orang.
_SAPAAN = r"(?:pak|bu|bapak|ibu|h\.|hj\.|ust\.|ustadz|ustadzah|ustaz|ustazah|drs\.|dr\.|kak|mas|mbak)"
RE_SAPAAN_NAMA = re.compile(r"(?<![\w.])(?i:" + _SAPAAN + r")\s*(?<=[.\s])([A-Z][a-zA-Z'\-]+)")
BUKAN_NAMA_SETELAH_SAPAAN = {"Asuh", "Kota", "Rumah", "Tangga", "Negara", "Pertiwi", "Hamil", "Menyusui",
                             "RT", "RW", "Lurah", "Camat", "Kades", "Guru", "Dosen"}


def memuat_sapaan_nama(s: str) -> bool:
    return any(m.group(1) not in BUKAN_NAMA_SETELAH_SAPAAN for m in RE_SAPAAN_NAMA.finditer(s))


POLA = (("email", RE_EMAIL), ("NIK", RE_NIK), ("nomor HP/telepon", RE_HP),
        ("nomor panjang (rekening/identitas)", RE_NOMOR_PANJANG))

# ---------------------------------------------------------------------------
# Klasifikasi dari nama kolom (token setelah huruf kecil & tanda baca dibuang)
# ---------------------------------------------------------------------------
TOKEN_ORANG = {"muzaki", "muzakki", "mustahik", "mustahiq", "donatur", "donor", "penyetor", "penerima",
               "anggota", "pelanggan", "jamaah", "peserta", "wali", "petugas", "amil", "penyumbang"}
TOKEN_NAMA = {"nama", "name"}
TOKEN_ID = {"id", "kode", "no", "nomor", "nmr", "npwz", "nim", "nis"}
NAMA_BUKAN_ORANG = {"program", "kampanye", "campaign", "bank", "kota", "kabupaten", "wilayah", "daerah",
                    "kegiatan", "produk", "dana", "kanal", "cabang", "kantor", "lembaga", "instansi", "jenis",
                    "file", "sheet", "bulan", "hari"}
HAPUS_KOLOM = [
    ({"hp"}, "nomor HP"), ({"handphone"}, "nomor HP"), ({"telepon"}, "telepon"), ({"telp"}, "telepon"),
    ({"tlp"}, "telepon"), ({"phone"}, "telepon"), ({"wa"}, "WhatsApp"), ({"whatsapp"}, "WhatsApp"),
    ({"kontak"}, "kontak"), ({"contact"}, "kontak"), ({"seluler"}, "nomor HP"), ({"ponsel"}, "nomor HP"),
    ({"alamat"}, "alamat"), ({"address"}, "alamat"), ({"jalan"}, "alamat"), ({"jl"}, "alamat"),
    ({"rt"}, "alamat"), ({"rw"}, "alamat"), ({"kelurahan"}, "alamat"), ({"desa"}, "alamat"),
    ({"dusun"}, "alamat"), ({"kodepos"}, "alamat"), ({"kode", "pos"}, "alamat"), ({"domisili", "lengkap"}, "alamat"),
    ({"email"}, "email"), ({"e", "mail"}, "email"), ({"surel"}, "email"), ({"mail"}, "email"),
    ({"nik"}, "NIK"), ({"ktp"}, "NIK/KTP"), ({"identitas"}, "nomor identitas"), ({"npwp"}, "NPWP"),
    ({"kk"}, "nomor KK"), ({"paspor"}, "paspor"), ({"passport"}, "paspor"), ({"sim"}, "SIM"),
    ({"rekening"}, "nomor rekening"), ({"rek"}, "nomor rekening"), ({"norek"}, "nomor rekening"),
    ({"account"}, "nomor rekening"), ({"iban"}, "nomor rekening"), ({"va"}, "nomor virtual account"),
    ({"virtual"}, "nomor virtual account"), ({"kartu"}, "nomor kartu"),
    ({"lahir"}, "tanggal/tempat lahir"), ({"umur"}, "umur"), ({"usia"}, "umur"), ({"kelamin"}, "jenis kelamin"),
    ({"gender"}, "jenis kelamin"), ({"pekerjaan"}, "pekerjaan"), ({"agama"}, "agama"),
    ({"catatan"}, "catatan bebas"), ({"keterangan"}, "catatan bebas"), ({"ket"}, "catatan bebas"),
    ({"memo"}, "catatan bebas"), ({"note"}, "catatan bebas"), ({"notes"}, "catatan bebas"),
    ({"pesan"}, "catatan bebas"), ({"komentar"}, "catatan bebas"), ({"comment"}, "catatan bebas"),
    ({"doa"}, "catatan bebas"), ({"harapan"}, "catatan bebas"), ({"uraian"}, "catatan bebas"),
    ({"deskripsi"}, "catatan bebas"), ({"description"}, "catatan bebas"), ({"remark"}, "catatan bebas"),
    ({"remarks"}, "catatan bebas"), ({"foto"}, "foto/berkas"), ({"ttd"}, "tanda tangan"),
]
# kolom transaksi yang harus tetap utuh (dicocokkan bila SEMUA token kunci ada di judul)
KOLOM_UTUH = [
    ({"tanggal"}, "tanggal"), ({"tgl"}, "tanggal"), ({"date"}, "tanggal"), ({"waktu"}, "tanggal"),
    ({"bulan"}, "tanggal"), ({"tahun"}, "tanggal"),
    ({"jumlah"}, "jumlah"), ({"nominal"}, "jumlah"), ({"amount"}, "jumlah"), ({"total"}, "jumlah"),
    ({"nilai"}, "jumlah"), ({"masuk"}, "jumlah"), ({"keluar"}, "jumlah"), ({"debet"}, "jumlah"),
    ({"kredit"}, "jumlah"), ({"jiwa"}, "jumlah"), ({"rupiah"}, "jumlah"), ({"setoran"}, "jumlah"),
    ({"biaya"}, "jumlah"), ({"saldo"}, "jumlah"), ({"harga"}, "jumlah"), ({"fee"}, "jumlah"),
    ({"jenis"}, "kategori"), ({"tipe"}, "kategori"), ({"kategori"}, "kategori"), ({"dana"}, "kategori"),
    ({"akad"}, "kategori"), ({"zis"}, "kategori"),
    ({"kanal"}, "kanal"), ({"metode"}, "kanal"), ({"channel"}, "kanal"), ({"via"}, "kanal"), ({"bayar"}, "kanal"),
    ({"wilayah"}, "wilayah"), ({"kota"}, "wilayah"), ({"kabupaten"}, "wilayah"), ({"kab"}, "wilayah"),
    ({"provinsi"}, "wilayah"), ({"kecamatan"}, "wilayah"), ({"daerah"}, "wilayah"), ({"cabang"}, "wilayah"),
    ({"region"}, "wilayah"), ({"city"}, "wilayah"), ({"area"}, "wilayah"),
    ({"program"}, "program"), ({"pilar"}, "program"), ({"bidang"}, "program"), ({"asnaf"}, "program"),
    ({"golongan"}, "program"), ({"kampanye"}, "program"), ({"campaign"}, "program"), ({"sumber"}, "program"),
    ({"status"}, "status"), ({"arus"}, "kategori"), ({"mutasi"}, "kategori"),
]


def token(s: Any) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", str(s).lower()) if t]


def _cocok(tok: Set[str], kunci: Set[str]) -> bool:
    return kunci <= tok


def peran_kolom(judul: str) -> Tuple[str, str]:
    """('pseudonim'|'hapus'|'utuh'|'lain', alasan) dari judul kolom saja."""
    tok = set(token(judul))
    if not tok:
        return "lain", ""
    for kunci, alasan in HAPUS_KOLOM:
        if _cocok(tok, kunci):
            return "hapus", f"nama kolom menunjukkan {alasan}"
    orang = bool(tok & TOKEN_ORANG)
    if (tok & TOKEN_NAMA) and not (tok & NAMA_BUKAN_ORANG):
        return "pseudonim", "nama orang"
    if orang and (tok & TOKEN_ID):
        return "pseudonim", "ID orang"
    if orang and not (tok & {"jumlah", "total", "jiwa", "kategori", "jenis", "tipe", "status"}):
        return "pseudonim", "nama orang"
    if tok == {"id"} or tok == {"nama"}:
        return "pseudonim", "ID/nama"
    for kunci, alasan in KOLOM_UTUH:
        if _cocok(tok, kunci):
            return "utuh", alasan
    return "lain", ""


# ---------------------------------------------------------------------------
# Kunci & pseudonim
# ---------------------------------------------------------------------------
def siapkan_kunci(path: Path) -> Tuple[bytes, bool]:
    """Baca kunci; buat sekali bila belum ada (izin 600). Tolak lokasi di dalam repo."""
    path = path.expanduser().resolve()
    if AKAR in path.parents or path == AKAR:
        raise SystemExit(f"Kunci tidak boleh disimpan di dalam folder repo ({AKAR}). Pilih lokasi lain.")
    baru = False
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32) + "\n")
        baru = True
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            os.chmod(path, 0o600)
    kunci = path.read_text().strip()
    if len(kunci) < 32:
        raise SystemExit(f"Berkas kunci {path} rusak (terlalu pendek). Pulihkan dari cadangan; jangan diganti "
                         "sembarangan karena pseudonim akan berubah.")
    return kunci.encode("utf-8"), baru


def normal_identitas(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return " ".join(str(v).split()).casefold()


def pseudonim(kunci: bytes, nilai: Any, awalan: str) -> str:
    h = hmac.new(kunci, normal_identitas(nilai).encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{awalan}-{h[:12].upper()}"


# ---------------------------------------------------------------------------
# Baca & tulis tabel
# ---------------------------------------------------------------------------
@dataclass
class Tabel:
    nama: str
    judul: List[str]
    baris: List[List[Any]]
    baris_atas_dibuang: int = 0


def _kosong(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _baris_judul(baris: List[Sequence[Any]]) -> int:
    lebar = max((sum(not _kosong(v) for v in r) for r in baris[:30]), default=0)
    for i, r in enumerate(baris[:30]):
        isi = [v for v in r if not _kosong(v)]
        if len(isi) >= max(2, lebar // 2) and all(isinstance(v, str) for v in isi):
            return i
    return 0


def _jadikan_tabel(nama: str, baris: List[Sequence[Any]]) -> Optional[Tabel]:
    baris = [list(r) for r in baris]
    while baris and all(_kosong(v) for v in baris[-1]):
        baris.pop()
    if not baris:
        return None
    lebar = max(len(r) for r in baris)
    baris = [r + [None] * (lebar - len(r)) for r in baris]
    i = _baris_judul(baris)
    judul = [str(v).strip() if not _kosong(v) else f"Kolom {k + 1}" for k, v in enumerate(baris[i])]
    return Tabel(nama, judul, baris[i + 1:], baris_atas_dibuang=i)


def baca(path: Path) -> Tuple[List[Tabel], Dict[str, Any]]:
    isi = path.read_bytes()
    if path.suffix.lower() in (".csv", ".txt", ".tsv"):
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                teks = isi.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        contoh = "\n".join(teks.splitlines()[:50])
        try:
            pemisah = csv.Sniffer().sniff(contoh, delimiters=",;\t|").delimiter
        except csv.Error:
            pemisah = ","
        baris = [[v if v != "" else None for v in r] for r in csv.reader(io.StringIO(teks), delimiter=pemisah)]
        t = _jadikan_tabel("CSV", baris)
        return ([t] if t else []), {"jenis": "csv", "pemisah": pemisah}
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(isi), read_only=True, data_only=True)
    try:
        tabel = []
        for ws in wb.worksheets:
            t = _jadikan_tabel(ws.title, list(ws.iter_rows(min_row=1, min_col=1, values_only=True)))
            if t:
                tabel.append(t)
    finally:
        wb.close()
    return tabel, {"jenis": "xlsx"}


def _aman_excel(v: Any) -> Any:
    """Cegah teks berawalan = + - @ terbaca sebagai rumus saat dibuka di Excel."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") and len(v) > 1:
        return "'" + v
    return v


def tulis(path: Path, tabel: List[Tabel], info: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if info["jenis"] == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=info.get("pemisah", ","), lineterminator="\r\n")
        t = tabel[0]
        w.writerow(t.judul)
        for r in t.baris:
            w.writerow(["" if v is None else v for v in r])
        data = buf.getvalue().encode("utf-8-sig")
    else:
        import openpyxl
        wb = openpyxl.Workbook(write_only=True)
        for t in tabel:
            ws = wb.create_sheet(t.nama[:31])
            ws.append(t.judul)
            for r in t.baris:
                ws.append([_aman_excel(v) for v in r])
        b = io.BytesIO()
        wb.save(b)
        data = b.getvalue()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


# ---------------------------------------------------------------------------
# Anonimisasi
# ---------------------------------------------------------------------------
@dataclass
class Laporan:
    berkas: str
    keluaran: str = ""
    per_tabel: List[Dict[str, Any]] = field(default_factory=list)
    peringatan: List[str] = field(default_factory=list)


def _teks_sel(v: Any) -> Optional[str]:
    """Representasi teks sel untuk pemeriksaan pola (angka bulat panjang ikut diperiksa)."""
    if v is None or isinstance(v, (datetime, date, bool)):
        return None
    if isinstance(v, float):
        if not v.is_integer():
            return None
        v = int(v)
    return str(v)


def _pola_cocok(s: str) -> Optional[str]:
    for nama, rx in POLA:
        if rx.search(s):
            return nama
    if s.isdigit() and len(s) >= 10 and s[0] == "8":  # HP yang kehilangan angka 0 di Excel
        return "nomor HP/telepon"
    return None


def _ngram(tok: List[str], n_maks: int = 4) -> Set[str]:
    return {" ".join(tok[i:i + n]) for n in range(1, n_maks + 1) for i in range(len(tok) - n + 1)}


def _memuat_nama(s: str, nama: Set[str]) -> bool:
    return bool(nama) and bool(_ngram([t for t in re.split(r"[^\w]+", s.casefold()) if t]) & nama)


def anonimkan_tabel(t: Tabel, kunci: bytes, hapus_paksa: Set[str]) -> Tuple[Tabel, Dict[str, Any], List[str]]:
    peran = []
    for j in t.judul:
        if normal_identitas(j) in hapus_paksa:
            peran.append(("hapus", "diminta pengguna (--hapus-kolom)"))
        else:
            peran.append(peran_kolom(j))
    kolom = list(zip(*t.baris)) if t.baris else [() for _ in t.judul]

    # kumpulkan nama orang dari kolom nama untuk mendeteksi nama yang bocor ke kolom lain
    nama_orang: Set[str] = set()
    for (p, alasan), isi in zip(peran, kolom):
        if p == "pseudonim" and "nama" in alasan:
            for v in isi:
                if isinstance(v, str):
                    n = normal_identitas(v)
                    if len(n) >= 4 and not n.isdigit():
                        nama_orang.add(n)

    # kolom 'lain': hapus bila isinya memuat pola data pribadi atau nama orang
    for k, ((p, _), isi) in enumerate(zip(peran, kolom)):
        if p != "lain":
            continue
        for v in isi:
            s = _teks_sel(v)
            if s is None:
                continue
            pola = _pola_cocok(s)
            if pola:
                peran[k] = ("hapus", f"isi kolom memuat {pola}")
                break
            if isinstance(v, str) and _memuat_nama(s, nama_orang):
                peran[k] = ("hapus", "isi kolom memuat nama orang dari kolom nama")
                break

    sensor = 0
    pakai = [k for k, (p, _) in enumerate(peran) if p != "hapus"]
    baris_baru = []
    for r in t.baris:
        b = []
        for k in pakai:
            v = r[k]
            p, alasan = peran[k]
            if p == "pseudonim" and not _kosong(v):
                awalan = "MST" if set(token(t.judul[k])) & {"mustahik", "mustahiq", "penerima"} else (
                    "PTG" if set(token(t.judul[k])) & {"petugas", "amil"} else "MZK")
                v = pseudonim(kunci, v, awalan)
            elif isinstance(v, str) and (_bocor_di_sel(v, p) or _memuat_nama(v, nama_orang)
                                         or memuat_sapaan_nama(v)):
                v, sensor = SENSOR, sensor + 1
            b.append(v)
        baris_baru.append(b)

    peringatan = []
    for k in pakai:
        p, _ = peran[k]
        if p not in ("lain", "utuh"):
            continue
        teks = [v for v in (r[k] for r in t.baris) if isinstance(v, str) and re.search(r"[A-Za-z]{3}", v)]
        unik = len(set(teks))
        # kolom 'lain': hati-hati, lebih baik peringatan berlebih daripada nama lolos. Kolom 'utuh' (kategori
        # seperti jenis dana/kanal) normalnya sedikit nilai; banyak nilai unik = kemungkinan teks bebas.
        banyak = unik >= 5 if p == "lain" else (unik >= 20 and unik / max(len(teks), 1) > 0.3)
        if teks and banyak:
            peringatan.append(f"Kolom '{t.judul[k]}' ({t.nama}) berisi teks beragam ({unik} nilai berbeda) yang mungkin "
                              "masih memuat nama atau data pribadi. Periksa manual; hapus dengan --hapus-kolom "
                              f"\"{t.judul[k]}\" bila perlu.")
    ringkas = {
        "tabel": t.nama, "baris": len(t.baris), "baris_atas_dibuang": t.baris_atas_dibuang,
        "dihapus": [(t.judul[k], a) for k, (p, a) in enumerate(peran) if p == "hapus"],
        "pseudonim": [(t.judul[k], a) for k, (p, a) in enumerate(peran) if p == "pseudonim"],
        "utuh": [t.judul[k] for k, (p, _) in enumerate(peran) if p == "utuh"],
        "lain": [t.judul[k] for k, (p, _) in enumerate(peran) if p == "lain"],
        "sel_disensor": sensor,
    }
    return Tabel(t.nama, [t.judul[k] for k in pakai], baris_baru), ringkas, peringatan


def _bocor_di_sel(v: str, peran: str) -> bool:
    """Sel teks memuat data pribadi? Di kolom 'utuh' (tanggal/jumlah/kategori) nomor panjang tidak
    dianggap bocor karena bisa berupa nominal, dan pola telepon diabaikan untuk teks tanggal."""
    if peran != "utuh":
        return _pola_cocok(v) is not None
    if RE_EMAIL.search(v) or RE_NIK.search(v):
        return True
    return bool(RE_HP.search(v)) and not _tanggal_teks(v)


def _tanggal_teks(s: str) -> bool:
    return bool(re.fullmatch(r"\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}(\s+\d{1,2}[:.]\d{2}(:\d{2})?)?\s*", s))


def anonimkan(masukan: Path, keluar: Path = KELUAR_BAWAAN, kunci_path: Path = KUNCI_BAWAAN,
              hapus_kolom: Sequence[str] = ()) -> Laporan:
    masukan = masukan.resolve()
    if not masukan.is_file():
        raise SystemExit(f"Berkas tidak ditemukan: {masukan}")
    if masukan.suffix.lower() not in (".xlsx", ".xlsm", ".csv", ".tsv", ".txt"):
        raise SystemExit("Format belum didukung. Simpan berkas sebagai .xlsx atau .csv lalu ulangi.")
    kunci, baru = siapkan_kunci(kunci_path)
    tabel, info = baca(masukan)
    if not tabel:
        raise SystemExit("Berkas tidak berisi tabel data.")
    akhiran = ".csv" if info["jenis"] == "csv" else ".xlsx"
    tujuan = (keluar / f"{masukan.stem}_anon{akhiran}").resolve()
    if tujuan == masukan:
        raise SystemExit("Berkas keluaran tidak boleh menimpa berkas asli.")
    lap = Laporan(berkas=masukan.name, keluaran=str(tujuan))
    if baru:
        lap.peringatan.append(f"Kunci rahasia BARU dibuat di {kunci_path.expanduser()}. Simpan cadangannya di tempat "
                              "aman (bukan di repo): kunci yang sama diperlukan agar pseudonim tetap sama.")
    paksa = {normal_identitas(h) for h in hapus_kolom}
    hasil = []
    for t in tabel:
        t2, ringkas, peringatan = anonimkan_tabel(t, kunci, paksa)
        hasil.append(t2)
        lap.per_tabel.append(ringkas)
        lap.peringatan.extend(peringatan)
    tulis(tujuan, hasil, info)
    return lap


def cetak(lap: Laporan) -> None:
    """Cetak laporan TANPA isi baris."""
    print(f"Berkas masukan : {lap.berkas} (tidak diubah)")
    print(f"Berkas keluaran: {lap.keluaran}")
    for r in lap.per_tabel:
        print(f"\n[{r['tabel']}] {r['baris']} baris data"
              + (f"; {r['baris_atas_dibuang']} baris judul/keterangan di atas tabel tidak disalin" if
                 r["baris_atas_dibuang"] else ""))
        print("  Dihapus      : " + ("; ".join(f"'{j}' ({a})" for j, a in r["dihapus"]) or "-"))
        print("  Dipseudonimkan: " + ("; ".join(f"'{j}'" for j, _ in r["pseudonim"]) or "-"))
        print("  Tetap utuh   : " + (", ".join(f"'{j}'" for j in r["utuh"]) or "-"))
        if r["lain"]:
            print("  Lainnya (tetap): " + ", ".join(f"'{j}'" for j in r["lain"]))
        if r["sel_disensor"]:
            print(f"  Sel disensor : {r['sel_disensor']} (memuat email/HP/NIK/nama di kolom yang dipertahankan)")
    if lap.peringatan:
        print("\nPERINGATAN:")
        for w in lap.peringatan:
            print(f"  - {w}")
    print("\nPeriksa hasilnya sebelum dibagikan. Jangan memasukkan berkas asli maupun hasil ke git.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Anonimkan berkas data ZIS (tanpa jaringan).")
    ap.add_argument("berkas", help="berkas .xlsx atau .csv")
    ap.add_argument("--keluar", default=str(KELUAR_BAWAAN), help="folder keluaran (bawaan: data/private/anon)")
    ap.add_argument("--kunci", default=str(KUNCI_BAWAAN), help="lokasi berkas kunci rahasia (di luar repo)")
    ap.add_argument("--hapus-kolom", action="append", default=[], help="judul kolom tambahan yang harus dihapus")
    a = ap.parse_args(argv)
    lap = anonimkan(Path(a.berkas), Path(a.keluar), Path(a.kunci), a.hapus_kolom)
    cetak(lap)
    return 0


if __name__ == "__main__":
    sys.exit(main())
