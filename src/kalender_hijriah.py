"""Penanda musiman berbasis kalender Hijriah: Ramadan dan Idulfitri.

PERHATIAN: tanggal di bawah adalah PERKIRAAN (hisab umum / kalender pemerintah
yang lazim dipakai di Indonesia) dan dapat berbeda 1-2 hari dengan penetapan
resmi (rukyat/isbat) atau antar-ormas. Untuk fitur bulanan, selisih 1-2 hari
hanya sedikit menggeser porsi hari Ramadan antara dua bulan.

Tabel sengaja di-hardcode untuk rentang 2015-2030 (bukan dihitung dengan
algoritma) agar mudah diperiksa manusia. Di luar rentang itu fitur dinonaktifkan.
"""
from datetime import date, timedelta
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# (1 Ramadan, 1 Syawal/Idulfitri) -- perkiraan, +/- 1-2 hari
PERKIRAAN_RAMADAN: List[Tuple[date, date]] = [
    (date(2015, 6, 18), date(2015, 7, 17)),   # 1436 H
    (date(2016, 6, 6), date(2016, 7, 6)),     # 1437 H
    (date(2017, 5, 27), date(2017, 6, 25)),   # 1438 H
    (date(2018, 5, 17), date(2018, 6, 15)),   # 1439 H
    (date(2019, 5, 6), date(2019, 6, 5)),     # 1440 H
    (date(2020, 4, 24), date(2020, 5, 24)),   # 1441 H
    (date(2021, 4, 13), date(2021, 5, 13)),   # 1442 H
    (date(2022, 4, 3), date(2022, 5, 2)),     # 1443 H
    (date(2023, 3, 23), date(2023, 4, 22)),   # 1444 H
    (date(2024, 3, 12), date(2024, 4, 10)),   # 1445 H
    (date(2025, 3, 1), date(2025, 3, 31)),    # 1446 H
    (date(2026, 2, 19), date(2026, 3, 20)),   # 1447 H
    (date(2027, 2, 8), date(2027, 3, 10)),    # 1448 H
    (date(2028, 1, 28), date(2028, 2, 26)),   # 1449 H
    (date(2029, 1, 16), date(2029, 2, 14)),   # 1450 H
    (date(2030, 1, 6), date(2030, 2, 4)),     # 1451 H
    (date(2030, 12, 26), date(2031, 1, 24)),  # 1452 H (Ramadan di akhir 2030)
]

TAHUN_AWAL = 2015
TAHUN_AKHIR = 2030


def cek_cakupan(tanggal: pd.DatetimeIndex) -> Optional[str]:
    """None jika semua bulan berada dalam rentang tabel, selain itu pesan penjelasan."""
    if len(tanggal) == 0:
        return "tidak ada bulan untuk diperiksa"
    luar = sorted({d.year for d in tanggal if not (TAHUN_AWAL <= d.year <= TAHUN_AKHIR)})
    if luar:
        return (
            f"tabel perkiraan Ramadan hanya mencakup {TAHUN_AWAL}-{TAHUN_AKHIR}, "
            f"sedangkan data/proyeksi mencakup tahun {', '.join(map(str, luar))}"
        )
    return None


def fitur_ramadan(tanggal: pd.DatetimeIndex) -> pd.DataFrame:
    """Fitur per bulan.

    - porsi_ramadan: jumlah hari Ramadan di bulan itu / panjang Ramadan (0..1;
      jumlah per Ramadan = 1)
    - idulfitri: 1 jika 1 Syawal jatuh di bulan itu, selain itu 0
    """
    hasil = []
    for d in tanggal:
        awal = date(d.year, d.month, 1)
        akhir = (pd.Timestamp(awal) + pd.offsets.MonthEnd(0)).date()
        porsi = 0.0
        idul = 0.0
        for mulai, syawal in PERKIRAAN_RAMADAN:
            selesai = syawal - timedelta(days=1)
            irisan = (min(akhir, selesai) - max(awal, mulai)).days + 1
            if irisan > 0:
                porsi += irisan / ((syawal - mulai).days)
            if awal <= syawal <= akhir:
                idul = 1.0
        hasil.append({"porsi_ramadan": porsi, "idulfitri": idul})
    return pd.DataFrame(hasil, index=tanggal)
