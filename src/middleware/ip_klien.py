"""Menentukan IP klien di belakang proxy (Render) tanpa bisa dipalsukan lewat header buatan.

Aturan:
1. Header proxy (X-Forwarded-For, atau IP_HEADER_KLIEN mis. CF-Connecting-IP) HANYA dipercaya bila koneksi
   langsung ke aplikasi (``peer``) berasal dari proxy tepercaya (PROXY_TEPERCAYA). Bila tidak, IP ``peer``
   dipakai dan semua header diabaikan.
2. X-Forwarded-For dibaca dari KANAN: proxy menambahkan IP di belakang, jadi entri paling kiri bisa diisi
   bebas oleh klien. Entri yang termasuk proxy tepercaya dilewati; entri pertama dari kanan yang BUKAN proxy
   tepercaya adalah IP klien. Entri yang bukan IP valid menghentikan penelusuran (dianggap buatan klien).

PROXY_TEPERCAYA berisi CIDR dipisah koma dan/atau preset: ``privat`` (10/8, 172.16/12, 192.168/16, loopback,
fc00::/7), ``cloudflare`` (rentang IP Cloudflare yang dipublikasikan), ``render`` (= privat + cloudflare).
Kosong (bawaan) = tidak ada proxy dipercaya: cocok untuk development/lokal.
"""
import ipaddress
import re
from functools import lru_cache
from typing import Iterable, List, Mapping, Optional, Tuple, Union

from src.config import settings

IPNet = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
TIDAK_DIKETAHUI = "tidak-diketahui"

PRESET = {
    "privat": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7",
               "100.64.0.0/10"],
    # https://www.cloudflare.com/ips/ (diperiksa dari pengetahuan umum; perbarui bila Cloudflare mengubahnya)
    "cloudflare": ["173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
                   "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
                   "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
                   "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
                   "2a06:98c0::/29", "2c0f:f248::/32"],
}
PRESET["render"] = PRESET["privat"] + PRESET["cloudflare"]


@lru_cache(maxsize=16)
def jaringan_tepercaya(teks: str) -> Tuple[IPNet, ...]:
    hasil: List[IPNet] = []
    for bagian in (teks or "").split(","):
        b = bagian.strip().lower()
        if not b:
            continue
        for cidr in PRESET.get(b, [b]):
            hasil.append(ipaddress.ip_network(cidr, strict=False))
    return tuple(hasil)


def _ip(teks: Optional[str]) -> Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    if not teks:
        return None
    t = teks.strip().strip('"')
    if t.startswith("[") and "]" in t:          # [IPv6]:port
        t = t[1:t.index("]")]
    elif t.count(":") == 1 and "." in t:        # IPv4:port
        t = t.split(":")[0]
    try:
        ip = ipaddress.ip_address(t)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def _tepercaya(ip, jaringan: Iterable[IPNet]) -> bool:
    return any(ip.version == n.version and ip in n for n in jaringan)


def _ambil(headers: Mapping[str, str], nama: str) -> Optional[str]:
    for k, v in headers.items():
        if k.lower() == nama.lower():
            return v
    return None


def ip_klien(headers: Optional[Mapping[str, str]], peer: Optional[str],
             proxy_tepercaya: Optional[str] = None, header_klien: Optional[str] = None) -> str:
    """IP klien sebagai string; ``TIDAK_DIKETAHUI`` bila tidak dapat ditentukan."""
    proxy_tepercaya = settings.PROXY_TEPERCAYA if proxy_tepercaya is None else proxy_tepercaya
    header_klien = settings.IP_HEADER_KLIEN if header_klien is None else header_klien
    headers = headers or {}
    jaringan = jaringan_tepercaya(proxy_tepercaya)
    ip_peer = _ip(peer)
    if ip_peer is None:
        return TIDAK_DIKETAHUI
    if not jaringan or not _tepercaya(ip_peer, jaringan):
        return str(ip_peer)  # koneksi langsung dari klien/pihak tak dikenal: abaikan semua header
    if header_klien:
        ip_h = _ip(_ambil(headers, header_klien))
        if ip_h is not None:
            return str(ip_h)
    xff = _ambil(headers, "X-Forwarded-For")
    if not xff:
        return str(ip_peer)
    terakhir = ip_peer
    for bagian in reversed([b for b in xff.split(",") if b.strip()]):
        ip = _ip(bagian)
        if ip is None:
            break  # entri rusak/buatan: jangan telusuri lebih ke kiri
        if not _tepercaya(ip, jaringan):
            return str(ip)
        terakhir = ip
    return str(terakhir)


_KONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def bersihkan_ua(ua: Optional[str]) -> Optional[str]:
    if not ua:
        return None
    return _KONTROL.sub(" ", str(ua))[:256]


def ip_dan_ua() -> Tuple[str, Optional[str]]:
    """IP klien & user agent permintaan Streamlit saat ini (aman dipanggil di luar konteks Streamlit)."""
    try:
        import streamlit as st
        ctx = st.context
        headers = dict(ctx.headers) if ctx.headers is not None else {}
        peer = getattr(ctx, "ip_address", None)
    except Exception:
        return TIDAK_DIKETAHUI, None
    return ip_klien(headers, peer), bersihkan_ua(_ambil(headers, "User-Agent"))
