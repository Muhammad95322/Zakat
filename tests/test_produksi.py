"""Produksi aman secara bawaan (konfigurasi, HTTPS) dan observabilitas tanpa data pribadi."""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import Settings, periksa_konfigurasi_produksi
from src.middleware import https
from src.observabilitas import FormatJSON, FormatTeks, bersihkan_event, bersihkan_pii
from tests.test_config import PROD_LENGKAP

ROOT = Path(__file__).parent.parent


def _settings(**ubah) -> Settings:
    s = Settings()
    nilai = {**PROD_LENGKAP, **ubah}
    s.APP_ENV = nilai["APP_ENV"]
    s.APP_SECRET_KEY = nilai["APP_SECRET_KEY"]
    s.DATABASE_URL = nilai["DATABASE_URL"]
    s.APP_BASE_URL = nilai["APP_BASE_URL"]
    s.EMAIL_ENABLED = str(nilai["EMAIL_ENABLED"]).lower() == "true"
    for k in ("EMAIL_SMTP_HOST", "EMAIL_SMTP_USER", "EMAIL_SMTP_PASS", "EMAIL_FROM", "PENYIMPANAN", "S3_BUCKET",
              "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "PROXY_TEPERCAYA"):
        setattr(s, k, nilai[k])
    s.EMAIL_SMTP_PORT = int(nilai.get("EMAIL_SMTP_PORT", 587))
    return s


# ---------------------------------------------------------------------------
# Konfigurasi production
# ---------------------------------------------------------------------------
def test_konfigurasi_lengkap_lolos():
    galat, peringatan = periksa_konfigurasi_produksi(_settings())
    assert galat == []
    assert any("SENTRY_DSN" in w for w in peringatan)


@pytest.mark.parametrize("ubah, potongan", [
    ({"APP_SECRET_KEY": ""}, "APP_SECRET_KEY"),
    ({"APP_SECRET_KEY": "dev-secret-key-ganti-di-production-32chars"}, "APP_SECRET_KEY"),
    ({"DATABASE_URL": "sqlite:////app/var/z.db"}, "DATABASE_URL harus PostgreSQL"),
    ({"APP_BASE_URL": "http://zakat.contoh.invalid"}, "APP_BASE_URL harus alamat publik https"),
    ({"APP_BASE_URL": "https://localhost:8501"}, "APP_BASE_URL"),
    ({"EMAIL_ENABLED": "false"}, "EMAIL_ENABLED harus true"),
    ({"EMAIL_SMTP_PASS": ""}, "EMAIL_SMTP_PASS kosong"),
    ({"EMAIL_FROM": "noreply@zakatinsight.id"}, "EMAIL_FROM masih bawaan"),
    ({"EMAIL_SMTP_PORT": 25}, "EMAIL_SMTP_PORT 25 diblokir"),
    ({"S3_BUCKET": ""}, "S3_BUCKET kosong"),
    ({"PENYIMPANAN": "lokal"}, "PENYIMPANAN=lokal di production"),
    ({"PENYIMPANAN": "ftp"}, "PENYIMPANAN harus"),
])
def test_setiap_kekurangan_ditolak(ubah, potongan):
    galat, _ = periksa_konfigurasi_produksi(_settings(**ubah))
    assert any(potongan in g for g in galat), galat
    teks = " ".join(galat)
    assert "RAHASIA" not in teks and "AKIAUJI" not in teks


def test_lokal_permanen_diizinkan_dengan_pernyataan_eksplisit(monkeypatch):
    monkeypatch.setenv("PENYIMPANAN_LOKAL_PERMANEN", "true")
    assert periksa_konfigurasi_produksi(_settings(PENYIMPANAN="lokal"))[0] == []


def test_validate_melaporkan_semua_galat_sekaligus():
    s = _settings(DATABASE_URL="sqlite:///x.db", EMAIL_ENABLED="false", APP_BASE_URL="http://x")
    with pytest.raises(Exception) as e:
        s.validate()
    assert str(e.value).count("\n- ") == 3


def test_dockerfile_dan_render_menjalankan_validator_sebelum_start():
    df = (ROOT / "Dockerfile").read_text()
    ry = (ROOT / "render.yaml").read_text()
    assert "python scripts/validate_config.py &&" in df
    assert "python scripts/validate_config.py &&" in ry
    assert "healthCheckPath: /_stcore/health" in ry
    assert "PROXY_TEPERCAYA" in ry and "PENYIMPANAN" in ry


# ---------------------------------------------------------------------------
# HTTPS
# ---------------------------------------------------------------------------
@pytest.fixture
def prod(monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PROXY_TEPERCAYA", "render")


def test_http_dari_proxy_tepercaya_dialihkan(prod):
    assert https.perlu_dialihkan({"X-Forwarded-Proto": "http"}, "10.0.0.5", None)
    assert not https.perlu_dialihkan({"X-Forwarded-Proto": "https"}, "10.0.0.5", None)


def test_header_proto_palsu_dari_klien_langsung_diabaikan(prod):
    # klien yang langsung terhubung tidak bisa "mengaku" https lewat header
    assert https.skema_permintaan({"X-Forwarded-Proto": "https"}, "198.51.100.9", "http://x/") == "http"
    assert https.perlu_dialihkan({"X-Forwarded-Proto": "https"}, "198.51.100.9", "http://x/")


def test_development_tidak_dipaksa(monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "APP_ENV", "development")
    assert not https.perlu_dialihkan({"X-Forwarded-Proto": "http"}, "10.0.0.5", "http://localhost:8501/")


def test_cookie_xsrf_samesite_strict():
    assert 'xsrfCookieSameSite = "strict"' in (ROOT / ".streamlit" / "config.toml").read_text()


# ---------------------------------------------------------------------------
# Log terstruktur tanpa data pribadi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("masuk, tidak_boleh", [
    ("kirim ke siti.rahma@contoh.invalid", "siti.rahma"),
    ("hp 0812-3456-7890 dan +62 857 1122 3344", "3456"),
    ("NIK 3404012345670001", "3404012345670001"),
    ("?page=reset_password&token=AbC-123_xyz", "AbC-123_xyz"),
    ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
    ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlLXVqaQ", "eyJzdWIi"),
    ("postgresql://zakat:sandiDB@host:5432/db", "sandiDB"),
    ("password=Rahasia123", "Rahasia123"),
])
def test_bersihkan_pii(masuk, tidak_boleh):
    assert tidak_boleh not in bersihkan_pii(masuk)


