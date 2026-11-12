"""Simpan & ambil pemetaan kolom per lembaga (hasil wizard unggah)."""
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.pemetaan_kolom import PemetaanKolom
from src.pemetaan import BIDANG, tanda_kolom
from src.services.audit_service import catat_log
from src.waktu import utc_now

MAKS_PER_LEMBAGA = 50
KUNCI_OPSI = "_opsi"  # disimpan di dalam JSON pemetaan (tanpa migrasi)
OPSI_DIIZINKAN = {"buang_duplikat_persis"}


def daftar_pemetaan(db: Session, tenant_id: str) -> List[Dict[str, Any]]:
    """Pemetaan tersimpan lembaga, terbaru lebih dulu, dalam bentuk yang dipakai ``siapkan_data``."""
    if not tenant_id:
        return []
    baris = (db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == tenant_id)
             .order_by(PemetaanKolom.updated_at.desc(), PemetaanKolom.id.desc()).all())
    hasil = []
    for b in baris:
        isi = dict(b.pemetaan or {})
        opsi = isi.pop(KUNCI_OPSI, {}) or {}
        hasil.append({"tanda": b.tanda_kolom, "pemetaan": isi, "opsi": dict(opsi), "diperbarui": b.updated_at})
    return hasil


def simpan_pemetaan(db: Session, tenant_id: str, user_id: Optional[str], kolom: List[str],
                    pemetaan: Dict[str, Optional[str]], opsi: Optional[Dict[str, Any]] = None) -> PemetaanKolom:
    """Simpan (atau perbarui) pemetaan untuk susunan kolom ini. Hanya judul kolom yang disimpan.

    ``opsi`` (mis. ``{"buang_duplikat_persis": True}``) disimpan bersama pemetaan. Bila None, opsi yang
    sudah tersimpan untuk susunan kolom yang sama dipertahankan.
    """
    bersih = {b: str(k) for b, k in pemetaan.items() if k and b in BIDANG and k in kolom}
    tanda = tanda_kolom(kolom)
    rec = (db.query(PemetaanKolom)
           .filter(PemetaanKolom.tenant_id == tenant_id, PemetaanKolom.tanda_kolom == tanda).first())
    lama_opsi = dict((rec.pemetaan or {}).get(KUNCI_OPSI) or {}) if rec is not None else {}
    opsi_bersih = {k: bool(v) for k, v in (lama_opsi if opsi is None else opsi).items() if k in OPSI_DIIZINKAN}
    isi = {**bersih, **({KUNCI_OPSI: opsi_bersih} if opsi_bersih else {})}
    if rec is None:
        rec = PemetaanKolom(tenant_id=tenant_id, tanda_kolom=tanda, pemetaan=isi, dibuat_oleh=user_id)
        db.add(rec)
    else:
        rec.pemetaan = isi
        rec.dibuat_oleh = user_id
        rec.updated_at = utc_now()
    db.flush()
    lama = (db.query(PemetaanKolom).filter(PemetaanKolom.tenant_id == tenant_id)
            .order_by(PemetaanKolom.updated_at.desc(), PemetaanKolom.id.desc()).offset(MAKS_PER_LEMBAGA).all())
    for x in lama:
        db.delete(x)
    db.commit()
    catat_log(db, user_id, "simpan_pemetaan_kolom", tenant_id=tenant_id,
              detail={"bidang": sorted(bersih), **({"opsi": opsi_bersih} if opsi_bersih else {})})
    return rec
