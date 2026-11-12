"""Penghapusan data pribadi dan retensi (audit F4; draf kebijakan privasi di docs/).

- hapus_lembaga  : menghapus TUNTAS satu lembaga: pengguna, token, undangan, unggahan (baris DB dan
                   berkas di disk), sesi analisis, dan log audit lembaga itu. Hanya super admin.
- hapus_pengguna : menghapus satu pengguna: token & undangan yang dikirimnya dihapus, log audit
                   dianonimkan (user_id dikosongkan, detail yang memuat email dibersihkan). Unggahan
                   adalah data milik lembaga, sehingga dialihkan ke pelaku penghapusan, bukan dihapus.
- bersihkan_retensi : menghapus log audit yang melewati masa retensi paket (bawaan 90 hari bila paket
                   tidak menetapkan), serta token/undangan kedaluwarsa > 30 hari.
"""
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy.orm import Session

from src.config import settings
from src.models.analysis_session import AnalysisSession
from src.models.audit_log import AuditLog
from src.models.invitation import Invitation
from src.models.pemetaan_kolom import PemetaanKolom
from src.models.tenant import Tenant
from src.models.token_model import Token
from src.models.upload import Upload
from src.models.user import User
from src.services.audit_service import catat_log
from src.waktu import utc_now

RETENSI_LOG_BAWAAN_HARI = 90
RETENSI_LOG_PLATFORM_HARI = 365
RETENSI_TOKEN_HARI = 30


class AksesDitolak(PermissionError):
    pass


def _folder_lembaga(tenant_id: str) -> Path:
    akar = settings.UPLOAD_DIR.resolve()
    folder = (akar / str(tenant_id)).resolve()
    if akar not in folder.parents:  # cegah penghapusan di luar UPLOAD_DIR
        raise ValueError("Jalur unggahan tidak valid.")
    return folder


def hapus_lembaga(db: Session, tenant_id: str, oleh: dict, konfirmasi_slug: str) -> Dict[str, int]:
    if not oleh or oleh.get("peran") != "super_admin":
        raise AksesDitolak("Hanya Super Administrator yang dapat menghapus lembaga.")
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise ValueError("Lembaga tidak ditemukan.")
    if konfirmasi_slug != tenant.slug:
        raise ValueError("Konfirmasi tidak cocok dengan slug lembaga.")
    user_ids = [u.id for u in db.query(User.id).filter(User.tenant_id == tenant_id)]
    jumlah = {
        "sesi_analisis": db.query(AnalysisSession).filter(AnalysisSession.tenant_id == tenant_id).delete(),
        "unggahan": db.query(Upload).filter(Upload.tenant_id == tenant_id).delete(),
        "undangan": db.query(Invitation).filter(Invitation.tenant_id == tenant_id).delete(),
        "pemetaan_kolom": db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == tenant_id).delete(),
        "token": db.query(Token).filter(Token.user_id.in_(user_ids)).delete(synchronize_session=False) if user_ids else 0,
        "log_audit": db.query(AuditLog).filter(
            (AuditLog.tenant_id == tenant_id) | (AuditLog.user_id.in_(user_ids) if user_ids else False)
        ).delete(synchronize_session=False),
        "pengguna": db.query(User).filter(User.tenant_id == tenant_id).delete(),
    }
    db.query(Tenant).filter(Tenant.id == tenant_id).delete()
    db.commit()
    folder = _folder_lembaga(tenant_id)
    if folder.exists():
        shutil.rmtree(folder)
    catat_log(db, oleh.get("id"), "hapus_lembaga", detail={"tenant_id": str(tenant_id), **jumlah})
    return jumlah


def hapus_pengguna(db: Session, user_id: str, oleh: dict) -> Dict[str, int]:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise ValueError("Pengguna tidak ditemukan.")
    if not oleh:
        raise AksesDitolak("Tidak ada sesi.")
    super_admin = oleh.get("peran") == "super_admin"
    if not super_admin and (oleh.get("peran") != "admin" or str(oleh.get("tenant_id")) != str(target.tenant_id)):
        raise AksesDitolak("Hanya admin lembaga yang sama atau Super Administrator.")
    if str(target.id) == str(oleh.get("id")):
        raise ValueError("Tidak dapat menghapus akun sendiri.")
    if target.peran == "admin" and db.query(User).filter(
            User.tenant_id == target.tenant_id, User.peran == "admin", User.id != target.id).count() == 0:
        raise ValueError("Tidak dapat menghapus admin terakhir; hapus lembaganya bila perlu.")
    email = target.email
    jumlah = {
        "token": db.query(Token).filter(Token.user_id == user_id).delete(),
        "undangan": db.query(Invitation).filter(Invitation.invited_by == user_id).delete(),
        "unggahan_dialihkan": db.query(Upload).filter(Upload.user_id == user_id).update({Upload.user_id: oleh.get("id")}),
        "pemetaan_kolom_dilepas": db.query(PemetaanKolom).filter(PemetaanKolom.dibuat_oleh == user_id).update(
            {PemetaanKolom.dibuat_oleh: None}),
        "sesi_analisis_dialihkan": db.query(AnalysisSession).filter(AnalysisSession.user_id == user_id).update(
            {AnalysisSession.user_id: oleh.get("id")}),
    }
    n_log = 0
    for log in db.query(AuditLog).filter(AuditLog.user_id == user_id):
        log.user_id = None
        if email and email in str(log.detail or ""):
            log.detail = {}
        n_log += 1
    jumlah["log_dianonimkan"] = n_log
    tenant_id = target.tenant_id
    db.delete(target)
    db.commit()
    catat_log(db, oleh.get("id"), "hapus_pengguna", tenant_id=tenant_id, detail=jumlah)
    return jumlah


def bersihkan_retensi(db: Session, sekarang: Optional[object] = None) -> Dict[str, int]:
    from src.services.tenant_service import PAKET_LIMITS
    sekarang = sekarang or utc_now()
    terhapus = 0
    for t in db.query(Tenant).all():
        hari = PAKET_LIMITS.get(t.paket, PAKET_LIMITS["basic"]).get("audit_retensi_hari") or RETENSI_LOG_BAWAAN_HARI
        terhapus += db.query(AuditLog).filter(
            AuditLog.tenant_id == t.id, AuditLog.created_at < sekarang - timedelta(days=hari)).delete()
    terhapus += db.query(AuditLog).filter(
        AuditLog.tenant_id.is_(None), AuditLog.created_at < sekarang - timedelta(days=RETENSI_LOG_PLATFORM_HARI)).delete()
    batas_token = sekarang - timedelta(days=RETENSI_TOKEN_HARI)
    token = db.query(Token).filter(Token.expires_at < batas_token).delete()
    undangan = db.query(Invitation).filter(Invitation.expires_at < batas_token).delete()
    db.commit()
    return {"log_audit": terhapus, "token": token, "undangan": undangan}
