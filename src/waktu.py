"""Sumber waktu terpusat.

Kolom ``DateTime`` di model tidak menyimpan zona waktu (dan SQLite memang tidak
mendukungnya), sehingga nilai disimpan sebagai UTC *naive*, sama seperti
perilaku ``datetime.utcnow()`` sebelumnya. ``utc_now()`` memakai
``datetime.now(timezone.utc)`` (bukan ``utcnow()`` yang deprecated) lalu
melepas tzinfo agar tetap bisa dibandingkan dengan nilai dari basis data.
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Waktu UTC sekarang sebagai datetime naive (tanpa tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
