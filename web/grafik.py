"""Penyesuaian TAMPILAN figur dari ``src/charts.py`` untuk frontend web.

Figur dibuat oleh fungsi yang sudah ada (``chart_trend_bulanan``, ``chart_forecasting``); di sini hanya
tata letak dan gaya yang ditimpa: warna, huruf, label sumbu gaya Indonesia (rb/jt/M/T), teks tooltip,
titik bulan digeser ke tengah bulan, dan pita Ramadan dari ``src/kalender_hijriah.py``. Nilai data dan
jumlah jejak tidak diubah.
"""
import json
import math
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

import pandas as pd
import plotly.graph_objects as go

from src.charts import chart_forecasting, chart_trend_bulanan
from src.kalender_hijriah import PERKIRAAN_RAMADAN
from web.format import bulan_tahun, rupiah_singkat, singkat_tanpa_rp

TINTA = "#1A2130"
STEMPEL = "#3B3F9C"
KUNYIT = "#B37400"
GARIS = "#D3D8E0"
ABU = "#566070"
HURUF = "Plus Jakarta Sans, system-ui, sans-serif"

NAMA_JEJAK = {
    "Total Penghimpunan": "Terkumpul per bulan",
    "Historis Aktual": "Terkumpul (data)",
    "Proyeksi Prediksi": "Proyeksi",
    "Proyeksi (terkoreksi bias)": "Proyeksi (terkoreksi bias)",
    "Sebelum koreksi bias": "Proyeksi sebelum koreksi bias",
}


def _tengah_bulan(x: Iterable) -> List[str]:
    """'2024-03' -> '2024-03-15' agar titik bulanan duduk di tengah bulannya (sejajar pita Ramadan)."""
    hasil = []
    for v in x:
        s = str(v)
        hasil.append(f"{s[:7]}-15" if len(s) >= 7 else s)
    return hasil


def _langkah_rapi(maks: float, jumlah: int = 4) -> float:
    if maks <= 0:
        return 1.0
    kasar = maks / jumlah
    pangkat = 10 ** math.floor(math.log10(kasar))
    for k in (1, 2, 2.5, 5, 10):
        if kasar <= k * pangkat:
            return k * pangkat
    return 10 * pangkat


