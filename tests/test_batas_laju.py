"""IP klien di belakang proxy (tidak bisa dipalsukan) dan pembatasan laju per IP berbasis DB."""
from datetime import timedelta

import pytest

from src.config import settings
from src.middleware.ip_klien import TIDAK_DIKETAHUI, bersihkan_ua, ip_klien
from src.models.audit_log import AuditLog
from src.models.batas_laju import BatasLaju
from src.services import batas_laju as bl
from src.waktu import utc_now

PROXY = "10.1.2.3"  # alamat proxy Render (jaringan privat) yang menghubungi aplikasi
CF = "172.70.1.1"   # salah satu IP edge Cloudflare


# ---------------------------------------------------------------------------
# Resolusi IP klien
# ---------------------------------------------------------------------------
def test_tanpa_proxy_tepercaya_header_diabaikan():
    h = {"X-Forwarded-For": "1.1.1.1", "CF-Connecting-IP": "2.2.2.2"}
    assert ip_klien(h, "203.0.113.9", proxy_tepercaya="", header_klien="CF-Connecting-IP") == "203.0.113.9"


def test_koneksi_langsung_dari_klien_tidak_bisa_memalsukan():
    # peer bukan proxy tepercaya -> header buatan klien diabaikan walau PROXY_TEPERCAYA diisi
    h = {"X-Forwarded-For": "8.8.8.8", "CF-Connecting-IP": "8.8.4.4"}
    assert ip_klien(h, "198.51.100.7", "render", "CF-Connecting-IP") == "198.51.100.7"


def test_xff_dibaca_dari_kanan_entri_kiri_palsu_diabaikan():
    # klien mengirim "X-Forwarded-For: 6.6.6.6"; proxy menambahkan IP asli klien & IP edge Cloudflare
    h = {"x-forwarded-for": f"6.6.6.6, 198.51.100.20, {CF}"}
    assert ip_klien(h, PROXY, "render", "") == "198.51.100.20"


def test_xff_entri_rusak_menghentikan_penelusuran():
    h = {"X-Forwarded-For": f"bukan-ip, 198.51.100.21, {CF}"}
    assert ip_klien(h, PROXY, "render", "") == "198.51.100.21"
    h = {"X-Forwarded-For": f"198.51.100.22, bukan-ip, {CF}"}
    assert ip_klien(h, PROXY, "render", "") == CF  # berhenti di entri rusak; tidak percaya yang di kirinya


def test_header_cf_hanya_dari_proxy_tepercaya():
    h = {"CF-Connecting-IP": "198.51.100.30", "X-Forwarded-For": "5.5.5.5"}
    assert ip_klien(h, PROXY, "render", "CF-Connecting-IP") == "198.51.100.30"
    assert ip_klien({"CF-Connecting-IP": "bukan ip"}, PROXY, "render", "CF-Connecting-IP") == PROXY


def test_ipv6_port_dan_peer_kosong():
    assert ip_klien({"X-Forwarded-For": "[2001:db8::5]:443"}, PROXY, "privat", "") == "2001:db8::5"
    assert ip_klien({"X-Forwarded-For": "198.51.100.40:5555"}, PROXY, "privat", "") == "198.51.100.40"
    assert ip_klien({}, None, "render", "") == TIDAK_DIKETAHUI


def test_semua_entri_proxy_tepercaya_pakai_paling_kiri_tepercaya():
    assert ip_klien({"X-Forwarded-For": "10.9.9.9"}, PROXY, "privat", "") == "10.9.9.9"


def test_ua_dibersihkan():
    assert bersihkan_ua("Mozilla\r\nX-Sisip: 1" + "a" * 500) == ("Mozilla X-Sisip: 1" + "a" * 500)[:256]


# ---------------------------------------------------------------------------
# Batas laju per IP (DB)
# ---------------------------------------------------------------------------
@pytest.fixture
def batas(monkeypatch):
    monkeypatch.setattr(settings, "BATAS_LOGIN_IP", "3/60")
    monkeypatch.setattr(settings, "BATAS_RESET_IP", "2/3600")


