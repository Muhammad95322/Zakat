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
from src.auth.hashing import hash_password, verify_password, validate_password_strength
from src.auth.jwt_handler import create_access_token, create_refresh_token, decode_token
from src.services.audit_service import catat_log
from src.services.email_service import kirim_email, email_verifikasi, email_reset_password
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
    
    # Kirim email verifikasi
    verify_link = buat_tautan("verify_email", raw_token)
    body = email_verifikasi(admin_user.nama_lengkap, verify_link)
    kirim_email(admin_user.email, "Verifikasi Email Lembaga - Zakat Insight", body)
    
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
        return None
        
    now = utc_now()
    
    # Cek lockout
    if user.locked_until and user.locked_until > now:
        return None
        
    # Cek aktif & verifikasi
    if not user.is_active or not user.is_verified:
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
        email=user.email
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
    
    catat_log(db, user.id, "login", tenant_id=user.tenant_id, detail={"email": user.email}, ip=ip, ua=ua)
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


def request_reset_password(db: Session, email: str) -> bool:
    """Mengirim tautan reset kata sandi ke email pengguna."""
    email_clean = email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
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
    body = email_reset_password(user.nama_lengkap, link)
    kirim_email(user.email, "Reset Kata Sandi - Zakat Insight", body)
    
    catat_log(db, user.id, "request_reset_password", tenant_id=user.tenant_id)
    return True


def reset_password(db: Session, token_str: str, new_password: str) -> bool:
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
    now = utc_now()
    token_obj.used_at = now
    # Batalkan token reset lain yang masih berlaku untuk pengguna ini
    db.query(Token).filter(
        Token.user_id == user.id, Token.jenis == "reset_password", Token.used_at.is_(None)
    ).update({Token.used_at: now}, synchronize_session=False)
    db.commit()
    
    catat_log(db, user.id, "reset_password_success", tenant_id=user.tenant_id)
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

