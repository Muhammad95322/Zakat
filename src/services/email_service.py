"""Pengiriman email (verifikasi, reset sandi, undangan) lewat SMTP dengan TLS wajib.

Prinsip:
- TLS selalu wajib: STARTTLS (port 587/2525) atau SSL langsung (port 465), dengan verifikasi sertifikat.
  Bila server tidak mendukung STARTTLS, pengiriman DIBATALKAN (tidak pernah kirim/login tanpa enkripsi).
- Timeout koneksi (EMAIL_SMTP_TIMEOUT) agar halaman tidak menggantung.
- Log tidak memuat alamat penerima, isi, atau tautan bertoken; hanya jenis email dan jenis galat.
- ``kirim_email_latar`` mengirim di thread latar sehingga waktu respons halaman tidak bergantung pada
  SMTP (mencegah enumerasi email lewat waktu: email terdaftar vs tidak).
"""
import logging
import smtplib
import ssl
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from typing import Callable, Optional

from src.config import settings

logger = logging.getLogger("zakat.email")
_eksekutor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email")


@dataclass
class HasilKirim:
    berhasil: bool
    alasan: str = ""   # kode singkat untuk log/audit, BUKAN untuk ditampilkan apa adanya ke pengguna

    def __bool__(self) -> bool:
        return self.berhasil


def mode_tls() -> str:
    m = settings.EMAIL_SMTP_TLS or ("ssl" if settings.EMAIL_SMTP_PORT == 465 else "starttls")
    if m not in ("ssl", "starttls"):
        raise ValueError("EMAIL_SMTP_TLS harus 'starttls' atau 'ssl' (TLS tidak boleh dimatikan).")
    return m


def _konteks_tls() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=settings.EMAIL_SMTP_CA_FILE or None)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _susun(to_email: str, subject: str, body_html: str, teks: Optional[str]) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=(settings.EMAIL_FROM.split("@")[-1] or None))
    msg.set_content(teks or "Buka email ini di aplikasi email yang mendukung HTML.")
    msg.add_alternative(body_html, subtype="html")
    return msg


def kirim_email(to_email: str, subject: str, body_html: str, teks: Optional[str] = None,
                jenis: str = "umum") -> HasilKirim:
    """Kirim satu email secara sinkron. Tidak pernah melempar exception."""
    if not settings.EMAIL_ENABLED:
        if settings.is_production:
            logger.error("email tidak dikirim: EMAIL_ENABLED=false", extra={"jenis_email": jenis})
            return HasilKirim(False, "email_nonaktif")
        # development: tampilkan di konsol agar alur verifikasi/reset bisa dicoba tanpa SMTP
        print("\n================ [EMAIL SIMULASI - hanya development] ================")
        print(f"Kepada  : {to_email}\nSubjek  : {subject}\nIsi     :\n{body_html}")
        print("======================================================================\n")
        return HasilKirim(True, "simulasi")
    if not settings.EMAIL_SMTP_HOST:
        logger.error("email tidak dikirim: EMAIL_SMTP_HOST kosong", extra={"jenis_email": jenis})
        return HasilKirim(False, "konfigurasi")
    try:
        mode = mode_tls()
        msg = _susun(to_email, subject, body_html, teks)
        ctx = _konteks_tls()
        host, port, t = settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT, settings.EMAIL_SMTP_TIMEOUT
        if mode == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=t, context=ctx)
        else:
            server = smtplib.SMTP(host, port, timeout=t)
        with server:
            server.ehlo()
            if mode == "starttls":
                if not server.has_extn("starttls"):
                    raise smtplib.SMTPNotSupportedError("server tidak menawarkan STARTTLS")
                server.starttls(context=ctx)
                server.ehlo()
            if settings.EMAIL_SMTP_USER:
                server.login(settings.EMAIL_SMTP_USER, settings.EMAIL_SMTP_PASS)
            server.send_message(msg)
        logger.info("email terkirim", extra={"jenis_email": jenis})
        return HasilKirim(True)
    except Exception as e:  # jaringan, TLS, autentikasi, penolakan penerima, timeout
        alasan = _kode_galat(e)
        logger.warning("email gagal dikirim", extra={"jenis_email": jenis, "alasan": alasan,
                                                     "galat": type(e).__name__})
        return HasilKirim(False, alasan)


