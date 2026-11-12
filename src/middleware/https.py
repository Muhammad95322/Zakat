"""Paksa HTTPS di production.

TLS diterminasi oleh proxy Render; aplikasi melihat skema asli dari header X-Forwarded-Proto yang HANYA
dipercaya bila koneksi datang dari proxy tepercaya (PROXY_TEPERCAYA). Permintaan http:// di production
dihentikan dan pengguna diarahkan ke APP_BASE_URL (https). Render sendiri juga mengalihkan http->https.
"""
from typing import Mapping, Optional

from src.config import settings
from src.middleware.ip_klien import _ambil, _ip, _tepercaya, jaringan_tepercaya


def skema_permintaan(headers: Optional[Mapping[str, str]], peer: Optional[str], url: Optional[str]) -> str:
    """'https' | 'http' | 'tidak-diketahui'."""
    headers = headers or {}
    ip_peer = _ip(peer)
    jaringan = jaringan_tepercaya(settings.PROXY_TEPERCAYA)
    if ip_peer is not None and jaringan and _tepercaya(ip_peer, jaringan):
        proto = (_ambil(headers, "X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        if proto in ("http", "https"):
            return proto
    if url and "://" in url:
        return url.split("://", 1)[0].lower()
    return "tidak-diketahui"


def perlu_dialihkan(headers, peer, url) -> bool:
    return settings.is_production and skema_permintaan(headers, peer, url) == "http"


def paksa_https() -> None:
    """Dipanggil di awal app.py. Menghentikan render halaman bila production diakses lewat http."""
    import streamlit as st
    try:
        ctx = st.context
        headers, peer, url = dict(ctx.headers or {}), getattr(ctx, "ip_address", None), getattr(ctx, "url", None)
    except Exception:
        return
    if perlu_dialihkan(headers, peer, url):
        st.error("Koneksi tidak aman (http). Buka aplikasi lewat alamat https berikut.")
        st.markdown(f"[{settings.APP_BASE_URL}]({settings.APP_BASE_URL})")
        st.stop()
