"""Header keamanan, CSRF, dan IP/UA klien untuk frontend web.

``ip_dan_ua`` adalah padanan ``src.middleware.ip_klien.ip_dan_ua`` (yang membaca ``st.context``):
ia memanggil ``ip_klien`` dan ``bersihkan_ua`` dari modul yang sama, sehingga aturan proxy tepercaya
(PROXY_TEPERCAYA, IP_HEADER_KLIEN) identik dengan versi Streamlit.
"""
import hmac
import secrets
from typing import Optional, Tuple
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.config import settings
from src.middleware.ip_klien import bersihkan_ua, ip_klien

# Plotly.js menyisipkan elemen <style> dan atribut style saat menggambar grafik, jadi style-src
# memerlukan 'unsafe-inline'. Skrip TIDAK: hanya berkas dari origin sendiri, tanpa inline dan tanpa eval.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

HEADER_KEAMANAN = {
    "content-security-policy": CSP,
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "cross-origin-opener-policy": "same-origin",
}


class HeaderKeamanan:
    """Middleware ASGI murni: tambahkan header keamanan ke setiap respons HTTP."""

    def __init__(self, app: ASGIApp, produksi: Optional[bool] = None):
        self.app = app
        self.produksi = produksi  # None = baca APP_ENV pada setiap permintaan

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def kirim(pesan: Message) -> None:
            if pesan["type"] == "http.response.start":
                headers = [(k, v) for k, v in pesan.get("headers", [])
                           if k.decode().lower() not in HEADER_KEAMANAN]
                headers += [(k.encode(), v.encode()) for k, v in HEADER_KEAMANAN.items()]
                if settings.is_production if self.produksi is None else self.produksi:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                jalur = scope.get("path", "")
                if not jalur.startswith("/statis/"):
                    headers.append((b"cache-control", b"no-store"))  # halaman berisi data lembaga
                pesan["headers"] = headers
            await send(pesan)

        await self.app(scope, receive, kirim)


def ip_dan_ua(request: Request) -> Tuple[str, Optional[str]]:
    peer = request.client.host if request.client else None
    return ip_klien(dict(request.headers), peer), bersihkan_ua(request.headers.get("user-agent"))


def token_baru() -> str:
    return secrets.token_urlsafe(32)


def token_cocok(dikirim: Optional[str], seharusnya: Optional[str]) -> bool:
    if not dikirim or not seharusnya:
        return False
    return hmac.compare_digest(dikirim.encode(), seharusnya.encode())


def asal_sah(request: Request) -> bool:
    """Header Origin (bila ada) harus sama dengan host yang dilayani. Lapisan tambahan di atas token CSRF."""
    origin = request.headers.get("origin")
    if not origin or origin == "null":
        return origin is None
    host = request.headers.get("host", "")
    return urlsplit(origin).netloc == host
