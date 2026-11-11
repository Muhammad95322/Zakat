# 🏗️ Prompt Tahap 2: Zakat Insight — Transformasi ke Produk SaaS

> **Versi**: 2.0 | **Dibuat**: November 2026
> **Nama Produk Baru**: Zakat Insight (dari Lazismu Insight — kini untuk semua lembaga zakat)
> **Tujuan Tahap 2**: Mengubah aplikasi analitik single-tenant menjadi produk SaaS siap jual

---

## 📌 Konteks & Status Saat Ini

Tahap 1 menghasilkan aplikasi Streamlit analitik ZIS dengan fitur:
- Upload & cleaning data Excel/CSV
- Dashboard interaktif (tren, komposisi, muzaki, penyaluran)
- Analisis RFM, peramalan, Gini
- Ekspor PDF & Excel

**Tahap 2 mengubahnya menjadi platform SaaS** dengan:
- Multi-tenant (setiap lembaga punya data terpisah)
- Autentikasi & otorisasi (peran: Super Admin, Admin Lembaga, Staf, Pembaca)
- Database persisten (PostgreSQL prod / SQLite dev)
- Riwayat unggahan & sesi analisis tersimpan
- Halaman langganan & manajemen paket
- Log audit & keamanan data
- Deploy siap produksi

---

## 🎯 Kriteria Penerimaan Terukur

### AC-1: Autentikasi & Otorisasi
- [ ] Login dengan email + password (bcrypt hash, min 8 karakter, 1 huruf besar, 1 angka)
- [ ] Session token JWT dengan expiry 8 jam, refresh token 30 hari
- [ ] Rate limiting: maks 5 percobaan login gagal → lockout 15 menit
- [ ] Registrasi lembaga baru dengan verifikasi email (link aktif 24 jam)
- [ ] Reset password via email (link aktif 1 jam)
- [ ] 4 peran dengan izin berbeda (lihat tabel di bawah)
- [ ] Logout di semua perangkat (invalidasi semua session)

### AC-2: Multi-Tenant & Isolasi Data
- [ ] Setiap lembaga (`tenant_id`) hanya bisa akses datanya sendiri
- [ ] Query database selalu disertai filter `tenant_id` — tidak ada celah cross-tenant
- [ ] File unggahan disimpan di folder terpisah per tenant: `uploads/{tenant_id}/`
- [ ] Tidak ada data tenant lain yang bisa diakses meski dengan manipulasi URL/parameter

### AC-3: Database & Migrasi
- [ ] Schema database terdefinisi dengan Alembic migrations
- [ ] `alembic upgrade head` berjalan bersih dari versi 0
- [ ] `alembic downgrade -1` bisa rollback tanpa kehilangan data lain
- [ ] Data seed untuk dev tersedia: `python scripts/seed_dev.py`
- [ ] SQLite untuk dev, PostgreSQL untuk prod (konfigurasi via `.env`)

### AC-4: Riwayat & Manajemen Data
- [ ] Setiap unggahan tersimpan di database: nama file, ukuran, waktu, pengunggah, status
- [ ] Pengguna bisa akses ulang hasil analisis sesi sebelumnya tanpa upload ulang
- [ ] Kuota penyimpanan per paket (Basic: 500MB, Pro: 5GB, Enterprise: unlimited)
- [ ] Pengguna bisa hapus riwayat unggahan mereka sendiri
- [ ] File fisik ikut terhapus saat record dihapus

### AC-5: Langganan & Paket
- [ ] 3 paket: Basic (gratis), Pro (Rp 299.000/bulan), Enterprise (Rp 999.000/bulan)
- [ ] Halaman pricing dengan fitur perbandingan
- [ ] Soft-lock fitur premium: banner upgrade, bukan error
- [ ] Admin dapat set paket lembaga secara manual (untuk demo/negosiasi)
- [ ] Tanggal mulai & berakhir langganan tersimpan di database

