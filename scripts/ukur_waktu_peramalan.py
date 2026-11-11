"""Ukur waktu forecast_donations untuk beberapa panjang data (detik).

Contoh: python scripts/ukur_waktu_peramalan.py --bulan 36 120 --ulang 3
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src import forecasting as fc  # noqa: E402


def deret(n: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    nilai = (2e8 + 1e6 * t) * (1 + 0.4 * np.sin(2 * np.pi * t / 12)) * rng.lognormal(0, 0.25, n)
    periode = pd.period_range("2016-01" if n <= 180 else "2000-01", periods=n, freq="M")
    return pd.DataFrame({"periode_str": periode.astype(str), "total_dana": nilai})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bulan", type=int, nargs="+", default=[36, 120])
    ap.add_argument("--ulang", type=int, default=3)
    args = ap.parse_args()
    for n in args.bulan:
        data = deret(n)
        waktu = []
        for _ in range(args.ulang):
            mulai = time.perf_counter()
            _, meta = fc.forecast_donations(data)
            waktu.append(time.perf_counter() - mulai)
        hw = next(b for b in meta["perbandingan"] if b["kode"] == "holt_winters")
        print(f"{n:4d} bulan: median {np.median(waktu):.2f} s (min {min(waktu):.2f}, maks {max(waktu):.2f}) | "
              f"terpilih: {meta['metode']} | HW jendela {hw['n_jendela']}, gagal {hw['n_gagal']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
