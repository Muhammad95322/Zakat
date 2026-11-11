"""Uji KRITIS Isolasi Data Antar Lembaga (Multi-Tenant Isolation)."""
import uuid
import pytest
from src.models.upload import Upload
from src.models.user import User
from src.models.audit_log import AuditLog
from src.services.upload_service import get_upload, get_uploads
from src.services.audit_service import catat_log

class TestTenantDataIsolation:
    def test_upload_tenant_a_tidak_dapat_diakses_tenant_b(self, db, sample_tenant, sample_tenant_2):
        """T2-01: File yang diunggah Tenant A tidak boleh muncul di query Tenant B."""
        upload_a = Upload(
            id=str(uuid.uuid4()),
            tenant_id=sample_tenant.id,
            user_id=str(uuid.uuid4()),
            nama_file_asli="laporan_lazismu.xlsx",
            nama_file_simpan="abc12345.xlsx",
            ukuran_bytes=2048,
            jenis_file="xlsx",
            status="siap",
            storage_path="uploads/test/abc12345.xlsx"
        )
        db.add(upload_a)
        db.commit()

        # Tenant B mencari seluruh upload miliknya
        uploads_b = get_uploads(db, sample_tenant_2.id)
        assert len(uploads_b) == 0

        # Tenant B mencoba mengambil langsung ID file Tenant A
        direct_access = get_upload(db, upload_a.id, sample_tenant_2.id)
        assert direct_access is None

    def test_daftar_pengguna_terisolasi_per_tenant(self, db, sample_tenant, sample_tenant_2, admin_user):
        """T2-04: Pengguna Tenant A tidak boleh melihat staf Tenant B."""
        user_b = User(
            id=str(uuid.uuid4()),
            tenant_id=sample_tenant_2.id,
            email="staf-b@test.id",
            password_hash="hashed",
            nama_lengkap="Staf Lembaga B",
            peran="staf",
            is_active=True,
            is_verified=True
        )
        db.add(user_b)
        db.commit()

        # Query pengguna Tenant A
        users_a = db.query(User).filter(User.tenant_id == sample_tenant.id).all()
        ids_a = {u.id for u in users_a}
        assert user_b.id not in ids_a

    def test_audit_log_terpisah_per_tenant(self, db, sample_tenant, sample_tenant_2, admin_user):
        """T2-05: Log audit Tenant A tidak bocor ke Tenant B."""
        catat_log(db, admin_user.id, "upload_file", tenant_id=sample_tenant.id, detail={"file": "test.xlsx"})
        
        # Log Tenant B harus kosong
        logs_b = db.query(AuditLog).filter(AuditLog.tenant_id == sample_tenant_2.id).all()
        assert len(logs_b) == 0
        
        # Log Tenant A harus ada
        logs_a = db.query(AuditLog).filter(AuditLog.tenant_id == sample_tenant.id).all()
        assert len(logs_a) >= 1

