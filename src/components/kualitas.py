"""Tampilan laporan kualitas data (halaman Unggah & Analisis)."""
from typing import Any, Dict

import streamlit as st

from src.kualitas_data import tabel_kualitas


def tampilkan_kualitas(lap: Dict[str, Any], judul: str = "📋 Laporan Kualitas Data", terbuka: bool = False) -> None:
    if not lap:
        return
    with st.expander(judul, expanded=terbuka):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Baris valid", f"{lap['persen_valid']:.1f}%",
                  help=f"{lap['baris_valid']:,} dari {lap['baris_dibaca']:,} baris data".replace(",", "."))
        c2.metric("Baris dibuang", f"{lap['baris_dibuang']:,}".replace(",", "."))
        c3.metric("Rentang data", f"{lap['rentang_bulan']} bulan")
        c4.metric("Kategori tak dikenal", sum(len(v) for v in (lap.get("kategori_tak_dikenal") or {}).values()))
        st.caption(f"Rentang tanggal: {lap['rentang_tanggal']}")
        for w in lap.get("peringatan", []):
            st.warning(w)
        st.dataframe(tabel_kualitas(lap).astype(str), hide_index=True, width="stretch")
