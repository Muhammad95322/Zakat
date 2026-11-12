"""Validasi konfigurasi sebelum server dijalankan (dipanggil Dockerfile & render.yaml sebelum `streamlit run`).

Keluar dengan kode 1 (pesan jelas, tanpa stack trace dan TANPA mencetak nilai rahasia) bila konfigurasi
production tidak aman/lengkap: kunci bawaan, database SQLite, APP_BASE_URL bukan https, email/SMTP belum
diisi, penyimpanan unggahan tidak permanen, dll. Peringatan dicetak tetapi tidak menghentikan start.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import ConfigError, settings  # noqa: E402


def main() -> int:
    try:
        settings.validate()
    except ConfigError as e:
        print(f"❌ Startup dibatalkan: {e}", file=sys.stderr)
        print("Lihat docs/PANDUAN_DEPLOY.md bagian 'Variabel lingkungan'.", file=sys.stderr)
        return 1
    if settings.is_production:
        for w in settings.periksa_produksi()[1]:
            print(f"⚠️  {w}", file=sys.stderr)
    print(f"✅ Konfigurasi valid (APP_ENV={settings.APP_ENV}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
