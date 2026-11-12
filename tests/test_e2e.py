"""Alur ujung ke ujung dengan data sintetis + skenario kegagalan yang ramah pengguna."""
import io
import os
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.analysis import (
    get_composition_analysis, get_distribution_analysis, get_summary_stats, get_trend_analysis,
)
from src.forecasting import forecast_donations, format_mape
from src.pipeline import siapkan_data
from src.report_excel import generate_excel_report
from src.report_pdf import generate_pdf_report
from src.rfm import segment_rfm
from src.sample_data import generate_sample_data

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def berkas_sintetis():
    df_h, df_s = generate_sample_data(3000, 400)
    # Tambah baris kotor yang harus dibuang
    kotor = pd.DataFrame([
        {**df_h.iloc[0].to_dict(), "jumlah": "bukan angka"},
        {**df_h.iloc[1].to_dict(), "jumlah": -75_000},
        {**df_h.iloc[2].to_dict(), "jumlah": 0},
        {**df_h.iloc[3].to_dict(), "tanggal": "tanggal-rusak", "id_muzaki": "MZK-X"},
    ])
    df_h = pd.concat([df_h, kotor], ignore_index=True)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_h.to_excel(w, sheet_name="Penghimpunan", index=False)
        df_s.to_excel(w, sheet_name="Penyaluran", index=False)
    return buf.getvalue()


def _total_pandas_langsung(xlsx: bytes) -> float:
    raw = pd.read_excel(io.BytesIO(xlsx), sheet_name="Penghimpunan").drop_duplicates()
    jumlah = pd.to_numeric(raw["jumlah"], errors="coerce")
    tanggal = pd.to_datetime(raw["tanggal"], errors="coerce", format="%Y-%m-%d")
    return float(jumlah[(jumlah > 0) & tanggal.notna()].sum())


def test_alur_ujung_ke_ujung(berkas_sintetis):
    hasil = siapkan_data(berkas_sintetis, "sintetis.xlsx")
    df = hasil["df_himpun"]

    stats = get_summary_stats(df)
    assert stats["total_dana"] == pytest.approx(_total_pandas_langsung(berkas_sintetis))
    assert stats["total_transaksi"] == len(df)

    trend = get_trend_analysis(df)
    assert trend["monthly"]["total_dana"].sum() == pytest.approx(stats["total_dana"])
    comp = get_composition_analysis(df)
    assert comp["jenis_dana"]["total"].sum() == pytest.approx(stats["total_dana"])

    rfm_df, rfm_meta = segment_rfm(df)
    assert rfm_df["monetary"].sum() == pytest.approx(stats["total_dana"])
    assert 0 <= rfm_meta["gini_index"] <= 1

    dist = get_distribution_analysis(df, hasil["df_salur"])
    fdf, meta = forecast_donations(trend["monthly"])
    assert len(fdf) == 12
    assert meta["mape"] is None or isinstance(meta["mape"], float)

    pdf = generate_pdf_report("Lembaga Sintetis", stats, dist, rfm_meta,
                              trend["monthly"], comp["jenis_dana"], fdf, meta)
    assert pdf.startswith(b"%PDF") and len(pdf) > 20_000

    xlsx = generate_excel_report(df, stats, rfm_df, fdf, hasil["log_himpun"])
    sheets = pd.read_excel(io.BytesIO(xlsx), sheet_name=None)
    assert {"Data Bersih", "Ringkasan KPI", "Segmentasi RFM", "Proyeksi Dana", "Log Pembersihan"} <= set(sheets)
    kpi = sheets["Ringkasan KPI"].set_index("Metrik")["Nilai"]
    assert float(kpi["Total Penghimpunan"]) == pytest.approx(stats["total_dana"])
    assert sheets["Data Bersih"]["jumlah"].sum() == pytest.approx(stats["total_dana"])


