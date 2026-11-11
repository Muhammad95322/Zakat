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


RUMUS = ['=HYPERLINK("http://contoh.invalid","klik")', "+1+1", "-2+3", "@SUM(1)", "\t=1+1", "=cmd|' /C calc'!A0"]


class TestT2InjeksiRumus:
    def test_netralkan_nilai(self):
        from src.ekspor_aman import netralkan_nilai
        for v in RUMUS:
            assert netralkan_nilai(v) == "'" + v
        assert netralkan_nilai("Budi") == "Budi"
        assert netralkan_nilai("-") == "-"            # pengisi tunggal tidak berbahaya
        assert netralkan_nilai(-5000.0) == -5000.0    # angka tidak disentuh
        assert netralkan_nilai(None) is None

    def test_ekspor_excel_tanpa_sel_rumus(self):
        import io as _io
        import openpyxl
        import pandas as pd
        from src.report_excel import generate_excel_report
        from src.rfm import segment_rfm
        df = pd.DataFrame({
            "id_muzaki": [f"M{i}" for i in range(len(RUMUS))],
            "nama_muzaki": RUMUS,
            "tanggal": pd.date_range("2024-01-01", periods=len(RUMUS)),
            "jumlah": [100.0, -5.0, 300.0, 400.0, 500.0, 600.0],
        })
        rfm, _ = segment_rfm(df)
        x = generate_excel_report(df, {"total_dana": 1}, rfm, None, [{"aksi": "=1+1", "jumlah_baris": 1}])
        wb = openpyxl.load_workbook(_io.BytesIO(x))
        sel_rumus = [(ws.title, c.coordinate, c.value) for ws in wb for row in ws.iter_rows() for c in row
                     if c.data_type == "f"]
        assert sel_rumus == []
        nama = [c.value for c in wb["Data Bersih"]["B"][1:]]
        assert nama == ["'" + v for v in RUMUS]
        assert wb["Data Bersih"]["D3"].value == -5.0  # angka negatif tetap angka

    def test_csv_log_audit(self):
        import pandas as pd
        from src.ekspor_aman import ke_csv_aman
        csv = ke_csv_aman(pd.DataFrame({"Detail": RUMUS})).decode("utf-8")
        baris = csv.splitlines()[1:]
        assert all(b.lstrip('"').startswith("'") for b in baris)
        import inspect
        import src.pages.pg_audit as pa
        assert "ke_csv_aman(df_logs)" in inspect.getsource(pa)