def sumbu_rupiah(maks: float) -> Dict:
    langkah = _langkah_rapi(maks)
    nilai = [langkah * i for i in range(0, int(maks // langkah) + 2)]
    return {"tickvals": nilai, "ticktext": [singkat_tanpa_rp(v) for v in nilai], "range": [0, nilai[-1]]}


def sumbu_bulan(awal: str, akhir: str) -> Dict:
    """Label bulan berbahasa Indonesia; jarak 3/6/12 bulan sesuai rentang."""
    a = pd.Period(str(awal)[:7], "M")
    b = pd.Period(str(akhir)[:7], "M")
    n = (b - a).n + 1
    langkah = 3 if n <= 24 else 6 if n <= 60 else 12
    vals, teks = [], []
    p = a
    while p <= b:
        if (p.month - 1) % langkah == 0:
            vals.append(f"{p.year:04d}-{p.month:02d}-15")
            teks.append(bulan_tahun(str(p)))
        p += 1
    return {"tickvals": vals, "ticktext": teks,
            "range": [f"{a.year:04d}-{a.month:02d}-01", (b.to_timestamp(how="end")).strftime("%Y-%m-%d")]}


def pita_ramadan(awal: str, akhir: str) -> List[Dict]:
    """Bentuk vrect untuk setiap Ramadan (perkiraan) yang beririsan dengan rentang grafik."""
    t0 = pd.Period(str(awal)[:7], "M").to_timestamp().date()
    t1 = pd.Period(str(akhir)[:7], "M").to_timestamp(how="end").date()
    bentuk = []
    for i, (mulai, syawal) in enumerate(PERKIRAAN_RAMADAN):
        selesai = syawal - timedelta(days=1)
        if selesai < t0 or mulai > t1:
            continue
        bentuk.append({
            "type": "rect", "xref": "x", "yref": "paper", "x0": mulai.isoformat(), "x1": syawal.isoformat(),
            "y0": 0, "y1": 1, "fillcolor": KUNYIT, "opacity": 0.13, "line": {"width": 0}, "layer": "below",
            "label": {"text": f"Ramadan {1436 + i} H", "textposition": "top center",
                      "font": {"size": 11, "color": "#7A4E00", "family": HURUF}},
        })
    return bentuk


def _tema(fig: go.Figure, tinggi: int) -> None:
    fig.update_layout(
        title=None, template=None, height=tinggi, separators=",.",
        font={"family": HURUF, "size": 13, "color": TINTA},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 8, "r": 8, "t": 28, "b": 40},
        hovermode="closest", hoverlabel={"bgcolor": "#FFFFFF", "bordercolor": GARIS,
                                         "font": {"family": HURUF, "size": 13, "color": TINTA}},
        legend={"orientation": "h", "x": 0, "y": -0.12, "xanchor": "left", "yanchor": "top",
                "font": {"size": 12, "color": ABU}},
        xaxis={"title": None, "showgrid": False, "linecolor": GARIS, "ticks": "outside", "tickcolor": GARIS,
               "type": "date", "fixedrange": True},
        yaxis={"title": None, "gridcolor": "#E6E9EE", "zeroline": False, "fixedrange": True,
               "side": "right", "ticklabelposition": "inside top", "tickfont": {"size": 11, "color": ABU}},
        dragmode=False,
    )


def figur_tren(monthly: pd.DataFrame) -> Optional[Dict]:
    """Grafik tren bulanan (chart_trend_bulanan) + pita Ramadan. None bila tidak ada data."""
    if monthly is None or monthly.empty:
        return None
    fig = chart_trend_bulanan(monthly)
    jejak = fig.data[0]
    teks = [f"<b>{bulan_tahun(p)}</b><br>{rupiah_singkat(v)} dari {int(n):,} transaksi".replace(",", ".")
            for p, v, n in zip(monthly["periode_str"], monthly["total_dana"], monthly["jumlah_transaksi"])]
    jejak.update(x=_tengah_bulan(jejak.x), name=NAMA_JEJAK.get(jejak.name, jejak.name),
                 line={"color": STEMPEL, "width": 2.5}, marker={"size": 5, "color": STEMPEL},
                 fillcolor="rgba(59,63,156,0.07)", customdata=teks, hovertemplate="%{customdata}<extra></extra>")
    _tema(fig, 340)
    awal, akhir = monthly["periode_str"].iloc[0], monthly["periode_str"].iloc[-1]
    fig.update_layout(xaxis=sumbu_bulan(awal, akhir), yaxis=sumbu_rupiah(float(monthly["total_dana"].max())),
                      shapes=pita_ramadan(awal, akhir), showlegend=False)
    return json.loads(fig.to_json())


def figur_proyeksi(monthly: pd.DataFrame, forecast_df: pd.DataFrame, meta: Dict,
                   bulan_konteks: int = 24) -> Optional[Dict]:
    """Grafik proyeksi (chart_forecasting) dengan 24 bulan data terakhir sebagai konteks."""
    if forecast_df is None or forecast_df.empty:
        return None
    konteks = monthly.tail(bulan_konteks) if monthly is not None else pd.DataFrame()
    terkoreksi = bool((meta.get("koreksi_bias") or {}).get("dipakai"))
    fig = chart_forecasting(konteks, forecast_df, meta.get("selang_label"), terkoreksi)
    bawah = dict(zip(forecast_df["periode"].astype(str), forecast_df["batas_bawah"]))
    atas = dict(zip(forecast_df["periode"].astype(str), forecast_df["batas_atas"]))
    maks = 0.0
    for jejak in fig.data:
        x_asli = [str(v) for v in jejak.x]
        y = list(jejak.y)
        maks = max([maks] + [float(v) for v in y if v is not None and not pd.isna(v)])
        nama = NAMA_JEJAK.get(jejak.name, jejak.name)
        jejak.update(x=_tengah_bulan(x_asli), name=nama)
        if jejak.hoverinfo == "skip" or (jejak.fill == "tonexty"):
            jejak.update(hoverinfo="skip", fillcolor="rgba(179,116,0,0.16)")
            continue
        if jejak.name == "Terkumpul (data)":
            jejak.update(line={"color": STEMPEL, "width": 2}, marker={"size": 4, "color": STEMPEL},
                         mode="lines+markers")
            teks = [f"<b>{bulan_tahun(p)}</b><br>Terkumpul {rupiah_singkat(v)}" for p, v in zip(x_asli, y)]
        elif nama.startswith("Proyeksi sebelum"):
            jejak.update(line={"color": ABU, "width": 1, "dash": "dot"})
            teks = [f"<b>{bulan_tahun(p)}</b><br>Sebelum koreksi bias {rupiah_singkat(v)}" for p, v in zip(x_asli, y)]
        else:
            jejak.update(line={"color": KUNYIT, "width": 2.5, "dash": "dash"}, marker={"size": 5, "color": KUNYIT})
            teks = []
            for p, v in zip(x_asli, y):
                t = f"<b>{bulan_tahun(p)}</b><br>Proyeksi {rupiah_singkat(v)}"
                if not pd.isna(bawah.get(p)) and not pd.isna(atas.get(p)):
                    t += f"<br>Rentang {rupiah_singkat(bawah[p])} sampai {rupiah_singkat(atas[p])}"
                teks.append(t)
        jejak.update(customdata=teks, hovertemplate="%{customdata}<extra></extra>")
    _tema(fig, 320)
    semua = ([str(v) for v in konteks["periode_str"]] if not konteks.empty else []) + \
        [str(v) for v in forecast_df["periode"]]
    awal, akhir = min(semua), max(semua)
    fig.update_layout(xaxis=sumbu_bulan(awal, akhir), yaxis=sumbu_rupiah(maks), shapes=pita_ramadan(awal, akhir),
                      showlegend=True)
    return json.loads(fig.to_json())


def ramadan_berikutnya(hari_ini: date) -> Optional[Dict]:
    """Ramadan berikutnya (atau yang sedang berjalan) dari tabel perkiraan, untuk layar masuk dan beranda."""
    for i, (mulai, syawal) in enumerate(PERKIRAAN_RAMADAN):
        if syawal > hari_ini:
            return {"mulai": mulai, "syawal": syawal, "tahun_h": 1436 + i,
                    "sedang": mulai <= hari_ini, "hari_lagi": (mulai - hari_ini).days}
    return None


def pita_dua_belas_bulan(hari_ini: date) -> List[Dict]:
    """Dua belas bulan mulai bulan ini; tiap bulan ditandai bila beririsan dengan Ramadan."""
    bulan = []
    p = pd.Period(hari_ini.strftime("%Y-%m"), "M")
    for k in range(12):
        q = p + k
        awal = q.to_timestamp().date()
        akhir = q.to_timestamp(how="end").date()
        ramadan = any(m <= akhir and (s - timedelta(days=1)) >= awal for m, s in PERKIRAAN_RAMADAN)
        bulan.append({"label": bulan_tahun(str(q)).split(" ")[0], "tahun": q.year, "ramadan": ramadan,
                      "awal_tahun": q.month == 1 or k == 0})
    return bulan
