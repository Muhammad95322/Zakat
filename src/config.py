"""Konfigurasi aplikasi dari environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "dev-secret-key-ganti-di-production-32chars")
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
        return self.APP_ENV == "production"


settings = Settings()
