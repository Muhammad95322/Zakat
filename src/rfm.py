"""Modul segmentasi Muzaki dengan metode RFM dan analisis konsentrasi Gini."""
from datetime import datetime
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np

def calculate_gini(series: pd.Series) -> Tuple[float, np.ndarray, np.ndarray]:
    """Menghitung koefisien Gini dan kurva Lorenz dari array donasi."""
    arr = series.dropna().values.astype(float)
    if len(arr) == 0 or np.all(arr == 0):
        return 0.0, np.array([0, 1]), np.array([0, 1])
        
    arr = np.sort(arr)
    n = len(arr)
    cum_arr = np.cumsum(arr)
    total = cum_arr[-1]
    
    # Lorenz curve points
    lorenz_x = np.linspace(0, 1, n + 1)
    lorenz_y = np.insert(cum_arr / total, 0, 0.0)
    
    # Area under Lorenz curve (trapezoidal rule)
    area = np.trapezoid(lorenz_y, lorenz_x)
    gini = round(float((0.5 - area) / 0.5), 3)
    gini = max(0.0, min(1.0, gini))
    
    return gini, lorenz_x, lorenz_y


def _skor_kuantil(nilai: pd.Series, labels: list) -> pd.Series:
    """Skor kuantil 1-5. Jika banyak nilai kembar sehingga batas kuantil tidak
    unik (qcut gagal), pakai peringkat agar tetap terbagi 5 kelompok."""
    try:
        return pd.qcut(nilai, q=5, labels=labels).astype(int)
    except ValueError:
        return pd.qcut(nilai.rank(method="first"), q=5, labels=labels).astype(int)


def segment_rfm(df_himpun: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Melakukan segmentasi RFM (Recency, Frequency, Monetary) pada data muzaki.
    
    Returns:
        (rfm_df, summary_metrics)
    """
    if df_himpun.empty or "jumlah" not in df_himpun.columns:
        return pd.DataFrame(), {}
        
    mzk_id_col = "id_muzaki" if "id_muzaki" in df_himpun.columns else "nama_muzaki"
    nama_col = "nama_muzaki" if "nama_muzaki" in df_himpun.columns else mzk_id_col
    
    max_date = df_himpun["tanggal"].max() if "tanggal" in df_himpun.columns else pd.Timestamp.now()
    
    # Agregasi per muzaki
    rfm = df_himpun.groupby(mzk_id_col).agg(
        nama=(nama_col, "first"),
        terakhir_donasi=("tanggal", "max") if "tanggal" in df_himpun.columns else ("jumlah", "count"),
        frequency=("jumlah", "count"),
        monetary=("jumlah", "sum")
    ).reset_index()
    
    if "tanggal" in df_himpun.columns:
        rfm["recency_days"] = (max_date - rfm["terakhir_donasi"]).dt.days
    else:
        rfm["recency_days"] = 30
        
    # Scoring 1 - 5 berbasis kuantil
    n_records = len(rfm)
    
    # Recency score (lebih baru / hari lebih sedikit = skor lebih tinggi)
    if n_records >= 5:
        rfm["r_score"] = _skor_kuantil(rfm["recency_days"], [5, 4, 3, 2, 1])
        rfm["m_score"] = _skor_kuantil(rfm["monetary"], [1, 2, 3, 4, 5])
    else:
        rfm["r_score"] = 3
        rfm["m_score"] = 3
        
    # Frequency score (jumlah donasi)
    def _score_f(f):
        if f >= 10: return 5
        elif f >= 5: return 4
        elif f >= 3: return 3
        elif f >= 2: return 2
        return 1
    rfm["f_score"] = rfm["frequency"].apply(_score_f)
    
    # Label Segmentasi
    def _assign_segment(row):
        r = row["r_score"]
        f = row["f_score"]
        m = row["m_score"]
        
        if r >= 4 and f >= 4:
            return "🌟 Muzaki Setia"
        elif r >= 3 and f >= 3 and m >= 4:
            return "💎 Muzaki Potensial"
        elif f == 1 and r >= 4:
            return "🆕 Muzaki Baru"
        elif (r in [2, 3]) and f >= 2:
            return "😴 Muzaki Tidur"
        elif (r in [1, 2]) and f >= 3:
            return "⚠️ Muzaki Berisiko"
        else:
            return "👋 Muzaki Pasif/Hilang"
            
    rfm["segmen"] = rfm.apply(_assign_segment, axis=1)
    
    # Hitung Gini Donasi
    gini_val, lorenz_x, lorenz_y = calculate_gini(rfm["monetary"])
    
    # Pareto: berapa % muzaki menyumbang 80% dana
    sorted_m = rfm["monetary"].sort_values(ascending=False).values
    cum_pct = np.cumsum(sorted_m) / sorted_m.sum()
    top_80_idx = np.where(cum_pct >= 0.8)[0]
    pareto_pct = round(((top_80_idx[0] + 1) / len(rfm) * 100), 1) if len(top_80_idx) > 0 else 100.0
    
    summary = {
        "total_muzaki": len(rfm),
        "gini_index": gini_val,
        "pareto_pct": pareto_pct,
        "lorenz_x": lorenz_x.tolist(),
        "lorenz_y": lorenz_y.tolist(),
        "segmen_counts": rfm["segmen"].value_counts().to_dict(),
        "interpretasi_gini": (
            f"Koefisien Gini donasi adalah {gini_val} (skala 0 - 1). "
            f"Sekitar {pareto_pct}% muzaki teratas telah menyumbang 80% dari total dana yang terhimpun."
        )
    }
    
    return rfm, summary