def _kode_galat(e: Exception) -> str:
    if isinstance(e, smtplib.SMTPNotSupportedError):
        return "tls_tidak_didukung"
    if isinstance(e, ssl.SSLError):
        return "tls_gagal"
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "autentikasi"
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "penerima_ditolak"
    if isinstance(e, (TimeoutError, OSError)) and "timed out" in str(e).lower():
        return "timeout"
    if isinstance(e, (ConnectionError, OSError)):
        return "koneksi"
    return "lainnya"


def kirim_email_latar(to_email: str, subject: str, body_html: str, teks: Optional[str] = None,
                      jenis: str = "umum", setelah: Optional[Callable[[HasilKirim], None]] = None) -> Future:
    """Kirim di thread latar; ``setelah(hasil)`` dipanggil sesudahnya (mis. mencatat audit)."""
    def _tugas() -> HasilKirim:
        hasil = kirim_email(to_email, subject, body_html, teks, jenis)
        if setelah is not None:
            try:
                setelah(hasil)
            except Exception:
                logger.exception("callback setelah kirim email gagal")
        return hasil
    if not settings.EMAIL_ENABLED:
        # simulasi/nonaktif: tanpa jaringan sehingga tidak ada selisih waktu yang perlu disembunyikan
        f: Future = Future()
        f.set_result(_tugas())
        return f
    return _eksekutor.submit(_tugas)


# ---------------------------------------------------------------------------
# Templat (semua nilai di-escape)
# ---------------------------------------------------------------------------
_TOMBOL = ("display: inline-block; padding: 10px 20px; background-color: #0d9488; color: white; "
           "text-decoration: none; border-radius: 5px;")


def email_verifikasi(nama: str, link: str) -> str:
    nama, link = escape(nama), escape(link)
    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0d9488;">Selamat Datang di Zakat Insight</h2>
        <p>Halo <b>{nama}</b>,</p>
        <p>Terima kasih telah mendaftarkan lembaga Anda di Zakat Insight. Silakan klik tombol di bawah ini untuk memverifikasi alamat email Anda:</p>
        <p><a href="{link}" style="{_TOMBOL}">Verifikasi Email Saya</a></p>
        <p>Jika tombol di atas tidak berfungsi, salin dan buka tautan ini di browser Anda:<br><a href="{link}">{link}</a></p>
        <p>Tautan ini berlaku selama 24 jam.</p>
    </div>
    """


def email_reset_password(nama: str, link: str) -> str:
    nama, link = escape(nama), escape(link)
    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0d9488;">Permintaan Reset Kata Sandi</h2>
        <p>Halo <b>{nama}</b>,</p>
        <p>Kami menerima permintaan untuk mereset kata sandi akun Zakat Insight Anda. Klik tombol di bawah ini untuk membuat kata sandi baru:</p>
        <p><a href="{link}" style="{_TOMBOL}">Reset Kata Sandi</a></p>
        <p>Tautan ini berlaku selama 1 jam. Jika Anda tidak meminta reset ini, abaikan email ini.</p>
    </div>
    """


def email_akun_sudah_ada(nama: str, link_login: str, link_reset: str) -> str:
    nama, link_login, link_reset = escape(nama), escape(link_login), escape(link_reset)
    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0d9488;">Percobaan Pendaftaran dengan Email Anda</h2>
        <p>Halo <b>{nama}</b>,</p>
        <p>Seseorang mencoba mendaftarkan lembaga baru di Zakat Insight memakai alamat email ini, padahal email ini
        sudah memiliki akun. Tidak ada akun baru yang dibuat.</p>
        <p>Bila itu Anda, silakan <a href="{link_login}">masuk</a> atau <a href="{link_reset}">reset kata sandi</a>.
        Bila bukan, abaikan email ini.</p>
    </div>
    """


def email_undangan(nama_lembaga: str, peran: str, link: str) -> str:
    nama_lembaga, peran, link = escape(nama_lembaga), escape(peran), escape(link)
    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0d9488;">Undangan Bergabung ke Zakat Insight</h2>
        <p>Anda telah diundang untuk bergabung dengan tim <b>{nama_lembaga}</b> sebagai <b>{peran}</b> di Zakat Insight.</p>
        <p><a href="{link}" style="{_TOMBOL}">Terima Undangan</a></p>
        <p>Tautan ini berlaku selama 48 jam.</p>
    </div>
    """


def teks_polos(judul: str, link: str, berlaku: str) -> str:
    return f"{judul}\n\nBuka tautan berikut di browser:\n{link}\n\nTautan berlaku {berlaku}. Abaikan bila Anda tidak memintanya."
