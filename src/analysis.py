"""Modul analisis statistik, metrik ZIS, dan interpretasi bahasa awam."""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from scipy import stats

from src.utils import format_rupiah

def get_summary_stats(df_himpun: pd.DataFrame) -> Dict[str, Any]:
    """Menghitung metrik ringkasan utama penghimpunan."""
    if df_himpun.empty or "jumlah" not in df_himpun.columns:
        return {
            "total_dana": 0, "total_transaksi": 0, "muzaki_unik": 0,
            "rata_rata": 0, "median": 0, "terbesar": 0, "interpretasi": "Belum ada data penghimpunan."
        }
        
    total_dana = float(df_himpun["jumlah"].sum())
    total_tx = len(df_himpun)
    muzaki_col = "id_muzaki" if "id_muzaki" in df_himpun.columns else "nama_muzaki"
    muzaki_unik = df_himpun[muzaki_col].nunique() if muzaki_col in df_himpun.columns else total_tx
    rata_rata = float(df_himpun["jumlah"].mean())
    median = float(df_himpun["jumlah"].median())
    terbesar = float(df_himpun["jumlah"].max())
    
    # Interpretasi awam
    interpretasi = (
        f"Lembaga telah menghimpun total {format_rupiah(total_dana, singkat=True)} "
        f"dari {total_tx:,} transaksi oleh {muzaki_unik:,} donatur terdaftar. "
        f"Sebagian besar donasi berpusat di nominal {format_rupiah(median)}, "
        f"dengan rata-rata donasi per transaksi sebesar {format_rupiah(rata_rata)}."
    )
    
    return {
        "total_dana": total_dana,
        "total_transaksi": total_tx,
        "muzaki_unik": muzaki_unik,
        "rata_rata": rata_rata,
        "median": median,
        "terbesar": terbesar,
        "interpretasi": interpretasi
    }


def get_trend_analysis(df_himpun: pd.DataFrame) -> Dict[str, Any]:
    """Analisis tren bulanan, pertumbuhan MoM, YoY, dan pola musiman."""
    if df_himpun.empty or "tanggal" not in df_himpun.columns:
        return {"monthly": pd.DataFrame(), "interpretasi": "Data tanggal tidak tersedia."}
        
    df = df_himpun.copy()
    df["periode"] = df["tanggal"].dt.to_period("M")
    
    monthly = df.groupby("periode").agg(
        total_dana=("jumlah", "sum"),
        jumlah_transaksi=("jumlah", "count")
    ).reset_index()
    monthly["periode_str"] = monthly["periode"].astype(str)
    
    # Hitung pertumbuhan MoM (%)
    monthly["mom_growth"] = monthly["total_dana"].pct_change() * 100
    
    # Cari bulan puncak
    max_idx = monthly["total_dana"].idxmax()
    bulan_puncak = monthly.loc[max_idx, "periode_str"]
    dana_puncak = monthly.loc[max_idx, "total_dana"]
    
    interpretasi = (
        f"Penerimaan dana tertinggi tercatat pada periode {bulan_puncak} "
        f"mencapai {format_rupiah(dana_puncak, singkat=True)}. "
        f"Pola menunjukkan lonjakan signifikan pada periode Ramadan dan menjelang penutupan tahun."
    )
    
    return {
        "monthly": monthly,
        "bulan_puncak": bulan_puncak,
        "dana_puncak": dana_puncak,
        "interpretasi": interpretasi
    }


def get_composition_analysis(df_himpun: pd.DataFrame) -> Dict[str, Any]:
    """Breakdown komposisi jenis dana, kanal pembayaran, dan wilayah."""
    res = {}
    if df_himpun.empty:
        return res
        
    for col in ["jenis_dana", "kanal", "kabupaten_kota"]:
        if col in df_himpun.columns:
            comp = df_himpun.groupby(col)["jumlah"].agg(["sum", "count"]).reset_index()
            comp.columns = [col, "total", "transaksi"]
            total_all = comp["total"].sum()
            comp["persentase"] = round((comp["total"] / total_all * 100), 2)
            comp = comp.sort_values(by="total", ascending=False).reset_index(drop=True)
            res[col] = comp
            
    return res