def test_ip_sama_diblokir_setelah_batas(db, batas):
    ip = "198.51.100.50"
    for _ in range(3):
        assert bl.periksa(db, "login", ip)[0]
        bl.catat(db, "login", ip)
    boleh, tunggu = bl.periksa(db, "login", ip)
    assert not boleh and 1 <= tunggu <= 60
    assert "Coba lagi dalam 1 menit" in bl.pesan_terlalu_sering(tunggu)


def test_banyak_ip_berbeda_tidak_saling_memblokir(db, batas):
    for i in range(20):
        ip = f"198.51.100.{100 + i}"
        bl.catat(db, "login", ip)
        bl.catat(db, "login", ip)
        assert bl.periksa(db, "login", ip)[0]


def test_aksi_terpisah_dan_jendela_berlalu(db, batas):
    ip = "198.51.100.60"
    t0 = utc_now()
    for _ in range(3):
        bl.catat(db, "login", ip, sekarang=t0)
    assert not bl.periksa(db, "login", ip, sekarang=t0)[0]
    assert bl.periksa(db, "reset", ip, sekarang=t0)[0]                         # aksi lain tidak terpengaruh
    assert bl.periksa(db, "login", ip, sekarang=t0 + timedelta(seconds=61))[0]  # jendela berlalu


def test_periksa_dan_catat_reset(db, batas):
    ip = "198.51.100.61"
    assert bl.periksa_dan_catat(db, "reset", ip)[0]
    assert bl.periksa_dan_catat(db, "reset", ip)[0]
    assert not bl.periksa_dan_catat(db, "reset", ip)[0]
    assert db.query(BatasLaju).filter(BatasLaju.kunci == bl._kunci("reset", ip)).count() == 2  # yang ditolak tidak dicatat


def test_ip_tidak_disimpan_mentah_dan_peristiwa_dicatat_sekali(db, batas):
    ip = "198.51.100.62"
    for _ in range(5):
        bl.catat(db, "login", ip, ua="Peramban Uji")
    assert db.query(BatasLaju).filter(BatasLaju.kunci.contains("198.51")).count() == 0
    ev = db.query(AuditLog).filter(AuditLog.aksi == "batas_laju_terlampaui", AuditLog.ip_address == ip).all()
    assert len(ev) == 1 and ev[0].user_agent == "Peramban Uji" and ev[0].detail == {"aksi": "login"}


def test_tahan_restart_karena_di_db(db, batas, engine):
    from sqlalchemy.orm import sessionmaker
    ip = "198.51.100.63"
    for _ in range(3):
        bl.catat(db, "login", ip)
    sesi_baru = sessionmaker(bind=engine)()  # proses/instans lain membaca tabel yang sama
    try:
        assert not bl.periksa(sesi_baru, "login", ip)[0]
    finally:
        sesi_baru.close()


def test_retensi_membersihkan_batas_laju_dan_ip_audit(db, batas, sample_tenant, monkeypatch):
    from src.services.data_pribadi import bersihkan_retensi
    monkeypatch.setattr(settings, "IP_RETENSI_HARI", 10)  # log (retensi paket pro 30 hari) tetap, IP dikosongkan
    lama = utc_now() - timedelta(days=20)
    db.add(BatasLaju(kunci="x" * 64, aksi="login", waktu=utc_now() - timedelta(days=2)))
    db.add(AuditLog(tenant_id=sample_tenant.id, aksi="login", detail={}, ip_address="198.51.100.70",
                    user_agent="UA", created_at=lama))
    baru = AuditLog(tenant_id=sample_tenant.id, aksi="login", detail={}, ip_address="198.51.100.71",
                    user_agent="UA", created_at=utc_now())
    db.add(baru)
    db.commit()
    hasil = bersihkan_retensi(db)
    assert hasil["batas_laju"] >= 1 and hasil["ip_dianonimkan"] >= 1
    assert db.query(AuditLog).filter(AuditLog.ip_address == "198.51.100.70").count() == 0
    assert db.query(AuditLog).filter(AuditLog.created_at == lama, AuditLog.ip_address.is_(None),
                                     AuditLog.user_agent.is_(None)).count() == 1  # baris tetap ada
    assert db.query(AuditLog).filter(AuditLog.ip_address == "198.51.100.71").count() == 1
