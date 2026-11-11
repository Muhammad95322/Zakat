"""Jalankan pembersihan retensi (log audit lewat masa retensi, token/undangan kedaluwarsa).
Jadwalkan harian, mis. cron: 15 2 * * *  python scripts/bersihkan_retensi.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import get_db  # noqa: E402
from src.services.data_pribadi import bersihkan_retensi  # noqa: E402

if __name__ == "__main__":
    with get_db() as db:
        print("Dihapus:", bersihkan_retensi(db))
