"""Pemetaan kolom tersimpan per lembaga: isolasi, pembaruan, dipakai otomatis, ikut terhapus."""
import io

import openpyxl
import pytest

from src.models.audit_log import AuditLog
from src.models.pemetaan_kolom import PemetaanKolom
from src.pipeline import periksa_berkas, siapkan_data
from src.services import data_pribadi as dp
from src.services.pemetaan_service import MAKS_PER_LEMBAGA, daftar_pemetaan, simpan_pemetaan

KOLOM = ["Kapan", "Siapa", "Berapa"]
PEM = {"tanggal": "Kapan", "jumlah": "Berapa", "nama_muzaki": "Siapa"}


def _xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(KOLOM)
    for i in range(1, 8):
        ws.append([f"0{i}/03/2024", f"D{i}", f"{i * 100}.000"])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_simpan_dan_pakai_otomatis(db, sample_tenant, admin_user):
    assert periksa_berkas(_xlsx(), "a.xlsx").status == "ragu"
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, KOLOM, PEM)
    lembaga = daftar_pemetaan(db, sample_tenant.id)
    assert lembaga[0]["pemetaan"] == PEM
    p = periksa_berkas(_xlsx(), "a.xlsx", lembaga)
    assert p.status == "tersimpan" and not p.perlu_wizard
    hasil = siapkan_data(_xlsx(), "a.xlsx", pemetaan_lembaga=lembaga)
    assert hasil["df_himpun"]["jumlah"].sum() == 2_800_000
    assert hasil["kualitas"]["status_pemetaan"] == "tersimpan"
    log = db.query(AuditLog).filter(AuditLog.aksi == "simpan_pemetaan_kolom",
                                    AuditLog.tenant_id == sample_tenant.id).one()
    assert log.detail == {"bidang": ["jumlah", "nama_muzaki", "tanggal"]}  # hanya nama bidang, tanpa isi data


def test_isolasi_antar_lembaga(db, sample_tenant, sample_tenant_2, admin_user):
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, KOLOM, PEM)
    assert daftar_pemetaan(db, sample_tenant_2.id) == []
    assert periksa_berkas(_xlsx(), "a.xlsx", daftar_pemetaan(db, sample_tenant_2.id)).status == "ragu"


def test_susunan_sama_diperbarui_bukan_ditambah(db, sample_tenant, admin_user):
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, KOLOM, PEM)
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, KOLOM, {**PEM, "nama_muzaki": None})
    rows = db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == sample_tenant.id).all()
    assert len(rows) == 1 and rows[0].pemetaan == {"tanggal": "Kapan", "jumlah": "Berapa"}


def test_kolom_asing_dan_bidang_tak_dikenal_dibuang(db, sample_tenant, admin_user):
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, KOLOM, {**PEM, "kanal": "TidakAda", "<script>": "Kapan"})
    assert daftar_pemetaan(db, sample_tenant.id)[0]["pemetaan"] == PEM


def test_batas_per_lembaga(db, sample_tenant, admin_user):
    for i in range(MAKS_PER_LEMBAGA + 5):
        simpan_pemetaan(db, sample_tenant.id, admin_user.id, [f"T{i}", "N"], {"tanggal": f"T{i}", "jumlah": "N"})
    assert db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == sample_tenant.id).count() == MAKS_PER_LEMBAGA


def test_tersimpan_tidak_dipakai_bila_isinya_tidak_cocok(db, sample_tenant, admin_user):
    # pemetaan lama menunjuk kolom 'Siapa' sebagai jumlah -> isinya teks -> jangan dipakai diam-diam
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, KOLOM, {"tanggal": "Kapan", "jumlah": "Siapa"})
    assert periksa_berkas(_xlsx(), "a.xlsx", daftar_pemetaan(db, sample_tenant.id)).status == "ragu"


def test_hapus_lembaga_ikut_menghapus_pemetaan(db, sample_tenant, admin_user, tmp_path, monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, KOLOM, PEM)
    hasil = dp.hapus_lembaga(db, sample_tenant.id, {"id": None, "peran": "super_admin"}, sample_tenant.slug)
    assert hasil["pemetaan_kolom"] == 1
    assert db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == sample_tenant.id).count() == 0


def test_hapus_pengguna_melepas_pembuat(db, sample_tenant, admin_user, staf_user):
    simpan_pemetaan(db, sample_tenant.id, staf_user.id, KOLOM, PEM)
    staf_user.is_active = False
    db.commit()
    dp.hapus_pengguna(db, staf_user.id, {"id": admin_user.id, "peran": "admin", "tenant_id": sample_tenant.id})
    rec = db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == sample_tenant.id).one()
    assert rec.dibuat_oleh is None and rec.pemetaan == PEM