### AC-6: Log Audit
- [ ] Setiap aksi penting tercatat: login, logout, upload, hapus, ubah peran, ubah langganan
- [ ] Log mencatat: `timestamp`, `user_id`, `tenant_id`, `aksi`, `detail`, `ip_address`
- [ ] Super Admin bisa lihat log semua tenant
- [ ] Admin Lembaga bisa lihat log lembaganya sendiri
- [ ] Log tidak bisa dihapus oleh siapapun kecuali Super Admin
- [ ] Ekspor log sebagai CSV

### AC-7: Keamanan
- [ ] Semua input disanitasi (tidak ada SQL injection, XSS)
- [ ] File upload divalidasi: ekstensi whitelist, magic bytes check, ukuran maks 50MB
- [ ] HTTPS enforced di production (redirect HTTP → HTTPS)
- [ ] Environment variable untuk semua secret (tidak ada hardcode)
- [ ] `.env` di `.gitignore`, tersedia `.env.example`
- [ ] Header keamanan: X-Frame-Options, X-Content-Type-Options, CSP

### AC-8: Deploy
- [ ] `Dockerfile` yang berjalan dengan `docker build` dan `docker run`
- [ ] `docker-compose.yml` untuk dev (app + PostgreSQL + pgAdmin)
- [ ] `render.yaml` atau `railway.toml` untuk one-click deploy
- [ ] Health check endpoint: `GET /healthz` → `{"status": "ok", "version": "2.0.0"}`
- [ ] Variabel environment terdokumentasi di README

---

## 👥 Tabel Peran & Izin

| Izin | Super Admin | Admin Lembaga | Staf | Pembaca |
|------|:-----------:|:-------------:|:----:|:-------:|
| Lihat dashboard & analisis | ✅ | ✅ | ✅ | ✅ |
| Upload data | ✅ | ✅ | ✅ | ❌ |
| Hapus data unggahan | ✅ | ✅ | ❌ | ❌ |
| Ekspor PDF/Excel | ✅ | ✅ | ✅ | ✅ |
| Kelola pengguna lembaga | ✅ | ✅ | ❌ | ❌ |
| Undang pengguna baru | ✅ | ✅ | ❌ | ❌ |
| Lihat log audit lembaga | ✅ | ✅ | ❌ | ❌ |
| Ubah paket langganan | ✅ | ❌ | ❌ | ❌ |
| Lihat semua tenant | ✅ | ❌ | ❌ | ❌ |
| Lihat log audit semua tenant | ✅ | ❌ | ❌ | ❌ |
| Nonaktifkan lembaga | ✅ | ❌ | ❌ | ❌ |

---

## 🗄️ Skema Database (ERD)

