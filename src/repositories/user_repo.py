"""Repository untuk manipulasi data User."""
from typing import Optional, List
from sqlalchemy.orm import Session
from src.models.user import User

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.strip().lower()).first()

def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()

def get_users_by_tenant(db: Session, tenant_id: str) -> List[User]:
    return db.query(User).filter(User.tenant_id == tenant_id).all()



def update_user_name(db: Session, user_id: str, nama: str) -> bool:
    user = get_user_by_id(db, user_id)
    nama = (nama or "").strip()
    if not user or not nama or len(nama) > 200:
        return False
    user.nama_lengkap = nama
    db.commit()
    return True


def _target_di_lembaga(db: Session, user_id: str, oleh: dict) -> User:
    from src.services.auth_service import AksesDitolak, _wajib_admin_lembaga
    target = get_user_by_id(db, user_id)
    if not target or target.peran == "super_admin":
        raise AksesDitolak("Pengguna tidak ditemukan.")
    _wajib_admin_lembaga(oleh, target.tenant_id)
    return target


def _admin_aktif_lain(db: Session, target: User) -> int:
    return db.query(User).filter(User.tenant_id == target.tenant_id, User.peran == "admin",
                                 User.is_active.is_(True), User.id != target.id).count()


def update_user_role(db: Session, user_id: str, peran: str, oleh: dict) -> bool:
    """Ubah peran anggota lembaga; hanya admin lembaga yang sama; admin terakhir tidak boleh diturunkan."""
    from src.services.audit_service import catat_log
    if peran not in ("admin", "staf", "pembaca"):
        raise ValueError("Peran tidak valid.")
    target = _target_di_lembaga(db, user_id, oleh)
    if target.peran == "admin" and peran != "admin" and _admin_aktif_lain(db, target) == 0:
        raise ValueError("Tidak dapat menurunkan admin terakhir lembaga.")
    lama = target.peran
    target.peran = peran
    db.commit()
    catat_log(db, oleh.get("id"), "ubah_peran", tenant_id=target.tenant_id, detail={"dari": lama, "ke": peran})
    return True


def deactivate_user(db: Session, user_id: str, oleh: dict) -> bool:
    """Nonaktifkan anggota (sesi aktifnya langsung berakhir lewat sesi_versi)."""
    from src.services.audit_service import catat_log
    target = _target_di_lembaga(db, user_id, oleh)
    if str(target.id) == str(oleh.get("id")):
        raise ValueError("Tidak dapat menonaktifkan akun sendiri.")
    if target.peran == "admin" and _admin_aktif_lain(db, target) == 0:
        raise ValueError("Tidak dapat menonaktifkan admin terakhir lembaga.")
    target.is_active = False
    target.sesi_versi = (target.sesi_versi or 0) + 1
    db.commit()
    catat_log(db, oleh.get("id"), "nonaktifkan_pengguna", tenant_id=target.tenant_id)
    return True
