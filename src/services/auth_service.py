"""Layanan autentikasi, registrasi, dan sesi pengguna."""
import hashlib
import uuid
import secrets
from datetime import timedelta
from src.waktu import utc_now
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.tenant import Tenant
from src.models.token_model import Token
from src.auth.hashing import hash_password, verify_password, validate_password_strength, verifikasi_tiruan
from src.auth.jwt_handler import create_access_token, create_refresh_token, decode_token
from src.services.audit_service import catat_log
from src.models.invitation import Invitation
from src.services.email_service import (
    HasilKirim, email_akun_sudah_ada, email_reset_password, email_undangan, email_verifikasi, kirim_email,
    kirim_email_latar, teks_polos,
)
from src.config import settings

def hash_token(raw: str) -> str:
    """SHA-256 dari token acak. Hanya hash yang disimpan di DB, token mentah hanya ada di tautan email."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def buat_tautan(page: str, raw_token: str) -> str:
    return f"{settings.APP_BASE_URL}/?page={page}&token={raw_token}"


def register_lembaga(
    db: Session,
    nama_lembaga: str,
    email_admin: str,
    password: str,
    nama_admin: str
) -> Tuple[Tenant, User]:
    """Mendaftarkan lembaga baru dan akun admin pertama."""
    email_clean = email_admin.strip().lower()
    
    # Cek apakah email sudah terdaftar
    existing_user = db.query(User).filter(User.email == email_clean).first()
    if existing_user:
        raise ValueError(f"Email {email_clean} sudah terdaftar di sistem.")
        
    is_valid, pesan = validate_password_strength(password)
    if not is_valid:
        raise ValueError(pesan)
        
    # Buat slug dari nama lembaga
    base_slug = nama_lembaga.lower().replace(" ", "-").replace(".", "")
    slug = base_slug
    idx = 1
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        slug = f"{base_slug}-{idx}"
        idx += 1
        
    # Buat Tenant
    tenant = Tenant(
        id=str(uuid.uuid4()),
        nama=nama_lembaga.strip(),
        slug=slug,
        email_kontak=email_clean,
        paket="basic",
        is_active=True
    )
    db.add(tenant)
    db.flush()
    
    # Buat User Admin
    admin_user = User(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        email=email_clean,
        password_hash=hash_password(password),
        nama_lengkap=nama_admin.strip(),
        peran="admin",
        is_active=True,
        is_verified=False
    )
    db.add(admin_user)
    db.flush()
    
    # Buat token verifikasi email
    raw_token = secrets.token_urlsafe(32)
    token_obj = Token(
        id=str(uuid.uuid4()),
        user_id=admin_user.id,
        jenis="verifikasi_email",
        token_hash=hash_token(raw_token),
        expires_at=utc_now() + timedelta(hours=24)
    )
    db.add(token_obj)
    db.commit()
    
    # Kirim email verifikasi (latar belakang; kegagalan dicatat di audit tanpa alamat email)
    _kirim_verifikasi(admin_user, raw_token)
    
    catat_log(db, admin_user.id, "register_lembaga", tenant_id=tenant.id, detail={"lembaga": tenant.nama})
    return tenant, admin_user


def login(
    db: Session,
    email: str,
    password: str,
    ip: Optional[str] = None,
    ua: Optional[str] = None
) -> Optional[Tuple[str, str]]:
    """Proses login pengguna: return (access_token, refresh_token) atau None."""
    email_clean = email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()

    if not user:
        verifikasi_tiruan(password)  # samakan waktu respons (cegah enumerasi email)
        return None

    now = utc_now()
    
    # Cek lockout
    if user.locked_until and user.locked_until > now:
        # Tetap jalankan bcrypt agar waktu respons sama dengan sandi salah / email tidak ada;
        # informasi penguncian hanya masuk log audit, pengguna melihat pesan generik yang sama.
        verifikasi_tiruan(password)
        catat_log(db, user.id, "login_ditolak_terkunci", tenant_id=user.tenant_id, ip=ip, ua=ua)
        return None
        
    # Cek aktif & verifikasi (tetap jalankan bcrypt agar waktu respons seragam)
    if not user.is_active or not user.is_verified or (user.tenant is not None and not user.tenant.is_active):
        verifikasi_tiruan(password)
        return None
        
    # Cek password
    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.LOGIN_MAX_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            catat_log(db, user.id, "account_locked", tenant_id=user.tenant_id, ip=ip, ua=ua)
        db.commit()
        return None
        
    # Login sukses
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login = now
    
    access_token = create_access_token(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id) if user.tenant_id else "",
        peran=user.peran,
        email=user.email,
        sesi_versi=user.sesi_versi or 0,
    )
    refresh_token = create_refresh_token(user_id=str(user.id))
    
    # Simpan refresh token di DB
    token_obj = Token(
        id=str(uuid.uuid4()),
        user_id=user.id,
        jenis="refresh",
        token_hash=hash_token(refresh_token),
        expires_at=now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    )
    db.add(token_obj)
    db.commit()
    
    catat_log(db, user.id, "login", tenant_id=user.tenant_id, ip=ip, ua=ua)  # tanpa email (data pribadi)
    return access_token, refresh_token


def verifikasi_email(db: Session, token_str: str) -> bool:
    """Verifikasi email menggunakan token."""
    token_obj = db.query(Token).filter(
        Token.token_hash == hash_token(token_str or ""),
        Token.jenis == "verifikasi_email",
        Token.used_at == None
    ).first()
    
    if not token_obj or token_obj.is_expired:
        return False
        
    user = db.query(User).filter(User.id == token_obj.user_id).first()
    if not user:
        return False
        
    user.is_verified = True
    token_obj.used_at = utc_now()
    db.commit()
    
    catat_log(db, user.id, "email_verified", tenant_id=user.tenant_id)
    return True


def request_reset_password(db: Session, email: str, ip: Optional[str] = None, ua: Optional[str] = None) -> bool:
    """Kirim tautan reset sandi di latar belakang.

    Halaman selalu menampilkan pesan yang sama, dan waktu respons tidak bergantung pada SMTP,
    sehingga tidak membocorkan apakah email terdaftar. Nilai kembali hanya untuk tes/internal.
    """
    email_clean = email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user or not user.is_active:
        return False
        
    raw_token = secrets.token_urlsafe(32)
    token_obj = Token(
        id=str(uuid.uuid4()),
        user_id=user.id,
        jenis="reset_password",
        token_hash=hash_token(raw_token),
        expires_at=utc_now() + timedelta(hours=1)
    )
    db.add(token_obj)
    db.commit()
    
    link = buat_tautan("reset_password", raw_token)
    kirim_email_latar(user.email, "Reset Kata Sandi - Zakat Insight", email_reset_password(user.nama_lengkap, link),
                      teks_polos("Reset kata sandi Zakat Insight", link, "1 jam"), jenis="reset_password",
                      setelah=_audit_gagal_kirim(user.id, user.tenant_id, "reset_password"))
    catat_log(db, user.id, "request_reset_password", tenant_id=user.tenant_id, ip=ip, ua=ua)
    return True


def _audit_gagal_kirim(user_id, tenant_id, jenis: str):
    """Callback: catat kegagalan kirim email di audit (tanpa alamat email) memakai sesi DB baru."""
    def _cb(hasil: HasilKirim) -> None:
        if hasil.berhasil:
            return
        from src.database import get_db
        with get_db() as db2:
            catat_log(db2, user_id, "email_gagal_kirim", tenant_id=tenant_id,
                      detail={"jenis": jenis, "alasan": hasil.alasan})
    return _cb


def _kirim_verifikasi(user: User, raw_token: str):
    link = buat_tautan("verify_email", raw_token)
    return kirim_email_latar(user.email, "Verifikasi Email Lembaga - Zakat Insight",
                             email_verifikasi(user.nama_lengkap, link),
                             teks_polos("Verifikasi email Zakat Insight", link, "24 jam"), jenis="verifikasi",
                             setelah=_audit_gagal_kirim(user.id, user.tenant_id, "verifikasi"))


def kirim_ulang_verifikasi(db: Session, email: str, ip: Optional[str] = None, ua: Optional[str] = None) -> bool:
    """Kirim ulang tautan verifikasi bila akun ada dan belum terverifikasi. Pesan di halaman selalu sama."""
    user = db.query(User).filter(User.email == (email or "").strip().lower()).first()
    if not user or user.is_verified or not user.is_active:
        return False
    now = utc_now()
    db.query(Token).filter(Token.user_id == user.id, Token.jenis == "verifikasi_email",
                           Token.used_at.is_(None)).update({Token.used_at: now}, synchronize_session=False)
    raw = secrets.token_urlsafe(32)
    db.add(Token(id=str(uuid.uuid4()), user_id=user.id, jenis="verifikasi_email", token_hash=hash_token(raw),
                 expires_at=now + timedelta(hours=24)))
    db.commit()
    _kirim_verifikasi(user, raw)
    catat_log(db, user.id, "kirim_ulang_verifikasi", tenant_id=user.tenant_id, ip=ip, ua=ua)
    return True


def reset_password(db: Session, token_str: str, new_password: str,
                   ip: Optional[str] = None, ua: Optional[str] = None) -> bool:
    """Mereset password dengan token valid."""
    token_obj = db.query(Token).filter(
        Token.token_hash == hash_token(token_str or ""),
        Token.jenis == "reset_password",
        Token.used_at == None
    ).first()
    
    if not token_obj or token_obj.is_expired:
        return False
        
    is_valid, _ = validate_password_strength(new_password)
    if not is_valid:
        return False
        
    user = db.query(User).filter(User.id == token_obj.user_id).first()
    if not user:
        return False
        
    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    user.sesi_versi = (user.sesi_versi or 0) + 1  # akhiri semua sesi lama
    now = utc_now()
    token_obj.used_at = now
    # Batalkan token reset lain yang masih berlaku untuk pengguna ini
    db.query(Token).filter(
        Token.user_id == user.id, Token.jenis == "reset_password", Token.used_at.is_(None)
    ).update({Token.used_at: now}, synchronize_session=False)
    db.commit()
    
    catat_log(db, user.id, "reset_password_success", tenant_id=user.tenant_id, ip=ip, ua=ua)
    return True


def logout(db: Session, user_id: str, refresh_token: Optional[str] = None) -> None:
    """Invalidasi refresh token dan catat log logout."""
    if refresh_token:
        token_obj = db.query(Token).filter(
            Token.user_id == user_id,
            Token.token_hash == hash_token(refresh_token)
        ).first()
        if token_obj:
            token_obj.used_at = utc_now()
            db.commit()
    catat_log(db, user_id, "logout")



# ---------------------------------------------------------------------------
# Fungsi akun yang dipanggil halaman (sebelumnya tidak ada; audit S2)
# ---------------------------------------------------------------------------
PERAN_LEMBAGA = ("admin", "staf", "pembaca")
MASA_UNDANGAN_JAM = 48


class AksesDitolak(PermissionError):
    """Aksi ditolak oleh pemeriksaan peran/lembaga di lapisan layanan."""


def _wajib_admin_lembaga(oleh: dict, tenant_id: str) -> None:
    """Pemeriksaan server-side: pelaku harus admin lembaga itu (atau super admin)."""
    if not oleh:
        raise AksesDitolak("Tidak ada sesi.")
    if oleh.get("peran") == "super_admin":
        return
    if oleh.get("peran") != "admin" or str(oleh.get("tenant_id")) != str(tenant_id):
        raise AksesDitolak("Hanya admin lembaga ini yang boleh melakukan aksi ini.")


PESAN_DAFTAR_TERKIRIM = (
    "Kami telah mengirim email ke alamat yang Anda masukkan. Ikuti petunjuk di dalamnya untuk melanjutkan. "
    "Bila email tidak masuk dalam 10 menit, periksa folder spam lalu gunakan 'Kirim ulang email verifikasi' "
    "di halaman masuk."
)


def register_tenant(db: Session, nama_lembaga: str, nama_admin: str, email: str, password: str,
                    ip: Optional[str] = None, ua: Optional[str] = None):
    """Pendaftaran dari halaman publik, tanpa membocorkan apakah email sudah terdaftar.

    Email baru: lembaga + admin dibuat, email verifikasi dikirim. Email sudah terdaftar: TIDAK ada akun
    dibuat; pemilik email diberi tahu lewat email, dan bcrypt tetap dijalankan agar waktu respons sama.
    Keduanya mengembalikan nilai truthy dan halaman menampilkan PESAN_DAFTAR_TERKIRIM.
    None hanya untuk galat validasi yang tidak terkait keberadaan akun (mis. sandi lemah).
    """
    email_clean = (email or "").strip().lower()
    valid, _ = validate_password_strength(password)
    if not valid:
        return None
    ada = db.query(User).filter(User.email == email_clean).first()
    if ada:
        hash_password(password)  # samakan waktu dengan pembuatan akun baru
        kirim_email_latar(ada.email, "Percobaan pendaftaran dengan email Anda - Zakat Insight",
                          email_akun_sudah_ada(ada.nama_lengkap, settings.APP_BASE_URL,
                                               f"{settings.APP_BASE_URL}/?page=reset_password"),
                          jenis="akun_sudah_ada")
        catat_log(db, ada.id, "daftar_dengan_email_terdaftar", tenant_id=ada.tenant_id, ip=ip, ua=ua)
        return {"status": "terkirim"}
    try:
        tenant, admin = register_lembaga(db, nama_lembaga, email_clean, password, nama_admin)
    except ValueError:
        db.rollback()
        return None
    catat_log(db, admin.id, "daftar_lembaga_ip", tenant_id=tenant.id, ip=ip, ua=ua)
    return {"status": "terkirim"}


def change_password(db: Session, user_id: str, password_lama: str, password_baru: str) -> bool:
    """Ganti sandi setelah memverifikasi sandi lama; sesi lain ikut berakhir."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not verify_password(password_lama, user.password_hash):
        return False
    valid, _ = validate_password_strength(password_baru)
    if not valid:
        return False
    user.password_hash = hash_password(password_baru)
    user.sesi_versi = (user.sesi_versi or 0) + 1
    db.commit()
    catat_log(db, user.id, "ganti_password", tenant_id=user.tenant_id)
    return True


