"""Simpan & ambil pemetaan kolom per lembaga (hasil wizard unggah)."""
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.pemetaan_kolom import PemetaanKolom
from src.pemetaan import BIDANG, tanda_kolom
from src.services.audit_service import catat_log
from src.waktu import utc_now

MAKS_PER_LEMBAGA = 50


def daftar_pemetaan(db: Session, tenant_id: str) -> List[Dict[str, Any]]:
    """Pemetaan tersimpan lembaga, terbaru lebih dulu, dalam bentuk yang dipakai ``siapkan_data``."""
    if not tenant_id:
        return []
    baris = (db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == tenant_id)
             .order_by(PemetaanKolom.updated_at.desc(), PemetaanKolom.id.desc()).all())
    return [{"tanda": b.tanda_kolom, "pemetaan": dict(b.pemetaan or {}), "diperbarui": b.updated_at} for b in baris]


def simpan_pemetaan(db: Session, tenant_id: str, user_id: Optional[str], kolom: List[str],
                    pemetaan: Dict[str, Optional[str]]) -> PemetaanKolom:
    """Simpan (atau perbarui) pemetaan untuk susunan kolom ini. Hanya judul kolom yang disimpan."""
    bersih = {b: str(k) for b, k in pemetaan.items() if k and b in BIDANG and k in kolom}
    tanda = tanda_kolom(kolom)
    rec = (db.query(PemetaanKolom)
           .filter(PemetaanKolom.tenant_id == tenant_id, PemetaanKolom.tanda_kolom == tanda).first())
    if rec is None:
        rec = PemetaanKolom(tenant_id=tenant_id, tanda_kolom=tanda, pemetaan=bersih, dibuat_oleh=user_id)
        db.add(rec)
    else:
        rec.pemetaan = bersih
        rec.dibuat_oleh = user_id
        rec.updated_at = utc_now()
    db.flush()
    lama = (db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == tenant_id)
            .order_by(PemetaanKolom.updated_at.desc(), PemetaanKolom.id.desc()).offset(MAKS_PER_LEMBAGA).all())
    for x in lama:
        db.delete(x)
    db.commit()
    catat_log(db, user_id, "simpan_pemetaan_kolom", tenant_id=tenant_id, detail={"bidang": sorted(bersih)})
    return rec