```sql
-- Tenant (Lembaga)
tenants
  id UUID PK
  nama VARCHAR(200) NOT NULL
  slug VARCHAR(100) UNIQUE NOT NULL        -- untuk URL: /lembaga/{slug}
  email_kontak VARCHAR(200) NOT NULL
  telepon VARCHAR(20)
  alamat TEXT
  logo_url VARCHAR(500)
  paket ENUM('basic','pro','enterprise') DEFAULT 'basic'
  paket_mulai DATE
  paket_berakhir DATE
  is_active BOOLEAN DEFAULT true
  created_at TIMESTAMP DEFAULT NOW()
  updated_at TIMESTAMP DEFAULT NOW()

-- Pengguna
users
  id UUID PK
  tenant_id UUID FK → tenants.id
  email VARCHAR(200) UNIQUE NOT NULL
  password_hash VARCHAR(255) NOT NULL
  nama_lengkap VARCHAR(200) NOT NULL
  peran ENUM('super_admin','admin','staf','pembaca') NOT NULL
  is_active BOOLEAN DEFAULT true
  is_verified BOOLEAN DEFAULT false
  last_login TIMESTAMP
  failed_login_count INT DEFAULT 0
  locked_until TIMESTAMP
  created_at TIMESTAMP DEFAULT NOW()
  updated_at TIMESTAMP DEFAULT NOW()

-- Token (email verification, reset password, refresh token)
tokens
  id UUID PK
  user_id UUID FK → users.id
  jenis ENUM('verifikasi_email','reset_password','refresh') NOT NULL
  token_hash VARCHAR(255) NOT NULL
  expires_at TIMESTAMP NOT NULL
  used_at TIMESTAMP
  created_at TIMESTAMP DEFAULT NOW()

-- Unggahan File
uploads
  id UUID PK
  tenant_id UUID FK → tenants.id
  user_id UUID FK → users.id
  nama_file_asli VARCHAR(500) NOT NULL
  nama_file_simpan VARCHAR(500) NOT NULL   -- UUID-based filename di storage
  ukuran_bytes BIGINT NOT NULL
  jenis_file VARCHAR(20) NOT NULL          -- xlsx, xls, csv
  status ENUM('processing','siap','error') DEFAULT 'processing'
  error_pesan TEXT
  periode_mulai DATE                       -- dari data di file
  periode_selesai DATE
  jumlah_baris_penghimpunan INT
  jumlah_baris_penyaluran INT
  storage_path VARCHAR(500) NOT NULL
  created_at TIMESTAMP DEFAULT NOW()

-- Sesi Analisis (snapshot hasil analisis per upload)
analysis_sessions
  id UUID PK
  upload_id UUID FK → uploads.id
  tenant_id UUID FK → tenants.id
  user_id UUID FK → users.id
  nama_sesi VARCHAR(200)                   -- bisa diberi nama oleh pengguna
  filter_json JSONB                        -- filter yang diterapkan saat analisis
  summary_json JSONB                       -- snapshot KPI hasil analisis
  created_at TIMESTAMP DEFAULT NOW()

-- Log Audit
audit_logs
  id BIGSERIAL PK
  tenant_id UUID FK → tenants.id (nullable untuk aksi super admin)
  user_id UUID FK → users.id
  aksi VARCHAR(100) NOT NULL               -- 'login', 'upload', 'hapus_upload', dll.
  detail JSONB                             -- konteks tambahan
  ip_address INET
  user_agent TEXT
  created_at TIMESTAMP DEFAULT NOW()

-- Undangan Pengguna
invitations
  id UUID PK
  tenant_id UUID FK → tenants.id
  email VARCHAR(200) NOT NULL
  peran ENUM('admin','staf','pembaca') NOT NULL
  token_hash VARCHAR(255) NOT NULL
  invited_by UUID FK → users.id
  expires_at TIMESTAMP NOT NULL
  accepted_at TIMESTAMP
  created_at TIMESTAMP DEFAULT NOW()
```

---

## 🏗️ Arsitektur Teknis

