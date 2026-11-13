"""Pendaftaran lembaga, verifikasi email, dan nama lembaga di layar web. Semua data sintetis.

Mode pengembangan (EMAIL_ENABLED=false, APP_ENV bukan production): ``email_service`` mencetak isi email,
termasuk tautan verifikasi, ke konsol server. Tes mengambil token dari keluaran itu, sama seperti
yang dilakukan pengembang.
"""
import re
import time
from datetime import timedelta

import pytest

from src.config import settings
from src.models.tenant import Tenant
from src.models.token_model import Token
from src.models.upload import Upload
from src.models.user import User
from src.waktu import utc_now
from tests.web.conftest import buat_pengguna, csrf_dari, masuk

SANDI_BARU = "SandiBaru123"


def _kirim(klien, **isi):
    data = {"nama_lembaga": "Yayasan Amil Uji", "nama": "Rina Amil", "email": "rina@contoh.invalid",
            "sandi": SANDI_BARU, "ulangi": SANDI_BARU}
    data.update(isi)
    if "csrf" not in data:
        data["csrf"] = csrf_dari(klien.get("/daftar").text)
    return klien.post("/daftar", data=data, follow_redirects=False)


def _token_dari_konsol(capsys) -> str:
    keluar = capsys.readouterr().out
    cocok = re.findall(r"token=([A-Za-z0-9_\-]+)", keluar.replace("&amp;", "&"))
    assert cocok, "tautan verifikasi tidak tercetak di konsol"
    return cocok[-1]


