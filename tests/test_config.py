"""Tes validasi konfigurasi keamanan (APP_ENV / APP_SECRET_KEY)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.config import (
    DEFAULT_SECRET_KEY,
    ConfigError,
    Settings,
    validate_security_settings,
)

ROOT = Path(__file__).parent.parent


def test_development_boleh_kunci_bawaan():
    validate_security_settings("development", DEFAULT_SECRET_KEY)


def test_production_tolak_kunci_bawaan():
    with pytest.raises(ConfigError, match="bawaan"):
        validate_security_settings("production", DEFAULT_SECRET_KEY)


def test_production_tolak_kunci_pendek():
    with pytest.raises(ConfigError, match="minimal 32"):
        validate_security_settings("production", "pendek-sekali")


def test_production_tolak_kunci_kosong():
    with pytest.raises(ConfigError):
        validate_security_settings("production", "")


def test_production_terima_kunci_kuat():
    validate_security_settings("production", "x" * 20 + "AcakSekali1234567890")


def test_is_production_dipakai_validate():
    s = Settings()
    s.APP_ENV = "production"
    s.APP_SECRET_KEY = DEFAULT_SECRET_KEY
    assert s.is_production
    with pytest.raises(ConfigError):
        s.validate()


def _jalankan_validator(env_tambahan):
    env = {k: v for k, v in os.environ.items() if k not in ("APP_ENV", "APP_SECRET_KEY")}
    env.update(env_tambahan)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_config.py")],
        env=env, capture_output=True, text=True, cwd=str(ROOT),
    )


def test_startup_production_kunci_bawaan_ditolak():
    hasil = _jalankan_validator({"APP_ENV": "production"})
    assert hasil.returncode == 1
    assert "Startup dibatalkan" in hasil.stderr
    assert "Traceback" not in hasil.stderr


def test_startup_production_kunci_kuat_diterima():
    hasil = _jalankan_validator({"APP_ENV": "production", "APP_SECRET_KEY": "k" * 48})
    assert hasil.returncode == 0, hasil.stderr
