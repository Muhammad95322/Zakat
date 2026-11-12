"""Generator berkas data ZIS SINTETIS yang "kotor", meniru kebiasaan lembaga zakat yang berbeda-beda.

Semua data dibuat dari nol dengan seed tetap (bukan data donatur asli). Setiap variasi ditulis ke
berkas tersendiri, dan ``manifest.json`` mencatat kunci jawabannya: jumlah baris transaksi yang
sah, total nominal, rentang tanggal, dan jumlah per kategori. Dengan kunci itu,
``scripts/ukur_impor.py`` dapat menilai apakah impor terbaca BENAR, bukan sekadar tidak error.

Pemakaian:
    python scripts/buat_data_kotor.py                       # ke data/sintetis_kotor/
    python scripts/buat_data_kotor.py --keluar /tmp/x --tanpa-besar
"""
# nosec B311 (seluruh berkas): `random` hanya untuk membuat DATA SINTETIS, bukan kriptografi
import argparse
import csv
import io
import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd

SEED = 20241112
AKAR = Path(__file__).resolve().parent.parent

BULAN_ID = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
            "Oktober", "November", "Desember"]
BULAN_EN3 = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
BULAN_ID3 = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

NAMA_DEPAN = ["Ahmad", "Siti", "Budi", "Dewi", "Rizki", "Nur", "Agus", "Fitri", "Hendra", "Rina", "Yusuf",
              "Lestari", "Fajar", "Indah", "Wahyu", "Ayu", "Dimas", "Putri", "Arif", "Maya"]
NAMA_BELAKANG = ["Santoso", "Rahmawati", "Hidayat", "Lestari", "Pratama", "Saputra", "Wulandari", "Nugroho",
                 "Kurniawan", "Setiawan", "Hasanah", "Fauzi", "Ramadhan", "Purnama", "Syahputra"]
WILAYAH = ["Kota Yogyakarta", "Sleman", "Bantul", "Gunungkidul", "Kulon Progo", "Kota Semarang", "Klaten"]
JENIS = ["Zakat Maal", "Zakat Fitrah", "Zakat Profesi", "Infak", "Sedekah", "Wakaf",
         "Dana Sosial Keagamaan Lainnya"]
BOBOT_JENIS = [25, 15, 15, 20, 15, 5, 5]
KANAL = ["Transfer Bank", "Tunai", "QRIS", "Kantor Layanan", "Mitra/Online"]
BOBOT_KANAL = [35, 25, 20, 10, 10]
PROGRAM = ["Pendidikan", "Kesehatan", "Ekonomi", "Sosial-Dakwah", "Kemanusiaan"]
ASNAF = ["Fakir", "Miskin", "Amil", "Muallaf", "Gharimin", "Fisabilillah", "Ibnu Sabil"]

EJAAN_JENIS = {
    "Zakat Maal": ["zakat mal", "Zakat Maal", "ZAKAT MAAL", "zakat harta", "Maal"],
    "Zakat Fitrah": ["fitrah", "Zakat Fitrah", "zakat fithrah", "ZAKAT FITRAH"],
    "Zakat Profesi": ["zakat profesi", "Profesi", "zakat penghasilan"],
    "Infak": ["infaq", "Infak", "INFAQ", "infaaq"],
    "Sedekah": ["shodaqoh", "sedekah", "Shadaqah", "sodaqoh", "Sedekah"],
    "Wakaf": ["wakaf", "waqaf", "Wakaf Uang"],
    "Dana Sosial Keagamaan Lainnya": ["DSKL", "dskl", "Dana Sosial Keagamaan Lainnya"],
}
EJAAN_KANAL = {
    "Transfer Bank": ["transfer", "TF", "trf BSI", "Transfer Bank", "bank", "Transfer BCA"],
    "Tunai": ["tunai", "cash", "CASH", "Kas", "Tunai"],
    "QRIS": ["qris", "QRIS", "QR"],
    "Kantor Layanan": ["kantor", "Kantor Layanan", "counter"],
    "Mitra/Online": ["online", "Mitra/Online", "website"],
}

FIELD_HIMPUN = ["tanggal", "id_muzaki", "nama_muzaki", "jenis_dana", "kanal", "kabupaten_kota", "jumlah"]