@pytest.fixture(autouse=True)
def _email_simulasi(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
    monkeypatch.setattr(settings, "APP_ENV", "development")


# --------------------------------------------------------------------------- alur utama
def test_daftar_verifikasi_masuk_dan_nama_lembaga_di_kepala(klien, web_db, capsys):
    r = _kirim(klien, nama_lembaga="  Yayasan   Amil   Uji  ")
    assert r.status_code == 303 and r.headers["location"] == "/daftar/cek-email"
    web_db.expire_all()
    t = web_db.query(Tenant).filter(Tenant.nama == "Yayasan Amil Uji").one()  # spasi berlebih dirapikan
    u = web_db.query(User).filter(User.email == "rina@contoh.invalid").one()
    assert u.tenant_id == t.id and u.peran == "admin" and u.is_verified is False and t.paket == "basic"
    token = _token_dari_konsol(capsys)

    # belum terverifikasi: tidak bisa masuk, dan diberi arahan
    r = masuk(klien, "rina@contoh.invalid", SANDI_BARU)
    assert r.status_code == 401 and "belum diverifikasi" in r.text and 'href="/daftar/cek-email"' in r.text

    cek = klien.get("/daftar/cek-email")
    assert cek.status_code == 200 and "Cek email Anda" in cek.text and token not in cek.text
    assert "Mode pengembangan" in cek.text

    r = klien.get("/verifikasi", params={"token": token})
    assert r.status_code == 200 and "Email terverifikasi" in r.text and token not in r.text
    r = masuk(klien, "rina@contoh.invalid", SANDI_BARU)
    assert r.status_code == 303
    beranda = klien.get("/beranda").text
    assert 'class="kepala__lembaga" title="Yayasan Amil Uji">Yayasan Amil Uji<' in beranda
    assert "<title>Beranda | Zakat Insight</title>" in beranda


def test_tautan_format_lama_di_akar_juga_memverifikasi(klien, web_db, capsys):
    _kirim(klien)
    token = _token_dari_konsol(capsys)
    r = klien.get("/", params={"page": "verify_email", "token": token}, follow_redirects=False)
    assert r.status_code == 200 and "Email terverifikasi" in r.text and "location" not in r.headers
    assert token not in r.text


def test_token_dipakai_ulang_kedaluwarsa_atau_sampah_ditolak(klien, web_db, capsys):
    _kirim(klien)
    token = _token_dari_konsol(capsys)
    assert klien.get("/verifikasi", params={"token": token}).status_code == 200
    r = klien.get("/verifikasi", params={"token": token})
    assert r.status_code == 400 and "Tautan tidak berlaku" in r.text and 'href="/daftar/cek-email"' in r.text
    for sampah in ("", "x", "a" * 500):
        assert klien.get("/verifikasi", params={"token": sampah}).status_code == 400

    _kirim(klien, email="kedaluwarsa@contoh.invalid")
    token2 = _token_dari_konsol(capsys)
    u = web_db.query(User).filter(User.email == "kedaluwarsa@contoh.invalid").one()
    tok = web_db.query(Token).filter(Token.user_id == u.id, Token.jenis == "verifikasi_email").one()
    tok.expires_at = utc_now() - timedelta(minutes=1)
    web_db.commit()
    assert klien.get("/verifikasi", params={"token": token2}).status_code == 400
    web_db.expire_all()
    assert web_db.get(User, u.id).is_verified is False


def test_kirim_ulang_membatalkan_tautan_lama_dan_pesannya_seragam(klien, web_db, capsys):
    _kirim(klien)
    lama = _token_dari_konsol(capsys)
    token = csrf_dari(klien.get("/daftar/cek-email").text)
    r1 = klien.post("/verifikasi/kirim-ulang", data={"csrf": token, "email": "rina@contoh.invalid"})
    baru = _token_dari_konsol(capsys)
    r2 = klien.post("/verifikasi/kirim-ulang", data={"csrf": token, "email": "tidak.ada@contoh.invalid"})
    assert r1.status_code == r2.status_code == 200
    assert "Jika email tersebut terdaftar" in r1.text and r1.text == r2.text
    assert lama != baru
    assert klien.get("/verifikasi", params={"token": lama}).status_code == 400
    assert klien.get("/verifikasi", params={"token": baru}).status_code == 200


# --------------------------------------------------------------------------- keamanan
def test_csrf_ditolak(klien, web_db):
    r = klien.post("/daftar", data={"nama_lembaga": "X Lembaga", "nama": "A B", "email": "a@contoh.invalid",
                                    "sandi": SANDI_BARU, "ulangi": SANDI_BARU}, follow_redirects=False)
    assert r.status_code == 400
    r = _kirim(klien, csrf="palsu")
    assert r.status_code == 400
    r = _kirim(klien, csrf=csrf_dari(klien.get("/daftar").text))
    assert r.status_code == 303  # kendali: token benar diterima
    token = csrf_dari(klien.get("/daftar").text)
    r = klien.post("/daftar", data={"csrf": token, "nama_lembaga": "Y Lembaga", "nama": "A B",
                                    "email": "b@contoh.invalid", "sandi": SANDI_BARU, "ulangi": SANDI_BARU},
                   headers={"Origin": "https://penyerang.invalid"}, follow_redirects=False)
    assert r.status_code == 400
    assert klien.post("/verifikasi/kirim-ulang", data={"email": "a@contoh.invalid"}).status_code == 400
    assert web_db.query(Tenant).count() == 1


def test_email_terdaftar_tidak_terbedakan(klien, web_db, lembaga_a):
    ada = buat_pengguna(web_db, lembaga_a)
    n_lembaga = web_db.query(Tenant).count()
    _kirim(klien, email="pemanasan@contoh.invalid")  # muat modul & cache lebih dulu agar waktu adil

    def coba(email):
        token = csrf_dari(klien.get("/daftar").text)
        t0 = time.perf_counter()
        r = klien.post("/daftar", data={"csrf": token, "nama_lembaga": "Lembaga Palsu", "nama": "Orang Lain",
                                        "email": email, "sandi": SANDI_BARU, "ulangi": SANDI_BARU},
                       follow_redirects=False)
        return r, time.perf_counter() - t0

    r_ada, t_ada = coba(ada.email.upper())
    r_baru, t_baru = coba("benar.baru@contoh.invalid")
    assert (r_ada.status_code, r_ada.headers["location"], r_ada.text) == \
        (r_baru.status_code, r_baru.headers["location"], r_baru.text)
    assert sorted(c.split("=")[0] for c in r_ada.headers.get_list("set-cookie")) == \
        sorted(c.split("=")[0] for c in r_baru.headers.get_list("set-cookie"))
    assert abs(t_ada - t_baru) < max(0.3 * t_baru, 0.15)  # bcrypt berjalan di kedua jalur
    web_db.expire_all()
    assert web_db.query(Tenant).count() == n_lembaga + 2  # pemanasan + email baru; email lama tidak membuat apa pun
    assert web_db.query(User).filter(User.email == ada.email).count() == 1
    assert web_db.get(User, ada.id).tenant_id == lembaga_a.id


def test_batas_laju_per_ip(klien, web_db, monkeypatch):
    monkeypatch.setattr(settings, "BATAS_DAFTAR_IP", "2/3600")
    assert _kirim(klien, email="a1@contoh.invalid").status_code == 303
    assert _kirim(klien, email="a2@contoh.invalid").status_code == 303
    r = _kirim(klien, email="a3@contoh.invalid")
    assert r.status_code == 429 and "dari jaringan Anda" in r.text and "⚠" not in r.text
    assert web_db.query(User).filter(User.email == "a3@contoh.invalid").count() == 0


def test_batas_laju_per_email(klien, web_db, monkeypatch):
    monkeypatch.setattr(settings, "BATAS_DAFTAR_IP", "100/3600")
    for _ in range(3):
        _kirim(klien, email="ulang@contoh.invalid")
    r = _kirim(klien, email="ULANG@contoh.invalid")
    assert r.status_code == 429 and "dengan email ini" in r.text


def test_batas_laju_kirim_ulang(klien, web_db, monkeypatch):
    monkeypatch.setattr(settings, "BATAS_VERIFIKASI_IP", "2/3600")
    token = csrf_dari(klien.get("/daftar/cek-email").text)
    for i in range(2):
        assert klien.post("/verifikasi/kirim-ulang", data={"csrf": token, "email": f"k{i}@contoh.invalid"}).status_code == 200
    assert klien.post("/verifikasi/kirim-ulang", data={"csrf": token, "email": "k9@contoh.invalid"}).status_code == 429


# --------------------------------------------------------------------------- validasi per kolom
def test_kata_sandi_lemah_dan_tidak_sama_ditolak_per_kolom(klien, web_db):
    r = _kirim(klien, sandi="lemah", ulangi="lemah")
    assert r.status_code == 400 and 'id="galat-sandi"' in r.text and "minimal 8 karakter" in r.text
    assert 'aria-invalid="true" aria-describedby="galat-sandi bantu-sandi"' in r.text
    r = _kirim(klien, sandi="semuakecil123", ulangi="semuakecil123")
    assert r.status_code == 400 and "huruf besar" in r.text
    r = _kirim(klien, ulangi="BerbedaSandi9")
    assert r.status_code == 400 and 'id="galat-ulangi"' in r.text
    assert SANDI_BARU not in r.text  # kata sandi tidak dikembalikan ke halaman
    assert web_db.query(Tenant).count() == 0


def test_aturan_sandi_dan_autocomplete_tampil_sebelum_gagal(klien, web_db):
    html = klien.get("/daftar").text
    assert "Minimal 8 karakter, memuat 1 huruf besar dan 1 angka." in html
    for nama, ac in (("nama_lembaga", "organization"), ("nama", "name"), ("email", "email"),
                     ("sandi", "new-password"), ("ulangi", "new-password")):
        assert re.search(rf'name="{nama}"[^>]*autocomplete="{ac}"', html), nama
    assert html.index('name="nama_lembaga"') < html.index('name="nama"')  # nama lembaga paling atas
    assert "tampil di seluruh aplikasi dan di laporan" in html


def test_panjang_karakter_kontrol_dan_kolom_kosong(klien, web_db):
    from web.daftar import MAKS_NAMA_LEMBAGA
    r = _kirim(klien, nama_lembaga="A" * (MAKS_NAMA_LEMBAGA + 1))
    assert r.status_code == 400 and f"paling panjang {MAKS_NAMA_LEMBAGA} karakter" in r.text
    r = _kirim(klien, nama_lembaga="Lembaga​Tersembunyi")
    assert r.status_code == 400 and "karakter tak terlihat" in r.text
    r = _kirim(klien, nama="Nama\x00Nol")
    assert r.status_code == 400 and 'id="galat-nama"' in r.text
    r = _kirim(klien, nama_lembaga="", nama="", email="bukan-email")
    assert r.status_code == 400 and "Ada 3 isian yang perlu diperbaiki" in r.text
    assert _kirim(klien, nama_lembaga="B" * MAKS_NAMA_LEMBAGA).status_code == 303
    assert web_db.query(Tenant).count() == 1


def test_nama_lembaga_kembar_dibolehkan_dengan_slug_berbeda(klien, web_db):
    assert _kirim(klien, email="satu@contoh.invalid").status_code == 303
    assert _kirim(klien, email="dua@contoh.invalid").status_code == 303
    slug = sorted(t.slug for t in web_db.query(Tenant).filter(Tenant.nama == "Yayasan Amil Uji"))
    assert len(slug) == 2 and slug[0] != slug[1]


def test_nama_berisi_script_di_escape(klien, web_db, capsys):
    jahat = "<script>alert(1)</script> Amil"
    r = _kirim(klien, nama_lembaga=jahat, sandi="lemah", ulangi="lemah")  # dikembalikan ke form saat galat
    assert "<script>alert(1)" not in r.text and "&lt;script&gt;alert(1)&lt;/script&gt; Amil" in r.text
    _kirim(klien, nama_lembaga=jahat, nama='"><img src=x onerror=alert(2)>')
    klien.get("/verifikasi", params={"token": _token_dari_konsol(capsys)})
    masuk(klien, "rina@contoh.invalid", SANDI_BARU)
    for jalur in ("/beranda", "/analisis", "/segera-hadir"):
        html = klien.get(jalur).text
        assert "<script>alert(1)" not in html and "<img src=x" not in html, jalur
        assert 'title="&lt;script&gt;alert(1)&lt;/script&gt; Amil"' in html


def test_production_tidak_pernah_menampilkan_token(web_db, monkeypatch, capsys):
    from fastapi.testclient import TestClient
    from web.main import app
    klien = TestClient(app, base_url="https://testserver")
    monkeypatch.setattr(settings, "APP_ENV", "production")
    r = _kirim(klien)
    assert r.status_code == 303
    halaman = klien.get("/daftar/cek-email").text
    assert "Mode pengembangan" not in halaman and "token" not in halaman.lower().replace('name="csrf"', "")
    assert "token=" not in capsys.readouterr().out  # tidak dicetak di production
    assert "token=" not in r.text and "token" not in r.headers.get("location", "")


# --------------------------------------------------------------------------- isolasi & tautan
def test_lembaga_baru_tidak_melihat_data_lembaga_lain(klien, web_db, lembaga_b, capsys):
    staf_b = buat_pengguna(web_db, lembaga_b, peran="staf")
    masuk(klien, staf_b.email)
    r = klien.post("/unggah/contoh", data={"csrf": csrf_dari(klien.get("/beranda").text)}, follow_redirects=False)
    id_b = r.headers["location"].rsplit("/", 1)[1]
    klien.cookies.clear()

    _kirim(klien, nama_lembaga="Yayasan Pendatang Uji")
    klien.get("/verifikasi", params={"token": _token_dari_konsol(capsys)})
    masuk(klien, "rina@contoh.invalid", SANDI_BARU)
    for jalur in ("/beranda", "/analisis", "/unggah", "/segera-hadir"):
        html = klien.get(jalur).text
        assert "Lembaga B" not in html and "data_contoh" not in html and "Yayasan Pendatang Uji" in html, jalur
    assert "Belum ada berkas" in klien.get("/analisis").text
    assert klien.get(f"/analisis/{id_b}").status_code == 404
    assert web_db.query(Upload).count() == 1


def test_tautan_daftar_di_layar_masuk_dan_segera_hadir(klien, web_db, lembaga_a):
    html = klien.get("/masuk").text
    assert 'href="/daftar"' in html and "Lupa kata sandi" in html
    u = buat_pengguna(web_db, lembaga_a)
    masuk(klien, u.email)
    assert "Daftar lembaga baru" not in klien.get("/segera-hadir").text
    assert klien.get("/daftar", follow_redirects=False).status_code == 303  # sudah masuk -> beranda


def test_nama_lembaga_tidak_bocor_antar_lembaga(klien, web_db, lembaga_a, lembaga_b):
    """Pengguna lembaga A tidak pernah melihat nama lembaga B di halaman mana pun (termasuk galat)."""
    staf_b = buat_pengguna(web_db, lembaga_b, peran="staf")
    masuk(klien, staf_b.email)
    r = klien.post("/unggah/contoh", data={"csrf": csrf_dari(klien.get("/beranda").text)}, follow_redirects=False)
    id_b = r.headers["location"].rsplit("/", 1)[1]
    klien.cookies.clear()
    staf_a = buat_pengguna(web_db, lembaga_a, peran="staf")
    masuk(klien, staf_a.email)
    r = klien.post("/unggah/contoh", data={"csrf": csrf_dari(klien.get("/beranda").text)}, follow_redirects=False)
    jalur_a = r.headers["location"]
    halaman = ["/beranda", "/analisis", jalur_a, jalur_a + "?tahun=2023", "/unggah", "/segera-hadir",
               f"/analisis/{id_b}", "/tidak-ada", "/daftar/cek-email"]
    for jalur in halaman:
        html = klien.get(jalur).text
        assert "Lembaga B" not in html, jalur
    assert 'title="Lembaga A">Lembaga A<' in klien.get("/beranda").text


def test_nama_lembaga_panjang_terpotong_dengan_title(klien, web_db):
    from tests.web.conftest import buat_lembaga
    from web.daftar import MAKS_NAMA_LEMBAGA
    panjang = ("Yayasan Badan Amil Zakat Infak dan Sedekah Kabupaten Contoh Raya Sejahtera " * 2)[:MAKS_NAMA_LEMBAGA]
    t = buat_lembaga(web_db, nama=panjang)
    u = buat_pengguna(web_db, t)
    masuk(klien, u.email)
    html = klien.get("/beranda").text
    assert f'class="kepala__lembaga" title="{panjang}">{panjang}<' in html
    css = klien.get("/statis/css/situs.css").text
    aturan = css.split(".kepala__lembaga {", 1)[1].split("}", 1)[0]
    assert "text-overflow: ellipsis" in aturan and "white-space: nowrap" in aturan and "overflow: hidden" in aturan