```
zakat-insight/
├── app.py                    ← Entry point Streamlit (router utama)
├── requirements.txt
├── requirements-dev.txt      ← pytest, black, ruff, mypy
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── render.yaml               ← Deploy ke Render
├── alembic.ini
├── README.md
│
├── migrations/               ← Alembic migration files
│   ├── env.py
│   └── versions/
│       ├── 001_initial_schema.py
│       └── 002_add_invitations.py
│
├── src/
│   ├── __init__.py
│   │
│   ├── config.py             ← Settings dari env var (pydantic BaseSettings)
│   ├── database.py           ← SQLAlchemy engine, session, Base
│   │
│   ├── models/               ← SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── tenant.py
│   │   ├── user.py
│   │   ├── token.py
│   │   ├── upload.py
│   │   ├── analysis_session.py
│   │   ├── audit_log.py
│   │   └── invitation.py
│   │
│   ├── auth/                 ← Autentikasi & otorisasi
│   │   ├── __init__.py
│   │   ├── hashing.py        ← bcrypt
│   │   ├── jwt_handler.py    ← JWT encode/decode
│   │   ├── session.py        ← Streamlit session state management
│   │   └── decorators.py     ← @require_login, @require_role
│   │
│   ├── pages/                ← Halaman Streamlit
│   │   ├── __init__.py
│   │   ├── pg_login.py
│   │   ├── pg_register.py
│   │   ├── pg_verify_email.py
│   │   ├── pg_reset_password.py
│   │   ├── pg_dashboard.py   ← Dashboard utama (dari tahap 1)
│   │   ├── pg_upload.py      ← Upload & riwayat
│   │   ├── pg_analisis.py    ← Analisis (dari tahap 1)
│   │   ├── pg_profil.py      ← Profil pengguna
│   │   ├── pg_tim.py         ← Manajemen tim/pengguna lembaga
│   │   ├── pg_langganan.py   ← Paket & billing
│   │   ├── pg_audit.py       ← Log audit
│   │   └── pg_superadmin.py  ← Panel Super Admin
│   │
│   ├── services/             ← Business logic
│   │   ├── __init__.py
│   │   ├── auth_service.py   ← Login, register, verifikasi
│   │   ├── tenant_service.py
│   │   ├── upload_service.py ← Simpan file, proses, kuota
│   │   ├── audit_service.py  ← Catat log
│   │   ├── email_service.py  ← Kirim email (SMTP)
│   │   └── subscription_service.py
│   │
│   ├── repositories/         ← Data access layer
│   │   ├── __init__.py
│   │   ├── user_repo.py
│   │   ├── tenant_repo.py
│   │   ├── upload_repo.py
│   │   ├── audit_repo.py
│   │   └── session_repo.py
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── rate_limiter.py   ← Login rate limiting
│   │   └── security.py       ← Input sanitasi, file validation
│   │
│   ├── components/           ← UI components reusable
│   │   ├── __init__.py
│   │   ├── navbar.py
│   │   ├── sidebar.py
│   │   ├── pricing_card.py
│   │   ├── upload_history.py
│   │   └── audit_table.py
│   │
│   # Modul analitik dari Tahap 1 (tetap di src/)
│   ├── loader.py
│   ├── cleaning.py
│   ├── analysis.py
│   ├── forecasting.py
│   ├── rfm.py
│   ├── charts.py
│   ├── report_pdf.py
│   ├── report_excel.py
│   ├── sample_data.py
│   └── utils.py
│
├── scripts/
│   ├── seed_dev.py           ← Data dev: 3 tenant, 10 user, data contoh
│   ├── create_superadmin.py  ← CLI buat super admin pertama
│   └── check_health.py
│
├── uploads/                  ← Storage file (di luar repo, ada di .gitignore)
│   └── {tenant_id}/
│       └── {upload_id}.xlsx
│
└── tests/
    ├── conftest.py           ← Fixtures: test DB, test client, dummy tenant/user
    ├── test_auth.py
    ├── test_tenant.py
    ├── test_upload.py
    ├── test_audit.py
    ├── test_subscription.py
    ├── test_security.py
    ├── test_rate_limiter.py
    └── test_isolation.py     ← KRITIS: uji isolasi data antar tenant
```

---

## 🔒 Paket Langganan

| Fitur | Basic (Gratis) | Pro (Rp 299rb/bln) | Enterprise (Rp 999rb/bln) |
|-------|:--------------:|:------------------:|:-------------------------:|
| Jumlah pengguna | 2 | 10 | Unlimited |
| Penyimpanan | 100MB | 2GB | 20GB |
| Riwayat unggahan | 10 file | 100 file | Unlimited |
| Analisis dasar | ✅ | ✅ | ✅ |
| RFM & Peramalan | ❌ | ✅ | ✅ |
| Ekspor PDF/Excel | ❌ | ✅ | ✅ |
| Log Audit | ❌ | 30 hari | 1 tahun |
| Support | Email | Email + Chat | Dedicated |
| White-label (logo sendiri) | ❌ | ❌ | ✅ |
| API akses | ❌ | ❌ | ✅ |

