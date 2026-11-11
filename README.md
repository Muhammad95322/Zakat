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
  - Metode dipilih sesuai panjang data: rata-rata bergerak (< 12 bulan), tren linier + faktor musiman (12–23 bulan), *Holt-Winters* (≥ 24 bulan, statsmodels). Bila statsmodels tidak ada atau model gagal konvergen, dipakai *Tren linier sederhana* dengan peringatan eksplisit.
  - Interval ~95% dan **MAPE dari backtest nyata**; jika data terlalu pendek, MAPE ditampilkan "tidak tersedia".
- 📑 **Ekspor Laporan Resmi**:
  - **Laporan Eksekutif PDF**: Siap cetak, memuat grafik tren bulanan, komposisi jenis dana, proyeksi, serta catatan metode & asumsi.
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

Suite mencakup tes unit (loader, pembersihan, RFM/Gini, peramalan, utilitas, PDF, konfigurasi)
dan tes ujung ke ujung (`tests/test_e2e.py`) yang juga merender halaman Analisis lewat
`streamlit.testing` serta mensimulasikan statsmodels tidak terpasang dan `APP_ENV=production`.

Validasi konfigurasi sebelum start (dipakai otomatis oleh Dockerfile dan render.yaml):
```bash
python scripts/validate_config.py
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
│   ├── check_health.py         # Skrip healthcheck
├── src/
│   ├── config.py               # Pengaturan aplikasi
│   ├── database.py             # Koneksi engine SQLAlchemy
│   ├── utils.py                # Utilitas format rupiah & tanggal
│   ├── sample_data.py          # Generator data sintetis realistis
│   ├── loader.py               # Loader berkas Excel/CSV cerdas
│   ├── cleaning.py             # Pembersihan & normalisasi data
│   ├── analysis.py             # Mesin analisis statistik & KPI
│   ├── rfm.py                  # Segmentasi RFM & Kurva Lorenz
│   ├── pipeline.py             # Muat -> validasi -> bersihkan (pesan error ramah)
│   ├── forecasting.py          # Peramalan + MAPE backtest + fallback jujur
│   ├── charts.py               # Visualisasi interaktif Plotly
│   ├── report_charts.py        # Grafik statis matplotlib untuk PDF
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

## 🔐 Keamanan Konfigurasi

- Dengan `APP_ENV=production`, aplikasi **menolak start** bila `APP_SECRET_KEY` masih nilai bawaan/contoh
  atau kurang dari 32 karakter (dicek di `app.py`, `scripts/validate_config.py`, dan healthcheck).
- `docker-compose.yml` tidak memberi nilai bawaan untuk `APP_SECRET_KEY`; `docker compose up` gagal sampai kunci diisi.
- Kata sandi Postgres/pgAdmin di `docker-compose.yml` dapat dioverride lewat `POSTGRES_PASSWORD` dan `PGADMIN_PASSWORD`;
  nilai bawaannya hanya untuk pengembangan lokal. Port DB dan pgAdmin hanya dibuka di `127.0.0.1`.
- `scripts/seed_dev.py` menolak berjalan bila `APP_ENV=production`.

---

## 🔎 Investigasi Selisih MAPE (asal angka 218%)

Backtest per metode (6 bulan terakhir sebagai data uji, 30 bulan pertama sebagai data latih), dijalankan
dengan kode peramalan versi PR #1 pada data sintetis `generate_sample_data()` (biji acak 42):

| Metode | Bulan latih | Bulan uji | MAPE — data bawaan (5000 transaksi) | MAPE — data uji UI (1500 transaksi) |
|---|---|---|---|---|
| Rata-rata bergerak 3 bulan | 30 | 6 | 18,20% | 38,40% |
| Tren linier sederhana | 30 | 6 | 21,95% | **218,40%** |
| Tren linier + faktor musiman bulanan | 30 | 6 | 46,22% | 101,76% |
| Holt-Winters (statsmodels) | 30 | 6 | 72,91% | 82,12% |

**Kesimpulan:** angka 218% *bisa direproduksi*, tetapi bukan dari data contoh bawaan. Angka itu berasal dari
uji UI di laporan PR #1 yang memakai `generate_sample_data(1500, 200)` dengan statsmodels diblokir. Biji acaknya
sama (42), tetapi jumlah transaksinya berbeda sehingga deret bulanannya juga lain: penerimaan 6 bulan uji di data
kecil hanya Rp 40–112 jt, sedangkan tren linier yang dilatih pada 30 bulan sebelumnya masih memproyeksikan jauh di atasnya.
Ringkasan PR #1 keliru karena menyandingkan angka itu dengan MAPE Holt-Winters dari data lain, seolah keduanya dari
data yang sama. Pada data bawaan yang sama, tren linier (21,95%) jauh lebih baik daripada Holt-Winters (72,91%),
dan rata-rata bergerak (18,20%) lebih baik lagi. Inilah alasan pemilihan metode diubah agar berbasis backtest.

Catatan ukuran data contoh: generator bawaan memakai 5000 transaksi, tombol "Muat Data Contoh" di UI memakai 2000,
dan `data/sample/data_contoh.xlsx` dibuat dari 2000. Hasil MAPE berbeda untuk tiap ukuran.

Reproduksi: `python scripts/bandingkan_metode.py` (lihat juga `--transaksi 1500`).

---

## 📝 Asumsi & Catatan Metode

Asumsi yang diambil selama perbaikan rilis (silakan koreksi bila tidak sesuai kebutuhan lembaga):

1. **Kolom wajib** sheet penghimpunan hanya `tanggal` dan `jumlah` (atau sinonimnya, mis. `tgl`, `nominal`).
   Kolom lain opsional; analisis yang membutuhkannya (mis. RFM tanpa `id_muzaki`/`nama_muzaki`) menyesuaikan.
   Sheet penyaluran bersifat opsional: bila kosong atau kolom wajibnya hilang, sheet diabaikan dengan catatan di log, analisis penghimpunan tetap berjalan.
2. **Berkas divalidasi saat unggah**: berkas kosong, rusak, tanpa kolom wajib, atau tanpa satu pun baris valid
   ditolak sebelum disimpan dan tidak memakan kuota. Berkas lama yang sudah tersimpan tetap divalidasi saat dianalisis.
3. **Pembersihan**: baris dengan `jumlah` teks/nol/negatif dan tanggal tidak valid dibuang dan dicatat di log;
   duplikat persis dihapus; outlier (IQR × 3) tetap dihitung dalam total. Total di KPI = jumlah `jumlah` setelah pembersihan
   (diverifikasi otomatis terhadap perhitungan pandas langsung di `tests/test_e2e.py`).
4. **Peramalan**: metode per panjang data — rata-rata 3 bulan (3–11 bulan), tren linier + faktor musiman bulanan
   (12–23 bulan), Holt-Winters aditif periode 12 (≥ 24 bulan). Fallback = tren linier sederhana tanpa musiman.
5. **MAPE backtest**: hingga 6 bulan terakhir disisihkan sebagai data uji dengan syarat minimal 3 bulan uji dan
   data latih sepanjang minimum metode (3 / 12 / 24 bulan). Karena itu MAPE "tidak tersedia" untuk data 3–5, 12–14,
   dan 24–26 bulan. Bulan dengan nilai aktual 0 dikecualikan dari MAPE. Nilai MAPE dilaporkan apa adanya (bisa > 50%).
   Holt-Winters yang memberi `ConvergenceWarning` diperlakukan sebagai gagal konvergen sehingga fallback dipakai.
6. **Interval ~95%** = proyeksi ± 1,96 × simpangan baku residual in-sample; asumsi galat kira-kira normal dan pola historis berlanjut.
   Interval ini cenderung terlalu sempit untuk horizon jauh.
7. **RFM**: bila banyak nilai recency/monetary kembar sehingga kuantil tidak unik, skor kuantil dihitung dari peringkat
   (sebelumnya kasus ini membuat aplikasi crash).
8. **Grafik PDF** dirender dengan matplotlib (bukan plotly+kaleido) agar tidak memerlukan browser/Chrome di server.
   Teks PDF memakai font inti Latin-1; karakter di luar itu (emoji, dsb.) diganti `?`.
9. **Sesi basis data** memakai `expire_on_commit=False` karena halaman membaca objek setelah sesi ditutup.
10. File `.env` tidak lagi di-mount ke container; Docker Compose tetap membaca `.env` di folder proyek untuk substitusi variabel,
    dan aplikasi membaca konfigurasi dari environment variable.
11. Data contoh di `data/sample/` sepenuhnya sintetis (dibuat `src/sample_data.py`), bukan data donatur asli.

---

*Dikembangkan dengan ❤️ untuk transparansi dan tata kelola digital filantropi Islam Indonesia.*
