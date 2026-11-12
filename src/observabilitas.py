"""Observabilitas tanpa data pribadi: log JSON terstruktur, pembersih PII, dan Sentry opsional.

Prinsip:
- Teks log dibersihkan dari email, nomor HP, NIK/nomor panjang, token/JWT, dan pasangan sandi=...
- PESAN exception TIDAK PERNAH dicatat/dikirim (bisa memuat isi sel berkas donatur atau parameter SQL);
  yang dicatat hanya jenis exception dan lokasi baris kode (berkas:baris:fungsi).
- Sentry hanya aktif bila SENTRY_DSN diisi dan paket sentry-sdk terpasang; tanpa PII, tanpa variabel lokal,
  tanpa isi permintaan, dan event dibersihkan lagi di ``before_send``.
"""
import json
import logging
import re
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.config import settings

_POLA = [
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[JWT]"),
    (re.compile(r"(?i)\b(token|kode|code|sandi|password|passwd|pwd|secret|rahasia|api[_-]?key|dsn)"
                r"(\s*[=:]\s*|=)[^\s&\"',;]+"), r"\1=[DISENSOR]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [DISENSOR]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"(?<![\d])(?:\+?62[\s.-]?|0)8\d{1,3}(?:[\s.-]?\d){6,9}(?![\d])"), "[HP]"),
    (re.compile(r"(?<![\d])\d(?:[\s.-]?\d){9,19}(?![\d])"), "[NOMOR]"),
    (re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://)[^@\s]+@"), r"\1[KREDENSIAL]@"),
]


def bersihkan_pii(teks: Any) -> str:
    s = str(teks)
    for rx, ganti in _POLA:
        s = rx.sub(ganti, s)
    return s


def ringkas_exception(exc_info) -> Dict[str, Any]:
    """Jenis + lokasi stack (tanpa pesan exception & tanpa nilai variabel)."""
    tipe, _, tb = exc_info
    frames = [f"{f.filename.rsplit('/', 1)[-1]}:{f.lineno}:{f.name}" for f in traceback.extract_tb(tb)][-15:]
    return {"jenis": getattr(tipe, "__name__", str(tipe)), "lokasi": frames}


_ATRIBUT_BAWAAN = set(vars(logging.LogRecord("x", 0, "", 0, "", None, None)).keys()) | {"message", "asctime"}


class FormatJSON(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: Dict[str, Any] = {
            "waktu": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "pesan": bersihkan_pii(record.getMessage()),
        }
        for k, v in record.__dict__.items():
            if k not in _ATRIBUT_BAWAAN and not k.startswith("_"):
                data[k] = v if isinstance(v, (int, float, bool)) or v is None else bersihkan_pii(v)
        if record.exc_info and record.exc_info[0] is not None:
            data["exception"] = ringkas_exception(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


class FormatTeks(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        s = f"{record.levelname} {record.name}: {bersihkan_pii(record.getMessage())}"
        if record.exc_info and record.exc_info[0] is not None:
            r = ringkas_exception(record.exc_info)
            s += f" [{r['jenis']} @ {' > '.join(r['lokasi'][-3:])}]"
        return s


_SUDAH = {"log": False, "sentry": False}


def atur_logging(paksa: bool = False) -> None:
    if _SUDAH["log"] and not paksa:
        return
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(FormatJSON() if settings.LOG_FORMAT == "json" else FormatTeks())
    akar = logging.getLogger()
    for lama in [x for x in akar.handlers if getattr(x, "_zakat", False)]:
        akar.removeHandler(lama)
    h._zakat = True  # type: ignore[attr-defined]
    akar.addHandler(h)
    akar.setLevel(settings.LOG_LEVEL if settings.LOG_LEVEL in logging._nameToLevel else "INFO")
    _SUDAH["log"] = True


# ---------------------------------------------------------------------------
# Sentry (opsional)
# ---------------------------------------------------------------------------
def _bersihkan_nilai(v: Any) -> Any:
    if isinstance(v, str):
        return bersihkan_pii(v)
    if isinstance(v, dict):
        return {k: _bersihkan_nilai(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_bersihkan_nilai(x) for x in v]
    return v


def bersihkan_event(event: Dict[str, Any], hint: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """before_send Sentry: buang isi permintaan, pengguna, extra, variabel lokal, dan PESAN exception."""
    from src.loader import DataFileError
    exc = (hint or {}).get("exc_info")
    if exc is not None and len(exc) > 1 and isinstance(exc[1], DataFileError):
        return None  # galat isi berkas pengguna: bukan bug, dan pesannya memuat isi sel
    for kunci in ("request", "user", "extra", "server_name", "modules"):
        event.pop(kunci, None)
    for nilai in (event.get("exception") or {}).get("values", []) or []:
        nilai["value"] = "[pesan exception tidak dikirim]"
        for fr in (nilai.get("stacktrace") or {}).get("frames", []) or []:
            fr.pop("vars", None)
            fr.pop("pre_context", None)
            fr.pop("post_context", None)
            fr.pop("context_line", None)
    if "logentry" in event:
        le = event["logentry"]
        le["message"] = bersihkan_pii(le.get("message", ""))
        le.pop("params", None)
        le.pop("formatted", None)
    if "message" in event:
        event["message"] = bersihkan_pii(event["message"])
    bc = event.get("breadcrumbs")
    daftar = bc.get("values", []) if isinstance(bc, dict) else (bc or [])
    for b in daftar:
        b.pop("data", None)
        if "message" in b:
            b["message"] = bersihkan_pii(b["message"])
    if "tags" in event:
        event["tags"] = _bersihkan_nilai(event["tags"])
    return event


def bersihkan_breadcrumb(crumb: Dict[str, Any], hint=None) -> Optional[Dict[str, Any]]:
    crumb.pop("data", None)
    if "message" in crumb:
        crumb["message"] = bersihkan_pii(crumb["message"])
    return crumb


def atur_sentry() -> bool:
    """Aktifkan Sentry bila SENTRY_DSN diisi. Kembalikan True bila aktif."""
    if _SUDAH["sentry"] or not settings.SENTRY_DSN:
        return _SUDAH["sentry"]
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger("zakat.observabilitas").warning("SENTRY_DSN diisi tetapi paket sentry-sdk tidak terpasang")
        return False
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_LINGKUNGAN or settings.APP_ENV,
        release=settings.APP_VERSION,
        send_default_pii=False,
        include_local_variables=False,
        include_source_context=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=bersihkan_event,
        before_breadcrumb=bersihkan_breadcrumb,
    )
    _SUDAH["sentry"] = True
    return True
