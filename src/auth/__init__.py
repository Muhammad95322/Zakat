"""Auth package."""
from src.auth.hashing import hash_password, verify_password, validate_password_strength
from src.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user_from_token,
)
from src.auth.session import (
    get_current_user,
    set_current_user,
    clear_session,
    is_logged_in,
    get_user_role,
    get_tenant_id,
    require_login,
    has_permission,
)
from src.auth.decorators import check_role

__all__ = [
    "hash_password",
    "verify_password",
    "validate_password_strength",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_user_from_token",
    "get_current_user",
    "set_current_user",
    "clear_session",
    "is_logged_in",
    "get_user_role",
    "get_tenant_id",
    "require_login",
    "has_permission",
    "check_role",
]
