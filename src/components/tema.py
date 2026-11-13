"""Tema visual Zakat Insight: CSS global, kepala halaman, dan format angka gaya Indonesia.

Arah desain
- Warna: tinta hijau pinus (sidebar), hijau pinus (aksi), kunyit (hanya untuk proyeksi dan sorotan),
  latar putih kehijauan dingin. Tanpa gradasi dan tanpa kartu seragam.
- Huruf: Plus Jakarta Sans (dirancang di Jakarta); fallback ke huruf sistem bila tanpa internet.
- Ikon: Material (bawaan Streamlit), bukan emoji.
"""
from html import escape

import streamlit as st

TINTA = "#12332E"
PINUS = "#14705E"
PINUS_TUA = "#0F5648"
KUNYIT = "#B7791F"
LATAR = "#F5F6F3"
GARIS = "#DDE2DE"
TEKS = "#1A2421"
REDUP = "#5F6B67"

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

html, body, .stApp, .stApp p, .stApp label, .stApp button, .stApp input, .stApp textarea,
.stApp li, .stApp td, .stApp th, .stApp summary, .stApp a, .stApp div[data-baseweb] {{
    font-family: 'Plus Jakarta Sans', 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif;
}}
/* Jangan timpa font ikon Material bawaan Streamlit */
[data-testid="stIconMaterial"], .material-symbols-rounded, [class*="material-icons"] {{
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
}}
.stApp {{ background: {LATAR}; color: {TEKS}; }}
[data-testid="stHeader"] {{ background: transparent; height: 2.5rem; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1180px; }}

/* Judul */
h1, h2, h3, h4 {{ font-family: 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif; color: {TEKS};
    letter-spacing: -0.01em; }}
h1 {{ font-size: 1.75rem; font-weight: 700; padding: 0 0 .25rem; }}
h2 {{ font-size: 1.3rem; font-weight: 650; }}
h3 {{ font-size: 1.08rem; font-weight: 650; }}
h4 {{ font-size: .98rem; font-weight: 650; }}
.zi-kepala {{ margin: 0 0 1.4rem; }}
.zi-kepala h1 {{ margin: 0; font-size: 1.75rem; font-weight: 700; line-height: 1.2; }}
.zi-kepala p {{ margin: .35rem 0 0; color: {REDUP}; font-size: .95rem; max-width: 60ch; line-height: 1.5; }}
.zi-bagian {{ margin: 2rem 0 .6rem; font-size: 1.08rem; font-weight: 650; }}
.zi-bagian small {{ display: block; margin-top: .15rem; font-size: .88rem; font-weight: 400; color: {REDUP}; }}

