"""Visualisasi interaktif Plotly dengan tema Zakat Insight dan format angka Indonesia."""
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from typing import Optional

import pandas as pd
import numpy as np

PINUS, KUNYIT, BIRU, TANAH, ZAITUN, UNGU, ABU = "#14705E", "#B7791F", "#3B6A8C", "#8A5A44", "#7A9E4E", "#8E6A9C", "#8B9692"
COLOR_PALETTE = [PINUS, KUNYIT, BIRU, TANAH, ZAITUN, UNGU, ABU]
_FONT = "Plus Jakarta Sans, Segoe UI, system-ui, sans-serif"

pio.templates["zakat"] = go.layout.Template(layout=dict(
    font=dict(family=_FONT, size=12.5, color="#1A2421"),
    colorway=COLOR_PALETTE,
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    title=dict(font=dict(size=15, color="#1A2421"), x=0, xanchor="left", y=0.97),
    xaxis=dict(gridcolor="rgba(0,0,0,0)", linecolor="#C9D0CC", ticks="outside", tickcolor="#C9D0CC",
               zeroline=False, title=dict(text="")),
    yaxis=dict(gridcolor="#E3E7E3", zeroline=False, linecolor="rgba(0,0,0,0)", title=dict(text="")),
    legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor="#12332E", font=dict(family=_FONT, color="#F2F7F4", size=12.5), bordercolor="#12332E"),
    separators=",.",  # desimal koma, ribuan titik
    margin=dict(l=8, r=8, t=56, b=16),
))


def _langkah_bagus(maks: float) -> float:
    kasar = maks / 5
    pangkat = 10 ** np.floor(np.log10(kasar)) if kasar > 0 else 1
    for k in (1, 2, 2.5, 5, 10):
        if k * pangkat >= kasar:
            return k * pangkat
    return 10 * pangkat


def sumbu_rupiah(fig: go.Figure, maks: float, sumbu: str = "y") -> go.Figure:
    """Label sumbu uang dengan singkatan Indonesia (rb / jt / M / T), konsisten dengan angka KPI."""
    from src.utils import format_rupiah
    if not maks or maks <= 0 or not np.isfinite(maks):
        return fig
    langkah = _langkah_bagus(float(maks))
    nilai = [langkah * i for i in range(int(np.ceil(maks / langkah)) + 1)]
    teks = ["0" if v == 0 else format_rupiah(v, singkat=True).replace("Rp ", "") for v in nilai]
    (fig.update_yaxes if sumbu == "y" else fig.update_xaxes)(tickvals=nilai, ticktext=teks)
    return fig



def chart_trend_bulanan(monthly_df: pd.DataFrame) -> go.Figure:
    """Grafik garis tren penerimaan bulanan."""
    fig = go.Figure()
    if monthly_df.empty:
        return fig
        
    fig.add_trace(go.Scatter(
        x=monthly_df["periode_str"],
        y=monthly_df["total_dana"],
        mode="lines+markers",
        line=dict(color=PINUS, width=2.5),
        marker=dict(size=5, color=PINUS),
        name="Penghimpunan",
        fill="tozeroy",
        fillcolor="rgba(20, 112, 94, 0.08)",
        hovertemplate="Rp %{y:,.0f}<extra></extra>",
    ))
    
    fig.update_layout(
        title="Penghimpunan dana per bulan (rupiah)",
        template="zakat",
        hovermode="x unified",
        showlegend=False,
    )
    sumbu_rupiah(fig, float(monthly_df["total_dana"].max()))
    return fig


def chart_komposisi_donut(df_comp: pd.DataFrame, col_name: str, title: str) -> go.Figure:
    """Grafik donut untuk komposisi jenis dana atau kanal."""
    if df_comp.empty:
        return go.Figure()
        
    fig = px.pie(
        df_comp,
        names=col_name,
        values="total",
        title=title,
        hole=0.45,
        color_discrete_sequence=COLOR_PALETTE
    )
    fig.update_traces(textposition="inside", textinfo="percent", textfont=dict(color="#fff", size=12),
                      marker=dict(line=dict(color="#F5F6F3", width=2)),
                      hovertemplate="%{label}<br>Rp %{value:,.0f} (%{percent})<extra></extra>")
    fig.update_layout(template="zakat", height=340, uniformtext=dict(minsize=11, mode="hide"),
                      legend=dict(orientation="v", yanchor="middle", y=0.5, x=1.02), margin=dict(l=8, r=8, t=48, b=8))
    return fig


