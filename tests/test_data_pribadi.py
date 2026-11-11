"""Tes penghapusan tuntas lembaga/pengguna dan retensi (audit F4)."""
import uuid
from datetime import timedelta

import pytest

from src.auth.hashing import hash_password
from src.config import settings
from src.models.analysis_session import AnalysisSession
from src.models.audit_log import AuditLog
from src.models.invitation import Invitation
from src.models.tenant import Tenant
from src.models.token_model import Token
from src.models.upload import Upload
from src.models.user import User
from src.services import data_pribadi as dp
from src.waktu import utc_now


def _lembaga(db, tmp_path, label):
    t = Tenant(id=str(uuid.uuid4()), nama=f"L{label}", slug=f"l{label}-{uuid.uuid4().hex[:5]}", email_kontak="a@b.id",
               paket="pro", is_active=True)
    db.add(t); db.flush()
    pengguna = []
    for peran in ("admin", "admin", "staf"):
        u = User(id=str(uuid.uuid4()), tenant_id=t.id, email=f"{peran}{uuid.uuid4().hex[:6]}@{label}.id",
                 password_hash=hash_password("Rahasia123"), nama_lengkap=f"{peran}{label}", peran=peran,
                 is_active=True, is_verified=True)
        db.add(u); pengguna.append(u)
    db.flush()
    folder = settings.UPLOAD_DIR / t.id
    folder.mkdir(parents=True, exist_ok=True)
    berkas = folder / "data.xlsx"; berkas.write_bytes(b"donatur")
    up = Upload(id=str(uuid.uuid4()), tenant_id=t.id, user_id=pengguna[2].id, nama_file_asli="data.xlsx",
                ukuran_bytes=7, jenis_file="xlsx", status="siap", storage_path=str(berkas))
    db.add(up); db.flush()
    db.add(AnalysisSession(id=str(uuid.uuid4()), upload_id=up.id, tenant_id=t.id, user_id=pengguna[2].id))
    db.add(Token(id=str(uuid.uuid4()), user_id=pengguna[2].id, jenis="refresh", token_hash="h", expires_at=utc_now()))
    db.add(Invitation(id=str(uuid.uuid4()), tenant_id=t.id, email="calon@x.id", peran="staf", token_hash="h2",
                      invited_by=pengguna[2].id, expires_at=utc_now() + timedelta(days=1)))
    db.add(AuditLog(tenant_id=t.id, user_id=pengguna[2].id, aksi="login", detail={"email": pengguna[2].email}))
    db.commit()
    return t, pengguna, berkas


@pytest.fixture
def unggah(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path / "uploads")
    return tmp_path


SUPER = {"id": None, "peran": "super_admin", "tenant_id": None}


class TestHapusLembaga:
    def test_tuntas_dan_lembaga_lain_utuh(self, db, unggah):
        ta, ua, fa = _lembaga(db, unggah, "a")
        tb, ub, fb = _lembaga(db, unggah, "b")
        ids_a = [u.id for u in ua]
        dp.hapus_lembaga(db, ta.id, SUPER, ta.slug)
        assert db.query(Tenant).filter(Tenant.id == ta.id).count() == 0
        assert db.query(User).filter(User.id.in_(ids_a)).count() == 0
        for model, kolom in ((Upload, Upload.tenant_id), (AnalysisSession, AnalysisSession.tenant_id),
                             (Invitation, Invitation.tenant_id), (AuditLog, AuditLog.tenant_id)):
            assert db.query(model).filter(kolom == ta.id).count() == 0
        assert db.query(Token).filter(Token.user_id.in_(ids_a)).count() == 0
        assert db.query(AuditLog).filter(AuditLog.user_id.in_(ids_a)).count() == 0
        assert not fa.exists() and not fa.parent.exists()
        assert fb.exists() and db.query(User).filter(User.tenant_id == tb.id).count() == 3  # lembaga B utuh

    def test_hanya_super_admin_dan_konfirmasi(self, db, unggah):
        ta, ua, _ = _lembaga(db, unggah, "c")
        with pytest.raises(dp.AksesDitolak):
            dp.hapus_lembaga(db, ta.id, {"id": ua[0].id, "peran": "admin", "tenant_id": ta.id}, ta.slug)
        with pytest.raises(ValueError, match="Konfirmasi"):
            dp.hapus_lembaga(db, ta.id, SUPER, "salah")
        assert db.query(Tenant).filter(Tenant.id == ta.id).count() == 1


class TestHapusPengguna:
    def test_hapus_dan_anonimkan(self, db, unggah):
        ta, ua, fa = _lembaga(db, unggah, "d")
        admin, staf = ua[0], ua[2]
        email = staf.email
        hasil = dp.hapus_pengguna(db, staf.id, {"id": admin.id, "peran": "admin", "tenant_id": ta.id})
        assert db.query(User).filter(User.id == staf.id).count() == 0
        assert db.query(Token).filter(Token.user_id == staf.id).count() == 0
        assert db.query(Invitation).filter(Invitation.invited_by == staf.id).count() == 0
        assert db.query(Upload).filter(Upload.tenant_id == ta.id).one().user_id == admin.id  # data lembaga tetap
        assert fa.exists()
        log = db.query(AuditLog).filter(AuditLog.tenant_id == ta.id, AuditLog.aksi == "login").one()
        assert log.user_id is None and email not in str(log.detail)
        assert hasil["log_dianonimkan"] == 1

    def test_izin(self, db, unggah):
        ta, ua, _ = _lembaga(db, unggah, "e")
        tb, ub, _ = _lembaga(db, unggah, "f")
        with pytest.raises(dp.AksesDitolak):
            dp.hapus_pengguna(db, ua[2].id, {"id": ub[0].id, "peran": "admin", "tenant_id": tb.id})  # lembaga lain
        with pytest.raises(dp.AksesDitolak):
            dp.hapus_pengguna(db, ua[0].id, {"id": ua[2].id, "peran": "staf", "tenant_id": ta.id})  # staf
        with pytest.raises(ValueError, match="sendiri"):
            dp.hapus_pengguna(db, ua[0].id, {"id": ua[0].id, "peran": "admin", "tenant_id": ta.id})
        dp.hapus_pengguna(db, ua[1].id, {"id": ua[0].id, "peran": "admin", "tenant_id": ta.id})
        with pytest.raises(ValueError, match="admin terakhir"):
            dp.hapus_pengguna(db, ua[0].id, SUPER)


def test_retensi(db, unggah):
    ta, ua, _ = _lembaga(db, unggah, "g")  # paket pro: retensi log 30 hari
    sekarang = utc_now()
    lama = AuditLog(tenant_id=ta.id, aksi="lama", detail={}, created_at=sekarang - timedelta(days=31))
    baru = AuditLog(tenant_id=ta.id, aksi="baru", detail={}, created_at=sekarang - timedelta(days=29))
    tok = Token(id=str(uuid.uuid4()), user_id=ua[0].id, jenis="reset_password", token_hash="x",
                expires_at=sekarang - timedelta(days=40))
    db.add_all([lama, baru, tok]); db.commit()
    tok_id = tok.id
    hasil = dp.bersihkan_retensi(db, sekarang)
    aksi = {a for (a,) in db.query(AuditLog.aksi).filter(AuditLog.tenant_id == ta.id)}
    assert "lama" not in aksi and "baru" in aksi
    assert db.query(Token).filter(Token.id == tok_id).count() == 0
    assert hasil["log_audit"] >= 1 and hasil["token"] >= 1
