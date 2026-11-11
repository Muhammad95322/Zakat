"""Konfigurasi aplikasi dari environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def muat_env_file() -> None:
    """Muat variabel dari file .env (python-dotenv) TANPA menimpa environment.

    Lokasi file: APP_ENV_FILE bila diset (string kosong = jangan muat apa pun),
    selain itu BASE_DIR/.env. Variabel yang sudah ada di environment selalu menang.
    """
    lokasi = os.environ.get("APP_ENV_FILE")
    if lokasi == "":
        return
    path = Path(lokasi) if lokasi else BASE_DIR / ".env"
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv opsional saat runtime
        return
    load_dotenv(path, override=False)


muat_env_file()

# Nilai kunci bawaan/contoh yang TIDAK boleh dipakai di production.
DEFAULT_SECRET_KEY = "dev-secret-key-ganti-di-production-32chars"
KNOWN_INSECURE_SECRET_KEYS = {
    DEFAULT_SECRET_KEY,
    "changeme",
    "secret",
    "ganti-saya",
}
MIN_SECRET_KEY_LENGTH = 32


class ConfigError(RuntimeError):
    """Konfigurasi tidak aman atau tidak valid untuk dijalankan."""


def validate_security_settings(app_env: str, secret_key: str) -> None:
    """Pastikan konfigurasi aman sebelum aplikasi berjalan di production.

    Raises:
        ConfigError: jika APP_ENV=production dan APP_SECRET_KEY masih nilai
            bawaan/contoh atau panjangnya kurang dari 32 karakter.
    """
    if (app_env or "").strip().lower() != "production":
        return
    key = secret_key or ""
    if key in KNOWN_INSECURE_SECRET_KEYS:
        raise ConfigError(
            "APP_ENV=production tetapi APP_SECRET_KEY masih memakai nilai bawaan/contoh. "
            "Set APP_SECRET_KEY ke string acak minimal 32 karakter, misalnya hasil dari: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    if len(key) < MIN_SECRET_KEY_LENGTH:
        raise ConfigError(
            f"APP_ENV=production tetapi APP_SECRET_KEY hanya {len(key)} karakter "
            f"(minimal {MIN_SECRET_KEY_LENGTH}). Gunakan kunci acak yang lebih panjang."
        )


class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", DEFAULT_SECRET_KEY)
    APP_VERSION: str = os.getenv("APP_VERSION", "2.0.0")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/zakat_insight.db")

    # Email
    EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    EMAIL_SMTP_HOST: str = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
    EMAIL_SMTP_PORT: int = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    EMAIL_SMTP_USER: str = os.getenv("EMAIL_SMTP_USER", "")
    EMAIL_SMTP_PASS: str = os.getenv("EMAIL_SMTP_PASS", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "noreply@zakatinsight.id")

    # Storage
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))

    # Security
    JWT_ACCESS_EXPIRE_HOURS: int = int(os.getenv("JWT_ACCESS_EXPIRE_HOURS", "8"))
    JWT_REFRESH_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30"))
    LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

    # Super Admin
    SUPERADMIN_EMAIL: str = os.getenv("SUPERADMIN_EMAIL", "admin@zakatinsight.id")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.strip().lower() == "production"

    def validate(self) -> None:
        """Validasi keamanan saat startup. Lihat ``validate_security_settings``."""
        if self.is_production:
            validate_security_settings(self.APP_ENV, self.APP_SECRET_KEY)


settings = Settings()
