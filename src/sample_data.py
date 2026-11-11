"""Generator data sintetis realistis untuk Zakat Insight.
Menghasilkan transaksi 3 tahun (2022-2024) dengan:
- Pola musiman Ramadan dan akhir tahun
- Variasi kanal donasi dan jenis dana
- Outlier, duplikat, dan data kotor yang disengaja untuk pengujian cleaning
- Transaksi penghimpunan dan penyaluran
"""
import random
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Tuple
import pandas as pd
import numpy as np

KABUPATEN_KOTA = ["Kota Yogyakarta", "Sleman", "Bantul", "Gunungkidul", "Kulon Progo"]
JENIS_DANA = [
    "Zakat Fitrah", "Zakat Maal", "Zakat Profesi", 
    "Infak", "Sedekah", "Wakaf", "Dana Sosial Keagamaan Lainnya"
]
KANAL = ["Transfer Bank", "Tunai", "QRIS", "Kantor Layanan", "Mitra/Online"]
PROGRAM = ["Pendidikan", "Kesehatan", "Ekonomi", "Sosial-Dakwah", "Kemanusiaan/Bencana"]
ASNAF = ["Fakir", "Miskin", "Amil", "Muallaf", "Riqab", "Gharimin", "Fisabilillah", "Ibnu Sabil"]

# Bulan Ramadan perkiraan: 2022 (April), 2023 (Maret/April), 2024 (Maret/April)
RAMADAN_MONTHS = {
    2022: [4],
    2023: [3, 4],
    2024: [3, 4]
}

