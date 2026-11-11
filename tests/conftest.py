"""Fixtures pengujian pytest untuk basis data in-memory dan mock data."""
import sys
import uuid
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup root path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Base
from src.models.tenant import Tenant
from src.models.user import User
from src.auth.hashing import hash_password

@pytest.fixture(scope="session")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    return eng

@pytest.fixture(scope="function")
def db(engine):
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def sample_tenant(db):
    t = Tenant(
        id=str(uuid.uuid4()),
        nama="Lazismu DIY Test",
        slug=f"lazismu-test-{uuid.uuid4().hex[:6]}",
        email_kontak="admin@lazismu-test.id",
        paket="pro",
        is_active=True
    )
    db.add(t)
    db.commit()
    return t

@pytest.fixture
def sample_tenant_2(db):
    t = Tenant(
        id=str(uuid.uuid4()),
        nama="BAZNAS Sleman Test",
        slug=f"baznas-test-{uuid.uuid4().hex[:6]}",
        email_kontak="admin@baznas-test.id",
        paket="basic",
        is_active=True
    )
    db.add(t)
    db.commit()
    return t

@pytest.fixture
def admin_user(db, sample_tenant):
    u = User(
        id=str(uuid.uuid4()),
        tenant_id=sample_tenant.id,
        email=f"admin-{uuid.uuid4().hex[:6]}@test.id",
        password_hash=hash_password("Admin123"),
        nama_lengkap="Admin Lazismu Test",
        peran="admin",
        is_active=True,
        is_verified=True
    )
    db.add(u)
    db.commit()
    return u

@pytest.fixture
def staf_user(db, sample_tenant):
    u = User(
        id=str(uuid.uuid4()),
        tenant_id=sample_tenant.id,
        email=f"staf-{uuid.uuid4().hex[:6]}@test.id",
        password_hash=hash_password("Staf1234"),
        nama_lengkap="Staf Lazismu Test",
        peran="staf",
        is_active=True,
        is_verified=True
    )
    db.add(u)
    db.commit()
    return u

@pytest.fixture
def pembaca_user(db, sample_tenant):
    u = User(
        id=str(uuid.uuid4()),
        tenant_id=sample_tenant.id,
        email=f"pembaca-{uuid.uuid4().hex[:6]}@test.id",
        password_hash=hash_password("Baca1234"),
        nama_lengkap="Pembaca Lazismu Test",
        peran="pembaca",
        is_active=True,
        is_verified=True
    )
    db.add(u)
    db.commit()
    return u