---

## 🧪 Skenario Pengujian Wajib

### Group T1: Autentikasi
```
T1-01: Register lembaga baru → email verifikasi dikirim → klik link → login berhasil
T1-02: Login salah password 5x → akun terkunci → tunggu 15 menit → bisa login lagi
T1-03: Token verifikasi email kadaluarsa (simulasi) → minta kirim ulang → berhasil
T1-04: Reset password → link dikirim → pakai link → password baru aktif → link lama gagal
T1-05: JWT expired → aksi apapun redirect ke login (bukan error 500)
T1-06: Refresh token valid → session diperpanjang tanpa login ulang
```

### Group T2: Isolasi Data (KRITIS)
```
T2-01: Tenant A upload file → Tenant B query uploads → hasilnya 0 (bukan file Tenant A)
T2-02: User Tenant A manipulasi upload_id Tenant B di URL → mendapat 403, bukan data
T2-03: Super Admin query tanpa tenant_id filter → dapat semua tenant (by design)
T2-04: Staf Tenant A tidak bisa lihat daftar pengguna Tenant B
T2-05: Pembaca tidak bisa akses endpoint upload (403)
```

### Group T3: Manajemen Pengguna
```
T3-01: Admin undang user baru → email undangan → klik link → isi password → masuk sebagai Staf
T3-02: Admin ubah peran Staf → Pembaca → Staf tidak bisa upload lagi
T3-03: Admin nonaktifkan pengguna → pengguna tidak bisa login (bukan error 500)
T3-04: Super Admin nonaktifkan tenant → semua user tenant tidak bisa login
```

### Group T4: Upload & Kuota
```
T4-01: Upload file valid → status 'processing' → selesai → status 'siap' → analisis bisa diakses
T4-02: Upload file > 50MB → ditolak dengan pesan ramah sebelum diproses
T4-03: Upload file .exe yang di-rename .xlsx → ditolak (magic bytes check)
T4-04: Tenant Basic sudah 10 file → upload ke-11 → soft-lock dengan banner upgrade
T4-05: Hapus upload → file fisik ikut terhapus (cek di filesystem)
T4-06: Akses analisis dari riwayat (tanpa upload ulang) → data tampil benar
```

### Group T5: Log Audit
```
T5-01: Login berhasil → log terbuat dengan aksi='login', ip_address terisi
T5-02: Upload file → log terbuat dengan detail nama file dan ukuran
T5-03: Admin lihat log lembaganya → hanya log tenant sendiri yang muncul
T5-04: Pembaca coba akses halaman audit → redirect/pesan tidak diizinkan
T5-05: Ekspor log CSV → file berisi semua kolom yang benar
```

### Group T6: Keamanan
```
T6-01: Inject SQL di field email login → tidak ada error DB, tidak bypass
T6-02: Upload file dengan nama `../../etc/passwd` → ditolak atau disanitasi
T6-03: JWT token dari tenant lain dipakai → akses ditolak
T6-04: Akses endpoint tanpa token → redirect ke login
T6-05: Password tanpa huruf besar → validasi frontend + backend menolak
```

---

## 📋 Urutan Kerja (Work Order)