# ---------------------------------------------------------------------------
# Data kanonik (kebenaran)
# ---------------------------------------------------------------------------
def buat_himpun(rng: random.Random, n: int, mulai: date = date(2022, 1, 1), bulan: int = 36,
                desimal: bool = False) -> pd.DataFrame:
    hari = (date(mulai.year + (mulai.month - 1 + bulan) // 12, (mulai.month - 1 + bulan) % 12 + 1, 1)
            - mulai).days
    n_donatur = max(5, n // 6)
    donatur = [(f"D{i:05d}", f"{rng.choice(NAMA_DEPAN)} {rng.choice(NAMA_BELAKANG)}") for i in range(1, n_donatur + 1)]
    baris = []
    for _ in range(n):
        d = mulai + timedelta(days=rng.randrange(hari))
        i, nama = rng.choice(donatur)
        nominal = float(rng.choice([25, 50, 100, 150, 250, 500, 1000, 2500]) * 1000 + rng.randrange(0, 50) * 1000)
        if desimal and rng.random() < 0.4:
            nominal += 0.5
        baris.append({"tanggal": pd.Timestamp(d), "id_muzaki": i, "nama_muzaki": nama,
                      "jenis_dana": rng.choices(JENIS, BOBOT_JENIS)[0],
                      "kanal": rng.choices(KANAL, BOBOT_KANAL)[0],
                      "kabupaten_kota": rng.choice(WILAYAH), "jumlah": nominal})
    df = pd.DataFrame(baris).drop_duplicates().sort_values("tanggal", kind="stable").reset_index(drop=True)
    return df


def buat_salur(rng: random.Random, n: int, mulai: date = date(2022, 1, 1), bulan: int = 36) -> pd.DataFrame:
    hari = bulan * 30
    baris = []
    for _ in range(n):
        baris.append({"tanggal": pd.Timestamp(mulai + timedelta(days=rng.randrange(hari))),
                      "program": rng.choice(PROGRAM), "asnaf": rng.choice(ASNAF),
                      "kabupaten_kota": rng.choice(WILAYAH), "jumlah_penerima": rng.randint(1, 80),
                      "jumlah": float(rng.randint(5, 400) * 10000)})
    return pd.DataFrame(baris).drop_duplicates().sort_values("tanggal", kind="stable").reset_index(drop=True)


def harapan(df: pd.DataFrame, salur: Optional[pd.DataFrame] = None,
            jenis_aktual: Optional[pd.Series] = None, kanal_aktual: Optional[pd.Series] = None) -> Dict[str, Any]:
    h: Dict[str, Any] = {
        "n": int(len(df)), "total": round(float(df["jumlah"].sum()), 2),
        "tanggal_min": df["tanggal"].min().date().isoformat(), "tanggal_maks": df["tanggal"].max().date().isoformat(),
        # total per bulan: menangkap tanggal yang tertukar hari/bulan walau min/maks kebetulan sama
        "per_bulan": {k.strftime("%Y-%m"): round(float(v), 2)
                      for k, v in df.groupby(df["tanggal"].dt.to_period("M"))["jumlah"].sum().items()},
    }
    if "jenis_dana" in df.columns:
        s = jenis_aktual if jenis_aktual is not None else df["jenis_dana"]
        h["jenis_dana"] = {k: int(v) for k, v in s.value_counts().items()}
    if "kanal" in df.columns:
        s = kanal_aktual if kanal_aktual is not None else df["kanal"]
        h["kanal"] = {k: int(v) for k, v in s.value_counts().items()}
    if salur is not None:
        h["salur_n"] = int(len(salur))
        h["salur_total"] = round(float(salur["jumlah"].sum()), 2)
    return h


# ---------------------------------------------------------------------------
# Pemformat nilai
# ---------------------------------------------------------------------------
def ribuan(v: float, sep: str = ".") -> str:
    return f"{int(round(v)):,}".replace(",", sep)


def f_iso(d, i, r):
    return d.strftime("%Y-%m-%d")


def f_dmy(d, i, r):
    return d.strftime("%d/%m/%Y")


def f_mdy(d, i, r):
    return d.strftime("%m/%d/%Y")


def f_indo(d, i, r):
    return f"{d.day} {BULAN_ID[d.month]} {d.year}"


def f_singkat(d, i, r):
    nama = BULAN_ID3 if i % 3 == 0 else BULAN_EN3
    return f"{d.day:02d}-{nama[d.month]}-{d.year % 100:02d}"


def f_serial(d, i, r):
    return (d.to_pydatetime() - datetime(1899, 12, 30)).days


def f_objek(d, i, r):
    return d.to_pydatetime()


def f_jam(d, i, r):
    return d.strftime("%Y-%m-%d") + f" {8 + i % 9:02d}:{(i * 7) % 60:02d}:00"


def f_campur(d, i, r):
    return [f_iso, f_dmy, f_indo, f_singkat, f_serial, f_objek, f_jam][i % 7](d, i, r)


def f_campur_teks(d, i, r):  # untuk CSV: serial Excel sebagai teks
    v = f_campur(d, i, r)
    return v.strftime("%d/%m/%Y") if isinstance(v, datetime) else str(v)


def j_angka(v, i, r):
    return v


def j_rp(v, i, r):
    return f"Rp {ribuan(v)},-"


def j_koma(v, i, r):
    return ribuan(v, ",")


def j_titik(v, i, r):
    return ribuan(v, ".")


def j_desimal(v, i, r):
    return f"{v:.2f}"


def j_desimal_koma(v, i, r):
    return f"{v:.2f}".replace(".", ",")


def j_spasi(v, i, r):
    sep = " " if i % 2 else " "
    return f"  {ribuan(v, sep)} "


def j_campur(v, i, r):
    return [j_angka, j_rp, j_koma, j_titik, j_spasi, lambda a, b, c: f"Rp{ribuan(a)}"][i % 6](v, i, r)


def k_ejaan(peta):
    def f(v, i, r):
        pilihan = peta.get(v, [v])
        return pilihan[i % len(pilihan)]
    return f


def ident(v, i, r):
    return v


# Spesifikasi kolom: (judul, field kanonik atau None untuk kolom kosong, pemformat)
Kolom = Tuple[str, Optional[str], Callable]


def render(df: pd.DataFrame, kolom: Sequence[Kolom], rng: random.Random) -> List[List[Any]]:
    baris = []
    for i, rec in enumerate(df.to_dict("records")):
        baris.append([fmt(rec[f], i, rng) if f else None for _, f, fmt in kolom])
    return baris


def judul(kolom: Sequence[Kolom]) -> List[str]:
    return [j for j, _, _ in kolom]


def pemetaan_benar(kolom: Sequence[Kolom]) -> Dict[str, str]:
    return {f: j.strip() if j else j for j, f, _ in kolom if f in FIELD_HIMPUN}


def kolom_standar(fmt_tgl=f_iso, fmt_jml=j_angka, nama=None, ejaan=False) -> List[Kolom]:
    nama = nama or {"tanggal": "tanggal", "id_muzaki": "id_muzaki", "nama_muzaki": "nama_muzaki",
                    "jenis_dana": "jenis_dana", "kanal": "kanal", "kabupaten_kota": "kabupaten_kota",
                    "jumlah": "jumlah"}
    fmt = {"tanggal": fmt_tgl, "jumlah": fmt_jml,
           "jenis_dana": k_ejaan(EJAAN_JENIS) if ejaan else ident,
           "kanal": k_ejaan(EJAAN_KANAL) if ejaan else ident}
    return [(nama[f], f, fmt.get(f, ident)) for f in FIELD_HIMPUN if f in nama]


# ---------------------------------------------------------------------------
# Penulis berkas
# ---------------------------------------------------------------------------
def tulis_xlsx(sheets: List[Tuple[str, List[List[Any]]]], gabung: Optional[Dict[str, List[str]]] = None,
               cepat: bool = False) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook(write_only=cepat)
    if not cepat:
        wb.remove(wb.active)
    for nama, baris in sheets:
        ws = wb.create_sheet(nama)
        for r in baris:
            ws.append(r)
        if not cepat:
            for rng in (gabung or {}).get(nama, []):
                ws.merge_cells(rng)
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, datetime):
                        c.number_format = "dd/mm/yyyy"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def tulis_csv(baris: List[List[Any]], pemisah: str = ",", encoding: str = "utf-8", bom: bool = False) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=pemisah, lineterminator="\r\n")
    for r in baris:
        w.writerow(["" if v is None else v for v in r])
    data = buf.getvalue().encode(encoding)
    return (b"\xef\xbb\xbf" + data) if bom else data