def _rekam(formatter, fungsi):
    rec = []

    class H(logging.Handler):
        def emit(self, r):
            rec.append(formatter.format(r))
    log = logging.getLogger("uji.observabilitas")
    h = H()
    log.addHandler(h)
    log.propagate = False
    try:
        fungsi(log)
    finally:
        log.removeHandler(h)
    return rec


def test_log_json_tanpa_pesan_exception_dan_extra_dibersihkan():
    def f(log):
        try:
            raise ValueError("Baris 7: donatur Budi Santoso 081234567890 nominal 'Rp 5.000.000'")
        except ValueError:
            log.exception("gagal memproses berkas", extra={"berkas": "donasi siti@contoh.invalid.xlsx", "baris": 7})
    baris = _rekam(FormatJSON(), f)
    d = json.loads(baris[0])
    assert d["pesan"] == "gagal memproses berkas" and d["baris"] == 7 and d["level"] == "ERROR"
    assert d["exception"]["jenis"] == "ValueError" and d["exception"]["lokasi"]
    teks = baris[0]
    for x in ("Budi", "081234567890", "5.000.000", "siti@"):
        assert x not in teks
    teks2 = _rekam(FormatTeks(), f)[0]
    assert "Budi" not in teks2 and "ValueError" in teks2


# ---------------------------------------------------------------------------
# Sentry opsional
# ---------------------------------------------------------------------------
def _event():
    return {
        "request": {"data": "isi berkas", "cookies": "c", "headers": {"Authorization": "x"}},
        "user": {"email": "a@b.id", "ip_address": "1.2.3.4"}, "extra": {"df": "Budi"},
        "exception": {"values": [{"type": "ValueError", "value": "donatur Budi 081234567890",
                                  "stacktrace": {"frames": [{"filename": "a.py", "vars": {"nama": "Budi"},
                                                             "context_line": "nama = 'Budi'"}]}}]},
        "logentry": {"message": "kirim ke siti@contoh.invalid", "params": ["Budi"]},
        "breadcrumbs": {"values": [{"message": "token=RAHASIA", "data": {"q": "Budi"}}]},
    }


