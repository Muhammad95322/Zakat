"""CLI Interaktif untuk membuat akun Super Admin baru."""
import sys
import uuid
from pathlib import Path
import getpass

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db, get_db
from src.auth.hashing import hash_password, validate_password_strength
from src.models.user import User

def main():
    print("=== Pembuatan Akun Super Administrator Zakat Insight ===")
    init_db()
    
    email = input("Alamat Email Super Admin: ").strip().lower()
    nama = input("Nama Lengkap Administrator: ").strip()
    password = getpass.getpass("Kata Sandi: ")
    konfirmasi = getpass.getpass("Konfirmasi Kata Sandi: ")
    
    if password != konfirmasi:
        print("❌ Konfirmasi kata sandi tidak cocok!")
        sys.exit(1)
        
    is_valid, pesan = validate_password_strength(password)
    if not is_valid:
        print(f"❌ {pesan}")
        sys.exit(1)
        
    with get_db() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"❌ Email {email} sudah terdaftar!")
            sys.exit(1)
            
        admin = User(
            id=str(uuid.uuid4()),
            tenant_id=None,
            email=email,
            password_hash=hash_password(password),
            nama_lengkap=nama,
            peran="super_admin",
            is_active=True,
            is_verified=True
        )
        db.add(admin)
        db.commit()
        print(f"✅ Super Administrator {email} berhasil dibuat!")

if __name__ == "__main__":
    main()

