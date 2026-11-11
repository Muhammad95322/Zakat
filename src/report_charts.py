"""Render grafik statis (PNG) untuk laporan PDF menggunakan matplotlib (backend Agg)."""
import io
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import pandas as pd  # noqa: E402

# Palet terang (untuk cetak): seri 1 biru, seri 2 oranye; teks netral.
WARNA_SERI_1 = "#2a78d6"
WARNA_SERI_2 = "#eb6834"
TEKS_UTAMA = "#0b0b0b"
TEKS_SEKUNDER = "#52514e"
GRID = "#e4e3df"
DPI = 150


def _format_rp_singkat(v: float, _pos=None) -> str:
    a = abs(v)
    if a >= 1e12:
        s = f"{v / 1e12:.1f} T"
    elif a >= 1e9:
        s = f"{v / 1e9:.1f} M"
    elif a >= 1e6:
        s = f"{v / 1e6:.0f} jt"
    elif a >= 1e3:
        s = f"{v / 1e3:.0f} rb"
    else:
        s = f"{v:.0f}"
    return s.replace(".", ",")


def _gaya(ax, judul: str) -> None:
    ax.set_title(judul, loc="left", fontsize=11, color=TEKS_UTAMA, fontweight="bold", pad=10)
    for sisi in ("top", "right"):
        ax.spines[sisi].set_visible(False)
    for sisi in ("left", "bottom"):
        ax.spines[sisi].set_color(GRID)
    ax.tick_params(colors=TEKS_SEKUNDER, labelsize=8, length=0)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_format_rp_singkat))
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _ke_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _label_x_jarang(ax, labels, maks: int = 12) -> None:
    langkah = max(1, -(-len(labels) // maks))
    ax.set_xticks(range(0, len(labels), langkah))
    ax.set_xticklabels([labels[i] for i in range(0, len(labels), langkah)], rotation=45, ha="right")


def chart_tren_png(monthly_df: pd.DataFrame) -> Optional[bytes]:
    """Grafik garis penghimpunan bulanan (Rp)."""
    if monthly_df is None or monthly_df.empty:
        return None
    labels = monthly_df["periode_str"].astype(str).tolist()
    y = monthly_df["total_dana"].astype(float).to_numpy()
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.plot(range(len(y)), y, color=WARNA_SERI_1, linewidth=2, marker="o", markersize=3)
    i_max = int(y.argmax())
    ax.annotate(f"Puncak {labels[i_max]}\nRp {_format_rp_singkat(y[i_max])}", (i_max, y[i_max]),
                xytext=(6, -2), textcoords="offset points", fontsize=7, color=TEKS_SEKUNDER, va="top")
    _gaya(ax, "Tren penghimpunan bulanan (Rp)")
    _label_x_jarang(ax, labels)
    ax.set_ylim(bottom=0)
    return _ke_png(fig)


def chart_komposisi_png(comp_df: pd.DataFrame, kolom: str = "jenis_dana") -> Optional[bytes]:
    """Bar horizontal total dana per jenis dana, terurut terbesar di atas."""
    if comp_df is None or comp_df.empty:
        return None
    df = comp_df.sort_values("total", ascending=True)
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(df) + 1.0))
    posisi = list(range(len(df)))
    ax.barh(posisi, df["total"].to_numpy(dtype=float), color=WARNA_SERI_1, height=0.6)
    for i, (tot, pct) in enumerate(zip(df["total"], df["persentase"])):
        ax.text(tot, i, f"  Rp {_format_rp_singkat(tot)} ({pct:.1f}%)".replace(".", ","),
                va="center", fontsize=7, color=TEKS_SEKUNDER)
    _gaya(ax, "Komposisi penghimpunan per jenis dana")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_format_rp_singkat))
    ax.yaxis.set_major_formatter(mticker.NullFormatter())
    ax.set_yticks(posisi)
    ax.set_yticklabels(df[kolom].astype(str).tolist(), color=TEKS_UTAMA, fontsize=8)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_xlim(0, df["total"].max() * 1.3)
    return _ke_png(fig)


def chart_peramalan_png(monthly_df: pd.DataFrame, forecast_df: pd.DataFrame,
                        label_selang: Optional[str] = "Selang proyeksi") -> Optional[bytes]:
    """Historis + proyeksi, dengan pita selang bila tersedia (batas tidak NaN)."""
    if forecast_df is None or forecast_df.empty or monthly_df is None or monthly_df.empty:
        return None
    hist_labels = monthly_df["periode_str"].astype(str).tolist()
    fc_labels = forecast_df["periode"].astype(str).tolist()
    labels = hist_labels + fc_labels
    n = len(hist_labels)
    xf = list(range(n, n + len(fc_labels)))
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(range(n), monthly_df["total_dana"], color=WARNA_SERI_1, linewidth=2, label="Historis")
    if label_selang and forecast_df[["batas_bawah", "batas_atas"]].notna().all().all():
        ax.fill_between(xf, forecast_df["batas_bawah"], forecast_df["batas_atas"],
                        color=WARNA_SERI_2, alpha=0.18, linewidth=0, label=label_selang)
    ax.plot([n - 1] + xf, [monthly_df["total_dana"].iloc[-1]] + forecast_df["proyeksi"].tolist(),
            color=WARNA_SERI_2, linewidth=2, linestyle="--", label="Proyeksi")
    _gaya(ax, "Proyeksi penghimpunan (Rp)")
    _label_x_jarang(ax, labels, maks=14)
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), fontsize=7, frameon=False,
              labelcolor=TEKS_SEKUNDER, ncol=3)
    return _ke_png(fig)
