"""Gagal (exit 1) bila ada berkas data (Excel/CSV/ODS) yang TERLACAK git di luar folder yang diizinkan.

Repo ini publik: data donatur/mustahik asli maupun hasil anonimisasinya tidak boleh masuk git.
.gitignore mencegah penambahan biasa, tetapi tidak mencegah ``git add -f`` atau berkas yang sudah
terlanjur dilacak. Pemeriksaan ini dijalankan di job "keamanan" CI.

Yang diizinkan hanya contoh sintetis di data/sample/ dan template di data/template/ (langsung di
folder itu, bukan subfolder). Apa pun di data/private/ selalu dilarang.

Pemakaian:  python scripts/cek_berkas_data.py
"""
import subprocess  # nosec B404 - hanya memanggil `git ls-files` dengan argumen tetap
import sys
from pathlib import Path
from typing import Iterable, List

AKAR = Path(__file__).resolve().parent.parent
EKSTENSI_DATA = {".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".ods"}
FOLDER_DIIZINKAN = {"data/sample", "data/template"}
FOLDER_TERLARANG = "data/private/"


def pelanggaran(berkas: Iterable[str]) -> List[str]:
    """Daftar path (gaya git, pemisah '/') yang melanggar aturan."""
    salah = []
    for p in berkas:
        p = p.replace("\\", "/")
        if p.startswith(FOLDER_TERLARANG):
            salah.append(p)
            continue
        if Path(p).suffix.lower() not in EKSTENSI_DATA:
            continue
        if str(Path(p).parent).replace("\\", "/") not in FOLDER_DIIZINKAN:
            salah.append(p)
    return salah


def berkas_terlacak(akar: Path = AKAR) -> List[str]:
    keluar = subprocess.run(["git", "ls-files", "-z"], cwd=akar, check=True,  # nosec B603 B607
                            capture_output=True).stdout
    return [b.decode("utf-8", "surrogateescape") for b in keluar.split(b"\0") if b]


def main() -> int:
    salah = pelanggaran(berkas_terlacak())
    if salah:
        print("GAGAL: berkas data terlacak git di luar data/sample/ dan data/template/:")
        for p in salah:
            print(f"  - {p}")
        print("Repo ini publik. Hapus dari git (git rm --cached <berkas>) dan pastikan isinya tidak berisi "
              "data asli. Bila data asli sempat ter-push, anggap bocor: hapus dari riwayat dan beri tahu pemilik.")
        return 1
    print("OK: tidak ada berkas data terlacak di luar data/sample/ dan data/template/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
