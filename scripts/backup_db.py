"""Backup & pemulihan basis data dan berkas unggahan Zakat Insight.

SQLite  : salinan konsisten lewat API backup sqlite3 + arsip folder UPLOAD_DIR -> satu .tar.gz
Postgres: pg_dump format custom (-Fc) + arsip UPLOAD_DIR. Butuh klien pg_dump/pg_restore
          (di docker compose: lihat scripts/backup_postgres_compose.sh).

Pemakaian:
    python scripts/backup_db.py backup  [--keluar backups/]
    python scripts/backup_db.py restore <berkas.tar.gz> --ya

Restore MENIMPA basis data dan folder unggahan saat ini; wajib --ya.
"""
import argparse
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings  # noqa: E402
from src.database import normalisasi_url_db  # noqa: E402


def _jalur_sqlite(url: str) -> Path:
    return Path(url.replace("sqlite:///", "", 1))


def backup(keluar: Path) -> Path:
    keluar.mkdir(parents=True, exist_ok=True)
    cap = datetime.now().strftime("%Y%m%d-%H%M%S")
    url = normalisasi_url_db(settings.DATABASE_URL)
    tujuan = keluar / f"zakat-backup-{cap}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(tujuan, "w:gz") as tar:
        if url.startswith("sqlite"):
            salinan = Path(tmp) / "db.sqlite3"
            with sqlite3.connect(_jalur_sqlite(url)) as sumber, sqlite3.connect(salinan) as dst:
                sumber.backup(dst)  # konsisten walau aplikasi sedang berjalan
            tar.add(salinan, arcname="db.sqlite3")
        else:
            dump = Path(tmp) / "db.dump"
            url_pg = url.replace("postgresql+psycopg://", "postgresql://")
            subprocess.run(["pg_dump", "-Fc", "-f", str(dump), url_pg], check=True)
            tar.add(dump, arcname="db.dump")
        if settings.UPLOAD_DIR.exists():
            tar.add(settings.UPLOAD_DIR, arcname="uploads")
    os.chmod(tujuan, 0o600)  # berisi data donatur
    return tujuan


def restore(berkas: Path) -> None:
    url = normalisasi_url_db(settings.DATABASE_URL)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(berkas, "r:gz") as tar:
            tar.extractall(tmp, filter="data")  # filter 'data' menolak jalur berbahaya
        akar = Path(tmp)
        if url.startswith("sqlite"):
            if not (akar / "db.sqlite3").exists():
                raise SystemExit("Arsip tidak berisi db.sqlite3 (bukan backup SQLite).")
            with sqlite3.connect(akar / "db.sqlite3") as sumber, sqlite3.connect(_jalur_sqlite(url)) as dst:
                sumber.backup(dst)
        else:
            url_pg = url.replace("postgresql+psycopg://", "postgresql://")
            subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "-d", url_pg,
                            str(akar / "db.dump")], check=True)
        if (akar / "uploads").exists():
            if settings.UPLOAD_DIR.exists():
                shutil.rmtree(settings.UPLOAD_DIR)
            shutil.copytree(akar / "uploads", settings.UPLOAD_DIR)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="aksi", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--keluar", default="backups")
    r = sub.add_parser("restore")
    r.add_argument("berkas")
    r.add_argument("--ya", action="store_true", help="konfirmasi menimpa data saat ini")
    a = ap.parse_args()
    if a.aksi == "backup":
        print(f"Backup tersimpan: {backup(Path(a.keluar))}")
    else:
        if not a.ya:
            print("Restore menimpa basis data & unggahan saat ini. Ulangi dengan --ya.", file=sys.stderr)
            return 2
        restore(Path(a.berkas))
        print("Restore selesai.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
