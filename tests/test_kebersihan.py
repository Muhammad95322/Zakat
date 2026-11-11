"""Tes kebersihan kode: waktu UTC, pemilihan kolom teks, dan pemuatan .env."""
import os
import subprocess
import sys
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.cleaning import clean_data
from src.waktu import utc_now

ROOT = Path(__file__).parent.parent


def test_utc_now_naive_dan_utc():
    t = utc_now()
    assert t.tzinfo is None
    acuan = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs(acuan - t) < timedelta(seconds=5)


def test_utc_now_bisa_dibandingkan_dengan_nilai_db(db, admin_user):
    admin_user.locked_until = utc_now() + timedelta(minutes=15)
    db.commit()
    db.refresh(admin_user)
    assert admin_user.locked_until > utc_now()  # naive vs naive: tidak TypeError
    assert admin_user.created_at <= utc_now()


def test_tidak_ada_utcnow_di_src():
    for p in (ROOT / "src").rglob("*.py"):
        if p.name == "waktu.py":
            continue
        assert "utcnow" not in p.read_text(), p


def test_clean_data_tanpa_peringatan_deprecation():
    df = pd.DataFrame({
        "tanggal": ["2024-01-01", "2024-01-02"],
        "nama_muzaki": ["Budi", None],
        "kabupaten_kota": ["  Sleman ", ""],
        "jumlah": ["100.000", "200.000"],
    })
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        hasil, _, _ = clean_data(df)
    assert hasil["nama_muzaki"].tolist() == ["Budi", "Tidak Diketahui"]
    assert hasil["kabupaten_kota"].tolist() == ["Sleman", "Tidak Diketahui"]
    assert not np.issubdtype(hasil["jumlah"].dtype, np.object_)


def _baca_config(env_file, env_tambahan):
    env = {k: v for k, v in os.environ.items() if k not in ("APP_ENV", "APP_SECRET_KEY", "APP_VERSION")}
    env.update({"APP_ENV_FILE": str(env_file), **env_tambahan})
    kode = "from src.config import settings as s; print(s.APP_ENV, s.APP_VERSION, s.APP_SECRET_KEY)"
    out = subprocess.run([sys.executable, "-c", kode], env=env, capture_output=True, text=True, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def test_env_file_dimuat(tmp_path):
    f = tmp_path / ".env"
    f.write_text("APP_ENV=staging\nAPP_VERSION=9.9.9\nAPP_SECRET_KEY=dari-file\n")
    assert _baca_config(f, {}) == ["staging", "9.9.9", "dari-file"]


def test_env_file_tidak_menimpa_environment(tmp_path):
    f = tmp_path / ".env"
    f.write_text("APP_ENV=staging\nAPP_VERSION=9.9.9\nAPP_SECRET_KEY=dari-file\n")
    assert _baca_config(f, {"APP_ENV": "production", "APP_SECRET_KEY": "dari-env"}) == [
        "production", "9.9.9", "dari-env"]


def test_env_file_tidak_ada(tmp_path):
    env, versi, _ = _baca_config(tmp_path / "tidak-ada.env", {})
    assert env == "development"


def test_normalisasi_url_db():
    from src.database import normalisasi_url_db
    assert normalisasi_url_db("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalisasi_url_db("postgresql://u:p@db/x") == "postgresql+psycopg://u:p@db/x"
    assert normalisasi_url_db("postgresql+psycopg2://u:p@db/x") == "postgresql+psycopg2://u:p@db/x"
    assert normalisasi_url_db("sqlite:///zakat.db") == "sqlite:///zakat.db"


def test_url_postgres_bisa_dibuat_engine():
    pytest = __import__("pytest")
    pytest.importorskip("psycopg")
    from sqlalchemy import create_engine
    from src.database import normalisasi_url_db
    eng = create_engine(normalisasi_url_db("postgres://u:p@localhost:5432/x"))
    assert eng.dialect.driver == "psycopg"
