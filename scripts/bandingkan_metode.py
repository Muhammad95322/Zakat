"""Tampilkan tabel MAPE backtest per metode peramalan untuk data contoh sintetis.

Contoh:
    python scripts/bandingkan_metode.py
    python scripts/bandingkan_metode.py --transaksi 1500
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis import get_trend_analysis  # noqa: E402
from src.cleaning import clean_data  # noqa: E402
from src.forecasting import forecast_donations, format_mape  # noqa: E402
from src.sample_data import generate_sample_data  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transaksi", type=int, default=5000, help="jumlah transaksi penghimpunan (bawaan 5000)")
    args = ap.parse_args()

    df_h, _ = generate_sample_data(args.transaksi, 10)
    df, _, _ = clean_data(df_h)
    monthly = get_trend_analysis(df)["monthly"]
    _, meta = forecast_donations(monthly)

    print(f"Data contoh: {args.transaksi} transaksi, {meta['n_bulan']} bulan")
    print(f"{'Metode':52s} {'Latih':>5s} {'Uji':>4s} {'MAPE':>10s}  Keterangan")
    for b in meta.get("perbandingan", []):
        mape = "-" if b["mape"] is None else f"{b['mape']:.2f}%"
        tanda = " <- terpilih" if b["terpilih"] else ""
        print(f"{b['metode']:52s} {b['bulan_latih']:>5} {b['bulan_uji']:>4} {mape:>10s}  {b['status']}{tanda}")
    print(f"\nMetode terpilih: {meta['metode']} | MAPE: {format_mape(meta)}")
    if meta.get("peringatan_keandalan"):
        print("PERINGATAN:", meta["peringatan_keandalan"])
    if meta.get("fallback_alasan"):
        print("PERINGATAN:", meta["fallback_alasan"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
