"""JWT token creation dan decoding."""
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from src.config import settings

_ALGORITHM = "HS256"


def create_access_token(
    user_id: str,
    tenant_id: Optional[str],
    peran: str,
    email: str,
) -> str:
    """Buat JWT access token.

    Args:
        user_id: UUID pengguna.
        tenant_id: UUID tenant (None untuk super_admin).
        peran: Peran pengguna.
        email: Email pengguna.

    Returns:
        JWT access token string.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.JWT_ACCESS_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "peran": peran,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Buat JWT refresh token.

    Args:
        user_id: UUID pengguna.

    Returns:
        JWT refresh token string.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.APP_SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode dan validasi JWT token.

    Args:
        token: JWT token string.

    Returns:
        Dict payload jika valid, None jika invalid atau expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.APP_SECRET_KEY,
            algorithms=[_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user_from_token(token: str) -> Optional[dict]:
    """Ambil informasi user dari access token.

    Args:
        token: JWT access token.

    Returns:
        Dict berisi user_id, tenant_id, peran, email; atau None jika invalid.
    """
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") != "access":
        return None
    return {
        "user_id": payload.get("sub"),
        "tenant_id": payload.get("tenant_id"),
        "peran": payload.get("peran"),
        "email": payload.get("email"),
    }
