"""Keamanan frontend web: login, sesi, CSRF, peran, isolasi lembaga, escape, header."""
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from src.config import settings
from src.models.audit_log import AuditLog
from src.models.sesi_web import SesiWeb
from src.models.token_model import Token
from src.models.upload import Upload
from src.services.auth_service import hash_token
from src.waktu import utc_now
from tests.web.conftest import SANDI, buat_lembaga, buat_pengguna, csrf_dari, masuk
from web.main import COOKIE_SESI

AKAR = Path(__file__).resolve().parents[2]
PESAN_SALAH = "Email atau kata sandi tidak cocok."


# --------------------------------------------------------------------------- login
def test_login_benar_membuat_sesi_server_dan_cookie_aman(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a)
    r = masuk(klien, u.email)
    assert r.status_code == 303 and r.headers["location"] == "/beranda"
    set_cookie = [h for h in r.headers.get_list("set-cookie") if h.startswith(COOKIE_SESI + "=")][0]
    assert "httponly" in set_cookie.lower() and "samesite=lax" in set_cookie.lower()
    mentah = klien.cookies.get(COOKIE_SESI)
    assert len(mentah) >= 40
    # DB hanya menyimpan hash ID sesi, bukan ID mentahnya
    web_db.expire_all()
    sesi = web_db.query(SesiWeb).filter(SesiWeb.user_id == u.id).one()
    assert sesi.id_hash == hash_token(mentah) and sesi.id_hash != mentah
    assert sesi.kedaluwarsa > utc_now() + timedelta(hours=settings.JWT_ACCESS_EXPIRE_HOURS - 1)
    tok = web_db.get(Token, sesi.refresh_token_id)
    assert tok.jenis == "refresh" and tok.used_at is None  # refresh token dari auth_service.login
    b = klien.get("/beranda")
    assert b.status_code == 200 and "Lembaga A" in b.text


def test_cookie_secure_di_production(web_db, lembaga_a, monkeypatch):
    from fastapi.testclient import TestClient
    from web.main import app
    klien = TestClient(app, base_url="https://testserver")
    u = buat_pengguna(web_db, lembaga_a)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    r = masuk(klien, u.email)
    assert r.status_code == 303
    assert all("secure" in h.lower() for h in r.headers.get_list("set-cookie"))
    assert "strict-transport-security" in r.headers


def test_login_salah_ditolak_dan_dicatat(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a)
    r = masuk(klien, u.email, "sandi-keliru")
    assert r.status_code == 401 and PESAN_SALAH in r.text
    assert COOKIE_SESI not in klien.cookies
    web_db.expire_all()
    assert web_db.query(SesiWeb).count() == 0
    assert web_db.query(AuditLog).filter(AuditLog.aksi == "login_gagal").count() == 1
    assert web_db.get(type(u), u.id).failed_login_count == 1
    r = masuk(klien, "tidak.ada@contoh.invalid")
    assert r.status_code == 401 and PESAN_SALAH in r.text  # sama persis: tidak membocorkan email terdaftar


def test_kolom_kosong(klien, web_db):
    r = klien.get("/masuk")
    r = klien.post("/masuk", data={"email": "", "sandi": "", "csrf": csrf_dari(r.text)})
    assert r.status_code == 400 and "Isi email dan kata sandi" in r.text


def test_akun_terkunci_menolak_sandi_benar_tanpa_membocorkan(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a)
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        masuk(klien, u.email, "keliru")
    web_db.expire_all()
    assert web_db.get(type(u), u.id).locked_until > utc_now()  # penguncian akun yang sudah ada berlaku
    from src.middleware.rate_limiter import RateLimiter
    RateLimiter()._attempts.clear()  # pisahkan dari batas per email agar yang diuji penguncian akun
    r = masuk(klien, u.email, SANDI)
    assert r.status_code == 401 and PESAN_SALAH in r.text
    assert "dikunci" in r.text and f"{settings.LOGIN_LOCKOUT_MINUTES} menit" in r.text  # arahan tindakan
    assert "akun Anda terkunci" not in r.text
    web_db.expire_all()
    assert web_db.query(AuditLog).filter(AuditLog.aksi == "login_ditolak_terkunci").count() == 1
    assert web_db.query(SesiWeb).count() == 0


def test_batas_per_email(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a)
    for _ in range(5):
        masuk(klien, u.email, "keliru")
    r = masuk(klien, u.email.upper(), SANDI)  # huruf besar tidak mengakali batas
    assert r.status_code == 429 and "Terlalu banyak percobaan gagal untuk email ini" in r.text


