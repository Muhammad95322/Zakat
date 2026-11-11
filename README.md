# 🕌 Zakat Insight — Platform SaaS Analitik Transaksi ZIS

> **Zakat Insight** adalah platform web SaaS multi-tenant yang dirancang untuk lembaga zakat, infak, dan sedekah (BAZNAS, LAZ nasional/daerah/provinsi) guna mengolah, menganalisis, memproyeksikan, dan menyajikan laporan penghimpunan serta penyaluran dana sosial keagamaan secara otomatis, transparan, dan profesional.

---

## 🌟 Fitur Utama

- 🏢 **Multi-Tenant & Isolasi Data Penuh**: Setiap lembaga memiliki ruang penyimpanan, pengguna, dan data transaksi yang terpisah secara ketat.
- 👥 **Manajemen Peran & Pengguna (RBAC)**:
  - **Super Administrator**: Mengelola seluruh lembaga dan langganan platform.
  - **Admin Lembaga**: Mengelola data, mengundang staf, dan memantau log audit.
  - **Staf**: Mengunggah berkas, menjalankan analisis, dan mengunduh laporan.
  - **Pembaca**: Mengakses dashboard analitik dan visualisasi (read-only).
- 🧹 **Pembersihan Data Cerdas**:
  - Deteksi sinonim kolom otomatis (*tanggal, nominal, muzaki, asnaf, dll.*).
  - Parsing format angka Indonesia (`Rp 1.500.000`, `Rp 2,5 jt`, `500 rb`).
  - Hapus duplikat persis dan deteksi transaksi bernilai besar (*Outlier IQR*).
- 📊 **Dashboard Analitik & Statistik**:
  - Indikator Kinerja Utama (Total Dana, Muzaki Unik, Rata-Rata Donasi).
  - Analisis Tren Waktu & Pola Musiman (Ramadan dan Akhir Tahun).
  - Komposisi Donasi per Jenis Dana, Kanal Pembayaran, dan Peringkat Wilayah.
  - Uji Statistik Inferensial (*Kruskal-Wallis*) dalam interpretasi bahasa awam.
- 👥 **Segmentasi Muzaki (RFM) & Koefisien Gini**:
  - Segmentasi perilaku donatur (*Muzaki Setia, Potensial, Baru, Tidur, Berisiko*).
  - Analisis Pareto dan Kurva Lorenz untuk pemerataan sumber donasi.
- 🤝 **Tata Kelola Penyaluran & Kas Dana**:
  - Rasio penyaluran terhadap penghimpunan, sisa saldo kas, serta batas wajar bagian amil (*PSAK 109*).
- 🔮 **Proyeksi Penerimaan 12 Bulan**:
  - Prediksi berbasis *Holt-Winters Seasonal Smoothing* lengkap dengan selang kepercayaan 95% dan metrik MAPE.
- 📑 **Ekspor Laporan Resmi**:
  - **Laporan Eksekutif PDF**: Siap cetak dan presentasi dewan pembina/pengawas.
  - **Berkas Excel Multi-Sheet**: Berisi data bersih, ringkasan KPI, segmentasi RFM, dan log pembersihan.
- 🔒 **Keamanan & Audit**:
  - Enkripsi password menggunakan `bcrypt` dan otentikasi berbasis `JWT`.
  - Rate limiting percobaan login dan sanitasi path traversal.
  - Jejak audit (*Audit Log*) setiap aktivitas sensitif.

---

## 🚀 Panduan Memulai Cepat

### 1. Prasyarat
- Python 3.11+
- Pip & Git

### 2. Instalasi Dependensi
```bash
# Clone repositori
git clone https://github.com/Muhammad95322/Zakat.git
cd Zakat

# Salin konfigurasi environment
cp .env.example .env

# Pasang pustaka
pip install -r requirements.txt
```

### 3. Inisialisasi & Data Seed Development
Jalankan perintah berikut untuk membuat tabel dan akun demo:
```bash
python scripts/seed_dev.py
```

