"""Email SMTP sungguhan diuji terhadap server SMTP tiruan lokal: TLS wajib, timeout, gagal kirim,
dan alur verifikasi/reset tanpa membocorkan apakah email terdaftar."""
import email
import time

import pytest

pytest.importorskip("cryptography")

from src.config import settings  # noqa: E402
from src.models.audit_log import AuditLog  # noqa: E402
from src.models.tenant import Tenant  # noqa: E402
from src.models.user import User  # noqa: E402
from src.services import auth_service as asv  # noqa: E402
from src.services import email_service as es  # noqa: E402
from tests.smtp_tiruan import ServerSMTPTiruan, buat_sertifikat, port_tertutup  # noqa: E402


@pytest.fixture(scope="module")
def sert(tmp_path_factory):
    return buat_sertifikat(tmp_path_factory.mktemp("sert"))


@pytest.fixture
def smtp(monkeypatch, sert):
    ca, _, _ = sert

    def atur(port, mode="starttls", ca_file=str(ca), timeout=3.0, user="uji", sandi="rahasia"):
        for k, v in {"EMAIL_ENABLED": True, "EMAIL_SMTP_HOST": "127.0.0.1", "EMAIL_SMTP_PORT": port,
                     "EMAIL_SMTP_TLS": "ssl" if mode == "ssl" else "starttls", "EMAIL_SMTP_CA_FILE": ca_file,
                     "EMAIL_SMTP_TIMEOUT": timeout, "EMAIL_SMTP_USER": user, "EMAIL_SMTP_PASS": sandi,
                     "EMAIL_FROM": "noreply@lembaga-uji.invalid"}.items():
            monkeypatch.setattr(settings, k, v)
    return atur


def _server(sert, mode="starttls"):
    _, crt, key = sert
    return ServerSMTPTiruan(crt, key, mode=mode)


def test_starttls_login_setelah_tls_dan_pesan_terkirim(sert, smtp):
    with _server(sert) as srv:
        smtp(srv.port)
        hasil = es.kirim_email("penerima@contoh.invalid", "Uji", "<p>Halo <a href='https://x/?t=1'>tautan</a></p>",
                               "Halo", jenis="uji")
    assert hasil.berhasil, hasil.alasan
    assert srv.catatan.login == [("uji", "rahasia", True)]           # kredensial hanya lewat TLS
    assert all(tls for cmd, tls in srv.catatan.perintah if cmd in ("AUTH", "MAIL", "RCPT", "DATA"))
    m = email.message_from_bytes(srv.catatan.pesan[0])
    assert m["To"] == "penerima@contoh.invalid" and m["From"] == "noreply@lembaga-uji.invalid"
    jenis = {p.get_content_type() for p in m.walk()}
    assert {"text/plain", "text/html"} <= jenis


def test_ssl_langsung_port_465(sert, smtp):
    with _server(sert, "ssl") as srv:
        smtp(srv.port, mode="ssl")
        assert es.kirim_email("a@contoh.invalid", "Uji", "<p>x</p>").berhasil
    assert srv.catatan.login[0][2] is True


def test_server_tanpa_starttls_ditolak_tanpa_kirim_kredensial(sert, smtp):
    with _server(sert, "tanpa_tls") as srv:
        smtp(srv.port)
        hasil = es.kirim_email("a@contoh.invalid", "Uji", "<p>x</p>")
    assert not hasil.berhasil and hasil.alasan == "tls_tidak_didukung"
    assert srv.catatan.login == [] and srv.catatan.pesan == []


def test_sertifikat_tidak_tepercaya_ditolak(sert, smtp):
    with _server(sert) as srv:
        smtp(srv.port, ca_file="")  # CA sistem tidak mengenal CA uji
        hasil = es.kirim_email("a@contoh.invalid", "Uji", "<p>x</p>")
    assert not hasil.berhasil and hasil.alasan == "tls_gagal"
    assert srv.catatan.login == []


def test_timeout_tidak_menggantung(sert, smtp):
    with _server(sert, "diam") as srv:
        smtp(srv.port, timeout=1.0)
        t0 = time.perf_counter()
        hasil = es.kirim_email("a@contoh.invalid", "Uji", "<p>x</p>")
        lama = time.perf_counter() - t0
    assert not hasil.berhasil and hasil.alasan == "timeout"
    assert lama < 3


def test_server_mati_dan_sandi_salah(sert, smtp):
    smtp(port_tertutup())
    assert es.kirim_email("a@contoh.invalid", "Uji", "<p>x</p>").alasan == "koneksi"
    with _server(sert) as srv:
        smtp(srv.port, sandi="salah")
        assert es.kirim_email("a@contoh.invalid", "Uji", "<p>x</p>").alasan == "autentikasi"


