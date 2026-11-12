"""Log audit peristiwa keamanan: IP & user agent tercatat, email & kata sandi tidak pernah."""
import inspect

from src.models.audit_log import AuditLog
from src.services import auth_service as asv
from src.services.audit_service import catat_log

IP, UA = "198.51.100.80", "Mozilla/5.0 Uji"


def _semua_log(db):
    return db.query(AuditLog).all()


def test_peristiwa_keamanan_mencatat_ip_ua_tanpa_email_sandi(db, admin_user, monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 2)
    asv.login(db, admin_user.email, "SalahSandi1", ip=IP, ua=UA)
    asv.login(db, admin_user.email, "SalahSandi2", ip=IP, ua=UA)          # mengunci akun
    admin_user.locked_until = None
    admin_user.failed_login_count = 0
    db.commit()
    asv.login(db, admin_user.email, "Admin123", ip=IP, ua=UA)
    asv.request_reset_password(db, admin_user.email, ip=IP, ua=UA)
    asv.register_tenant(db, "Lembaga IP", "Ani", "ani.ip@contoh.invalid", "SandiKuat123", ip=IP, ua=UA)
    asv.register_tenant(db, "Lembaga IP2", "X", admin_user.email, "SandiKuat123", ip=IP, ua=UA)
    aksi = {"account_locked", "login", "request_reset_password", "daftar_lembaga_ip", "daftar_dengan_email_terdaftar"}
    rows = [r for r in _semua_log(db) if r.aksi in aksi and r.ip_address == IP]
    assert {r.aksi for r in rows} == aksi
    assert all(r.user_agent == UA for r in rows)
    teks = " ".join(f"{r.detail} {r.ip_address} {r.user_agent}" for r in _semua_log(db))
    for rahasia in (admin_user.email, "ani.ip@contoh.invalid", "SalahSandi1", "Admin123", "SandiKuat123"):
        assert rahasia not in teks


def test_kunci_terlarang_dibuang_dari_detail(db):
    catat_log(db, None, "uji_detail", detail={"email": "x@y.id", "password": "p", "token": "t", "peran": "staf"})
    r = db.query(AuditLog).filter(AuditLog.aksi == "uji_detail").one()
    assert r.detail == {"peran": "staf"}
    assert r.ip_address is None and r.user_agent is None  # bukan peristiwa jaringan: tanpa nilai palsu


def test_halaman_login_mencatat_gagal_tanpa_email():
    import src.pages.pg_login as pl
    src = inspect.getsource(pl)
    assert 'catat_log(db, None, "login_gagal", ip=ip, ua=ua)' in src
    assert "batas_laju.periksa(db, \"login\", ip)" in src and "batas_laju.catat(db, \"login\", ip" in src