def test_tanpa_statsmodels_label_dan_peringatan_jujur():
    """Jalankan di proses terpisah yang memblokir import statsmodels."""
    kode = (
        "import sys; sys.modules['statsmodels'] = None\n"
        "from src.sample_data import generate_sample_data\n"
        "from src.pipeline import siapkan_data\n"
        "from src.cleaning import clean_data\n"
        "from src.analysis import get_trend_analysis\n"
        "from src.forecasting import forecast_donations, format_mape\n"
        "h, _ = generate_sample_data(1500, 10)\n"
        "c, _, _ = clean_data(h)\n"
        "_, m = forecast_donations(get_trend_analysis(c)['monthly'])\n"
        "print('METODE=' + m['metode']); print('FALLBACK=' + str(m['fallback']))\n"
        "print('ALASAN=' + str(m['fallback_alasan'])); print('MAPE=' + format_mape(m))\n"
        "hw = [b for b in m['perbandingan'] if b['kode'] == 'holt_winters'][0]\n"
        "print('HW_MAPE=' + str(hw['mape'])); print('HW_STATUS=' + hw['status'])\n"
        "terbaik = min(b['mape'] for b in m['perbandingan'] if b['mape'] is not None)\n"
        "print('TERBAIK=' + str(terbaik))\n"
    )
    hasil = subprocess.run([sys.executable, "-c", kode], capture_output=True, text=True, cwd=str(ROOT))
    assert hasil.returncode == 0, hasil.stderr
    out = hasil.stdout
    assert "METODE=Holt-Winters" not in out          # label jujur: HW tidak dipakai
    assert "FALLBACK=True" in out
    assert "statsmodels tidak dapat diimpor" in out
    assert "HW_MAPE=None" in out                      # tidak ada angka karangan untuk HW
    assert "HW_STATUS=tidak tersedia" in out
    mape = out.split("\nMAPE=")[1].split("\n")[0].strip()
    terbaik = float(out.split("TERBAIK=")[1].split("\n")[0])
    assert float(mape.rstrip("%")) == pytest.approx(terbaik)  # MAPE = metode terpilih
    assert float(mape.rstrip("%")) not in {18.5, 12.4, 14.2}


