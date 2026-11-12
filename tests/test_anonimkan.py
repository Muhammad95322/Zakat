"""Anonimisasi berkas data (scripts/anonimkan_data.py) dan pagar data di repo publik. Semua data SINTETIS."""
import hashlib
import importlib.util
import io
import os
import re
import socket
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

AKAR = Path(__file__).parent.parent


def _modul(nama):
    spec = importlib.util.spec_from_file_location(nama, AKAR / "scripts" / f"{nama}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[nama] = m
    spec.loader.exec_module(m)
    return m


an = _modul("anonimkan_data")
cek = _modul("cek_berkas_data")

# --- data sintetis yang sengaja berisi data pribadi --------------------------------------------
ORANG = [  # (nama, id, hp, nik, email)
    ("Siti Rahmawati", "D-0001", "0812-3456-7890", "3404012345670001", "siti.rahma@contoh.invalid"),
    ("Budi Santoso", "D-0002", "+62 857 1122 3344", "3471 0201 9988 0002", "budi_s@contoh.invalid"),
    ("Ahmad Fauzi", "D-0003", "081398765432", "3402123456789003", "ahmad.f@contoh.invalid"),
    ("Dewi Lestari", "D-0004", "(0274) 512345", "3404987654321004", "dewi@contoh.invalid"),
]
JUDUL = ["Tanggal", "ID Donatur", "Nama Muzaki", "No. HP", "Alamat Lengkap", "Email", "NIK", "No Rekening",
         "Jenis Dana", "Kanal", "Kabupaten/Kota", "Program", "Nominal", "Catatan", "Info Tambahan", "Data Tambahan",
         "Sapaan", "Referensi"]


def _baris(n=40):
    out = []
    for i in range(n):
        nama, idm, hp, nik, email = ORANG[i % 4]
        out.append([
            datetime(2024, 1 + i % 12, 1 + i % 27), idm if i % 5 else idm.lower(),
            nama if i % 3 else "  " + nama.upper() + " ",  # variasi huruf/spasi: harus pseudonim sama
            hp, f"Jl. Melati No. {i}, RT 0{i % 9}/RW 02, Sleman", email, nik, f"0123{i:08d}",
            ["infaq", "Zakat Maal", "sedekah"][i % 3], ["TF", "Tunai"][i % 2], ["Sleman", "Bantul"][i % 2],
            ["Pendidikan", "Kesehatan"][i % 2], 100000 + i * 1000,
            f"Titipan {nama}, hubungi {hp} atau {email}",
            f"kontak cadangan {email}" if i % 7 == 0 else "-",         # judul netral, isi email (sebagian baris)
            int(re.sub(r"\D", "", nik)) if i % 2 else nik,             # judul netral, isi NIK (angka & teks)
            f"Salam untuk {nama}" if i % 4 == 0 else "Semoga berkah",  # judul netral, isi nama
            ["kampanye ramadan", "brosur masjid", "teman kantor", "media sosial", "pengajian rutin",
             "spanduk jalan", "radio lokal"][i % 7],                    # teks beragam tanpa data pribadi
        ])
    return out


def _xlsx(path: Path, baris):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Penerimaan"
    ws.append(["LAPORAN PENERIMAAN ZIS - LEMBAGA SINTETIS"])
    ws.append([])
    ws.append(JUDUL)
    for r in baris:
        ws.append(r)
    ws2 = wb.create_sheet("Penyaluran")
    ws2.append(["Tanggal", "Nama Mustahik", "NIK Mustahik", "Asnaf", "Program", "Jumlah", "Alamat"])
    for i in range(10):
        nama, _, _, nik, _ = ORANG[i % 4]
        ws2.append([datetime(2024, 2, 1 + i), nama, nik, "Miskin", "Ekonomi", 500000, "Desa Sukamaju"])
    wb.save(path)


def _semua_sel(path: Path):
    if path.suffix == ".csv":
        return [v for v in path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace(";", "\n").split("\n")]
    wb = openpyxl.load_workbook(path)
    return [c.value for ws in wb for row in ws.iter_rows() for c in row if c.value is not None]


def _bocoran(nilai):
    """Data pribadi yang masih tersisa di nilai-nilai keluaran."""
    teks = " | ".join(str(v) for v in nilai)
    temuan = []
    for nama, idm, hp, nik, email in ORANG:
        for kata in (nama, nama.split()[0], nama.split()[1], idm, email, email.split("@")[0]):
            if kata.lower() in teks.lower():
                temuan.append(kata)
        for nomor in (hp, nik):
            digit = re.sub(r"\D", "", nomor)
            if digit in re.sub(r"[\s.\-()+]", "", teks):
                temuan.append(nomor)
    temuan += re.findall(r"[\w.]+@[\w.]+", teks)
    temuan += re.findall(r"Jl\. Melati", teks)
    return temuan


@pytest.fixture
def kunci(tmp_path):
    return tmp_path / "rahasia" / "kunci_anonim"


@pytest.fixture
def hasil(tmp_path, kunci, capsys):
    masuk = tmp_path / "asli.xlsx"
    _xlsx(masuk, _baris())
    hash_asli = hashlib.sha256(masuk.read_bytes()).hexdigest()
    lap = an.anonimkan(masuk, tmp_path / "anon", kunci)
    an.cetak(lap)
    out = capsys.readouterr().out
    return masuk, hash_asli, Path(lap.keluaran), lap, out


def test_tidak_ada_data_pribadi_tersisa(hasil):
    _, _, keluar, _, _ = hasil
    assert _bocoran(_semua_sel(keluar)) == []


def test_berkas_asli_tidak_diubah_dan_keluaran_di_folder_tujuan(hasil, tmp_path):
    masuk, hash_asli, keluar, _, _ = hasil
    assert hashlib.sha256(masuk.read_bytes()).hexdigest() == hash_asli
    assert keluar.parent == (tmp_path / "anon").resolve() and keluar.name == "asli_anon.xlsx"
    if os.name == "posix":
        assert stat.S_IMODE(keluar.stat().st_mode) == 0o600


def test_kolom_dihapus_dari_nama_dan_dari_isi(hasil):
    _, _, keluar, lap, _ = hasil
    dihapus = dict(lap.per_tabel[0]["dihapus"])
    for j in ("No. HP", "Alamat Lengkap", "Email", "NIK", "No Rekening", "Catatan"):
        assert dihapus[j].startswith("nama kolom")
    assert dihapus["Info Tambahan"] == "isi kolom memuat email"
    assert dihapus["Data Tambahan"] == "isi kolom memuat NIK"
    assert dihapus["Sapaan"] == "isi kolom memuat nama orang dari kolom nama"
    wb = openpyxl.load_workbook(keluar)
    assert [c.value for c in wb["Penerimaan"][1]] == ["Tanggal", "ID Donatur", "Nama Muzaki", "Jenis Dana", "Kanal",
                                                      "Kabupaten/Kota", "Program", "Nominal", "Referensi"]
    assert [c.value for c in wb["Penyaluran"][1]] == ["Tanggal", "Nama Mustahik", "Asnaf", "Program", "Jumlah"]


def test_kolom_transaksi_tetap_utuh(hasil):
    _, _, keluar, _, _ = hasil
    asli = _baris()
    ws = openpyxl.load_workbook(keluar)["Penerimaan"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(rows) == len(asli)
    for a, b in zip(asli, rows):
        assert b[0] == a[0]                      # tanggal
        assert list(b[3:8]) == [a[8], a[9], a[10], a[11], a[12]]  # jenis, kanal, wilayah, program, nominal


def test_pseudonim_konsisten_per_orang(hasil, tmp_path, kunci):
    _, _, keluar, _, _ = hasil
    rows = list(openpyxl.load_workbook(keluar)["Penerimaan"].iter_rows(min_row=2, values_only=True))
    per_orang = {}
    for i, r in enumerate(rows):
        per_orang.setdefault(i % 4, set()).add((r[1], r[2]))
    assert all(len(v) == 1 for v in per_orang.values())          # beda huruf/spasi -> pseudonim sama
    assert len({next(iter(v)) for v in per_orang.values()}) == 4  # orang berbeda -> pseudonim berbeda
    assert all(re.fullmatch(r"MZK-[0-9A-F]{12}", r[2]) for r in rows)
    mst = [r[1] for r in openpyxl.load_workbook(keluar)["Penyaluran"].iter_rows(min_row=2, values_only=True)]
    assert all(re.fullmatch(r"MST-[0-9A-F]{12}", v) for v in mst)
    # berjalan ulang dengan kunci sama -> hasil sama; kunci lain -> pseudonim lain
    masuk2 = tmp_path / "asli2.xlsx"
    _xlsx(masuk2, _baris())
    k2 = an.anonimkan(masuk2, tmp_path / "anon2", kunci)
    rows2 = list(openpyxl.load_workbook(k2.keluaran)["Penerimaan"].iter_rows(min_row=2, values_only=True))
    assert [r[2] for r in rows2] == [r[2] for r in rows]
    k3 = an.anonimkan(masuk2, tmp_path / "anon3", tmp_path / "lain" / "kunci")
    rows3 = list(openpyxl.load_workbook(k3.keluaran)["Penerimaan"].iter_rows(min_row=2, values_only=True))
    assert not set(r[2] for r in rows3) & set(r[2] for r in rows)


def test_kunci_dibuat_sekali_izin_600_dan_tidak_boleh_di_repo(hasil, kunci):
    isi = kunci.read_text()
    if os.name == "posix":
        assert stat.S_IMODE(kunci.stat().st_mode) == 0o600
    assert len(isi.strip()) == 64
    an.siapkan_kunci(kunci)
    assert kunci.read_text() == isi
    with pytest.raises(SystemExit, match="di dalam folder repo"):
        an.siapkan_kunci(AKAR / "data" / "private" / "kunci")


def test_laporan_tidak_mencetak_isi_baris(hasil):
    _, _, _, _, out = hasil
    assert _bocoran([out]) == []
    for kata in ("infaq", "Pendidikan", "Sleman", "100000", "LEMBAGA SINTETIS"):
        assert kata not in out
    assert "40 baris data" in out and "10 baris data" in out
    assert "'No. HP' (nama kolom menunjukkan nomor HP)" in out
    assert "Kolom 'Referensi' (Penerimaan) berisi teks beragam (7 nilai berbeda) yang mungkin masih memuat nama" in out
    assert "Kolom 'Jenis Dana'" not in out  # kolom transaksi yang utuh tidak diberi peringatan


def test_sel_bocor_di_kolom_utuh_disensor_hanya_selnya(tmp_path, kunci):
    p = tmp_path / "x.csv"
    p.write_text("Tanggal;Nama Donatur;Program;Nominal\n"
                 "01/02/2024;Siti Rahmawati;Bantuan untuk Siti Rahmawati;100000\n"
                 "02/02/2024;Budi Santoso;Pendidikan;200000\n"
                 "03/02/2024;Ahmad Fauzi;kirim ke ahmad.f@contoh.invalid;300000\n", encoding="utf-8")
    lap = an.anonimkan(p, tmp_path / "anon", kunci)
    teks = Path(lap.keluaran).read_text(encoding="utf-8-sig")
    assert _bocoran([teks]) == []
    assert teks.count(an.SENSOR) == 2 and "Pendidikan" in teks
    assert ";100000" in teks and "01/02/2024" in teks
    assert lap.per_tabel[0]["sel_disensor"] == 2


def test_csv_pemisah_dipertahankan_dan_bisa_diunggah(tmp_path, kunci):
    p = tmp_path / "donasi.csv"
    p.write_text("Tanggal,Nama Muzaki,HP,Jenis Dana,Nominal\n" + "".join(
        f"0{1 + i % 9}/03/2024,{ORANG[i % 4][0]},{ORANG[i % 4][2]},infaq,{(i + 1) * 1000}\n" for i in range(12)),
        encoding="utf-8")
    lap = an.anonimkan(p, tmp_path / "anon", kunci)
    keluar = Path(lap.keluaran)
    assert keluar.suffix == ".csv" and _bocoran([keluar.read_text(encoding="utf-8-sig")]) == []
    from src.pipeline import siapkan_data
    h = siapkan_data(keluar.read_bytes(), keluar.name)
    assert h["df_himpun"]["jumlah"].sum() == sum((i + 1) * 1000 for i in range(12))


def test_tanpa_jaringan(tmp_path, kunci, monkeypatch):
    def larang(*a, **k):
        raise AssertionError("anonimkan_data mencoba membuka koneksi jaringan")
    monkeypatch.setattr(socket, "socket", larang)
    monkeypatch.setattr(socket, "create_connection", larang)
    masuk = tmp_path / "a.xlsx"
    _xlsx(masuk, _baris(8))
    an.main([str(masuk), "--keluar", str(tmp_path / "o"), "--kunci", str(kunci)])
    sumber = (AKAR / "scripts" / "anonimkan_data.py").read_text()
    for modul in ("socket", "urllib", "requests", "http.client", "smtplib", "httpx"):
        assert not re.search(rf"^\s*(import|from)\s+{re.escape(modul)}", sumber, re.M)


def test_hapus_kolom_paksa(tmp_path, kunci):
    masuk = tmp_path / "a.xlsx"
    _xlsx(masuk, _baris(8))
    lap = an.anonimkan(masuk, tmp_path / "o", kunci, hapus_kolom=["referensi"])
    assert dict(lap.per_tabel[0]["dihapus"])["Referensi"] == "diminta pengguna (--hapus-kolom)"


# --- pagar repo publik --------------------------------------------------------------------------
def test_cek_berkas_data_menolak_data_di_luar_folder_contoh():
    assert cek.pelanggaran(["data/sample/data_contoh.xlsx", "data/template/template_zakat.xlsx", "src/a.py",
                            "README.md"]) == []
    salah = ["data/private/anon/x_anon.xlsx", "data/donasi.csv", "laporan.XLSX", "data/sample/sub/x.xlsx",
             "tests/fixtures/a.ods", "data/private/catatan.txt"]
    assert cek.pelanggaran(salah) == salah


def test_repo_saat_ini_lolos_pemeriksaan():
    if not (AKAR / ".git").exists():
        pytest.skip("bukan checkout git")
    assert cek.pelanggaran(cek.berkas_terlacak()) == []


@pytest.mark.parametrize("path, diabaikan", [
    ("data/private/donasi.xlsx", True), ("data/private/anon/donasi_anon.xlsx", True),
    ("data/private/catatan.txt", True), ("donasi_2024.xlsx", True), ("data/ekspor.csv", True),
    ("scripts/x.xls", True), ("data/sample/sub/x.xlsx", True),
    ("data/sample/data_contoh.xlsx", False), ("data/template/template_zakat.xlsx", False),
])
def test_gitignore_melindungi_berkas_data(path, diabaikan):
    if not (AKAR / ".git").exists():
        pytest.skip("bukan checkout git")
    r = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=AKAR)
    assert (r.returncode == 0) is diabaikan


def test_ci_menjalankan_pemeriksaan_di_job_keamanan():
    wf = (AKAR / ".github" / "workflows" / "tests.yml").read_text()
    bagian = wf.split("\n  keamanan:", 1)[1]
    assert "python scripts/cek_berkas_data.py" in bagian