def generate_sample_data(n_penghimpunan: int = 5000, n_penyaluran: int = 1500) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generate dataframe sintetis penghimpunan dan penyaluran."""
    random.seed(42)
    np.random.seed(42)

    # 1. Generate Muzaki Pool (600 muzaki unik)
    muzaki_pool = []
    for i in range(1, 601):
        muzaki_pool.append({
            "id": f"MZK-{i:04d}",
            "nama": f"Muzaki {i}",
            "tipe": "besar" if i <= 15 else ("menengah" if i <= 100 else "reguler")
        })

    # 2. Generate Penghimpunan
    start_date = date(2022, 1, 1)
    end_date = date(2024, 12, 31)
    total_days = (end_date - start_date).days

    rows_penghimpunan = []
    for _ in range(n_penghimpunan):
        d_offset = random.randint(0, total_days)
        tgl = start_date + timedelta(days=d_offset)
        
        mzk = random.choice(muzaki_pool)
        
        # Bobot jenis dana & nominal sesuai musim Ramadan
        is_ramadan = tgl.month in RAMADAN_MONTHS.get(tgl.year, [])
        is_december = (tgl.month == 12)
        
        if is_ramadan:
            jenis = random.choices(
                JENIS_DANA,
                weights=[30, 25, 20, 10, 10, 3, 2]
            )[0]
        else:
            jenis = random.choices(
                JENIS_DANA,
                weights=[2, 20, 35, 20, 15, 5, 3]
            )[0]
            
        kanal = random.choices(
            KANAL,
            weights=[40, 15, 25, 10, 10]
        )[0]
        
        wilayah = random.choices(
            KABUPATEN_KOTA,
            weights=[35, 30, 20, 8, 7]
        )[0]
        
        # Nominal donasi berdasarkan profil muzaki
        if mzk["tipe"] == "besar":
            nominal = round(random.uniform(5_000_000, 50_000_000), -4)
        elif mzk["tipe"] == "menengah":
            nominal = round(random.uniform(500_000, 5_000_000), -3)
        else:
            nominal = round(random.uniform(25_000, 1_000_000), -3)
            
        if is_ramadan:
            nominal *= random.uniform(1.2, 1.8)
            
        rows_penghimpunan.append({
            "tanggal": tgl.strftime("%Y-%m-%d"),
            "id_muzaki": mzk["id"],
            "nama_muzaki": mzk["nama"],
            "jenis_dana": jenis,
            "kanal": kanal,
            "kabupaten_kota": wilayah,
            "kampanye": "Ramadan Peduli" if is_ramadan else ("Berkah Akhir Tahun" if is_december else "Reguler"),
            "jumlah": int(nominal)
        })

    # Sisipkan dirty data yang disengaja
    # a. Duplikat (50 baris)
    for _ in range(50):
        rows_penghimpunan.append(rows_penghimpunan[random.randint(0, 1000)].copy())
        
    # b. Outlier ekstrem (5 baris)
    for _ in range(5):
        idx = random.randint(0, len(rows_penghimpunan)-1)
        rows_penghimpunan[idx]["jumlah"] = int(500_000_000)

    # c. Nilai kosong acak
    for _ in range(30):
        idx = random.randint(0, len(rows_penghimpunan)-1)
        rows_penghimpunan[idx]["kabupaten_kota"] = ""

    df_penghimpunan = pd.DataFrame(rows_penghimpunan)

    # 3. Generate Penyaluran
    rows_penyaluran = []
    for _ in range(n_penyaluran):
        d_offset = random.randint(0, total_days)
        tgl = start_date + timedelta(days=d_offset)
        
        prog = random.choices(
            PROGRAM,
            weights=[30, 25, 20, 15, 10]
        )[0]
        
        asnaf_val = random.choices(
            ASNAF,
            weights=[35, 30, 10, 5, 2, 8, 8, 2]
        )[0]
        
        wilayah = random.choice(KABUPATEN_KOTA)
        penerima = random.randint(1, 100)
        nominal = penerima * round(random.uniform(150_000, 1_000_000), -3)
        
        rows_penyaluran.append({
            "tanggal": tgl.strftime("%Y-%m-%d"),
            "program": prog,
            "asnaf": asnaf_val,
            "jenis_dana_sumber": random.choice(["Zakat Maal", "Zakat Fitrah", "Infak", "Sedekah"]),
            "kabupaten_kota": wilayah,
            "jumlah_penerima": penerima,
            "jumlah": int(nominal)
        })
        
    df_penyaluran = pd.DataFrame(rows_penyaluran)
    return df_penghimpunan, df_penyaluran


def save_sample_and_template_files():
    """Menyimpan file contoh dan template ke folder data/."""
    out_dir = Path("data/sample")
    tmpl_dir = Path("data/template")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl_dir.mkdir(parents=True, exist_ok=True)
    
    df_himpun, df_salur = generate_sample_data(2000, 600)
    
    # 1. Simpan data contoh Excel (2 sheets)
    sample_path = out_dir / "data_contoh.xlsx"
    with pd.ExcelWriter(sample_path, engine="openpyxl") as writer:
        df_himpun.to_excel(writer, sheet_name="Penghimpunan", index=False)
        df_salur.to_excel(writer, sheet_name="Penyaluran", index=False)
        
    # 2. Simpan template kosong dengan 1 baris contoh
    tmpl_path = tmpl_dir / "template_zakat.xlsx"
    df_h_tmpl = pd.DataFrame([{
        "tanggal": "2024-01-15",
        "id_muzaki": "MZK-0001",
        "nama_muzaki": "H. Sulaiman",
        "jenis_dana": "Zakat Maal",
        "kanal": "Transfer Bank",
        "kabupaten_kota": "Kota Yogyakarta",
        "kampanye": "Reguler",
        "jumlah": 2500000
    }])
    df_s_tmpl = pd.DataFrame([{
        "tanggal": "2024-01-20",
        "program": "Pendidikan",
        "asnaf": "Fakir",
        "jenis_dana_sumber": "Zakat Maal",
        "kabupaten_kota": "Bantul",
        "jumlah_penerima": 10,
        "jumlah": 5000000
    }])
    with pd.ExcelWriter(tmpl_path, engine="openpyxl") as writer:
        df_h_tmpl.to_excel(writer, sheet_name="Penghimpunan", index=False)
        df_s_tmpl.to_excel(writer, sheet_name="Penyaluran", index=False)
        
    print(f"Data contoh disimpan ke: {sample_path}")
    print(f"Template disimpan ke: {tmpl_path}")

if __name__ == "__main__":
    save_sample_and_template_files()