# ---------------------------------------------------------------------------
# Variasi
# ---------------------------------------------------------------------------
Variasi = Dict[str, Any]


def _v(kode, deskripsi, kelompok, nama_berkas, isi, harapan_=None, pemetaan=None, ditolak=False,
       harus_tolak_karena=None) -> Variasi:
    return {"kode": kode, "deskripsi": deskripsi, "kelompok": kelompok, "berkas": nama_berkas, "isi": isi,
            "harapan": harapan_, "pemetaan_benar": pemetaan, "harus_ditolak": ditolak,
            "alasan_tolak": harus_tolak_karena}


def _acak_kapital(s: str, rng: random.Random) -> str:
    huruf = "".join(c.upper() if rng.random() < 0.5 else c.lower() for c in s)
    return " " * rng.randint(0, 2) + huruf + " " * rng.randint(0, 3)


def _sampah_himpun(kolom: Sequence[Kolom], contoh: Dict[str, Any], rng) -> List[List[Any]]:
    """Baris yang harus dibuang: nominal nol, negatif, teks, dan tanggal kosong."""
    out = []
    for jml, tgl in ((0, contoh["tanggal"]), (-150000.0, contoh["tanggal"]), ("lima ratus ribu", contoh["tanggal"]),
                     (125000.0, None)):
        rec = {**contoh, "jumlah": jml, "tanggal": tgl}
        r = []
        for j, f, fmt in kolom:
            if f is None:
                r.append(None)
            elif f == "jumlah" and not isinstance(jml, float):
                r.append(jml)
            elif f == "tanggal" and tgl is None:
                r.append(None)
            else:
                r.append(fmt(rec[f], 1, rng))
        out.append(r)
    return out