### 4. Menjalankan Aplikasi
```bash
streamlit run app.py
```
Buka browser di `http://localhost:8501`.

---

## 🔑 Akun Uji Coba (Development)

Kata sandi akun uji **tidak** dicantumkan di README. Untuk membuat akun:

1. **Data & akun uji (khusus development/staging)** — jalankan:
   ```bash
   python scripts/seed_dev.py
   ```
   Skrip membuat beberapa lembaga contoh beserta akun uji dan mencetak kredensialnya
   di terminal Anda. Skrip **menolak berjalan** bila `APP_ENV=production`.
2. **Super Admin (semua lingkungan, termasuk production)** — jalankan:
   ```bash
   python scripts/create_superadmin.py
   ```
   Anda akan diminta email, nama, dan kata sandi kuat secara interaktif (tidak tersimpan di file mana pun).

---

## 🐳 Menjalankan dengan Docker

```bash
# APP_SECRET_KEY wajib diisi (lewat environment atau file .env)
export APP_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
# Opsional (sangat disarankan di luar laptop sendiri): ganti kata sandi bawaan lokal
export POSTGRES_PASSWORD='...'  PGADMIN_PASSWORD='...'

# Menjalankan aplikasi + PostgreSQL + pgAdmin
docker-compose up -d --build
```
- **Aplikasi Zakat Insight**: `http://localhost:8501`
- **pgAdmin**: `http://localhost:5050` (email dari `PGADMIN_EMAIL`, kata sandi dari `PGADMIN_PASSWORD`; nilai bawaan di `docker-compose.yml` hanya untuk lokal)

---

## 🧪 Menjalankan Pengujian (Testing)

```bash
# Jalankan seluruh unit test
pytest tests/ -v
```

Pemeriksaan kesehatan sistem (Healthcheck):
```bash
python scripts/check_health.py
```

---

## 📁 Struktur Direktori

```
Zakat/
├── app.py                      # Router utama aplikasi Streamlit
├── requirements.txt            # Dependensi paket Python
├── Dockerfile                  # Konfigurasi container produksi
├── docker-compose.yml          # Stack PostgreSQL + App + pgAdmin
├── render.yaml                 # Spesifikasi deploy Render Cloud
├── .env.example                # Contoh variabel lingkungan
├── scripts/
│   ├── seed_dev.py             # Seeding basis data awal
│   ├── create_superadmin.py    # CLI pembuatan Super Administrator
│   └── check_health.py         # Skrip healthcheck
├── src/
│   ├── config.py               # Pengaturan aplikasi
│   ├── database.py             # Koneksi engine SQLAlchemy
│   ├── utils.py                # Utilitas format rupiah & tanggal
│   ├── sample_data.py          # Generator data sintetis realistis
│   ├── loader.py               # Loader berkas Excel/CSV cerdas
│   ├── cleaning.py             # Pembersihan & normalisasi data
│   ├── analysis.py             # Mesin analisis statistik & KPI
│   ├── rfm.py                  # Segmentasi RFM & Kurva Lorenz
│   ├── forecasting.py          # Proyeksi peramalan Holt-Winters
│   ├── charts.py               # Visualisasi interaktif Plotly
│   ├── report_pdf.py           # Generator laporan PDF
│   ├── report_excel.py         # Generator laporan Excel
│   ├── auth/                   # Hashing, JWT, dan sesi
│   ├── middleware/             # Rate limiter & sanitasi keamanan
│   ├── models/                 # Model relasional SQLAlchemy ORM
│   ├── repositories/           # Akses data (Data Access Layer)
│   ├── services/               # Logika bisnis (Business Logic)
│   ├── components/             # Komponen UI navbar adaptif
│   └── pages/                  # Halaman antarmuka pengguna
└── tests/                      # Suite pengujian otomatis pytest
```

---

*Dikembangkan dengan ❤️ untuk transparansi dan tata kelola digital filantropi Islam Indonesia.*
