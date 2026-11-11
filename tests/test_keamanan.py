"""Tes regresi temuan audit keamanan (docs/AUDIT_KEAMANAN.md)."""
import contextlib
import io

import pytest

from src.config import settings
from src.models.token_model import Token
from src.services import auth_service as asv


def _minta_reset(db, user):
    """Minta reset dan kembalikan (keluaran stdout, token mentah dari tautan)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        asv.request_reset_password(db, user.email)
    keluaran = buf.getvalue()
    mentah = keluaran.split("token=")[1].split('"')[0] if "token=" in keluaran else None
    return keluaran, mentah


class TestT1TokenTidakDisimpanMentah:
    def test_token_disimpan_sebagai_sha256(self, db, admin_user):
        _, mentah = _minta_reset(db, admin_user)
        tok = db.query(Token).filter(Token.user_id == admin_user.id, Token.jenis == "reset_password").first()
        assert mentah and tok.token_hash == asv.hash_token(mentah)
        assert tok.token_hash != mentah and len(tok.token_hash) == 64

    def test_nilai_kolom_db_tidak_bisa_dipakai_untuk_reset(self, db, admin_user):
        _minta_reset(db, admin_user)
        tok = db.query(Token).filter(Token.user_id == admin_user.id, Token.jenis == "reset_password").first()
        assert asv.reset_password(db, tok.token_hash, "Diambil999X") is False  # hash bocor tidak berguna

    def test_token_mentah_dari_tautan_tetap_berfungsi(self, db, admin_user):
        _, mentah = _minta_reset(db, admin_user)
        assert asv.reset_password(db, mentah, "SandiBaru123") is True
        assert asv.reset_password(db, mentah, "SandiLagi123") is False  # sekali pakai

    def test_reset_membatalkan_token_reset_lain(self, db, admin_user):
        _, t1 = _minta_reset(db, admin_user)
        _, t2 = _minta_reset(db, admin_user)
        assert asv.reset_password(db, t2, "SandiBaru123") is True
        assert asv.reset_password(db, t1, "SandiLain123") is False

    def test_production_tanpa_smtp_tidak_mencetak_token(self, db, admin_user, monkeypatch):
        monkeypatch.setattr(settings, "APP_ENV", "production")
        keluaran, mentah = _minta_reset(db, admin_user)
        assert mentah is None and "token=" not in keluaran
        assert admin_user.email not in keluaran
        assert "Tidak dikirim" in keluaran

    def test_tautan_memakai_app_base_url(self, db, admin_user, monkeypatch):
        monkeypatch.setattr(settings, "APP_BASE_URL", "https://zakat.contoh.id")
        keluaran, _ = _minta_reset(db, admin_user)
        assert "https://zakat.contoh.id/?page=reset_password&amp;token=" in keluaran  # di-escape untuk HTML
        assert "localhost" not in keluaran


RUMUS = ['=HYPERLINK("http://contoh.invalid","klik")', "+1+1", "-2+3", "@SUM(1)", "\t=1+1", "=cmd|' /C calc'!A0"]


class TestT2InjeksiRumus:
    def test_netralkan_nilai(self):
        from src.ekspor_aman import netralkan_nilai
        for v in RUMUS:
            assert netralkan_nilai(v) == "'" + v
        assert netralkan_nilai("Budi") == "Budi"
        assert netralkan_nilai("-") == "-"            # pengisi tunggal tidak berbahaya
        assert netralkan_nilai(-5000.0) == -5000.0    # angka tidak disentuh
        assert netralkan_nilai(None) is None

    def test_ekspor_excel_tanpa_sel_rumus(self):
        import io as _io
        import openpyxl
        import pandas as pd
        from src.report_excel import generate_excel_report
        from src.rfm import segment_rfm
        df = pd.DataFrame({
            "id_muzaki": [f"M{i}" for i in range(len(RUMUS))],
            "nama_muzaki": RUMUS,
            "tanggal": pd.date_range("2024-01-01", periods=len(RUMUS)),
            "jumlah": [100.0, -5.0, 300.0, 400.0, 500.0, 600.0],
        })
        rfm, _ = segment_rfm(df)
        x = generate_excel_report(df, {"total_dana": 1}, rfm, None, [{"aksi": "=1+1", "jumlah_baris": 1}])
        wb = openpyxl.load_workbook(_io.BytesIO(x))
        sel_rumus = [(ws.title, c.coordinate, c.value) for ws in wb for row in ws.iter_rows() for c in row
                     if c.data_type == "f"]
        assert sel_rumus == []
        nama = [c.value for c in wb["Data Bersih"]["B"][1:]]
        assert nama == ["'" + v for v in RUMUS]
        assert wb["Data Bersih"]["D3"].value == -5.0  # angka negatif tetap angka

    def test_sheet_bias_koreksi_tanpa_sel_rumus(self):
        """Teks berawalan '=' di sheet "Bias & Koreksi" tetap teks saat dibuka ulang."""
        import io as _io
        import openpyxl
        from src.analysis import get_trend_analysis
        from src.cleaning import clean_data
        from src.forecasting import forecast_donations
        from src.report_excel import generate_excel_report
        from src.sample_data import generate_sample_data
        h, _ = generate_sample_data(1500, 100)
        c, _, _ = clean_data(h)
        fdf, meta = forecast_donations(get_trend_analysis(c)["monthly"])
        assert meta.get("perbandingan") and meta.get("bias_per_horizon")
        for i, b in enumerate(meta["bias_per_horizon"]):
            b["arah"] = RUMUS[i % len(RUMUS)]
        x = generate_excel_report(c, {"total_dana": 1}, None, fdf, None, meta)
        wb = openpyxl.load_workbook(_io.BytesIO(x))
        ws = wb["Bias & Koreksi"]
        kol = [cell.value for cell in ws[1]].index("Arah bias")
        sel = [row[kol] for row in ws.iter_rows(min_row=2)]
        assert sel and all(s.data_type != "f" for s in sel)
        assert [s.value for s in sel] == ["'" + RUMUS[i % len(RUMUS)] for i in range(len(sel))]
        assert all(c.data_type != "f" for row in ws.iter_rows() for c in row)

    def test_csv_log_audit(self):
        import pandas as pd
        from src.ekspor_aman import ke_csv_aman
        csv = ke_csv_aman(pd.DataFrame({"Detail": RUMUS})).decode("utf-8")
        baris = csv.splitlines()[1:]
        assert all(b.lstrip('"').startswith("'") for b in baris)
        import inspect
        import src.pages.pg_audit as pa
        assert "ke_csv_aman(df_logs)" in inspect.getsource(pa)


# ---------------------------------------------------------------------------
# S1/S2/S3/R2/R4/F1: akun dan sesi
# ---------------------------------------------------------------------------
import os as _os
import subprocess as _sp
import sys as _sys
import time as _time
import uuid as _uuid
from contextlib import contextmanager
from pathlib import Path as _Path

from src.auth.hashing import hash_password, validate_password_strength, verify_password
from src.auth.jwt_handler import create_access_token
from src.models.audit_log import AuditLog
from src.models.invitation import Invitation
from src.models.tenant import Tenant
from src.models.user import User
from src.repositories import user_repo


@pytest.fixture
def db_global(db, monkeypatch):
    """Arahkan get_db() global ke sesi uji (dipakai validasi sesi)."""
    import src.database as dbm

    @contextmanager
    def _get_db():
        yield db
        db.commit()
    monkeypatch.setattr(dbm, "get_db", _get_db)
    return db


def _pengguna(db, tenant, peran="staf", **kw):
    u = User(id=str(_uuid.uuid4()), tenant_id=tenant.id if tenant else None, email=f"{peran}-{_uuid.uuid4().hex[:6]}@t.id",
             password_hash=hash_password("Rahasia123"), nama_lengkap=f"{peran} uji", peran=peran,
             is_active=True, is_verified=True, **kw)
    db.add(u); db.commit()
    return u


def _sesi(u):
    tok = create_access_token(u.id, u.tenant_id or "", u.peran, u.email, u.sesi_versi or 0)
    return {"id": u.id, "tenant_id": u.tenant_id, "peran": u.peran, "email": u.email, "access_token": tok}


def _oleh(u):
    return {"id": u.id, "tenant_id": u.tenant_id, "peran": u.peran}


class TestS1Sesi:
    def test_sesi_valid(self, db_global, sample_tenant):
        from src.auth.session import validasi_sesi_data
        u = _pengguna(db_global, sample_tenant, "staf")
        assert validasi_sesi_data(_sesi(u))["peran"] == "staf"

    def test_tanpa_token_atau_token_palsu_ditolak(self, db_global, sample_tenant):
        from src.auth.session import validasi_sesi_data
        u = _pengguna(db_global, sample_tenant)
        sesi = _sesi(u)
        assert validasi_sesi_data({**sesi, "access_token": None}) is None
        assert validasi_sesi_data({**sesi, "access_token": sesi["access_token"][:-3] + "abc"}) is None
        lain = _pengguna(db_global, sample_tenant)
        assert validasi_sesi_data({**sesi, "access_token": _sesi(lain)["access_token"]}) is None  # token orang lain

    def test_token_kedaluwarsa_ditolak(self, db_global, sample_tenant, monkeypatch):
        from src.auth.session import validasi_sesi_data
        u = _pengguna(db_global, sample_tenant)
        monkeypatch.setattr(settings, "JWT_ACCESS_EXPIRE_HOURS", -1)
        assert validasi_sesi_data(_sesi(u)) is None

    def test_nonaktif_mengakhiri_sesi(self, db_global, sample_tenant):
        from src.auth.session import validasi_sesi_data
        admin = _pengguna(db_global, sample_tenant, "admin")
        u = _pengguna(db_global, sample_tenant, "staf")
        sesi = _sesi(u)
        user_repo.deactivate_user(db_global, u.id, oleh=_oleh(admin))
        assert validasi_sesi_data(sesi) is None

    def test_reset_dan_ganti_sandi_mengakhiri_sesi_lama(self, db_global, sample_tenant):
        from src.auth.session import validasi_sesi_data
        u = _pengguna(db_global, sample_tenant)
        sesi = _sesi(u)
        assert asv.change_password(db_global, u.id, "Rahasia123", "SandiBaru123")
        assert validasi_sesi_data(sesi) is None
        baru = {**sesi, "access_token": asv.token_akses_baru(db_global, u.id)}
        assert validasi_sesi_data(baru) is not None  # sesi yang mengganti sandi tetap jalan
        _, mentah = _minta_reset(db_global, u)
        assert asv.reset_password(db_global, mentah, "SandiLagi123")
        assert validasi_sesi_data(baru) is None

    def test_lembaga_nonaktif(self, db_global, sample_tenant):
        from src.auth.session import validasi_sesi_data
        from src.services.tenant_service import nonaktifkan_tenant
        u = _pengguna(db_global, sample_tenant)
        sesi = _sesi(u)
        nonaktifkan_tenant(db_global, sample_tenant.id)
        assert validasi_sesi_data(sesi) is None
        assert asv.login(db_global, u.email, "Rahasia123") is None
        sample_tenant.is_active = True; db_global.commit()

    def test_peran_selalu_dari_db(self, db_global, sample_tenant):
        from src.auth.session import validasi_sesi_data
        admin = _pengguna(db_global, sample_tenant, "admin")
        u = _pengguna(db_global, sample_tenant, "staf")
        sesi = _sesi(u)
        user_repo.update_user_role(db_global, u.id, "pembaca", oleh=_oleh(admin))
        assert validasi_sesi_data(sesi)["peran"] == "pembaca"  # token masih bilang 'staf'

    def test_logout_mencabut_refresh_token(self, db, admin_user):
        from src.models.token_model import Token
        _, refresh = asv.login(db, admin_user.email, "Admin123")
        asv.logout(db, admin_user.id, refresh)
        tok = db.query(Token).filter(Token.token_hash == asv.hash_token(refresh)).first()
        assert tok.used_at is not None


class TestS2IzinLayanan:
    def test_staf_tidak_boleh_ubah_peran_atau_nonaktifkan(self, db, sample_tenant):
        staf = _pengguna(db, sample_tenant, "staf")
        target = _pengguna(db, sample_tenant, "pembaca")
        with pytest.raises(asv.AksesDitolak):
            user_repo.update_user_role(db, target.id, "admin", oleh=_oleh(staf))
        with pytest.raises(asv.AksesDitolak):
            user_repo.deactivate_user(db, target.id, oleh=_oleh(staf))
        with pytest.raises(asv.AksesDitolak):
            user_repo.update_user_role(db, staf.id, "admin", oleh=_oleh(staf))  # menaikkan diri sendiri

    def test_admin_lembaga_lain_ditolak(self, db, sample_tenant, sample_tenant_2):
        admin_b = _pengguna(db, sample_tenant_2, "admin")
        target_a = _pengguna(db, sample_tenant, "staf")
        with pytest.raises(asv.AksesDitolak):
            user_repo.update_user_role(db, target_a.id, "pembaca", oleh=_oleh(admin_b))
        with pytest.raises(asv.AksesDitolak):
            user_repo.deactivate_user(db, target_a.id, oleh=_oleh(admin_b))
        with pytest.raises(asv.AksesDitolak):
            asv.kirim_undangan(db, sample_tenant.id, "x@x.id", "admin", oleh=_oleh(admin_b))

    def test_admin_terakhir_dilindungi(self, db):
        t = Tenant(id=str(_uuid.uuid4()), nama="T", slug="t-" + _uuid.uuid4().hex[:6], email_kontak="t@t.id",
                   paket="pro", is_active=True)
        db.add(t); db.commit()
        admin = _pengguna(db, t, "admin")
        with pytest.raises(ValueError, match="admin terakhir"):
            user_repo.update_user_role(db, admin.id, "staf", oleh=_oleh(admin))
        with pytest.raises(ValueError, match="sendiri"):
            user_repo.deactivate_user(db, admin.id, oleh=_oleh(admin))

    def test_undangan_hash_terima_dan_batal(self, db, sample_tenant, sample_tenant_2):
        admin = _pengguna(db, sample_tenant, "admin")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            inv = asv.kirim_undangan(db, sample_tenant.id, f"baru-{_uuid.uuid4().hex[:5]}@t.id", "staf", oleh=_oleh(admin))
        mentah = buf.getvalue().split("token=")[1].split('"')[0]
        assert inv.token_hash == asv.hash_token(mentah) != mentah
        assert any(p["id"] == inv.id for p in asv.get_pending_invitations(db, sample_tenant.id))
        assert asv.get_pending_invitations(db, sample_tenant_2.id) == [] or all(
            p["id"] != inv.id for p in asv.get_pending_invitations(db, sample_tenant_2.id))
        assert asv.terima_undangan(db, inv.token_hash, "Nama", "Rahasia123")[0] is False  # hash DB tidak berguna
        ok, _ = asv.terima_undangan(db, mentah, "Anggota Baru", "Rahasia123")
        baru = db.query(User).filter(User.email == inv.email).first()
        assert ok and baru.tenant_id == sample_tenant.id and baru.peran == "staf"
        assert asv.terima_undangan(db, mentah, "Lagi", "Rahasia123")[0] is False  # sekali pakai
        admin_b = _pengguna(db, sample_tenant_2, "admin")
        with contextlib.redirect_stdout(io.StringIO()):
            inv2 = asv.kirim_undangan(db, sample_tenant.id, f"lain-{_uuid.uuid4().hex[:5]}@t.id", "pembaca", oleh=_oleh(admin))
        with pytest.raises(asv.AksesDitolak):
            asv.cancel_invitation(db, inv2.id, sample_tenant.id, oleh=_oleh(admin_b))
        assert asv.cancel_invitation(db, inv2.id, sample_tenant_2.id, oleh=_oleh(admin_b)) is False  # beda lembaga
        assert asv.cancel_invitation(db, inv2.id, sample_tenant.id, oleh=_oleh(admin)) is True

    def test_fungsi_halaman_ada(self):
        import importlib
        for modul, nama in [("src.services.auth_service", "register_tenant"), ("src.services.auth_service", "kirim_undangan"),
                            ("src.services.auth_service", "change_password"), ("src.repositories.user_repo", "update_user_role"),
                            ("src.repositories.user_repo", "deactivate_user"), ("src.services.auth_service", "get_pending_invitations"),
                            ("src.repositories.user_repo", "update_user_name"), ("src.auth.session", "update_session_user")]:
            assert hasattr(importlib.import_module(modul), nama), nama


class TestS3R2R4:
    def test_waktu_login_seragam(self, db, admin_user):
        def median(email):
            hasil = []
            for _ in range(3):
                s = _time.perf_counter(); asv.login(db, email, "SalahSekali1"); hasil.append(_time.perf_counter() - s)
            return sorted(hasil)[1]
        tidak_ada, ada = median("tidak-ada-sama-sekali@x.id"), median(admin_user.email)
        admin_user.failed_login_count = 0; admin_user.locked_until = None; db.commit()
        assert tidak_ada > 0.5 * ada  # sebelumnya 0,3 ms vs 300 ms

    def test_sandi_lebih_72_byte(self):
        valid, pesan = validate_password_strength("A1" + "x" * 80)
        assert valid is False and "72" in pesan
        assert verify_password("A1" + "x" * 80, hash_password("Rahasia123")) is False  # tanpa exception

    def test_log_login_tanpa_email(self, db, admin_user):
        asv.login(db, admin_user.email, "Admin123")
        log = db.query(AuditLog).filter(AuditLog.user_id == admin_user.id, AuditLog.aksi == "login").order_by(
            AuditLog.id.desc()).first()
        assert admin_user.email not in str(log.detail)


_SKRIP_UI_TIM = r'''
import os, sys, uuid
sys.path.insert(0, os.environ["ROOT"])
from src.database import init_db, get_db
from src.models.tenant import Tenant
from src.models.user import User
from src.auth.hashing import hash_password
from src.auth.jwt_handler import create_access_token
from streamlit.testing.v1 import AppTest
init_db()
with get_db() as db:
    t = Tenant(id=str(uuid.uuid4()), nama="Uji", slug="uji", email_kontak="a@b.id", paket="pro", is_active=True)
    db.add(t); db.flush()
    a = User(id=str(uuid.uuid4()), tenant_id=t.id, email="admin@u.id", password_hash=hash_password("Rahasia123"),
             nama_lengkap="Admin Uji", peran="admin", is_active=True, is_verified=True)
    s = User(id=str(uuid.uuid4()), tenant_id=t.id, email="staf@u.id", password_hash=hash_password("Rahasia123"),
             nama_lengkap="Staf Uji", peran="staf", is_active=True, is_verified=True)
    db.add_all([a, s]); db.commit(); aid, sid, tid = a.id, s.id, t.id
def jalan(uid, peran, page):
    at = AppTest.from_file(os.path.join(os.environ["ROOT"], "app.py"), default_timeout=60)
    at.session_state["page"] = page; at.session_state["is_logged_in"] = True
    at.session_state["current_user"] = {"id": uid, "tenant_id": tid, "peran": peran, "email": "x",
                                        "access_token": create_access_token(uid, tid, peran, "x", 0)}
    at.run(); return at
at = jalan(aid, "admin", "tim")
print("TIM_EXC=" + str(len(at.exception)) + " " + " | ".join(e.message for e in at.exception))
print("TIM_ANGGOTA=" + " ".join(m.value for m in at.markdown if "Uji" in m.value))
with get_db() as db:
    db.query(User).filter(User.id == sid).update({"is_active": False, "sesi_versi": 1}); db.commit()
at = jalan(sid, "staf", "dashboard")
print("SESI_NONAKTIF_HALAMAN=" + str(at.session_state["page"]))
'''


def test_ui_tim_tidak_crash_dan_sesi_nonaktif_keluar(tmp_path):
    pytest.importorskip("streamlit.testing.v1")
    skrip = tmp_path / "ui.py"
    skrip.write_text(_SKRIP_UI_TIM)
    root = _Path(__file__).parent.parent
    env = {**_os.environ, "ROOT": str(root), "APP_ENV": "development", "APP_ENV_FILE": "",
           "DATABASE_URL": f"sqlite:///{tmp_path}/ui.db", "UPLOAD_DIR": str(tmp_path / "up")}
    hasil = _sp.run([_sys.executable, str(skrip)], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert hasil.returncode == 0, hasil.stderr[-1500:]
    out = hasil.stdout
    assert "TIM_EXC=0" in out, out[-800:]
    assert "Admin Uji" in out and "Staf Uji" in out
    assert "SESI_NONAKTIF_HALAMAN=login" in out


# ---------------------------------------------------------------------------
# S4/S5/S6/S7/R5/R6: keluaran HTML, log SQL, batas berkas, konfigurasi
# ---------------------------------------------------------------------------
class TestS4EscapeHtml:
    def test_template_email_di_escape(self):
        from src.services.email_service import email_reset_password, email_undangan, email_verifikasi
        jahat = '<img src=x onerror="alert(1)">'
        for html_ in (email_verifikasi(jahat, "https://a/?x=1"), email_reset_password(jahat, "https://a/"),
                      email_undangan(jahat, jahat, "https://a/")):
            assert "<img" not in html_ and "&lt;img" in html_

    def test_dashboard_escape(self):
        import inspect
        import src.pages.pg_dashboard as pd_
        sumber = inspect.getsource(pd_)
        assert "escape(user.get" in sumber and "escape(tenant.nama" in sumber


def test_s5_sql_echo_mati_secara_bawaan():
    from src.database import engine
    assert engine.echo is False


class TestS6R6Berkas:
    @staticmethod
    def _xlsx(n_sheet=1, baris=10, makro=False):
        import zipfile
        import pandas as pd
        b = io.BytesIO()
        with pd.ExcelWriter(b, engine="openpyxl") as w:
            for i in range(n_sheet):
                pd.DataFrame({"tanggal": ["2024-01-01"] * baris, "jumlah": [1] * baris}).to_excel(
                    w, sheet_name=f"S{i}", index=False)
        data = b.getvalue()
        if makro:
            b2 = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(b2, "w") as zout:
                for item in zin.infolist():
                    zout.writestr(item, zin.read(item.filename))
                zout.writestr("xl/vbaProject.bin", b"\x00" * 100)
            data = b2.getvalue()
        return data

    def test_xlsx_wajar_lolos(self):
        from src.middleware.security import validasi_file_upload
        assert validasi_file_upload("a.xlsx", self._xlsx()) == (True, "")

    def test_makro_ditolak(self):
        from src.middleware.security import validasi_file_upload
        ok, pesan = validasi_file_upload("a.xlsx", self._xlsx(makro=True))
        assert ok is False and "makro" in pesan

    def test_terlalu_banyak_sheet(self, monkeypatch):
        from src.middleware.security import validasi_file_upload
        monkeypatch.setattr(settings, "MAX_SHEET", 3)
        ok, pesan = validasi_file_upload("a.xlsx", self._xlsx(n_sheet=5))
        assert ok is False and "sheet" in pesan

    def test_bom_zip_ditolak_sebelum_parsing(self):
        import zipfile
        from src.middleware.security import validasi_file_upload
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", "<x/>")
            z.writestr("xl/worksheets/sheet1.xml", b"0" * (50 * 1024 * 1024))  # 50 MB nol -> rasio ~1000x
        data = b.getvalue()
        assert len(data) < 1024 * 1024
        ok, pesan = validasi_file_upload("bom.xlsx", data)
        assert ok is False and "rasio" in pesan

    def test_batas_dekompresi_total(self, monkeypatch):
        from src.middleware.security import validasi_file_upload
        monkeypatch.setattr(settings, "MAX_DEKOMPRESI_MB", 0)
        ok, pesan = validasi_file_upload("a.xlsx", self._xlsx(baris=2000))
        assert ok is False and "dekompresi" in pesan

    def test_batas_baris(self, monkeypatch):
        from src.loader import DataFileError, load_file
        monkeypatch.setattr(settings, "MAX_BARIS", 100)
        with pytest.raises(DataFileError, match="lebih dari 100 baris"):
            load_file(self._xlsx(baris=150), "a.xlsx")
        with pytest.raises(DataFileError, match="lebih dari 100 baris"):
            load_file(("tanggal,jumlah\n" + "2024-01-01,1\n" * 150).encode(), "a.csv")
        assert len(load_file(self._xlsx(baris=100), "a.xlsx")["Penghimpunan"]) == 100


def test_s7_r5_konfigurasi_streamlit():
    import tomllib
    cfg = tomllib.loads((_Path(__file__).parent.parent / ".streamlit" / "config.toml").read_text())
    assert cfg["client"]["showErrorDetails"] == "none"
    assert cfg["browser"]["gatherUsageStats"] is False
    assert cfg["server"]["enableXsrfProtection"] is True
    assert cfg["server"]["maxUploadSize"] == settings.MAX_UPLOAD_SIZE_MB


# ---------------------------------------------------------------------------
# S8/F2/F3: deploy
# ---------------------------------------------------------------------------
def test_s8_dockerfile_non_root_dan_tanpa_rahasia():
    akar = _Path(__file__).parent.parent
    df = (akar / "Dockerfile").read_text()
    baris_user = [l for l in df.splitlines() if l.startswith("USER ")]
    assert baris_user and baris_user[-1].split()[1] not in ("root", "0")
    ignore = (akar / ".dockerignore").read_text().split()
    assert ".env" in ignore and "*.db" in ignore and "backups/" in ignore


def test_f3_langganan_berlabel_tanpa_kontak_palsu():
    import inspect
    import src.pages.pg_langganan as pl
    sumber = inspect.getsource(pl)
    assert "Belum ada pembayaran" in sumber
    assert "+62 812-3456-7890" not in sumber


def test_f2_compose_dan_render_mengatur_email_dan_base_url():
    # Tanpa PyYAML (bukan dependensi proyek): periksa entri sebagai teks
    akar = _Path(__file__).parent.parent
    compose = (akar / "docker-compose.yml").read_text()
    blok_app = compose.split("\n  db:")[0]
    assert "- APP_BASE_URL=" in blok_app and "- EMAIL_ENABLED=" in blok_app
    render = (akar / "render.yaml").read_text()
    assert "key: APP_BASE_URL" in render and "key: EMAIL_SMTP_PASS" in render
