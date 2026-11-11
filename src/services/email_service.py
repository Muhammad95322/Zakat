"""Layanan pengiriman email notifikasi dan verifikasi."""
import smtplib
from html import escape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from src.config import settings

def kirim_email(to_email: str, subject: str, body_html: str) -> bool:
    """Mengirim email HTML via SMTP atau print ke console jika dinonaktifkan."""
    if not settings.EMAIL_ENABLED:
        if settings.is_production:
            # Jangan pernah menulis isi email (berisi tautan bertoken) ke log production.
            print(f"[EMAIL] Tidak dikirim karena EMAIL_ENABLED=false: '{subject}'. Atur SMTP untuk production.")
            return False
        print("\n================ [EMAIL SIMULASI - hanya development] ================")
        print(f"Kepada  : {to_email}")
        print(f"Subjek  : {subject}")
        print(f"Isi     :\n{body_html}")
        print("======================================================================\n")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = to_email
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT) as server:
            server.starttls()
            if settings.EMAIL_SMTP_USER and settings.EMAIL_SMTP_PASS:
                server.login(settings.EMAIL_SMTP_USER, settings.EMAIL_SMTP_PASS)
            server.sendmail(settings.EMAIL_FROM, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Gagal mengirim email: {e}")
        return False

def email_verifikasi(nama: str, link: str) -> str:
    nama, link = escape(nama), escape(link)
    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0d9488;">Selamat Datang di Zakat Insight</h2>
        <p>Halo <b>{nama}</b>,</p>
        <p>Terima kasih telah mendaftarkan lembaga Anda di Zakat Insight. Silakan klik tombol di bawah ini untuk memverifikasi alamat email Anda:</p>
        <p><a href="{link}" style="display: inline-block; padding: 10px 20px; background-color: #0d9488; color: white; text-decoration: none; border-radius: 5px;">Verifikasi Email Saya</a></p>
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
        <p><a href="{link}" style="display: inline-block; padding: 10px 20px; background-color: #0d9488; color: white; text-decoration: none; border-radius: 5px;">Reset Kata Sandi</a></p>
        <p>Tautan ini berlaku selama 1 jam. Jika Anda tidak meminta reset ini, abaikan email ini.</p>
    </div>
    """

def email_undangan(nama_lembaga: str, peran: str, link: str) -> str:
    nama_lembaga, peran, link = escape(nama_lembaga), escape(peran), escape(link)
    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0d9488;">Undangan Bergabung ke Zakat Insight</h2>
        <p>Anda telah diundang untuk bergabung dengan tim <b>{nama_lembaga}</b> sebagai <b>{peran}</b> di Zakat Insight.</p>
        <p><a href="{link}" style="display: inline-block; padding: 10px 20px; background-color: #0d9488; color: white; text-decoration: none; border-radius: 5px;">Terima Undangan</a></p>
        <p>Tautan ini berlaku selama 48 jam.</p>
    </div>
    """