def test_tls_tidak_bisa_dimatikan(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_SMTP_TLS", "none")
    with pytest.raises(ValueError):
        es.mode_tls()


def test_log_tanpa_alamat_isi_atau_token(sert, smtp, caplog):
    with caplog.at_level("INFO"):
        smtp(port_tertutup())
        es.kirim_email("rahasia.penerima@contoh.invalid", "Uji", "<p>?token=ABC123</p>", jenis="uji")
        with _server(sert) as srv:
            smtp(srv.port)
            es.kirim_email("rahasia.penerima@contoh.invalid", "Uji", "<p>?token=ABC123</p>", jenis="uji")
    assert "rahasia.penerima" not in caplog.text and "ABC123" not in caplog.text
    assert "email gagal dikirim" in caplog.text and "email terkirim" in caplog.text


# ---------------------------------------------------------------------------
# Alur: reset & pendaftaran tidak membocorkan keberadaan email, gagal kirim dicatat
# ---------------------------------------------------------------------------
def _tunggu(kondisi, detik=5.0):
    batas = time.time() + detik
    while time.time() < batas:
        if kondisi():
            return True
        time.sleep(0.05)
    return False


def test_reset_terkirim_lewat_smtp_dan_waktu_tidak_bergantung_smtp(db, admin_user, sert, smtp):
    with _server(sert, "diam") as lambat:  # server lambat/macet: halaman tetap cepat
        smtp(lambat.port, timeout=2.0)
        t0 = time.perf_counter()
        asv.request_reset_password(db, admin_user.email)
        t_ada = time.perf_counter() - t0
        t0 = time.perf_counter()
        asv.request_reset_password(db, "tidak.ada@contoh.invalid")
        t_tidak = time.perf_counter() - t0
    assert t_ada < 1.0 and t_tidak < 1.0
    with _server(sert) as srv:
        smtp(srv.port)
        asv.request_reset_password(db, admin_user.email)
        assert _tunggu(lambda: len(srv.catatan.pesan) == 1)
    isi = email.message_from_bytes(srv.catatan.pesan[0])
    html = [p for p in isi.walk() if p.get_content_type() == "text/html"][0].get_payload(decode=True).decode()
    assert "page=reset_password&amp;token=" in html


def test_gagal_kirim_dicatat_di_audit_tanpa_email(db, admin_user, monkeypatch):
    import contextlib

    import src.database as dbmod

    @contextlib.contextmanager
    def sesi_uji():
        yield db
    monkeypatch.setattr(dbmod, "get_db", sesi_uji)
    asv._audit_gagal_kirim(admin_user.id, admin_user.tenant_id, "reset_password")(es.HasilKirim(False, "timeout"))
    log = db.query(AuditLog).filter(AuditLog.user_id == admin_user.id, AuditLog.aksi == "email_gagal_kirim").one()
    assert log.detail == {"jenis": "reset_password", "alasan": "timeout"}
    assert admin_user.email not in str(log.detail)


def test_daftar_email_terdaftar_tidak_bocor(db, admin_user, sert, smtp):
    n_tenant = db.query(Tenant).count()
    with _server(sert) as srv:
        smtp(srv.port)
        t0 = time.perf_counter()
        r_baru = asv.register_tenant(db, "Lembaga Baru Uji", "Ani", "baru.unik@contoh.invalid", "SandiKuat123")
        t_baru = time.perf_counter() - t0
        t0 = time.perf_counter()
        r_ada = asv.register_tenant(db, "Lembaga Palsu", "X", admin_user.email.upper(), "SandiKuat123")
        t_ada = time.perf_counter() - t0
        assert _tunggu(lambda: len(srv.catatan.pesan) == 2)
    assert r_baru == r_ada == {"status": "terkirim"}          # halaman menampilkan pesan yang sama
    assert db.query(Tenant).count() == n_tenant + 1             # tidak ada akun kedua untuk email terdaftar
    assert db.query(User).filter(User.email == admin_user.email).count() == 1
    assert abs(t_baru - t_ada) < max(0.3 * t_baru, 0.15)        # bcrypt dijalankan di kedua jalur
    subjek = sorted(email.message_from_bytes(m)["Subject"] for m in srv.catatan.pesan)
    assert any("Percobaan pendaftaran" in x for x in subjek) and any("Verifikasi" in x for x in subjek)


def test_kirim_ulang_verifikasi(db, sert, smtp):
    with _server(sert) as srv:
        smtp(srv.port)
        asv.register_tenant(db, "Lembaga Verif", "Budi", "verif.ulang@contoh.invalid", "SandiKuat123")
        assert _tunggu(lambda: len(srv.catatan.pesan) == 1)
        assert asv.kirim_ulang_verifikasi(db, "verif.ulang@contoh.invalid") is True
        assert _tunggu(lambda: len(srv.catatan.pesan) == 2)
        assert asv.kirim_ulang_verifikasi(db, "tidak.ada@contoh.invalid") is False
    from src.models.token_model import Token
    u = db.query(User).filter(User.email == "verif.ulang@contoh.invalid").one()
    aktif = db.query(Token).filter(Token.user_id == u.id, Token.jenis == "verifikasi_email",
                                   Token.used_at.is_(None)).count()
    assert aktif == 1  # tautan lama dibatalkan


def test_undangan_gagal_kirim_diberitahukan_ke_admin(db, admin_user, smtp):
    smtp(port_tertutup())
    oleh = {"id": admin_user.id, "peran": "admin", "tenant_id": admin_user.tenant_id}
    u = asv.kirim_undangan(db, admin_user.tenant_id, "calon.anggota@contoh.invalid", "staf", oleh)
    assert u.email_terkirim is False