def chart_bar_wilayah(df_wilayah: pd.DataFrame) -> go.Figure:
    """Grafik batang horizontal peringkat wilayah donasi."""
    if df_wilayah.empty:
        return go.Figure()
        
    df_sorted = df_wilayah.sort_values(by="total", ascending=True)
    fig = px.bar(
        df_sorted,
        x="total",
        y="kabupaten_kota",
        orientation="h",
        title="Penghimpunan per wilayah (rupiah)",
    )
    fig.update_traces(marker_color=PINUS, hovertemplate="%{y}<br>Rp %{x:,.0f}<extra></extra>")
    fig.update_layout(template="zakat", xaxis=dict(gridcolor="#E3E7E3"), yaxis=dict(gridcolor="rgba(0,0,0,0)"))
    sumbu_rupiah(fig, float(df_sorted["total"].max()), "x")
    return fig


def chart_lorenz(lorenz_x: list, lorenz_y: list, gini_val: float) -> go.Figure:
    """Kurva Lorenz untuk melihat ketimpangan/konsentrasi donasi."""
    fig = go.Figure()
    
    # Garis kesetaraan sempurna (45 derajat)
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1],
        mode="lines",
        line=dict(dash="dash", color="#98A39E", width=1.5),
        name="Pemerataan sempurna"
    ))
    
    # Kurva Lorenz aktual
    fig.add_trace(go.Scatter(
        x=lorenz_x, y=lorenz_y,
        mode="lines",
        line=dict(color=PINUS, width=2.5),
        name=f"Kurva Lorenz (Gini {gini_val})"
    ))
    
    fig.update_layout(
        title=f"Konsentrasi donasi (Gini {gini_val})",
        xaxis=dict(title=dict(text="Porsi kumulatif muzaki (0 sampai 1)")),
        yaxis=dict(title=dict(text="Porsi kumulatif dana (0 sampai 1)")),
        template="zakat",
    )
    return fig


def chart_forecasting(monthly_df: pd.DataFrame, forecast_df: pd.DataFrame,
                      label_selang: Optional[str] = "Selang proyeksi", terkoreksi: bool = False) -> go.Figure:
    """Grafik historis + proyeksi peramalan ke depan, dengan selang bila tersedia."""
    fig = go.Figure()
    
    if not monthly_df.empty:
        fig.add_trace(go.Scatter(
            x=monthly_df["periode_str"],
            y=monthly_df["total_dana"],
            mode="lines+markers",
            line=dict(color=PINUS, width=2.5),
            marker=dict(size=4, color=PINUS),
            name="Data aktual"
        ))
        
    ada = (forecast_df[["batas_bawah", "batas_atas"]].notna().all(axis=1).to_numpy()
           if not forecast_df.empty else np.array([], dtype=bool))
    # Segmen bulan bersambung yang punya selang; bulan tanpa selang tidak diberi pita
    segmen, mulai = [], None
    for i, v in enumerate(ada):
        if v and mulai is None:
            mulai = i
        if mulai is not None and (not v or i == len(ada) - 1):
            segmen.append((mulai, i + 1 if v else i))
            mulai = None
    for nomor, (a, b) in enumerate(segmen if label_selang else []):
        bagian = forecast_df.iloc[a:b]
        # Upper bound
        fig.add_trace(go.Scatter(
            x=bagian["periode"],
            y=bagian["batas_atas"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip"
        ))
        # Lower bound + fill
        fig.add_trace(go.Scatter(
            x=bagian["periode"],
            y=bagian["batas_bawah"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(183, 121, 31, 0.14)",
            name=label_selang,
            legendgroup="selang",
            showlegend=nomor == 0,
        ))
    if not forecast_df.empty:
        # Proyeksi line
        fig.add_trace(go.Scatter(
            x=forecast_df["periode"],
            y=forecast_df["proyeksi"],
            mode="lines+markers",
            line=dict(color=KUNYIT, width=2.5, dash="dot"),
            marker=dict(size=5, color=KUNYIT),
            name="Proyeksi (terkoreksi bias)" if terkoreksi else "Proyeksi"
        ))
        if terkoreksi and "proyeksi_tanpa_koreksi" in forecast_df:
            fig.add_trace(go.Scatter(
                x=forecast_df["periode"],
                y=forecast_df["proyeksi_tanpa_koreksi"],
                mode="lines",
                line=dict(color="#98A39E", width=1, dash="dot"),
                name="Sebelum koreksi bias"
            ))
        
    fig.update_layout(
        title="Aktual dan proyeksi penerimaan (rupiah)",
        template="zakat",
        hovermode="x unified",
    )
    atas = [float(monthly_df["total_dana"].max())] if not monthly_df.empty else []
    if not forecast_df.empty:
        for kol in ("proyeksi", "batas_atas"):
            if kol in forecast_df and forecast_df[kol].notna().any():
                atas.append(float(forecast_df[kol].max()))
    if atas:
        sumbu_rupiah(fig, max(atas))
    return fig

