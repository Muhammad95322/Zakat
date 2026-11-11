"""Uji Autentikasi, Password Hashing, Validasi Kekuatan Password, dan JWT."""
import uuid
import pytest
from src.auth.hashing import hash_password, verify_password, validate_password_strength
from src.auth.jwt_handler import create_access_token, create_refresh_token, decode_token
from src.services.auth_service import login

class TestPasswordAndSecurity:
    def test_hashing_and_verification(self):
        pw = "Rahasia123"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True
        assert verify_password("Salah123", hashed) is False

    def test_password_strength(self):
        # Kurang dari 8 karakter
        ok, msg = validate_password_strength("Abc1")
        assert ok is False
        assert "8" in msg
        
        # Tanpa huruf besar
        ok, msg = validate_password_strength("rahasia123")
        assert ok is False
        
        # Tanpa angka
        ok, msg = validate_password_strength("RahasiaBagus")
        assert ok is False
        
        # Valid
        ok, msg = validate_password_strength("Rahasia123")
        assert ok is True

    def test_jwt_tokens(self):
        u_id = str(uuid.uuid4())
        token = create_access_token(u_id, "tenant-1", "admin", "test@test.com")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == u_id
        assert payload["peran"] == "admin"
        
        # Token acak invalid
        assert decode_token("token.palsu.acak") is None


class TestLoginFlow:
    def test_login_sukses(self, db, admin_user):
        res = login(db, admin_user.email, "Admin123")
        assert res is not None
        access, refresh = res
        assert len(access) > 10
        assert len(refresh) > 10

    def test_login_password_salah(self, db, admin_user):
        res = login(db, admin_user.email, "PasswordSalah")
        assert res is None

    def test_login_email_tidak_ada(self, db):
        res = login(db, "email.ngawur@test.id", "Password123")
        assert res is None

