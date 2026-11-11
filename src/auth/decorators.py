"""Dekorator dan helper pengecekan hak akses."""
from typing import List, Dict, Any
from src.auth.session import get_current_user

def check_role(user: Dict[str, Any], allowed_roles: List[str]) -> bool:
    """Memeriksa apakah user memiliki peran yang diizinkan."""
    if not user:
        return False
    user_role = user.get("peran")
    return user_role in allowed_roles

