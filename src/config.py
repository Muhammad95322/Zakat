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
# nosec B105: kunci khusus development; production dengan kunci ini ditolak validate_security_settings
DEFAULT_SECRET_KEY = "dev-secret-key-ganti-di-production-32chars"  # nosec B105
DEFAULT_EMAIL_FROM = "noreply@zakatinsight.id"
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

    # Email (SMTP). TLS selalu wajib: "starttls" (port 587/2525) atau "ssl" (port 465, TLS sejak awal).
    EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    EMAIL_SMTP_HOST: str = os.getenv("EMAIL_SMTP_HOST", "")
    EMAIL_SMTP_PORT: int = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    EMAIL_SMTP_USER: str = os.getenv("EMAIL_SMTP_USER", "")
    EMAIL_SMTP_PASS: str = os.getenv("EMAIL_SMTP_PASS", "")
    EMAIL_SMTP_TLS: str = os.getenv("EMAIL_SMTP_TLS", "").strip().lower()  # kosong = ssl bila port 465
    EMAIL_SMTP_TIMEOUT: float = float(os.getenv("EMAIL_SMTP_TIMEOUT", "15"))
    # CA tambahan (PEM) untuk relay SMTP internal/uji; kosong = CA sistem
    EMAIL_SMTP_CA_FILE: str = os.getenv("EMAIL_SMTP_CA_FILE", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", DEFAULT_EMAIL_FROM)

    # Storage unggahan: "lokal" (UPLOAD_DIR) atau "s3" (penyimpanan objek kompatibel S3; produksi Render)
    PENYIMPANAN: str = os.getenv("PENYIMPANAN", "lokal").strip().lower()
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")  # kosong = AWS; isi untuk R2/B2/MinIO
    S3_REGION: str = os.getenv("S3_REGION", "")
    S3_ACCESS_KEY_ID: str = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY: str = os.getenv("S3_SECRET_ACCESS_KEY", "")
    S3_AWALAN: str = os.getenv("S3_AWALAN", "unggahan")
    S3_SSE: str = os.getenv("S3_SSE", "")  # mis. AES256 (AWS); kosong bila penyedia mengenkripsi otomatis
    # Hari penyimpanan berkas unggahan sebelum dihapus otomatis (0 = sampai dihapus admin)
    RETENSI_UNGGAHAN_HARI: int = int(os.getenv("RETENSI_UNGGAHAN_HARI", "0"))
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    # Batas isi berkas (cegah bom zip / DoS memori)
    MAX_DEKOMPRESI_MB: int = int(os.getenv("MAX_DEKOMPRESI_MB", "300"))
    MAX_RASIO_KOMPRESI: int = int(os.getenv("MAX_RASIO_KOMPRESI", "100"))
    MAX_SHEET: int = int(os.getenv("MAX_SHEET", "20"))
    MAX_BARIS: int = int(os.getenv("MAX_BARIS", "500000"))

    # Security
    JWT_ACCESS_EXPIRE_HOURS: int = int(os.getenv("JWT_ACCESS_EXPIRE_HOURS", "8"))
    JWT_REFRESH_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "30"))
    LOGIN_MAX_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

    # IP klien di belakang proxy (lihat src/middleware/ip_klien.py). Kosong = tidak ada proxy dipercaya.
    # Render: "render" (jaringan privat + rentang IP Cloudflare).
    PROXY_TEPERCAYA: str = os.getenv("PROXY_TEPERCAYA", "")
    IP_HEADER_KLIEN: str = os.getenv("IP_HEADER_KLIEN", "")  # mis. CF-Connecting-IP; hanya dari proxy tepercaya
    # Hari penyimpanan IP & user agent di log audit sebelum dikosongkan (UU PDP: simpan seperlunya)
    IP_RETENSI_HARI: int = int(os.getenv("IP_RETENSI_HARI", "90"))
    # Batas per IP "jumlah/detik": login (percobaan GAGAL), daftar, reset, verifikasi (semua permintaan)
    BATAS_LOGIN_IP: str = os.getenv("BATAS_LOGIN_IP", "20/900")
    BATAS_DAFTAR_IP: str = os.getenv("BATAS_DAFTAR_IP", "5/3600")
    BATAS_RESET_IP: str = os.getenv("BATAS_RESET_IP", "5/3600")
    BATAS_VERIFIKASI_IP: str = os.getenv("BATAS_VERIFIKASI_IP", "5/3600")

    # Alamat publik aplikasi untuk tautan di email (verifikasi, reset, undangan)
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8501").rstrip("/")

    # Kontak penjualan yang ditampilkan di halaman langganan (kosong = belum dikonfigurasi)
    KONTAK_PENJUALAN: str = os.getenv("KONTAK_PENJUALAN", "")

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
