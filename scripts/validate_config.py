"""Validasi konfigurasi sebelum server dijalankan.

Keluar dengan kode 1 (dan pesan jelas, tanpa stack trace) jika konfigurasi
tidak aman, misalnya APP_ENV=production dengan APP_SECRET_KEY bawaan.
Dipakai oleh Dockerfile dan render.yaml sebelum `streamlit run`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings, ConfigError  # noqa: E402


def main() -> int:
    try:
        settings.validate()
    except ConfigError as e:
        print(f"❌ Startup dibatalkan: {e}", file=sys.stderr)
        return 1
    print(f"✅ Konfigurasi valid (APP_ENV={settings.APP_ENV}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
