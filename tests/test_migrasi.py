"""Tes migrasi Alembic (audit S9): kosong -> terbaru, DB lama create_all -> terbaru, idempoten."""
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import src.models  # noqa: F401
from src.database import Base, jalankan_migrasi

AKAR = Path(__file__).parent.parent


def _cfg(conn):
    cfg = Config(str(AKAR / "alembic.ini"))
    cfg.set_main_option("script_location", str(AKAR / "migrasi"))
    cfg.attributes["connection"] = conn
    return cfg


def _cfg_skrip(stdout=None):
    cfg = Config(str(AKAR / "alembic.ini"), stdout=stdout) if stdout is not None else Config(str(AKAR / "alembic.ini"))
    cfg.set_main_option("script_location", str(AKAR / "migrasi"))
    return cfg


def _head() -> str:
    """Revisi head dibaca dari skrip migrasi (tidak mengunci angka versi di tes)."""
    return ScriptDirectory.from_config(_cfg_skrip()).get_current_head()


HEAD = _head()


def _versi(eng):
    with eng.connect() as c:
        return c.execute(text("select version_num from alembic_version")).scalar()


def _beda_skema(eng):
    with eng.connect() as c:
        beda = compare_metadata(MigrationContext.configure(c), Base.metadata)
    # abaikan perbedaan server_default (create_all tidak menulis server_default lama)
    return [d for d in beda if not (isinstance(d, tuple) and d and d[0] == "modify_default")]


@pytest.fixture
def eng(tmp_path):
    return create_engine(f"sqlite:///{tmp_path}/m.db")


def test_kosong_ke_terbaru_sama_dengan_model(eng):
    assert jalankan_migrasi(eng) == "skema dibuat dari migrasi"
    assert _versi(eng) == HEAD
    assert _beda_skema(eng) == []


def test_db_lama_create_all_dimigrasi_tanpa_kehilangan_data(eng):
    with eng.begin() as conn:
        command.upgrade(_cfg(conn), "0001")          # = skema create_all sebelum migrasi ada
        conn.execute(text("drop table alembic_version"))  # DB lama tidak punya tabel versi
        tid, uid = str(uuid.uuid4()), str(uuid.uuid4())
        conn.execute(text("insert into tenants (id,nama,slug,email_kontak,paket,is_active,created_at,updated_at) "
                          "values (:i,'L','l','a@b.id','basic',1,'2024-01-01','2024-01-01')"), {"i": tid})
        conn.execute(text("insert into users (id,tenant_id,email,password_hash,nama_lengkap,peran,is_active,"
                          "is_verified,failed_login_count,created_at,updated_at) values "
                          "(:u,:t,'x@y.id','h','N','admin',1,1,0,'2024-01-01','2024-01-01')"), {"u": uid, "t": tid})
    assert "sesi_versi" not in {c["name"] for c in inspect(eng).get_columns("users")}
    assert jalankan_migrasi(eng) == "DB lama di-stamp lalu dimigrasi"
    assert _versi(eng) == HEAD
    with eng.connect() as c:
        assert c.execute(text("select email, sesi_versi from users")).one() == ("x@y.id", 0)
    assert _beda_skema(eng) == []


def test_create_all_terbaru_tanpa_versi_di_stamp(eng):
    Base.metadata.create_all(eng)
    assert jalankan_migrasi(eng) == "DB lama di-stamp lalu dimigrasi"
    assert _versi(eng) == HEAD


def test_idempoten_dan_downgrade(eng):
    jalankan_migrasi(eng)
    assert jalankan_migrasi(eng) == "migrasi diperbarui" and _versi(eng) == HEAD
    with eng.begin() as conn:
        command.downgrade(_cfg(conn), "0001")
    assert "sesi_versi" not in {c["name"] for c in inspect(eng).get_columns("users")}
    jalankan_migrasi(eng)
    assert _versi(eng) == HEAD


def test_hanya_satu_kepala_migrasi():
    """Dua PR yang sama-sama menambah migrasi dari induk yang sama menghasilkan dua head; Alembic lalu
    menolak 'upgrade head'. Pastikan rantai migrasi linear."""
    import io
    skrip = ScriptDirectory.from_config(_cfg_skrip())
    assert skrip.get_heads() == [HEAD]
    keluaran = io.StringIO()
    command.heads(_cfg_skrip(stdout=keluaran))
    baris = [b for b in keluaran.getvalue().splitlines() if b.strip()]
    assert len(baris) == 1 and baris[0].startswith(HEAD), baris
    # setiap revisi selain akar punya tepat satu induk dan tidak ada cabang
    for rev in skrip.walk_revisions():
        assert not rev.branch_labels and not rev.is_merge_point