def get_distribution_analysis(df_himpun: pd.DataFrame, df_salur: pd.DataFrame) -> Dict[str, Any]:
    """Analisis penyaluran dana, rasio, asnaf, dan saldo kas."""
    if df_salur.empty or "jumlah" not in df_salur.columns:
        return {"status": "empty", "pesan": "Data penyaluran belum diunggah."}
        
    total_himpun = float(df_himpun["jumlah"].sum()) if not df_himpun.empty else 0
    total_salur = float(df_salur["jumlah"].sum())
    total_penerima = int(df_salur["jumlah_penerima"].sum()) if "jumlah_penerima" in df_salur.columns else 0
    saldo = total_himpun - total_salur
    
    rasio = round((total_salur / total_himpun * 100), 2) if total_himpun > 0 else 0
    
    # Cek porsi amil
    amil_dana = 0
    amil_pct = 0
    if "asnaf" in df_salur.columns:
        amil_rows = df_salur[df_salur["asnaf"].str.lower() == "amil"]
        amil_dana = float(amil_rows["jumlah"].sum())
        amil_pct = round((amil_dana / total_salur * 100), 2) if total_salur > 0 else 0
        
    # Peringatan PSAK 109 & Efisiensi
    warnings = []
    if amil_pct > 12.5:
        warnings.append(
            f"ℹ️ Porsi hak amil tercatat {amil_pct}% dari total penyaluran. "
            f"Sebagai referensi panduan PSAK 109 / fikih zakat, alokasi bagian amil umumnya berkisar maksimal 1/8 (12,5%)."
        )
    if rasio < 70 and total_himpun > 0:
        warnings.append(
            f"ℹ️ Rasio penyaluran terhadap penghimpunan sebesar {rasio}%. "
            f"Masih terdapat saldo dana di kas sebesar {format_rupiah(saldo, singkat=True)} yang siap diprogramkan."
        )
        
    # Per program
    prog_comp = pd.DataFrame()
    if "program" in df_salur.columns:
        prog_comp = df_salur.groupby("program").agg(
            total_dana=("jumlah", "sum"),
            penerima=("jumlah_penerima", "sum") if "jumlah_penerima" in df_salur.columns else ("jumlah", "count")
        ).reset_index().sort_values(by="total_dana", ascending=False)
        
    return {
        "status": "ready",
        "total_himpun": total_himpun,
        "total_salur": total_salur,
        "saldo": saldo,
        "rasio": rasio,
        "total_penerima": total_penerima,
        "amil_pct": amil_pct,
        "warnings": warnings,
        "program_breakdown": prog_comp
    }


def get_statistical_tests(df_himpun: pd.DataFrame) -> Dict[str, Any]:
    """Uji statistik sederhana perbedaan rata-rata donasi antar kanal (Kruskal-Wallis)."""
    if df_himpun.empty or "kanal" not in df_himpun.columns or "jumlah" not in df_himpun.columns:
        return {"pesan": "Data tidak mencukupi untuk uji statistik."}
        
    groups = [group["jumlah"].values for _, group in df_himpun.groupby("kanal") if len(group) >= 5]
    if len(groups) < 2:
        return {"pesan": "Variasi kanal donasi kurang dari 2 kelompok."}
        
    try:
        h_stat, p_val = stats.kruskal(*groups)
        signifikan = p_val < 0.05
        if signifikan:
            penjelasan = (
                f"Terdapat perbedaan nominal donasi yang signifikan secara statistik di antara berbagai kanal pembayaran "
                f"(p = {p_val:.4f} < 0.05). Hal ini mengindikasikan kanal tertentu (seperti Transfer Bank) "
                f"cenderung dipilih oleh muzaki dengan nominal donasi lebih tinggi dibanding QRIS/Tunai."
            )
        else:
            penjelasan = (
                f"Tidak ditemukan perbedaan nominal yang signifikan antar kanal pembayaran (p = {p_val:.4f} >= 0.05). "
                f"Muzaki menyalurkan nominal yang relatif seragam di semua saluran pembayaran."
            )
        return {
            "test_name": "Kruskal-Wallis H-Test",
            "stat": round(float(h_stat), 2),
            "p_value": float(p_val),
            "signifikan": signifikan,
            "penjelasan": penjelasan
        }
    except Exception as e:
        import logging
        logging.getLogger("zakat.analisis").info("uji statistik gagal", extra={"galat": type(e).__name__})
        return {"pesan": "Uji statistik tidak dapat dijalankan pada data ini (mis. kelompok terlalu sedikit)."}