```
WO-01: Setup & Konfigurasi
  → config.py (pydantic settings dari .env)
  → database.py (SQLAlchemy engine, session factory)
  → .env.example dengan semua variabel terdokumentasi

WO-02: Models & Migrasi Database
  → Semua SQLAlchemy models (tenant, user, token, upload, session, audit, invitation)
  → alembic init + migration 001_initial_schema
  → Verifikasi: alembic upgrade head + downgrade -1

WO-03: Layer Autentikasi
  → hashing.py (bcrypt)
  → jwt_handler.py (encode, decode, refresh)
  → session.py (streamlit state management)
  → rate_limiter.py

WO-04: Services Inti
  → auth_service.py (register, login, verifikasi, reset)
  → email_service.py (SMTP via smtplib atau Resend API)
  → audit_service.py (log semua aksi)
  → tenant_service.py
  → upload_service.py (simpan file, cek kuota, proses async)
  → subscription_service.py

WO-05: Halaman Auth & Profil
  → pg_login.py (form + rate limit display)
  → pg_register.py (form lembaga + pengguna pertama)
  → pg_verify_email.py
  → pg_reset_password.py
  → pg_profil.py (edit profil, ganti password)

WO-06: Halaman Manajemen Lembaga
  → pg_tim.py (daftar user, undang, ubah peran, nonaktifkan)
  → pg_upload.py (upload baru + riwayat + hapus)
  → pg_audit.py (tabel log + filter + ekspor)
  → pg_langganan.py (info paket, batas, tombol upgrade)

WO-07: Integrasi Analitik
  → Adaptasi pg_dashboard.py dan pg_analisis.py dari Tahap 1
  → Hubungkan ke upload tersimpan (bukan hanya file yang baru di-upload)
  → Gunakan tenant_id untuk isolasi

WO-08: Panel Super Admin
  → pg_superadmin.py (daftar tenant, statistik, set paket, nonaktifkan)

WO-09: Router Utama & Navigasi
  → app.py yang routing berdasarkan status login & peran
  → navbar.py dan sidebar.py yang adaptif per peran

WO-10: Seed & Scripts
  → seed_dev.py: 3 tenant (Lazismu DIY, Baznas Sleman, YDSF Jogja)
                 10 user dengan semua peran
                 data contoh dari Tahap 1
  → create_superadmin.py: CLI interaktif

WO-11: Pengujian
  → conftest.py dengan fixtures lengkap
  → Semua test group T1–T6
  → pytest --cov dengan target ≥ 70%

WO-12: Docker & Deploy
  → Dockerfile (multi-stage build)
  → docker-compose.yml (app + postgres + pgadmin)
  → render.yaml
  → Health check endpoint
  → README update dengan cara deploy
```

---

## 🌐 Variabel Environment

```bash
# .env.example

# App
APP_ENV=development          # development | production
APP_SECRET_KEY=              # random 32+ chars (JWT signing)
APP_VERSION=2.0.0

# Database
DATABASE_URL=sqlite:///./zakat_insight.db          # dev
# DATABASE_URL=postgresql://user:pass@host/dbname  # prod

# Email (untuk verifikasi & reset password)
EMAIL_ENABLED=false                                 # false untuk dev (print ke console)
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USER=
EMAIL_SMTP_PASS=
EMAIL_FROM=noreply@zakatinsight.id

# Storage
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=50

# Security
JWT_ACCESS_EXPIRE_HOURS=8
JWT_REFRESH_EXPIRE_DAYS=30
LOGIN_MAX_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15

# Super Admin (seed)
SUPERADMIN_EMAIL=admin@zakatinsight.id
SUPERADMIN_PASSWORD=                               # isi sebelum seed
```

---

## 🚀 Target Deploy

| Platform | Konfigurasi | Biaya |
|----------|-------------|-------|
| **Render** (rekomendasi) | `render.yaml`, PostgreSQL addon | Gratis (dev) / \$7/bln (prod) |
| **Railway** | `railway.toml` | \$5/bln |
| **VPS** | Docker Compose | Sesuai VPS |
| **Self-hosted** | Docker Compose | Gratis |

---

## 📊 Metrik Keberhasilan Tahap 2

| Metrik | Target |
|--------|--------|
| Test suite lulus | 100% (0 failed) |
| Test coverage | ≥ 70% |
| Isolasi data antar tenant | 100% (semua T2-xx lulus) |
| Waktu load halaman login | < 2 detik |
| Waktu proses upload 10MB | < 30 detik |
| Docker build berhasil | ✅ |
| Health check endpoint aktif | ✅ |

---

*Zakat Insight v2.0 | SaaS Platform untuk Lembaga Zakat Indonesia*