def test_batas_per_ip_tahan_restart(klien, web_db, lembaga_a, monkeypatch):
    monkeypatch.setattr(settings, "BATAS_LOGIN_IP", "2/900")
    u = buat_pengguna(web_db, lembaga_a)
    masuk(klien, "a@contoh.invalid", "x")
    masuk(klien, "b@contoh.invalid", "x")
    r = masuk(klien, u.email, SANDI)
    assert r.status_code == 429 and "dari jaringan Anda" in r.text and "⚠" not in r.text


# --------------------------------------------------------------------------- rute terlindungi
def test_rute_terlindungi_menolak_tanpa_sesi(klien, web_db, lembaga_a):
    for jalur in ("/beranda", "/analisis", "/analisis/abc", "/unggah", "/segera-hadir"):
        r = klien.get(jalur, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/masuk", jalur
    for jalur in ("/unggah", "/unggah/contoh", "/keluar"):
        r = klien.post(jalur, data={"csrf": "x"}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/masuk", jalur
    klien.cookies.set(COOKIE_SESI, "id-sesi-karangan")
    assert klien.get("/beranda", follow_redirects=False).status_code == 303


def test_sesi_kedaluwarsa_dan_sesi_versi(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a)
    masuk(klien, u.email)
    assert klien.get("/beranda").status_code == 200
    u.sesi_versi = (u.sesi_versi or 0) + 1  # mis. sandi direset: semua sesi lama berakhir
    web_db.commit()
    assert klien.get("/beranda", follow_redirects=False).status_code == 303
    masuk(klien, u.email)
    sesi = web_db.query(SesiWeb).filter(SesiWeb.dicabut.is_(None), SesiWeb.sesi_versi == u.sesi_versi).one()
    sesi.kedaluwarsa = utc_now() - timedelta(seconds=1)
    web_db.commit()
    assert klien.get("/beranda", follow_redirects=False).status_code == 303


def test_pengguna_dinonaktifkan_sesinya_berakhir(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a)
    masuk(klien, u.email)
    u.is_active = False
    web_db.commit()
    assert klien.get("/beranda", follow_redirects=False).status_code == 303


# --------------------------------------------------------------------------- CSRF
def test_csrf_ditolak_tanpa_token(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a, peran="staf")
    r = klien.post("/masuk", data={"email": u.email, "sandi": SANDI}, follow_redirects=False)
    assert r.status_code == 400 and COOKIE_SESI not in klien.cookies
    r = klien.get("/masuk")
    r = klien.post("/masuk", data={"email": u.email, "sandi": SANDI, "csrf": "token-palsu"}, follow_redirects=False)
    assert r.status_code == 400
    masuk(klien, u.email)
    assert klien.post("/keluar", data={}, follow_redirects=False).status_code == 400
    assert klien.post("/unggah/contoh", data={"csrf": "salah"}, follow_redirects=False).status_code == 400
    assert klien.post("/unggah", data={}, files={"berkas": ("a.csv", b"x", "text/csv")},
                      follow_redirects=False).status_code == 400
    assert web_db.query(Upload).count() == 0
    assert klien.get("/beranda").status_code == 200  # keluar tanpa token tidak mencabut sesi


def test_origin_asing_ditolak_meski_token_benar(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a, peran="staf")
    masuk(klien, u.email)
    token = csrf_dari(klien.get("/beranda").text)
    r = klien.post("/unggah/contoh", data={"csrf": token}, headers={"Origin": "https://penyerang.invalid"},
                   follow_redirects=False)
    assert r.status_code == 400 and web_db.query(Upload).count() == 0


# --------------------------------------------------------------------------- logout
def test_logout_mencabut_sesi_di_server(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a)
    masuk(klien, u.email)
    mentah = klien.cookies.get(COOKIE_SESI)
    token = csrf_dari(klien.get("/beranda").text)
    r = klien.post("/keluar", data={"csrf": token}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/masuk")
    web_db.expire_all()
    sesi = web_db.get(SesiWeb, hash_token(mentah))
    assert sesi.dicabut is not None
    assert web_db.get(Token, sesi.refresh_token_id).used_at is not None  # refresh token ikut dicabut
    assert web_db.query(AuditLog).filter(AuditLog.aksi == "logout", AuditLog.user_id == u.id).count() == 1
    # Cookie lama yang disalin penyerang tidak berlaku lagi
    klien.cookies.clear()
    klien.cookies.set(COOKIE_SESI, mentah)
    assert klien.get("/beranda", follow_redirects=False).status_code == 303


# --------------------------------------------------------------------------- peran & lembaga
def test_pembaca_tidak_bisa_mengunggah(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a, peran="pembaca")
    masuk(klien, u.email)
    beranda = klien.get("/beranda").text
    assert 'href="/unggah"' not in beranda
    token = csrf_dari(beranda)
    assert klien.get("/unggah").status_code == 403
    assert klien.post("/unggah/contoh", data={"csrf": token}).status_code == 403
    r = klien.post("/unggah", data={"csrf": token}, files={"berkas": ("a.csv", b"tanggal,jumlah\n", "text/csv")})
    assert r.status_code == 403 and "Pembaca" in r.text
    assert web_db.query(Upload).count() == 0


def test_isolasi_lembaga_berkas_lain_404(klien, web_db, lembaga_a, lembaga_b):
    staf_b = buat_pengguna(web_db, lembaga_b, peran="staf")
    masuk(klien, staf_b.email)
    token = csrf_dari(klien.get("/beranda").text)
    r = klien.post("/unggah/contoh", data={"csrf": token}, follow_redirects=False)
    assert r.status_code == 303
    id_b = r.headers["location"].rsplit("/", 1)[1]
    assert klien.get(f"/analisis/{id_b}").status_code == 200

    klien.cookies.clear()
    admin_a = buat_pengguna(web_db, lembaga_a, peran="admin")
    masuk(klien, admin_a.email)
    for jalur in (f"/analisis/{id_b}", f"/analisis?berkas={id_b}", f"/analisis/{id_b}?tenant_id={lembaga_b.id}"):
        r = klien.get(jalur)
        assert r.status_code == 404, jalur
        assert "Lembaga B" not in r.text and "data_contoh" not in r.text
    assert "data_contoh" not in klien.get("/beranda").text


def test_super_admin_tanpa_lembaga_ditolak_di_analisis(klien, web_db):
    sa = buat_pengguna(web_db, None, peran="super_admin")
    masuk(klien, sa.email)
    assert klien.get("/beranda").status_code == 200
    assert klien.get("/analisis").status_code == 403
    assert klien.get("/unggah").status_code == 403


def test_lembaga_nonaktif_sesinya_berakhir(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a)
    masuk(klien, u.email)
    lembaga_a.is_active = False
    web_db.commit()
    assert klien.get("/beranda", follow_redirects=False).status_code == 303


# --------------------------------------------------------------------------- escape & header
def test_nama_berisi_script_di_escape(klien, web_db):
    t = buat_lembaga(web_db, nama='<img src=x onerror=alert(2)> Lembaga')
    u = buat_pengguna(web_db, t, peran="staf", nama="<script>alert(1)</script>")
    masuk(klien, u.email)
    html = klien.get("/beranda").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<img src=x" not in html and "&lt;img src=x onerror=alert(2)&gt;" in html
    token = csrf_dari(html)
    isi = b"tanggal,nama_muzaki,jumlah,jenis_dana\n" + b"".join(
        f"2024-{b:02d}-10,Muzaki {b},{100000 * b},Infak\n".encode() for b in range(1, 13))
    r = klien.post("/unggah", data={"csrf": token},
                   files={"berkas": ('"><script>alert(3)</script>.csv', isi, "text/csv")}, follow_redirects=True)
    assert r.status_code == 200
    assert "<script>alert(3)" not in r.text and "<script>alert(3)" not in klien.get("/beranda").text


def test_template_tidak_memakai_safe():
    for p in (AKAR / "web" / "templates").glob("*.html"):
        teks = p.read_text(encoding="utf-8")
        assert "|safe" not in teks.replace(" ", "") and "autoescape false" not in teks, p.name


def test_header_keamanan(klien, web_db):
    r = klien.get("/masuk")
    csp = r.headers["content-security-policy"]
    script_src = [d for d in csp.split(";") if d.strip().startswith("script-src")][0]
    assert script_src.strip() == "script-src 'self'"  # tanpa inline script dan tanpa eval
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"
    assert "<script>" not in r.text  # tidak ada skrip inline di halaman
    assert klien.get("/statis/css/situs.css").headers["x-content-type-options"] == "nosniff"


def test_web_tidak_memuat_streamlit():
    kode = "import sys, web.main; print('streamlit' in sys.modules)"
    keluar = subprocess.run([sys.executable, "-c", kode], cwd=AKAR, capture_output=True, text=True, check=True,
                            env={"APP_ENV_FILE": "", "PATH": "", "PYTHONPATH": str(AKAR)})  # nosec - argumen tetap
    assert keluar.stdout.strip() == "False"