def semua_variasi(besar: bool = True) -> List[Variasi]:
    rng = random.Random(SEED)
    V: List[Variasi] = []
    H = buat_himpun(rng, 300)
    S = buat_salur(rng, 80)

    def sederhana(kode, deskripsi, kelompok, kolom, ext="xlsx", df=None, csv_opsi=None, sheet="Penghimpunan",
                  sampah=False, jenis_aktual=None, kanal_aktual=None):
        df = H if df is None else df
        baris = [judul(kolom)] + render(df, kolom, rng)
        if sampah:
            baris += _sampah_himpun(kolom, df.iloc[0].to_dict(), rng)
        if ext == "xlsx":
            isi = tulis_xlsx([(sheet, baris)])
        else:
            isi = tulis_csv(baris, **(csv_opsi or {}))
        V.append(_v(kode, deskripsi, kelompok, f"{kode}.{ext}", isi,
                    harapan(df, jenis_aktual=jenis_aktual, kanal_aktual=kanal_aktual), pemetaan_benar(kolom)))

    # --- 1. nama kolom, urutan, huruf besar/kecil ---
    sederhana("v01_kanonik", "Template standar (pembanding)", "kolom", kolom_standar())
    sederhana("v02_tgl_nominal_muzaki", "Judul 'Tgl', 'Nominal', 'Muzaki', 'Jenis', 'Via', 'Kota'", "kolom",
              kolom_standar(nama={"tanggal": "Tgl", "nama_muzaki": "Muzaki", "jenis_dana": "Jenis", "kanal": "Via",
                                  "kabupaten_kota": "Kota", "jumlah": "Nominal"}), ext="csv")
    k = kolom_standar(nama={"tanggal": "Tanggal Transaksi", "id_muzaki": "No. Donatur", "nama_muzaki": "Donatur",
                            "jenis_dana": "Jenis Dana", "kanal": "Metode Pembayaran", "kabupaten_kota": "Kabupaten/Kota",
                            "jumlah": "Jumlah (Rp)"})
    rng.shuffle(k)
    sederhana("v03_judul_panjang_acak", "Judul 'Tanggal Transaksi', 'Jumlah (Rp)', 'Donatur'; urutan kolom acak",
              "kolom", k)
    k = [(_acak_kapital(j, rng), f, fmt) for j, f, fmt in kolom_standar(nama={
        "tanggal": "tgl", "nama_muzaki": "nama donatur", "jenis_dana": "jenis dana", "kanal": "kanal",
        "kabupaten_kota": "wilayah", "jumlah": "nominal"})]
    rng.shuffle(k)
    sederhana("v04_kapital_spasi_acak", "Huruf besar/kecil & spasi acak pada judul, urutan acak", "kolom", k)
    sederhana("v05_judul_tak_dikenal", "Judul kolom tidak lazim ('Kapan', 'Berapa', 'Siapa', ...)", "kolom",
              kolom_standar(nama={"tanggal": "Kapan", "nama_muzaki": "Siapa", "jenis_dana": "Untuk",
                                  "kanal": "Lewat", "kabupaten_kota": "Asal", "jumlah": "Berapa"}))
    k = kolom_standar(nama={"tanggal": "Tanggal", "nama_muzaki": "Donatur", "jenis_dana": "Jenis Dana",
                            "kanal": "Kanal", "jumlah": "Nominal"})
    k.append(("Total", "jumlah", lambda v, i, r: v + 2500))  # nominal + biaya admin: kolom jebakan
    pem = pemetaan_benar(k[:-1])
    baris = [judul(k)] + render(H, k, rng)
    V.append(_v("v06_dua_kolom_nominal", "Dua kandidat kolom nominal ('Nominal' dan 'Total' = nominal + biaya)",
                "kolom", "v06_dua_kolom_nominal.xlsx", tulis_xlsx([("Data", baris)]), harapan(H), pem))
    k = kolom_standar(nama={"tanggal": "Tanggal", "nama_muzaki": "Nama", "jenis_dana": "Jenis Dana",
                            "kanal": "Kanal", "kabupaten_kota": "Wilayah", "jumlah": "Jumlah"})
    baris = render(H, k, rng)
    V.append(_v("v07_tanpa_baris_judul", "Tanpa baris judul kolom sama sekali (langsung data)", "kolom",
                "v07_tanpa_baris_judul.xlsx", tulis_xlsx([("Sheet1", baris)]), harapan(H),
                {"tanggal": "Kolom A", "nama_muzaki": "Kolom B", "jenis_dana": "Kolom C", "kanal": "Kolom D",
                 "kabupaten_kota": "Kolom E", "jumlah": "Kolom F"}))

    # --- 2. tanggal ---
    for kode, desk, fmt, ext in [
        ("v08_tgl_iso", "Tanggal ISO 2024-01-12 (teks)", f_iso, "csv"),
        ("v09_tgl_dmy", "Tanggal dd/mm/yyyy (teks)", f_dmy, "csv"),
        ("v10_tgl_indonesia", "Tanggal '12 Januari 2024'", f_indo, "xlsx"),
        ("v11_tgl_singkat", "Tanggal '12-Jan-24' / '12-Agu-24'", f_singkat, "xlsx"),
        ("v12_tgl_serial_excel", "Tanggal sebagai nomor seri Excel (angka 45303)", f_serial, "xlsx"),
        ("v13_tgl_campuran", "Tujuh format tanggal bercampur dalam satu kolom", f_campur, "xlsx"),
        ("v14_tgl_mdy_amerika", "Tanggal mm/dd/yyyy (gaya Amerika) konsisten", f_mdy, "csv"),
        ("v15_tgl_dengan_jam", "Tanggal dengan jam '2024-01-12 14:30:00'", f_jam, "csv"),
        ("v16_tgl_campuran_csv", "Format tanggal bercampur di CSV (termasuk seri Excel sebagai teks)",
         f_campur_teks, "csv"),
    ]:
        sederhana(kode, desk, "tanggal", kolom_standar(fmt_tgl=fmt), ext=ext)

    # --- 3. nominal ---
    HD = buat_himpun(random.Random(SEED + 1), 300, desimal=True)
    for kode, desk, fmt, ext, df, opsi in [
        ("v17_nominal_rp_kuitansi", "Nominal 'Rp 1.500.000,-'", j_rp, "xlsx", H, None),
        ("v18_nominal_koma_ribuan", "Nominal '1,500,000'", j_koma, "csv", H, None),
        ("v19_nominal_titik_ribuan", "Nominal '1.500.000' (teks)", j_titik, "xlsx", H, None),
        ("v20_nominal_desimal", "Nominal '1500000.50'", j_desimal, "csv", HD, None),
        ("v21_nominal_spasi", "Nominal berspasi/NBSP '  1 500 000 '", j_spasi, "xlsx", H, None),
        ("v22_nominal_campuran", "Enam format nominal bercampur", j_campur, "xlsx", H, None),
    ]:
        sederhana(kode, desk, "nominal", kolom_standar(fmt_jml=fmt), ext=ext, df=df, csv_opsi=opsi)
    sederhana("v23_nominal_nol_negatif_teks", "Ada baris nominal 0, negatif, teks, dan tanggal kosong", "nominal",
              kolom_standar(fmt_jml=j_titik), sampah=True)

    # --- 4. struktur sheet ---
    k = kolom_standar(fmt_tgl=f_dmy)
    baris = [["LAPORAN PENERIMAAN ZIS"] + [None] * 6, ["Periode 2022 - 2024"] + [None] * 6, [None] * 7,
             judul(k)] + render(H, k, rng)
    V.append(_v("v24_judul_di_atas_header", "Judul laporan & baris kosong di atas header", "sheet",
                "v24_judul_di_atas_header.xlsx", tulis_xlsx([("Laporan", baris)], {"Laporan": ["A1:G1", "A2:G2"]}),
                harapan(H), pemetaan_benar(k)))
    # sel tanggal & wilayah digabung vertikal per kelompok hari
    k = kolom_standar(fmt_tgl=f_objek)
    data = render(H, k, rng)
    gab = ["A1:G1"]
    baris = [["Rekap Donasi Harian"] + [None] * 6, judul(k)]
    awal = 3
    i = 0
    while i < len(data):
        j = i
        while j + 1 < len(data) and data[j + 1][0] == data[i][0]:
            j += 1
        for t in range(i, j + 1):
            r = list(data[t])
            if t > i:
                r[0] = None
            baris.append(r)
        if j > i:
            gab.append(f"A{awal + i}:A{awal + j}")
        i = j + 1
    V.append(_v("v25_sel_digabung", "Sel judul digabung & sel tanggal digabung vertikal per hari", "sheet",
                "v25_sel_digabung.xlsx", tulis_xlsx([("Donasi", baris)], {"Donasi": gab}), harapan(H),
                pemetaan_benar(k)))
    k = kolom_standar()
    baris = [judul(k)] + render(H, k, rng) + [[None] * 7, ["TOTAL", None, None, None, None, None, H["jumlah"].sum()]]
    V.append(_v("v26_baris_total", "Baris kosong + baris 'TOTAL' di bawah data", "sheet", "v26_baris_total.xlsx",
                tulis_xlsx([("Penghimpunan", baris)]), harapan(H), pemetaan_benar(k)))
    k = kolom_standar()
    k = [k[0], ("", None, ident), *k[1:4], ("Keterangan", None, ident), *k[4:], ("", None, ident)]
    data = render(H, k, rng)
    baris = [judul(k)]
    for i, r in enumerate(data):
        baris.append(r)
        if i % 37 == 36:
            baris.append([None] * len(k))
    V.append(_v("v27_kolom_baris_kosong", "Kolom kosong di sela kolom data & baris kosong di tengah", "sheet",
                "v27_kolom_baris_kosong.xlsx", tulis_xlsx([("Data", baris)]), harapan(H),
                pemetaan_benar(k)))
    k = kolom_standar()
    petunjuk = [["Petunjuk pengisian"], ["Isi satu transaksi per baris."], ["Jangan ubah judul kolom."]]
    V.append(_v("v28_sheet_petunjuk", "Sheet petunjuk di depan, data di sheet 'Data 2024'", "sheet",
                "v28_sheet_petunjuk.xlsx", tulis_xlsx([("Petunjuk", petunjuk),
                                                       ("Data 2024", [judul(k)] + render(H, k, rng))]),
                harapan(H), pemetaan_benar(k)))
    k = kolom_standar(nama={"tanggal": "Tanggal", "nama_muzaki": "Donatur", "jenis_dana": "Jenis Dana",
                            "kanal": "Kanal", "kabupaten_kota": "Wilayah", "jumlah": "Nominal"})
    lembar = []
    for th in (2022, 2023, 2024):
        bag = H[H["tanggal"].dt.year == th]
        lembar.append((str(th), [judul(k)] + render(bag, k, rng)))
    V.append(_v("v29_sheet_per_tahun", "Satu sheet per tahun (2022, 2023, 2024), struktur sama", "sheet",
                "v29_sheet_per_tahun.xlsx", tulis_xlsx(lembar), harapan(H), pemetaan_benar(k)))
    # gabungan penghimpunan + penyaluran dalam satu sheet (kolom jenis transaksi)
    gab_rows = [["Tanggal", "Jenis Transaksi", "Keterangan", "Jenis Dana", "Wilayah", "Nominal"]]
    campur = []
    for rec in H.to_dict("records"):
        campur.append((rec["tanggal"], ["Penerimaan", rec["nama_muzaki"], rec["jenis_dana"],
                                        rec["kabupaten_kota"], rec["jumlah"]]))
    for rec in S.to_dict("records"):
        campur.append((rec["tanggal"], ["Penyaluran", f"Bantuan {rec['program']}", None, rec["kabupaten_kota"],
                                        rec["jumlah"]]))
    campur.sort(key=lambda x: x[0])
    for t, r in campur:
        gab_rows.append([t.strftime("%d/%m/%Y"), *r])
    V.append(_v("v30_sheet_gabungan_jenis", "Satu sheet gabungan penghimpunan+penyaluran (kolom 'Jenis Transaksi')",
                "sheet", "v30_sheet_gabungan_jenis.xlsx", tulis_xlsx([("Transaksi", gab_rows)]),
                {**harapan(H[["tanggal", "jenis_dana", "kabupaten_kota", "jumlah"]], S)}, None))
    gab_rows = [["Tgl", "Uraian", "Masuk", "Keluar"]]
    campur = [(r["tanggal"], [f"Donasi {r['nama_muzaki']}", r["jumlah"], None]) for r in H.to_dict("records")]
    campur += [(r["tanggal"], [f"Penyaluran {r['program']}", None, r["jumlah"]]) for r in S.to_dict("records")]
    campur.sort(key=lambda x: x[0])
    for t, r in campur:
        gab_rows.append([t.to_pydatetime(), *r])
    gab_rows.append(["Jumlah", None, H["jumlah"].sum(), S["jumlah"].sum()])
    V.append(_v("v31_buku_kas_masuk_keluar", "Buku kas: kolom 'Masuk' dan 'Keluar' dalam satu sheet + baris jumlah",
                "sheet", "v31_buku_kas_masuk_keluar.xlsx", tulis_xlsx([("Buku Kas", gab_rows)]),
                harapan(H[["tanggal", "jumlah"]], S), None))
    k = kolom_standar()
    ks = [("Tanggal", "tanggal", f_iso), ("Program", "program", ident), ("Asnaf", "asnaf", ident),
          ("Wilayah", "kabupaten_kota", ident), ("Jumlah Penerima", "jumlah_penerima", ident),
          ("Nominal", "jumlah", ident)]
    V.append(_v("v32_sheet_nama_tak_lazim", "Sheet 'Pemasukan 2024' & 'Pentasyarufan' (nama tidak standar)",
                "sheet", "v32_sheet_nama_tak_lazim.xlsx",
                tulis_xlsx([("Pemasukan 2024", [judul(k)] + render(H, k, rng)),
                            ("Pentasyarufan", [judul(ks)] + render(S, ks, rng))]),
                harapan(H, S), pemetaan_benar(k)))

    # --- 5. CSV: pemisah & encoding ---
    k = kolom_standar(fmt_tgl=f_dmy, fmt_jml=j_titik)
    for kode, desk, opsi in [
        ("v33_csv_koma", "CSV pemisah koma, UTF-8", {"pemisah": ","}),
        ("v34_csv_titik_koma", "CSV pemisah titik koma (gaya Excel Indonesia)", {"pemisah": ";"}),
        ("v35_csv_tab", "CSV pemisah tab", {"pemisah": "\t"}),
        ("v36_csv_utf8_bom", "CSV UTF-8 dengan BOM", {"pemisah": ";", "bom": True}),
    ]:
        sederhana(kode, desk, "csv", k, ext="csv", csv_opsi=opsi)
    HN = H.copy()
    HN["nama_muzaki"] = [n.replace("a", "á", 1) if i % 4 == 0 else n for i, n in enumerate(HN["nama_muzaki"])]
    HN["kabupaten_kota"] = [w + " – DIY" if i % 5 == 0 else w for i, w in enumerate(HN["kabupaten_kota"])]
    sederhana("v37_csv_windows1252", "CSV Windows-1252 (huruf beraksen & tanda pisah en)", "csv", k, ext="csv",
              df=HN, csv_opsi={"pemisah": ";", "encoding": "cp1252"})
    sederhana("v38_csv_desimal_koma", "CSV titik koma dengan nominal desimal koma '1500000,50'", "csv",
              kolom_standar(fmt_tgl=f_dmy, fmt_jml=j_desimal_koma), ext="csv", df=HD, csv_opsi={"pemisah": ";"})
    baris = [["Ekspor dari aplikasi kasir"], ["Dicetak: 2025-01-02"], judul(k)] + render(H, k, rng)
    V.append(_v("v39_csv_judul_di_atas", "CSV dengan baris keterangan di atas header (jumlah kolom tidak rata)", "csv",
                "v39_csv_judul_di_atas.csv", tulis_csv(baris, ";"), harapan(H), pemetaan_benar(k)))

    # --- 6. kategori ---
    sederhana("v40_ejaan_kategori", "Ejaan jenis dana & kanal beragam (infaq/infak, shodaqoh/sedekah, TF/trf BSI)",
              "kategori", kolom_standar(ejaan=True))
    HK = H.copy()
    tak = ["Kurban", "Hibah", "Titipan Lainnya"]
    HK["jenis_dana"] = [tak[i % 3] if i % 10 == 0 else j for i, j in enumerate(HK["jenis_dana"])]
    sederhana("v41_kategori_tak_dikenal", "Jenis dana di luar daftar ('Kurban', 'Hibah', 'Titipan Lainnya')",
              "kategori", kolom_standar(), df=HK)

    # --- 7. ukuran ---
    kecil = buat_himpun(random.Random(SEED + 2), 20, mulai=date(2024, 1, 1), bulan=8)
    sederhana("v42_kecil_20_baris", "Berkas kecil: 20 baris, 8 bulan", "ukuran", kolom_standar(), df=kecil)
    if besar:
        B = buat_himpun(random.Random(SEED + 3), 100_000)
        k = kolom_standar(fmt_tgl=f_dmy, fmt_jml=j_titik, ejaan=True)
        baris = [judul(k)] + render(B, k, rng)
        V.append(_v("v43_besar_100rb_csv", "CSV besar: 100.000 baris", "ukuran", "v43_besar_100rb_csv.csv",
                    tulis_csv(baris, ";"), harapan(B), pemetaan_benar(k)))
        k = kolom_standar(fmt_tgl=f_objek)
        V.append(_v("v44_besar_100rb_xlsx", "Excel besar: 100.000 baris", "ukuran", "v44_besar_100rb_xlsx.xlsx",
                    tulis_xlsx([("Penghimpunan", [judul(k)] + render(B, k, rng))], cepat=True), harapan(B),
                    pemetaan_benar(k)))

    # --- 8. kebiasaan lain yang lebih sulit ---
    HA = H[H["tanggal"].dt.day <= 12].reset_index(drop=True)
    sederhana("v45_tgl_mdy_ambigu", "Tanggal mm/dd/yyyy tetapi semua hari <= 12 (tidak bisa dibedakan dari dd/mm)",
              "sulit", kolom_standar(fmt_tgl=f_mdy), ext="csv", df=HA)
    k = kolom_standar(nama={"tanggal": "Tanggal", "id_muzaki": "ID", "nama_muzaki": "Nama", "jenis_dana": "Jenis",
                            "kanal": "Kanal", "kabupaten_kota": "Wilayah", "jumlah": "Nominal"})
    baris = [[None, "Donatur", None, "Transaksi", None, None, None], judul(k)] + render(H, k, rng)
    baris[0] = [None] * 7
    baris[0][0], baris[0][1], baris[0][3] = "Waktu", "Donatur", "Transaksi"
    V.append(_v("v46_judul_dua_baris", "Judul dua baris (kelompok digabung horizontal + sub-judul)", "sulit",
                "v46_judul_dua_baris.xlsx", tulis_xlsx([("Data", baris)], {"Data": ["B1:C1", "D1:G1"]}),
                harapan(H), pemetaan_benar(k)))
    k = kolom_standar(nama={"tanggal": "Tanggal", "nama_muzaki": "Donatur", "jenis_dana": "Jenis Dana",
                            "kanal": "Kanal", "kabupaten_kota": "Wilayah", "jumlah": "Jumlah (Rp ribu)"},
                      fmt_jml=lambda v, i, r: round(v / 1000, 1))
    sederhana("v47_nominal_dalam_ribuan", "Nominal dalam ribuan rupiah (judul 'Jumlah (Rp ribu)', isi 1500)",
              "sulit", k)
    # bug lokal Excel: tanggal dd/mm dibuka di Excel ber-lokal AS -> hari <= 12 menjadi sel tanggal dengan
    # hari & bulan tertukar, sisanya tetap teks dd/mm/yyyy
    def f_excel_tertukar(d, i, r):
        if d.day <= 12:
            return datetime(d.year, d.day, d.month)
        return d.strftime("%d/%m/%Y")
    sederhana("v48_tgl_tertukar_lokal_excel", "Bug lokal Excel: sebagian tanggal jadi sel tanggal tertukar "
              "hari/bulan, sisanya teks dd/mm/yyyy", "sulit", kolom_standar(fmt_tgl=f_excel_tertukar))
    k = kolom_standar()
    baris = [judul(k)] + render(H, k, rng) + [[None] * 7, ["Catatan: data belum diaudit."] + [None] * 6,
                                             ["Dicetak oleh: petugas keuangan"] + [None] * 6]
    V.append(_v("v49_catatan_kaki", "Catatan kaki teks di bawah data", "sulit", "v49_catatan_kaki.xlsx",
                tulis_xlsx([("Penghimpunan", baris)]), harapan(H), pemetaan_benar(k)))
    sederhana("v50_judul_bahasa_inggris", "Judul berbahasa Inggris ('Date', 'Amount', 'Donor', 'Fund Type', ...)",
              "sulit", kolom_standar(nama={"tanggal": "Date", "id_muzaki": "Donor ID", "nama_muzaki": "Donor Name",
                                           "jenis_dana": "Fund Type", "kanal": "Payment Channel",
                                           "kabupaten_kota": "City", "jumlah": "Amount"}), ext="csv")
    k = [("Tahun", "tanggal", lambda d, i, r: d.year), ("Bulan", "tanggal", lambda d, i, r: BULAN_ID[d.month]),
         ("Tgl", "tanggal", lambda d, i, r: d.day)] + kolom_standar()[1:]
    baris = [judul(k)] + render(H, k, rng)
    V.append(_v("v51_tahun_bulan_hari_terpisah", "Tanggal dipecah ke kolom 'Tahun', 'Bulan' (nama), 'Tgl' (angka)",
                "sulit", "v51_tahun_bulan_hari_terpisah.xlsx", tulis_xlsx([("Data", baris)]), harapan(H), None))
    k = kolom_standar(fmt_tgl=f_dmy, fmt_jml=j_titik) + [
        ("Keterangan", "nama_muzaki", lambda v, i, r: f"Titip salam, {v};\nsemoga berkah" if i % 9 == 0 else "")]
    sederhana("v52_csv_kutip_baris_baru", "CSV dengan sel berkutip berisi pemisah & baris baru", "sulit", k,
              ext="csv", csv_opsi={"pemisah": ";"})
    k = kolom_standar()
    n = len(H)
    baris = [judul(k)] + render(H, k, rng) + [["Total", None, None, None, None, None, f"=SUM(G2:G{n + 1})"]]
    V.append(_v("v53_total_rumus", "Baris 'Total' berisi rumus =SUM() tanpa nilai tersimpan", "sulit",
                "v53_total_rumus.xlsx", tulis_xlsx([("Penghimpunan", baris)]), harapan(H), pemetaan_benar(k)))

    # --- 9. yang HARUS ditolak dengan pesan jelas ---
    V.append(_v("t01_berkas_kosong", "Berkas 0 byte", "tolak", "t01_berkas_kosong.xlsx", b"", ditolak=True,
                harus_tolak_karena="kosong"))
    V.append(_v("t02_excel_rusak", "Berkas .xlsx rusak (bukan zip valid)", "tolak", "t02_excel_rusak.xlsx",
                b"PK\x03\x04" + bytes(random.Random(SEED).randrange(256) for _ in range(500)), ditolak=True,
                harus_tolak_karena="rusak"))
    V.append(_v("t03_hanya_judul", "Hanya baris judul, tanpa data", "tolak", "t03_hanya_judul.csv",
                tulis_csv([["Tanggal", "Nominal", "Donatur"]]), ditolak=True, harus_tolak_karena="baris data"))
    k = [c for c in kolom_standar(nama={"nama_muzaki": "Nama", "kabupaten_kota": "Kota", "jumlah": "Nominal"})]
    V.append(_v("t04_tanpa_kolom_tanggal", "Tidak ada kolom tanggal sama sekali", "tolak", "t04_tanpa_kolom_tanggal.xlsx",
                tulis_xlsx([("Data", [judul(k)] + render(H, k, rng))]), ditolak=True, harus_tolak_karena="tanggal"))
    k = kolom_standar(fmt_jml=lambda v, i, r: ["lima ratus ribu", "seratus ribu", "sejuta"][i % 3])
    V.append(_v("t05_nominal_huruf", "Semua nominal ditulis dengan huruf", "tolak", "t05_nominal_huruf.xlsx",
                tulis_xlsx([("Data", [judul(k)] + render(H, k, rng))]), ditolak=True, harus_tolak_karena="jumlah"))
    k = kolom_standar(fmt_tgl=lambda d, i, r: ["31/02/2024", "kemarin", "2024-13-45", "minggu lalu"][i % 4])
    V.append(_v("t06_tanggal_rusak", "Semua tanggal tidak valid ('31/02/2024', 'kemarin')", "tolak",
                "t06_tanggal_rusak.csv", tulis_csv([judul(k)] + render(H, k, rng)), ditolak=True,
                harus_tolak_karena="tanggal"))
    V.append(_v("t07_biner_bernama_csv", "Berkas biner (gambar) diberi nama .csv", "tolak", "t07_biner_bernama_csv.csv",
                b"\x89PNG\r\n\x1a\n" + bytes(random.Random(SEED + 5).randrange(256) for _ in range(800)),
                ditolak=True, harus_tolak_karena="biner"))
    V.append(_v("t08_xls_lama_atau_bersandi", "Kontainer OLE2 (.xls lama / Excel bersandi)", "tolak",
                "t08_xls_lama_atau_bersandi.xlsx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600, ditolak=True,
                harus_tolak_karena=".xls"))
    return V


def tulis_semua(keluar: Path, besar: bool = True) -> List[Dict[str, Any]]:
    keluar.mkdir(parents=True, exist_ok=True)
    manifest = []
    for v in semua_variasi(besar):
        (keluar / v["berkas"]).write_bytes(v["isi"])
        manifest.append({k: v[k] for k in v if k != "isi"})
    (keluar / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keluar", default=str(AKAR / "data" / "sintetis_kotor"))
    ap.add_argument("--tanpa-besar", action="store_true", help="lewati berkas 100.000 baris")
    a = ap.parse_args(argv)
    m = tulis_semua(Path(a.keluar), besar=not a.tanpa_besar)
    print(f"{len(m)} variasi ditulis ke {a.keluar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
