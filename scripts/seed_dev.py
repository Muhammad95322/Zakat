"""Seed database development dengan data awal multi-tenant dan data contoh."""
import sys
import uuid
from pathlib import Path
from datetime import date, timedelta

# Pastikan import src terbaca
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings  # noqa: E402

PESAN_TOLAK_PRODUCTION = (
    "❌ scripts/seed_dev.py ditolak: APP_ENV=production. Skrip ini membuat akun uji "
    "dengan kata sandi yang diketahui publik dan hanya boleh dijalankan di lingkungan "
    "development/staging. Untuk production, buat superadmin dengan "
    "`python scripts/create_superadmin.py`."
)


def tolak_jika_production() -> None:
    """Hentikan skrip (exit code 1) jika dijalankan dengan APP_ENV=production."""
    if settings.is_production:
        print(PESAN_TOLAK_PRODUCTION, file=sys.stderr)
        sys.exit(1)


from src.database import init_db, get_db  # noqa: E402
from src.auth.hashing import hash_password
from src.models.tenant import Tenant
from src.models.user import User

def seed():
    tolak_jika_production()
    print("🌱 Memulai inisialisasi basis data dan data seed...")
    init_db()
    
    with get_db() as db:
        # Cek apakah sudah ada data tenant
        existing = db.query(Tenant).first()
        if existing:
            print("⚠️ Basis data sudah memiliki data. Melewati proses seeding.")
            return

        # 1. Tenant 1: Lazismu DIY (Pro)
        t1 = Tenant(
            id=str(uuid.uuid4()),
            nama="Lazismu Wilayah DIY",
            slug="lazismu-diy",
            email_kontak="admin@lazismu-diy.id",
            telepon="0274-555123",
            alamat="Jl. Gedongkuning No. 130, Yogyakarta",
            paket="pro",
            paket_mulai=date.today(),
            paket_berakhir=date.today() + timedelta(days=365),
            is_active=True
        )

        # 2. Tenant 2: BAZNAS Sleman (Basic)
        t2 = Tenant(
            id=str(uuid.uuid4()),
            nama="BAZNAS Kabupaten Sleman",
            slug="baznas-sleman",
            email_kontak="admin@baznas-sleman.id",
            telepon="0274-888456",
            alamat="Jl. Parasamya No. 1, Beran, Tridadi, Sleman",
            paket="basic",
            is_active=True
        )

        # 3. Tenant 3: YDSF Yogyakarta (Enterprise)
        t3 = Tenant(
            id=str(uuid.uuid4()),
            nama="YDSF Yogyakarta",
            slug="ydsf-jogja",
            email_kontak="admin@ydsf-jogja.id",
            telepon="0274-777890",
            alamat="Jl. Kaliurang KM 5, Sleman",
            paket="enterprise",
            paket_mulai=date.today(),
            paket_berakhir=date.today() + timedelta(days=365),
            is_active=True
        )

        db.add_all([t1, t2, t3])
        db.flush()

        # Users untuk Lazismu DIY
        u_t1 = [
            User(
                id=str(uuid.uuid4()), tenant_id=t1.id, email="admin@lazismu-diy.id",
                password_hash=hash_password("Admin123"), nama_lengkap="Ahmad Fauzi",
                peran="admin", is_active=True, is_verified=True
            ),
            User(
                id=str(uuid.uuid4()), tenant_id=t1.id, email="staf@lazismu-diy.id",
                password_hash=hash_password("Staf1234"), nama_lengkap="Budi Santoso",
                peran="staf", is_active=True, is_verified=True
            ),
            User(
                id=str(uuid.uuid4()), tenant_id=t1.id, email="pembaca@lazismu-diy.id",
                password_hash=hash_password("Baca1234"), nama_lengkap="Citra Dewi",
                peran="pembaca", is_active=True, is_verified=True
            )
        ]

        # Users untuk BAZNAS Sleman
        u_t2 = [
            User(
                id=str(uuid.uuid4()), tenant_id=t2.id, email="admin@baznas-sleman.id",
                password_hash=hash_password("Admin123"), nama_lengkap="Dedi Kurniawan",
                peran="admin", is_active=True, is_verified=True
            ),
            User(
                id=str(uuid.uuid4()), tenant_id=t2.id, email="staf@baznas-sleman.id",
                password_hash=hash_password("Staf1234"), nama_lengkap="Eka Putri",
                peran="staf", is_active=True, is_verified=True
            )
        ]

        # Users untuk YDSF
        u_t3 = [
            User(
                id=str(uuid.uuid4()), tenant_id=t3.id, email="admin@ydsf-jogja.id",
                password_hash=hash_password("Admin123"), nama_lengkap="Fajar Rahman",
                peran="admin", is_active=True, is_verified=True
            )
        ]

        # Super Admin Pusat (tanpa tenant)
        super_admin = User(
            id=str(uuid.uuid4()), tenant_id=None, email="superadmin@zakatinsight.id",
            password_hash=hash_password("SuperAdmin123"), nama_lengkap="Super Administrator",
            peran="super_admin", is_active=True, is_verified=True
        )

        db.add_all(u_t1 + u_t2 + u_t3 + [super_admin])
        db.commit()

        print("✅ Seeding Berhasil!")
        print("\n================ DAFTAR AKUN SEED ================")
        print("1. Super Admin:")
        print("   - Email   : superadmin@zakatinsight.id")
        print("   - Password: SuperAdmin123")
        print("\n2. Lazismu Wilayah DIY (Paket Pro):")
        print("   - Admin   : admin@lazismu-diy.id / Admin123")
        print("   - Staf    : staf@lazismu-diy.id / Staf1234")
        print("   - Pembaca : pembaca@lazismu-diy.id / Baca1234")
        print("\n3. BAZNAS Kabupaten Sleman (Paket Basic):")
        print("   - Admin   : admin@baznas-sleman.id / Admin123")
        print("   - Staf    : staf@baznas-sleman.id / Staf1234")
        print("\n4. YDSF Yogyakarta (Paket Enterprise):")
        print("   - Admin   : admin@ydsf-jogja.id / Admin123")
        print("===================================================")

if __name__ == "__main__":
    seed()