def token_akses_baru(db: Session, user_id: str) -> Optional[str]:
    """Token akses baru dengan sesi_versi terkini (dipakai setelah pengguna mengganti sandinya sendiri)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    return create_access_token(str(user.id), str(user.tenant_id) if user.tenant_id else "", user.peran,
                               user.email, user.sesi_versi or 0)


def kirim_undangan(db: Session, tenant_id: str, email: str, peran: str, oleh: dict) -> Invitation:
    """Buat undangan bertoken (disimpan sebagai hash) dan kirim tautannya ke email."""
    _wajib_admin_lembaga(oleh, tenant_id)
    if peran not in PERAN_LEMBAGA:
        raise ValueError("Peran tidak valid.")
    email_clean = email.strip().lower()
    if db.query(User).filter(User.email == email_clean).first():
        raise ValueError("Email sudah terdaftar sebagai pengguna.")
    from src.services.tenant_service import PAKET_LIMITS
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant or not tenant.is_active:
        raise ValueError("Lembaga tidak aktif.")
    batas = PAKET_LIMITS.get(tenant.paket, PAKET_LIMITS["basic"])["max_users"]
    terpakai = db.query(User).filter(User.tenant_id == tenant_id, User.is_active.is_(True)).count() + len(
        get_pending_invitations(db, tenant_id))
    if terpakai >= batas:
        raise ValueError(f"Batas anggota paket {tenant.paket} ({batas}) tercapai.")
    raw = secrets.token_urlsafe(32)
    undangan = Invitation(
        id=str(uuid.uuid4()), tenant_id=tenant_id, email=email_clean, peran=peran,
        token_hash=hash_token(raw), invited_by=oleh.get("id"),
        expires_at=utc_now() + timedelta(hours=MASA_UNDANGAN_JAM),
    )
    db.add(undangan)
    db.commit()
    tautan = buat_tautan("terima_undangan", raw)
    hasil = kirim_email(email_clean, f"Undangan bergabung ke {tenant.nama} - Zakat Insight",
                        email_undangan(tenant.nama, peran, tautan), teks_polos("Undangan Zakat Insight", tautan, "48 jam"),
                        jenis="undangan")
    undangan.email_terkirim = bool(hasil)  # atribut sementara untuk halaman Tim (tidak disimpan)
    catat_log(db, oleh.get("id"), "kirim_undangan", tenant_id=tenant_id,
              detail={"peran": peran, "email_terkirim": bool(hasil), **({} if hasil else {"alasan": hasil.alasan})})
    return undangan


def get_pending_invitations(db: Session, tenant_id: str) -> list:
    """Undangan yang belum diterima dan belum kedaluwarsa, hanya milik lembaga itu."""
    sekarang = utc_now()
    hasil = db.query(Invitation).filter(
        Invitation.tenant_id == tenant_id, Invitation.accepted_at.is_(None), Invitation.expires_at > sekarang,
    ).order_by(Invitation.created_at.desc()).all()
    return [{"id": i.id, "email": i.email, "peran": i.peran,
             "created_at": i.created_at.strftime("%d/%m/%Y %H:%M"),
             "expires_at": i.expires_at.strftime("%d/%m/%Y %H:%M")} for i in hasil]


def cancel_invitation(db: Session, invitation_id: str, tenant_id: str, oleh: dict) -> bool:
    _wajib_admin_lembaga(oleh, tenant_id)
    inv = db.query(Invitation).filter(Invitation.id == invitation_id, Invitation.tenant_id == tenant_id).first()
    if not inv:
        return False
    db.delete(inv)
    db.commit()
    catat_log(db, oleh.get("id"), "batal_undangan", tenant_id=tenant_id)
    return True


def terima_undangan(db: Session, token_str: str, nama_lengkap: str, password: str) -> Tuple[bool, str]:
    """Terima undangan: buat akun di lembaga pengundang. Email dianggap terverifikasi lewat tautan."""
    inv = db.query(Invitation).filter(
        Invitation.token_hash == hash_token(token_str or ""), Invitation.accepted_at.is_(None)).first()
    if not inv or inv.is_expired:
        return False, "Undangan tidak valid atau sudah kedaluwarsa."
    if db.query(User).filter(User.email == inv.email).first():
        return False, "Email sudah terdaftar."
    valid, pesan = validate_password_strength(password)
    if not valid:
        return False, pesan
    if not (nama_lengkap or "").strip():
        return False, "Nama lengkap wajib diisi."
    user = User(id=str(uuid.uuid4()), tenant_id=inv.tenant_id, email=inv.email, password_hash=hash_password(password),
                nama_lengkap=nama_lengkap.strip(), peran=inv.peran, is_active=True, is_verified=True)
    db.add(user)
    inv.accepted_at = utc_now()
    db.commit()
    catat_log(db, user.id, "terima_undangan", tenant_id=inv.tenant_id, detail={"peran": inv.peran})
    return True, "Akun berhasil dibuat."
