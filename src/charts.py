"""Modul pembuatan visualisasi interaktif Plotly dengan tema Hijau-Teal."""
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional

import pandas as pd
import numpy as np

COLOR_PALETTE = ["#0d9488", "#0f766e", "#14b8a6", "#2dd4bf", "#5eead4", "#99f6e4", "#ccfbf1"]

def chart_trend_bulanan(monthly_df: pd.DataFrame) -> go.Figure:
    """Grafik garis tren penerimaan bulanan."""
    fig = go.Figure()
    if monthly_df.empty:
        return fig
        
    fig.add_trace(go.Scatter(
        x=monthly_df["periode_str"],
        y=monthly_df["total_dana"],
        mode="lines+markers",
        line=dict(color="#0d9488", width=3),
        marker=dict(size=7, color="#0f766e"),
        name="Total Penghimpunan",
        fill="tozeroy",
        fillcolor="rgba(13, 148, 136, 0.15)"
    ))
    
    fig.update_layout(
        title="Tren Penghimpunan Dana per Bulan",
        xaxis_title="Periode",
        yaxis_title="Nominal (Rp)",
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=50, b=20)
    )
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
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=20, r=20, t=50, b=20)
    )
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
        title="Peringkat Wilayah Penghimpunan",
        color="total",
        color_continuous_scale=["#5eead4", "#0d9488"]
    )
    fig.update_layout(
        xaxis_title="Total Donasi (Rp)",
        yaxis_title="Wilayah",
        template="plotly_white",
        coloraxis_showscale=False,
        margin=dict(l=20, r=20, t=50, b=20)
    )
    return fig


def chart_lorenz(lorenz_x: list, lorenz_y: list, gini_val: float) -> go.Figure:
    """Kurva Lorenz untuk melihat ketimpangan/konsentrasi donasi."""
    fig = go.Figure()
    
    # Garis kesetaraan sempurna (45 derajat)
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1],
        mode="lines",
        line=dict(dash="dash", color="#94a3b8"),
        name="Pemerataan Sempurna"
    ))
    
    # Kurva Lorenz aktual
    fig.add_trace(go.Scatter(
        x=lorenz_x, y=lorenz_y,
        mode="lines",
        line=dict(color="#0d9488", width=3),
        name=f"Kurva Lorenz (Gini = {gini_val})"
    ))
    
    fig.update_layout(
        title=f"Kurva Lorenz Konsentrasi Donasi (Koefisien Gini: {gini_val})",
        xaxis_title="Persentase Kumulatif Muzaki (0 - 1)",
        yaxis_title="Persentase Kumulatif Dana (0 - 1)",
        template="plotly_white",
        margin=dict(l=20, r=20, t=50, b=20)
    )
    return fig


def chart_forecasting(monthly_df: pd.DataFrame, forecast_df: pd.DataFrame,
                      label_selang: Optional[str] = "Selang proyeksi") -> go.Figure:
    """Grafik historis + proyeksi peramalan ke depan, dengan selang bila tersedia."""
    fig = go.Figure()
    
    if not monthly_df.empty:
        fig.add_trace(go.Scatter(
            x=monthly_df["periode_str"],
            y=monthly_df["total_dana"],
            mode="lines+markers",
            line=dict(color="#0d9488", width=2),
            name="Historis Aktual"
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
            fillcolor="rgba(20, 184, 166, 0.2)",
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
            line=dict(color="#f59e0b", width=3, dash="dot"),
            marker=dict(size=6, color="#d97706"),
            name="Proyeksi Prediksi"
        ))
        
    fig.update_layout(
        title="Proyeksi Penerimaan Dana ZIS (6 - 12 Bulan ke Depan)",
        xaxis_title="Periode",
        yaxis_title="Nominal (Rp)",
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=50, b=20)
    )
    return fig

