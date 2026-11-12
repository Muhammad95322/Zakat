"""Pemeriksaan kesehatan (Docker HEALTHCHECK / operator). Kode keluar 0 = sehat, 1 = ada yang gagal.

Tidak mencetak nilai rahasia; galat hanya berupa jenis (mis. OperationalError).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def check() -> int:
    from src.services.kesehatan import status_kesehatan
    hasil = status_kesehatan(ip_info={})
    print("=== Pemeriksaan Kesehatan Zakat Insight ===")
    for nama, (ok, ket) in hasil["periksa"].items():
        print(f"{ {True: '✅', False: '❌', None: '➖'}[ok]} {nama}: {ket}")
    return 0 if hasil["sehat"] else 1


if __name__ == "__main__":
    sys.exit(check())
