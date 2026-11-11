"""Pemeriksaan kesehatan sistem (Healthcheck)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def check():
    print("=== Pemeriksaan Kesehatan Zakat Insight ===")
    checks = []
    
    # 1. Cek Database & User Count
    try:
        from src.database import get_db
        from src.models.user import User
        with get_db() as db:
            n_users = db.query(User).count()
        checks.append(("Basis Data (SQLite/PostgreSQL)", True, f"{n_users} pengguna terdaftar"))
    except Exception as e:
        checks.append(("Basis Data", False, str(e)))
        
    # 2. Cek Konfigurasi
    try:
        from src.config import settings
        checks.append(("Konfigurasi Lingkungan", True, f"ENV={settings.APP_ENV}"))
    except Exception as e:
        checks.append(("Konfigurasi Lingkungan", False, str(e)))
        
    # 3. Cek Folder Storage
    try:
        from src.config import settings
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        checks.append(("Storage Unggahan", True, str(settings.UPLOAD_DIR)))
    except Exception as e:
        checks.append(("Storage Unggahan", False, str(e)))
        
    semua_sehat = all(status for _, status, _ in checks)
    for name, status, detail in checks:
        simbol = "✅" if status else "❌"
        print(f"{simbol} {name}: {detail}")
        
    return 0 if semua_sehat else 1

if __name__ == "__main__":
    sys.exit(check())

