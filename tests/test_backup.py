"""Uji backup & pemulihan SQLite + unggahan (audit S9)."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

AKAR = Path(__file__).parent.parent


def _jalan(args, env):
    return subprocess.run([sys.executable, str(AKAR / "scripts" / "backup_db.py"), *args],
                          capture_output=True, text=True, env=env, cwd=str(AKAR))


def test_backup_dan_restore_sqlite(tmp_path):
    db = tmp_path / "app.db"
    up = tmp_path / "uploads"
    (up / "lembaga-a").mkdir(parents=True)
    (up / "lembaga-a" / "f.xlsx").write_bytes(b"asli")
    with sqlite3.connect(db) as c:
        c.execute("create table donatur (nama text)")
        c.execute("insert into donatur values ('Budi')")
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "UPLOAD_DIR": str(up), "APP_ENV_FILE": ""}
    hasil = _jalan(["backup", "--keluar", str(tmp_path / "bk")], env)
    assert hasil.returncode == 0, hasil.stderr
    arsip = next((tmp_path / "bk").glob("zakat-backup-*.tar.gz"))
    assert oct(arsip.stat().st_mode)[-3:] == "600"
    # rusak data setelah backup
    with sqlite3.connect(db) as c:
        c.execute("delete from donatur"); c.execute("insert into donatur values ('Salah')")
    (up / "lembaga-a" / "f.xlsx").write_bytes(b"rusak")
    (up / "sampah.txt").write_text("x")
    assert _jalan(["restore", str(arsip)], env).returncode == 2  # tanpa --ya ditolak
    hasil = _jalan(["restore", str(arsip), "--ya"], env)
    assert hasil.returncode == 0, hasil.stderr
    with sqlite3.connect(db) as c:
        assert c.execute("select nama from donatur").fetchall() == [("Budi",)]
    assert (up / "lembaga-a" / "f.xlsx").read_bytes() == b"asli"
    assert not (up / "sampah.txt").exists()
