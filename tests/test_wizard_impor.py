"""AppTest wizard pemetaan kolom di halaman Unggah (data sintetis).

Skenario: berkas berjudul kolom tak lazim -> wizard tampil dengan pratinjau 5 baris -> pilihan salah
ditolak dengan pesan jelas -> pilihan benar disimpan -> unggahan berikutnya dengan susunan kolom sama
langsung diproses tanpa wizard. Berkas rusak menghasilkan pesan galat tanpa exception.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

_SKRIP = r'''
import io, os, sys, uuid
sys.path.insert(0, os.environ["ROOT"])
import openpyxl
import streamlit as st
from src.database import init_db, get_db
from src.models.tenant import Tenant
from src.models.user import User
from src.models.upload import Upload
from src.models.pemetaan_kolom import PemetaanKolom
from src.auth.hashing import hash_password
from src.auth.jwt_handler import create_access_token
from streamlit.testing.v1 import AppTest

init_db()
with get_db() as db:
    t = Tenant(id=str(uuid.uuid4()), nama="Uji", slug="uji", email_kontak="a@b.id", paket="pro", is_active=True)
    db.add(t); db.flush()
    a = User(id=str(uuid.uuid4()), tenant_id=t.id, email="admin@u.id", password_hash=hash_password("Rahasia123"),
             nama_lengkap="Admin Uji", peran="admin", is_active=True, is_verified=True)
    db.add(a); db.commit(); uid, tid = a.id, t.id


def xlsx(n, geser=0):
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Kapan", "Siapa", "Untuk", "Lewat", "Berapa"])
    for i in range(n):
        ws.append([f"{(i + geser) % 28 + 1:02d}/{i % 12 + 1:02d}/2024", f"Donatur {i % 7}",
                   ["infaq", "zakat mal", "shodaqoh"][i % 3], ["TF", "cash"][i % 2], f"{(i + 1) * 10}.000"])
    b = io.BytesIO(); wb.save(b); return b.getvalue()


class Berkas:
    def __init__(self, nama, isi):
        self.name, self._isi, self.size = nama, isi, len(isi)
    def getvalue(self):
        return self._isi


AKTIF = {"berkas": None}
st.file_uploader = lambda *a, **k: AKTIF["berkas"]

at = AppTest.from_file(os.path.join(os.environ["ROOT"], "app.py"), default_timeout=90)
at.session_state["page"] = "upload"; at.session_state["is_logged_in"] = True
at.session_state["current_user"] = {"id": uid, "tenant_id": tid, "peran": "admin", "email": "admin@u.id",
                                    "nama_lengkap": "Admin Uji",
                                    "access_token": create_access_token(uid, tid, "admin", "admin@u.id", 0)}

def lapor(tahap):
    print(f"{tahap}_EXC=" + str(len(at.exception)) + " " + " | ".join(e.message for e in at.exception))
    print(f"{tahap}_ERR=" + " | ".join(e.value for e in at.error))
    print(f"{tahap}_OK=" + " | ".join(e.value for e in at.success))
    print(f"{tahap}_WARN=" + " | ".join(e.value for e in at.warning))
    with get_db() as db:
        print(f"{tahap}_UPLOAD=" + str(db.query(Upload).filter(Upload.tenant_id == tid).count()))
        print(f"{tahap}_PEMETAAN=" + str(db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == tid).count()))

def pilih(label, nilai):
    [s for s in at.selectbox if s.label == label][0].set_value(nilai)

# 1. berkas berjudul tak lazim -> wizard
AKTIF["berkas"] = Berkas("lembaga_x.xlsx", xlsx(40))
at.run()
at.button(key="btn_proses_unggah").click().run()
lapor("WIZ")
print("WIZ_LABEL=" + " | ".join(s.label for s in at.selectbox))
print("WIZ_PRATINJAU=" + str([len(d.value) for d in at.dataframe]))
print("WIZ_SARAN_TANGGAL=" + str([s.value for s in at.selectbox if s.label.startswith("Tanggal")]))

# 2. pilihan salah: jumlah = kolom teks
pilih("Tanggal transaksi (wajib)", "Kapan"); pilih("Jumlah / nominal (wajib)", "Siapa")
at.button(key="wiz_simpan").click().run()
lapor("SALAH")

# 3. pilihan benar
pilih("Jumlah / nominal (wajib)", "Berapa"); pilih("Jenis dana", "Untuk"); pilih("Kanal / metode bayar", "Lewat")
pilih("Nama donatur", "Siapa")
at.button(key="wiz_simpan").click().run()
lapor("BENAR")
print("BENAR_TERTUNDA=" + str(bool(at.session_state["impor_tertunda"]) if "impor_tertunda" in at.session_state else False))

# 4. unggahan berikutnya, susunan kolom sama -> otomatis tanpa wizard
AKTIF["berkas"] = Berkas("lembaga_x_bulan_depan.xlsx", xlsx(25, geser=3))
at.run()
at.button(key="btn_proses_unggah").click().run()
lapor("ULANG")
print("ULANG_WIZARD=" + str(any(s.label == "Tanggal transaksi (wajib)" for s in at.selectbox)))

# 5. berkas rusak
AKTIF["berkas"] = Berkas("rusak.xlsx", b"PK\x03\x04bukan-zip")
at.run()
at.button(key="btn_proses_unggah").click().run()
lapor("RUSAK")

# 6. halaman analisis menampilkan laporan kualitas (pemetaan tersimpan dipakai)
at.session_state["page"] = "analisis"
at.run()
lapor("ANL")
print("ANL_EXPANDER=" + " | ".join(e.label for e in at.expander))

# 7. baris identik tanpa ID transaksi: peringatan + tombol buang duplikat; pilihan disimpan bersama pemetaan
at.session_state["page"] = "upload"
identik = ("Tanggal;Donatur;Jenis Dana;Nominal\n" + "05/01/2024;Siti;infaq;100.000\n" * 10
           + "06/01/2024;Budi;zakat mal;250.000\n").encode()
AKTIF["berkas"] = Berkas("identik.csv", identik)
at.run()
at.button(key="btn_proses_unggah").click().run()
lapor("IDENTIK")
print("IDENTIK_TOMBOL=" + " | ".join(b.label for b in at.button if b.key == "btn_buang_duplikat"))
at.button(key="btn_buang_duplikat").click().run()
lapor("BUANG")
print("BUANG_INFO=" + " | ".join(e.value for e in at.info))
with get_db() as db:
    from src.services.pemetaan_service import daftar_pemetaan
    print("BUANG_OPSI=" + str([p["opsi"] for p in daftar_pemetaan(db, tid)]))

# 8. berkas yang sama diunggah lagi: peringatan unggahan ganda utuh
at.run()
at.button(key="btn_proses_unggah").click().run()
lapor("KEMBAR")

# 9. kwitansi dua pos (ID sama, isi beda): dipertahankan + peringatan; tombol opsional "ID unik"
dua_pos = "No. Bukti;Tanggal;Donatur;Jenis Dana;Nominal\n" + "".join(
    f"KW-{k};{k:02d}/03/2024;D{k};zakat mal;1.000.000\nKW-{k};{k:02d}/03/2024;D{k};infaq;250.000\n"
    for k in range(1, 6))
AKTIF["berkas"] = Berkas("dua_pos.csv", dua_pos.encode())
at.run()
at.button(key="btn_proses_unggah").click().run()
lapor("IDBAGI")
print("IDBAGI_TOMBOL=" + " | ".join(b.label for b in at.button if b.key == "btn_id_unik"))
at.button(key="btn_id_unik").click().run()
lapor("IDUNIK")
print("IDUNIK_INFO=" + " | ".join(e.value for e in at.info))
with get_db() as db:
    print("IDUNIK_OPSI=" + str([p["opsi"] for p in daftar_pemetaan(db, tid)]))
at.button(key="btn_id_tidak_unik").click().run()
lapor("IDBATAL")
'''


@pytest.fixture(scope="module")
def keluaran(tmp_path_factory):
    pytest.importorskip("streamlit.testing.v1")
    tmp = tmp_path_factory.mktemp("wizard")
    skrip = tmp / "ui.py"
    skrip.write_text(_SKRIP)
    env = {**os.environ, "ROOT": str(ROOT), "APP_ENV": "development", "APP_ENV_FILE": "",
           "DATABASE_URL": f"sqlite:///{tmp}/ui.db", "UPLOAD_DIR": str(tmp / "up")}
    hasil = subprocess.run([sys.executable, str(skrip)], capture_output=True, text=True, env=env, cwd=str(tmp))
    assert hasil.returncode == 0, hasil.stderr[-3000:]
    return dict(b.split("=", 1) for b in hasil.stdout.splitlines() if "=" in b)


def test_wizard_tampil_dengan_pratinjau_5_baris(keluaran):
    assert keluaran["WIZ_EXC"].startswith("0"), keluaran["WIZ_EXC"]
    assert "Tanggal transaksi (wajib)" in keluaran["WIZ_LABEL"]
    assert "Wilayah (kabupaten/kota)" in keluaran["WIZ_LABEL"]
    assert "5" in keluaran["WIZ_PRATINJAU"]
    assert "tidak dapat dipastikan otomatis" in keluaran["WIZ_WARN"]
    assert keluaran["WIZ_SARAN_TANGGAL"] == "['Kapan']"  # tebakan dari isi kolom sudah terisi
    assert keluaran["WIZ_UPLOAD"] == "0"


def test_wizard_pilihan_salah_ditolak_jelas(keluaran):
    assert keluaran["SALAH_EXC"].startswith("0")
    assert "Kolom 'Siapa' yang dipilih sebagai jumlah hanya 0% berupa angka" in keluaran["SALAH_ERR"]
    assert keluaran["SALAH_UPLOAD"] == "0" and keluaran["SALAH_PEMETAAN"] == "0"


def test_wizard_pilihan_benar_disimpan_per_lembaga(keluaran):
    assert keluaran["BENAR_EXC"].startswith("0")
    assert keluaran["BENAR_UPLOAD"] == "1" and keluaran["BENAR_PEMETAAN"] == "1"
    assert "Pemetaan kolom disimpan" in keluaran["BENAR_OK"]
    assert keluaran["BENAR_TERTUNDA"] == "False"


def test_unggahan_berikutnya_otomatis(keluaran):
    assert keluaran["ULANG_EXC"].startswith("0")
    assert keluaran["ULANG_WIZARD"] == "False"
    assert keluaran["ULANG_UPLOAD"] == "2" and keluaran["ULANG_PEMETAAN"] == "1"
    assert "lembaga_x_bulan_depan.xlsx" in keluaran["ULANG_OK"]


def test_berkas_rusak_pesan_tanpa_traceback(keluaran):
    assert keluaran["RUSAK_EXC"].startswith("0")
    assert "rusak atau bukan file Excel yang valid" in keluaran["RUSAK_ERR"]
    assert "Traceback" not in keluaran["RUSAK_ERR"]
    assert keluaran["RUSAK_OK"] == ""  # pesan sukses unggahan sebelumnya tidak menyesatkan
    assert keluaran["RUSAK_UPLOAD"] == "2"


def test_baris_identik_peringatan_dan_tombol_buang(keluaran):
    assert keluaran["IDENTIK_EXC"].startswith("0"), keluaran["IDENTIK_EXC"]
    assert ("10 baris identik dipertahankan karena tidak ada ID transaksi; periksa apakah ada unggahan ganda."
            in keluaran["IDENTIK_WARN"])
    assert keluaran["IDENTIK_TOMBOL"] == "Buang 9 baris duplikat persis"
    assert keluaran["BUANG_EXC"].startswith("0")
    assert "duplikat persis DIBUANG" in keluaran["BUANG_OK"]
    assert "Duplikat persis dibuang" in keluaran["BUANG_INFO"]
    assert "'buang_duplikat_persis': True" in keluaran["BUANG_OPSI"]
    assert "baris identik dipertahankan" not in keluaran["BUANG_WARN"]


def test_berkas_sama_diunggah_lagi_diperingatkan(keluaran):
    assert keluaran["KEMBAR_EXC"].startswith("0")
    assert "identik byte demi byte dengan unggahan 'identik.csv'" in keluaran["KEMBAR_WARN"]


def test_id_berbagi_dipertahankan_dan_tombol_id_unik_opsional(keluaran):
    assert keluaran["IDBAGI_EXC"].startswith("0"), keluaran["IDBAGI_EXC"]
    assert ("10 baris berbagi ID transaksi yang sama tetapi isinya berbeda (mis. satu kwitansi untuk beberapa pos); "
            "semuanya dipertahankan." in keluaran["IDBAGI_WARN"])
    assert keluaran["IDBAGI_TOMBOL"] == "Anggap ID transaksi unik, buang baris ber-ID sama"
    assert keluaran["IDUNIK_EXC"].startswith("0")
    assert "ID transaksi dianggap UNIK" in keluaran["IDUNIK_OK"] and "dianggap unik" in keluaran["IDUNIK_INFO"]
    assert "'id_transaksi_unik': True" in keluaran["IDUNIK_OPSI"]
    assert keluaran["IDBATAL_EXC"].startswith("0")
    assert "baris berbagi ID transaksi yang sama" in keluaran["IDBATAL_WARN"]  # kembali dipertahankan


def test_halaman_analisis_menampilkan_kualitas(keluaran):
    assert keluaran["ANL_EXC"].startswith("0"), keluaran["ANL_EXC"]
    assert "Laporan kualitas data" in keluaran["ANL_EXPANDER"]
    assert "kurang dari 24 bulan" in keluaran["ANL_WARN"]
    assert "Berkas tidak dapat dianalisis" not in keluaran["ANL_ERR"]