/* Sidebar */
[data-testid="stSidebar"] {{ border-right: none; }}
[data-testid="stSidebar"] .block-container, [data-testid="stSidebarUserContent"] {{ padding-top: 1.4rem; }}
.zi-merek {{ display: flex; align-items: center; gap: .65rem; margin: 0 0 .2rem; }}
.zi-merek span {{ font-size: 1.12rem; font-weight: 700; color: #F2F7F4; letter-spacing: -0.01em; }}
.zi-merek svg {{ flex: none; }}
.zi-pengguna {{ margin: 1.1rem 0 .9rem; padding: .7rem 0 .2rem; border-top: 1px solid rgba(255,255,255,.12); }}
.zi-pengguna b {{ display: block; color: #F2F7F4; font-size: .93rem; font-weight: 600; }}
.zi-pengguna small {{ color: #A9BDB6; font-size: .8rem; }}
[data-testid="stSidebar"] .stButton > button[data-testid^="stBaseButton"] {{
    justify-content: flex-start; gap: .55rem; text-align: left; width: 100%;
    background: transparent; border: none; border-radius: 6px; color: #D3E0DA;
    font-weight: 500; font-size: .93rem; padding: .5rem .7rem; box-shadow: none; min-height: 2.5rem;
}}
[data-testid="stSidebar"] .stButton > button[data-testid^="stBaseButton"]:hover {{ background: rgba(255,255,255,.07); color: #fff; }}
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"][data-testid^="stBaseButton"] {{
    background: rgba(255,255,255,.11); color: #fff; font-weight: 600; box-shadow: inset 3px 0 0 {KUNYIT};
}}
[data-testid="stSidebar"] .stButton > button > div {{ justify-content: flex-start; width: 100%; }}
[data-testid="stSidebar"] .stButton > button p {{ font-size: .93rem; text-align: left; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.12); margin: .8rem 0; }}

/* Tombol */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
    border-radius: 6px; font-weight: 600; transition: background .15s, border-color .15s;
}}
.stButton > button[data-testid="stBaseButton-primary"],
[data-testid="stFormSubmitButton"] > button[data-testid="stBaseButton-primaryFormSubmit"],
.stDownloadButton > button[data-testid="stBaseButton-primary"] {{
    background: {PINUS}; border: 1px solid {PINUS}; color: #fff;
}}
.stButton > button[data-testid="stBaseButton-primary"]:hover,
[data-testid="stFormSubmitButton"] > button:hover,
.stDownloadButton > button[data-testid="stBaseButton-primary"]:hover {{ background: {PINUS_TUA}; border-color: {PINUS_TUA}; }}
.stButton > button[data-testid="stBaseButton-secondary"], .stDownloadButton > button[data-testid="stBaseButton-secondary"] {{
    background: #fff; border: 1px solid {GARIS}; color: {TEKS};
}}
.stButton > button[data-testid="stBaseButton-secondary"]:hover {{ border-color: {PINUS}; color: {PINUS}; }}
button:focus-visible, a:focus-visible, input:focus-visible {{ outline: 2px solid {KUNYIT}; outline-offset: 2px; }}

/* Angka kunci (KPI): deret bergaris, bukan kartu */
[data-testid="stMetric"] {{ background: transparent; border: none; border-top: 2px solid {TEKS};
    padding: .7rem .25rem .3rem 0; }}
[data-testid="stMetricLabel"] p {{ font-size: .85rem; font-weight: 500; color: {REDUP}; }}
[data-testid="stMetricValue"] {{ font-size: 1.85rem; font-weight: 650; letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums; }}

/* Tab */
.stTabs [data-baseweb="tab-list"] {{ gap: 1.4rem; border-bottom: 1px solid {GARIS}; overflow-x: auto; }}
.stTabs [data-baseweb="tab"] {{ padding: .55rem 0; height: auto; font-size: .93rem; font-weight: 500;
    color: {REDUP}; white-space: nowrap; }}
.stTabs [aria-selected="true"] {{ color: {TEKS}; font-weight: 650; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: {PINUS}; height: 3px; }}
.stTabs [data-baseweb="tab-panel"] {{ padding-top: 1.4rem; }}

/* Pesan: datar, bergaris di kiri */
[data-testid="stAlert"] {{ background: transparent; border: none; padding: 0; }}
[data-testid="stAlert"] > div {{ border-radius: 4px; border: none; border-left: 3px solid {PINUS};
    background: #EAF1EE; color: {TEKS}; padding: .7rem 1rem; }}
[data-testid="stAlert"] p {{ font-size: .92rem; line-height: 1.55; }}
[data-testid="stAlert"] [data-baseweb="notification"] {{ background: transparent; box-shadow: none; padding: 0; }}

/* Kotak, ekspander, tabel */
[data-testid="stExpander"] {{ border: 1px solid {GARIS}; border-radius: 6px; background: #fff; }}
[data-testid="stExpander"] summary {{ font-weight: 600; font-size: .93rem; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 6px; border-color: {GARIS}; }}
[data-testid="stDataFrame"] {{ border: 1px solid {GARIS}; border-radius: 6px; overflow: hidden; }}
[data-testid="stForm"] {{ border: 1px solid {GARIS}; border-radius: 8px; background: #fff; padding: 1.4rem; }}
[data-testid="stCaptionContainer"] {{ color: {REDUP}; }}
hr {{ border-color: {GARIS}; margin: 1.6rem 0; }}
[data-baseweb="input"], [data-baseweb="select"] > div {{ border-radius: 6px; }}
label p {{ font-size: .88rem; font-weight: 550; }}

/* Halaman publik (masuk, daftar, reset, verifikasi) */
.zi-publik {{ margin: 1.5rem 0 1.4rem; }}
.zi-publik .zi-merek span {{ color: {TEKS}; }}
.zi-publik h1 {{ margin: 1.6rem 0 .3rem; font-size: 1.6rem; }}
.zi-publik p {{ margin: 0; color: {REDUP}; font-size: .95rem; line-height: 1.5; }}
.error-box, .success-box, .info-box, .req-list {{ border-radius: 4px; padding: .8rem 1rem; font-size: .92rem;
    line-height: 1.55; border-left: 3px solid {PINUS}; background: #EAF1EE; margin-bottom: .6rem; }}
.error-box {{ border-left-color: #B3382C; background: #F8E7E4; }}
.req-list {{ font-size: .86rem; color: {REDUP}; }}

/* Baris riwayat berkas, paket, status */
.zi-baris {{ padding: .15rem 0; }}
.zi-baris b {{ font-weight: 600; }}
.zi-meta {{ color: {REDUP}; font-size: .85rem; }}
.zi-status {{ display: inline-block; padding: .1rem .55rem; border-radius: 99px; font-size: .78rem; font-weight: 600; }}
.zi-status.siap {{ background: #E1F0EA; color: {PINUS_TUA}; }}
.zi-status.proses {{ background: #F8EBD2; color: #7A5214; }}
.zi-status.galat {{ background: #F6DEDA; color: #8A2A20; }}
.zi-paket {{ border-top: 2px solid {GARIS}; padding: .9rem 0 .3rem; }}
.zi-paket.aktif {{ border-top-color: {PINUS}; }}
.zi-paket h3 {{ margin: 0; }}
.zi-harga {{ font-size: 1.5rem; font-weight: 650; font-variant-numeric: tabular-nums; margin: .15rem 0 .6rem; }}
.zi-harga small {{ font-size: .85rem; font-weight: 400; color: {REDUP}; }}
.zi-paket ul {{ list-style: none; padding: 0 !important; margin: 0 0 .8rem !important; }}
.zi-paket li {{ padding: .28rem 0 !important; margin-left: 0 !important; font-size: .92rem; border-bottom: 1px solid {GARIS}; }}
.zi-paket li.tidak {{ color: #8B9692; text-decoration: line-through; text-decoration-color: #C3CAC6; }}

@media (max-width: 640px) {{
    .block-container {{ padding-left: 1rem; padding-right: 1rem; padding-top: 1.2rem; }}
    h1, .zi-kepala h1 {{ font-size: 1.45rem; }}
    [data-testid="stMetricValue"] {{ font-size: 1.5rem; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 1rem; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""

# Lambang: bulan sabit di atas bidang tinta
_LAMBANG = (
    '<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">'
    f'<rect width="30" height="30" rx="7" fill="#1E4A42"/>'
    f'<path d="M18.5 6.2A9.2 9.2 0 1 0 24 18.4 7.4 7.4 0 0 1 18.5 6.2Z" fill="{KUNYIT}"/>'
    '<rect x="7" y="21" width="3" height="3" rx=".6" fill="#F2F7F4"/>'
    '<rect x="11.5" y="18.5" width="3" height="5.5" rx=".6" fill="#F2F7F4"/>'
    '<rect x="16" y="16" width="3" height="8" rx=".6" fill="#F2F7F4"/></svg>'
)


def terapkan_tema() -> None:
    """Suntikkan CSS global. Panggil sekali per eksekusi skrip, setelah set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


def merek_html() -> str:
    return f'<div class="zi-merek">{_LAMBANG}<span>Zakat Insight</span></div>'


def kepala_publik(judul: str, deskripsi: str = "") -> None:
    """Kepala halaman tanpa sidebar: merek, judul, dan satu kalimat penjelas."""
    desk = f"<p>{escape(deskripsi)}</p>" if deskripsi else ""
    st.markdown(f'<div class="zi-publik">{merek_html()}<h1>{escape(judul)}</h1>{desk}</div>', unsafe_allow_html=True)


def judul_halaman(judul: str, deskripsi: str = "") -> None:
    """Kepala halaman: satu judul, satu kalimat penjelas (teks diescape)."""
    desk = f"<p>{escape(deskripsi)}</p>" if deskripsi else ""
    st.markdown(f'<div class="zi-kepala"><h1>{escape(judul)}</h1>{desk}</div>', unsafe_allow_html=True)


def judul_bagian(judul: str, keterangan: str = "") -> None:
    ket = f"<small>{escape(keterangan)}</small>" if keterangan else ""
    st.markdown(f'<div class="zi-bagian">{escape(judul)}{ket}</div>', unsafe_allow_html=True)


def angka_id(n) -> str:
    """Bilangan bulat dengan pemisah ribuan titik: 3920 -> '3.920'."""
    try:
        return f"{int(round(float(n))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "-"


def ukuran_mb(mb) -> str:
    """Ukuran penyimpanan dengan koma desimal: 0.19 -> '0,19 MB', 2048 -> '2 GB'."""
    try:
        mb = float(mb)
    except (TypeError, ValueError):
        return "-"
    if mb >= 1024:
        g = mb / 1024
        return (f"{g:.1f}".rstrip("0").rstrip(".") + " GB").replace(".", ",")
    return (f"{mb:.2f}".rstrip("0").rstrip(".") + " MB").replace(".", ",")
