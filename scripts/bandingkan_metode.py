"""Tampilkan tabel MAPE backtest per metode peramalan untuk data contoh sintetis.

Contoh:
    python scripts/bandingkan_metode.py
    python scripts/bandingkan_metode.py --transaksi 1500
    python scripts/bandingkan_metode.py --berkas data/sample/data_contoh.xlsx
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis import get_trend_analysis  # noqa: E402
from src.cleaning import clean_data  # noqa: E402
from src.forecasting import (  # noqa: E402
    forecast_donations, format_mape_lengkap, ringkasan_catatan_metode, ringkasan_koreksi_bias,
)
from src.sample_data import generate_sample_data  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transaksi", type=int, default=5000, help="jumlah transaksi penghimpunan (bawaan 5000)")
    ap.add_argument("--berkas", help="berkas Excel/CSV (mis. data/sample/data_contoh.xlsx) sebagai ganti data sintetis")
    args = ap.parse_args()

    if args.berkas:
        from src.pipeline import siapkan_data
        df = siapkan_data(Path(args.berkas).read_bytes(), Path(args.berkas).name)["df_himpun"]
        args.transaksi = f"{len(df)} (berkas {args.berkas})"
    else:
        df_h, _ = generate_sample_data(args.transaksi, 10)
        df, _, _ = clean_data(df_h)
    monthly = get_trend_analysis(df)["monthly"]
    _, meta = forecast_donations(monthly)

    print(f"Data contoh: {args.transaksi} transaksi, {meta['n_bulan']} bulan, horizon uji {meta['bulan_uji']} bulan")
    print(f"{'Metode':60s} {'Rata2':>8s} {'Median':>8s} {'Terburuk':>9s} {'SD':>7s} {'Bersama':>8s} {'Jendela':>7s} {'Gagal':>5s}  Status")
    for b in meta.get("perbandingan", []):
        f = lambda v: "-" if v is None else f"{v:.2f}"
        tanda = "TERPILIH" if b["terpilih"] else b["status"]
        print(f"{b['metode']:60s} {f(b['mape']):>8s} {f(b['mape_median']):>8s} {f(b['mape_terburuk']):>9s} "
              f"{f(b['mape_std']):>7s} {f(b.get('mape_bersama')):>8s} {b['n_jendela']:>7} {b['n_gagal']:>5}  {tanda}")
    jb = meta.get("jendela_bersama") or []
    if jb:
        print(f"(Bersama = rata-rata pada {len(jb)} jendela yang diuji semua metode, bulan latih {jb[0]}-{jb[-1]}; "
              "dasar peringkat)")
    print(f"\nMetode terpilih: {meta['metode']} | rata-rata MAPE: {format_mape_lengkap(meta)}")
    print("Catatan metode:", ringkasan_catatan_metode(meta))
    bias = meta.get("bias_per_horizon") or []
    if bias:
        print(f"\nBias metode terpilih per langkah horizon (rasio aktual/prediksi backtest; >1 = meremehkan):")
        print(f"{'h':>3s} {'n':>3s} {'median':>8s} {'q10':>7s} {'q90':>7s}  arah")
        for b in bias:
            f = lambda v: "-" if v is None else f"{v:.3f}"
            print(f"{b['langkah']:>3} {b['n_rasio']:>3} {f(b['median_rasio']):>8s} {f(b['q10_rasio']):>7s} "
                  f"{f(b['q90_rasio']):>7s}  {b['arah']}")
    print("Koreksi bias:", ringkasan_koreksi_bias(meta))
    k = meta.get("konsistensi_selang") or {}
    print(f"Proyeksi titik di luar selang: {len(k.get('bulan_di_luar') or [])} dari {k.get('n_bulan_selang', 0)} bulan")
    for kunci in ("catatan_stabilitas", "peringatan_keandalan", "fallback_alasan", "selang_keterangan"):
        if meta.get(kunci):
            print(f"{kunci}: {meta[kunci]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
