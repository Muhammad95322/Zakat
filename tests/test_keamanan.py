"""Tes regresi temuan audit keamanan (docs/AUDIT_KEAMANAN.md)."""
import contextlib
import io

import pytest

from src.config import settings
from src.models.token_model import Token
from src.services import auth_service as asv


def _minta_reset(db, user):
    """Minta reset dan kembalikan (keluaran stdout, token mentah dari tautan)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        asv.request_reset_password(db, user.email)
    keluaran = buf.getvalue()
    mentah = keluaran.split("token=")[1].split('"')[0] if "token=" in keluaran else None
    return keluaran, mentah


class TestT1TokenTidakDisimpanMentah:
    def test_token_disimpan_sebagai_sha256(self, db, admin_user):
        _, mentah = _minta_reset(db, admin_user)
        tok = db.query(Token).filter(Token.user_id == admin_user.id, Token.jenis == "reset_password").first()
        assert mentah and tok.token_hash == asv.hash_token(mentah)
        assert tok.token_hash != mentah and len(tok.token_hash) == 64

    def test_nilai_kolom_db_tidak_bisa_dipakai_untuk_reset(self, db, admin_user):
        _minta_reset(db, admin_user)
        tok = db.query(Token).filter(Token.user_id == admin_user.id, Token.jenis == "reset_password").first()
        assert asv.reset_password(db, tok.token_hash, "Diambil999X") is False  # hash bocor tidak berguna

    def test_token_mentah_dari_tautan_tetap_berfungsi(self, db, admin_user):
        _, mentah = _minta_reset(db, admin_user)
        assert asv.reset_password(db, mentah, "SandiBaru123") is True
        assert asv.reset_password(db, mentah, "SandiLagi123") is False  # sekali pakai

    def test_reset_membatalkan_token_reset_lain(self, db, admin_user):
        _, t1 = _minta_reset(db, admin_user)
        _, t2 = _minta_reset(db, admin_user)
        assert asv.reset_password(db, t2, "SandiBaru123") is True
        assert asv.reset_password(db, t1, "SandiLain123") is False

    def test_production_tanpa_smtp_tidak_mencetak_token(self, db, admin_user, monkeypatch):
        monkeypatch.setattr(settings, "APP_ENV", "production")
        keluaran, mentah = _minta_reset(db, admin_user)
        assert mentah is None and "token=" not in keluaran
        assert admin_user.email not in keluaran
        assert "Tidak dikirim" in keluaran

    def test_tautan_memakai_app_base_url(self, db, admin_user, monkeypatch):
        monkeypatch.setattr(settings, "APP_BASE_URL", "https://zakat.contoh.id")
        keluaran, _ = _minta_reset(db, admin_user)
        assert "https://zakat.contoh.id/?page=reset_password&token=" in keluaran
        assert "localhost" not in keluaran
