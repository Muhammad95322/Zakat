"""Fixture frontend web: DB SQLite berkas sementara (endpoint sinkron FastAPI berjalan di thread lain,
jadi DB in-memory per-koneksi dari tests/conftest.py tidak bisa dipakai) dan penyimpanan unggahan
sementara. Semua data sintetis."""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import src.models  # noqa: E402,F401
from src.auth.hashing import hash_password  # noqa: E402
from src.config import settings  # noqa: E402
from src.database import Base  # noqa: E402
from src.middleware.rate_limiter import RateLimiter  # noqa: E402
from src.models.tenant import Tenant  # noqa: E402
from src.models.user import User  # noqa: E402
from web.main import ambil_db, app  # noqa: E402

SANDI = "SandiUji123"


@pytest.fixture
def web_db(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path}/web.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    Sesi = sessionmaker(bind=eng, expire_on_commit=False)
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path / "unggahan")
    monkeypatch.setattr(settings, "PENYIMPANAN", "lokal")
    RateLimiter()._attempts.clear()

    def _db():
        db = Sesi()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[ambil_db] = _db
    db = Sesi()
    yield db
    db.close()
    app.dependency_overrides.pop(ambil_db, None)
    RateLimiter()._attempts.clear()
    eng.dispose()


@pytest.fixture
def klien(web_db):
    return TestClient(app, base_url="http://testserver")


def buat_lembaga(db, nama="Lembaga Uji Web", paket="pro"):
    t = Tenant(id=str(uuid.uuid4()), nama=nama, slug=f"uji-{uuid.uuid4().hex[:8]}", email_kontak="x@contoh.invalid",
               paket=paket, is_active=True)
    db.add(t)
    db.commit()
    return t


def buat_pengguna(db, tenant, peran="admin", nama="Pengguna Uji", aktif=True):
    u = User(id=str(uuid.uuid4()), tenant_id=tenant.id if tenant else None,
             email=f"{peran}-{uuid.uuid4().hex[:8]}@contoh.invalid", password_hash=hash_password(SANDI),
             nama_lengkap=nama, peran=peran, is_active=aktif, is_verified=True)
    db.add(u)
    db.commit()
    return u


def csrf_dari(html: str) -> str:
    kunci = 'name="csrf" value="'
    i = html.index(kunci) + len(kunci)
    return html[i:html.index('"', i)]


def masuk(klien, email, sandi=SANDI):
    r = klien.get("/masuk")
    return klien.post("/masuk", data={"email": email, "sandi": sandi, "csrf": csrf_dari(r.text)},
                      follow_redirects=False)


@pytest.fixture
def lembaga_a(web_db):
    return buat_lembaga(web_db, "Lembaga A")


@pytest.fixture
def lembaga_b(web_db):
    return buat_lembaga(web_db, "Lembaga B")