def test_before_send_membuang_pii():
    e = bersihkan_event(_event(), {})
    teks = json.dumps(e)
    for x in ("Budi", "081234567890", "siti@", "RAHASIA", "1.2.3.4", "isi berkas"):
        assert x not in teks
    assert e["exception"]["values"][0]["type"] == "ValueError"
    assert "request" not in e and "user" not in e and "extra" not in e


def test_galat_isi_berkas_tidak_dikirim_ke_sentry():
    from src.loader import DataFileError
    try:
        raise DataFileError("kolom 'Nama' baris 3: 'Budi'")
    except DataFileError as exc:
        assert bersihkan_event(_event(), {"exc_info": (type(exc), exc, exc.__traceback__)}) is None


def test_sentry_ujung_ke_ujung_dengan_transport_tiruan(monkeypatch):
    sentry_sdk = pytest.importorskip("sentry_sdk")
    from sentry_sdk.transport import Transport

    from src import observabilitas as ob
    from src.config import settings

    terkirim = []

    class TransportUji(Transport):
        def capture_envelope(self, envelope):
            for item in envelope.items:
                if item.payload.json:
                    terkirim.append(item.payload.json)

    asli = sentry_sdk.init
    argumen = {}

    def init_uji(**kw):
        argumen.update(kw)
        return asli(transport=TransportUji(kw), **kw)
    monkeypatch.setattr(sentry_sdk, "init", init_uji)
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://kunci@o0.ingest.contoh.invalid/1")
    monkeypatch.setitem(ob._SUDAH, "sentry", False)
    try:
        assert ob.atur_sentry() is True
        assert argumen["send_default_pii"] is False and argumen["include_local_variables"] is False
        nama_donatur = "Budi Santoso"  # noqa: F841  (variabel lokal tidak boleh ikut terkirim)
        try:
            raise RuntimeError("gagal hitung untuk Budi Santoso 3404012345670001")
        except RuntimeError as e:
            sentry_sdk.capture_exception(e)
        sentry_sdk.flush()
    finally:
        sentry_sdk.init(dsn=None)
        ob._SUDAH["sentry"] = False
    teks = json.dumps(terkirim)
    assert terkirim and "RuntimeError" in teks
    assert "Budi" not in teks and "3404012345670001" not in teks


# ---------------------------------------------------------------------------
# Kesehatan
# ---------------------------------------------------------------------------
def test_status_kesehatan_dev_dan_produksi_salah(monkeypatch):
    from src.config import settings
    from src.services.kesehatan import status_kesehatan
    h = status_kesehatan(ip_info={})
    assert h["sehat"] is True and h["periksa"]["Basis data"][0] is True
    monkeypatch.setattr(settings, "APP_ENV", "production")
    h = status_kesehatan(ip_info={})
    assert h["sehat"] is False and h["periksa"]["Konfigurasi"][0] is False


def test_halaman_kesehatan_tanpa_rahasia(tmp_path):
    pytest.importorskip("streamlit.testing.v1")
    skrip = tmp_path / "ui.py"
    skrip.write_text(
        "import os, sys\nsys.path.insert(0, os.environ['ROOT'])\n"
        "from streamlit.testing.v1 import AppTest\n"
        "at = AppTest.from_file(os.path.join(os.environ['ROOT'], 'app.py'), default_timeout=60)\n"
        "at.query_params['page'] = 'kesehatan'\nat.run()\n"
        "print('EXC=' + str(len(at.exception)))\n"
        "print('TEKS=' + ' | '.join(m.value for m in at.markdown))\n"
    )
    env = {**os.environ, "ROOT": str(ROOT), "APP_ENV": "development", "APP_ENV_FILE": "",
           "DATABASE_URL": f"sqlite:///{tmp_path}/k.db", "UPLOAD_DIR": str(tmp_path / "up"),
           "EMAIL_SMTP_PASS": "RAHASIA-JANGAN-TAMPIL", "APP_SECRET_KEY": "kunci-uji-" + "x" * 40}
    r = subprocess.run([sys.executable, str(skrip)], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr[-1500:]
    assert "EXC=0" in r.stdout and "Basis data" in r.stdout and "Penyimpanan unggahan" in r.stdout
    assert "RAHASIA-JANGAN-TAMPIL" not in r.stdout and "kunci-uji-" not in r.stdout and "sqlite" not in r.stdout