def test_app_menolak_start_di_production_dengan_kunci_bawaan(tmp_path):
    pytest.importorskip("streamlit.testing.v1")
    kode = (
        "from streamlit.testing.v1 import AppTest\n"
        "at = AppTest.from_file('app.py', default_timeout=30).run()\n"
        "print('ERRORS=' + ' | '.join(e.value for e in at.error))\n"
        "print('EXC=' + str(len(at.exception)))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "APP_SECRET_KEY"}
    env.update({"APP_ENV": "production", "DATABASE_URL": f"sqlite:///{tmp_path}/app.db"})
    hasil = subprocess.run([sys.executable, "-c", kode], capture_output=True, text=True, cwd=str(ROOT), env=env)
    assert hasil.returncode == 0, hasil.stderr
    assert "konfigurasi tidak aman" in hasil.stdout
    assert "EXC=0" in hasil.stdout
    assert not (tmp_path / "app.db").exists()  # DB tidak diinisialisasi


class TestBerkasRusakDitolakRamah:
    """Berkas rusak ditolak saat unggah dengan pesan ramah, tanpa stack trace."""

    @staticmethod
    def _xlsx(sheets):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            for n, d in sheets.items():
                d.to_excel(w, sheet_name=n, index=False)
        return buf.getvalue()

    @pytest.mark.parametrize("nama, konten_fn, potongan_pesan", [
        ("kolom_hilang.xlsx", lambda s: s._xlsx({"Penghimpunan": pd.DataFrame({"tanggal": ["2024-01-01"], "nama": ["A"]})}), "kolom wajib"),
        ("sheet_kosong.xlsx", lambda s: s._xlsx({"Penghimpunan": pd.DataFrame()}), "kosong"),
        ("teks_angka.csv", lambda s: b"tanggal,jumlah\n2024-01-01,abc\n2024-01-02,tidak tahu\n", "Tidak ada baris penghimpunan yang valid"),
        ("rusak.xlsx", lambda s: b"PK\x03\x04sampah", "rusak"),
    ])
    def test_simpan_upload_menolak(self, db, sample_tenant, admin_user, tmp_path, monkeypatch,
                                   nama, konten_fn, potongan_pesan):
        from src.config import settings
        from src.services.upload_service import simpan_upload
        monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
        upload, pesan = simpan_upload(db, sample_tenant.id, admin_user.id, konten_fn(self), nama)
        assert upload is None
        assert potongan_pesan in pesan
        assert "Traceback" not in pesan
        assert not any(tmp_path.rglob("*.*"))


_SKRIP_UI = r'''
import io, os, sys, uuid
sys.path.insert(0, os.environ["ROOT"])
if os.getenv("BLOK_SM"):
    sys.modules["statsmodels"] = None
import pandas as pd
from src.database import init_db, get_db
from src.models.tenant import Tenant
from src.models.user import User
from src.auth.hashing import hash_password
from src.services.upload_service import simpan_upload
from src.sample_data import generate_sample_data
init_db()
with get_db() as db:
    t = Tenant(id=str(uuid.uuid4()), nama="Uji", slug="uji-" + uuid.uuid4().hex[:6], email_kontak="a@b.id", paket="pro", is_active=True)
    u = User(id=str(uuid.uuid4()), tenant_id=t.id, email=uuid.uuid4().hex[:6] + "@uji.id", password_hash=hash_password("Rahasia123"),
             nama_lengkap="X", peran="admin", is_active=True, is_verified=True)
    db.add_all([t, u]); db.commit()
    h, s = generate_sample_data(1200, 100)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        h.to_excel(w, sheet_name="Penghimpunan", index=False); s.to_excel(w, sheet_name="Penyaluran", index=False)
    up, msg = simpan_upload(db, t.id, u.id, buf.getvalue(), "contoh.xlsx")
    assert up is not None, msg
    if os.getenv("RUSAKKAN"):
        from src.penyimpanan import penyimpanan
        penyimpanan().simpan(up.storage_path, b"PK\x03\x04rusak")
    tid, uid, upid = t.id, u.id, up.id
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(os.path.join(os.environ["ROOT"], "app.py"), default_timeout=120)
at.session_state["page"] = "analisis"
at.session_state["is_logged_in"] = True
from src.auth.jwt_handler import create_access_token
token = create_access_token(uid, tid, "admin", "x@uji.id", 0)  # sesi divalidasi terhadap token & DB
at.session_state["current_user"] = {"id": uid, "tenant_id": tid, "peran": "admin", "nama_lengkap": "X",
                                    "email": "x@uji.id", "access_token": token}
at.session_state["selected_upload_id"] = upid
at.run()
print("EXC=" + str(len(at.exception)) + " " + " | ".join(e.message for e in at.exception))
print("ERR=" + " | ".join(e.value for e in at.error))
print("WARN=" + " | ".join(w.value for w in at.warning))
print("CAP=" + " | ".join(c.value for c in at.caption))
'''


def _jalankan_ui(tmp_path, **env_tambahan):
    pytest.importorskip("streamlit.testing.v1")
    skrip = tmp_path / "ui.py"
    skrip.write_text(_SKRIP_UI)
    env = {**os.environ, "ROOT": str(ROOT), "APP_ENV": "development",
           "DATABASE_URL": f"sqlite:///{tmp_path}/ui.db", "UPLOAD_DIR": str(tmp_path / "uploads"), **env_tambahan}
    hasil = subprocess.run([sys.executable, str(skrip)], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert hasil.returncode == 0, hasil.stderr[-2000:]
    return hasil.stdout


def test_ui_halaman_analisis_tanpa_exception(tmp_path):
    out = _jalankan_ui(tmp_path)
    assert "EXC=0" in out, out
    assert "MAPE backtest" in out


def test_ui_tanpa_statsmodels_tampilkan_peringatan(tmp_path):
    out = _jalankan_ui(tmp_path, BLOK_SM="1")
    assert "EXC=0" in out, out
    assert "Metode: **Holt-Winters" not in out
    assert "statsmodels tidak dapat diimpor" in out
    assert "Dasar pemilihan" in out


def test_ui_berkas_tersimpan_rusak_pesan_ramah(tmp_path):
    out = _jalankan_ui(tmp_path, RUSAKKAN="1")
    assert "EXC=0" in out, out
    assert "Berkas tidak dapat dianalisis" in out
    assert "Traceback" not in out
