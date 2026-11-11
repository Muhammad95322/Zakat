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
  - **Metode dipilih lewat backtest bergulir** (hingga 12 titik awal, horizon 6 bulan): rata-rata bergerak, tren linier, naif musiman, tren + faktor musiman, tren + penanda Ramadan/Idulfitri (kalender Hijriah), dan *Holt-Winters*. Peringkat memakai rata-rata MAPE pada jendela yang diuji semua metode.
  - MAPE yang tampil = **rata-rata lintas titik awal** metode terpilih, beserta SD dan rentangnya. **Tabel perbandingan** (rata-rata, terburuk, jumlah jendela, status) tampil di UI, PDF, dan Excel.
  - Peringatan bila MAPE terpilih > 50%, bila metode gagal di > 1/3 titik awal ("tidak andal"), bila statsmodels tidak tersedia, dan catatan bila pilihan metode tidak stabil.
  - **Selang 80% dari galat backtest** (bukan residual); "tidak tersedia" bila galat backtest kurang dari 10.
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
pip install -r requirements.txt -c constraints.txt
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
├── requirements.txt            # Dependensi paket Python (batas minimum)
├── constraints.txt             # Versi pasti pustaka numerik (wajib dipakai: -c constraints.txt)
├── Dockerfile                  # Konfigurasi container produksi
├── docker-compose.yml          # Stack PostgreSQL + App + pgAdmin
├── render.yaml                 # Spesifikasi deploy Render Cloud
├── .env.example                # Contoh variabel lingkungan
├── scripts/
│   ├── seed_dev.py             # Seeding basis data awal
│   ├── create_superadmin.py    # CLI pembuatan Super Administrator
│   ├── check_health.py         # Skrip healthcheck
│   ├── validate_config.py      # Tolak start jika konfigurasi production tidak aman
│   ├── bandingkan_metode.py    # Tabel MAPE backtest bergulir per metode
│   └── ukur_waktu_peramalan.py # Ukur waktu peramalan (36/120 bulan)
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
│   ├── forecasting.py          # Peramalan: backtest bergulir, pemilihan & selang
│   ├── kalender_hijriah.py     # Perkiraan Ramadan/Idulfitri 2015-2030 (fitur musiman)
│   ├── waktu.py                # utc_now() terpusat
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

### Hasil PR #2: satu jendela uji (digantikan backtest bergulir, lihat di bawah)

Tabel PR #2 (30 bulan latih, 6 bulan uji Jul–Des 2024; satu jendela):

| Metode | Data bawaan (5000 transaksi) | `data_contoh.xlsx` (2000 transaksi) |
|---|---|---|
| Rata-rata bergerak 3 bulan terakhir | **18,20% (terpilih)** | 233,86% |
| Tren linier sederhana | 21,95% | 102,29% |
| Naif musiman (bulan yang sama tahun lalu) | 30,38% | 117,41% |
| Tren linier + faktor musiman bulanan | 46,22% | 71,67% |
| Tren linier + penanda Ramadan/Idulfitri | 40,68% | **51,21% (terpilih)** |
| Holt-Winters (statsmodels) | 72,91% | 153,05% |

Satu jendela uji ternyata berisik: pemenangnya dipilih dari enam kandidat pada enam bulan saja, sehingga MAPE yang
tampil terlalu optimistis (mis. 18,20% untuk rata-rata bergerak, padahal rata-ratanya di 12 jendela 37,97%).

### Hasil backtest bergulir (versi sekarang)

36 bulan data, horizon 6 bulan, titik awal = bulan latih 19–30 (12 jendela; Holt-Winters 24–30 karena butuh
24 bulan latih). "Bersama" = rata-rata pada 7 jendela (bulan latih 24–30) yang diuji semua metode; kolom inilah
dasar peringkat. MAPE dalam persen. Reproduksi: `python scripts/bandingkan_metode.py [--transaksi 2000 | --berkas data/sample/data_contoh.xlsx]`.

**Data bawaan (5000 transaksi)** — terpilih: **tren linier sederhana, 26,86%** (SD 5,61; rentang 18,44–37,15%)

| Metode | Rata-rata | Median | Terburuk | SD | Bersama | Jendela |
|---|---|---|---|---|---|---|
| Rata-rata bergerak 3 bulan | 37,97 | 32,04 | 78,98 | 17,48 | 30,77 | 12 |
| **Tren linier sederhana** | **26,86** | 26,57 | 37,15 | 5,61 | **26,65** | 12 |
| Naif musiman | 45,76 | 43,91 | 63,78 | 10,61 | 50,60 | 12 |
| Tren linier + faktor musiman | 39,47 | 40,46 | 57,23 | 10,38 | 46,23 | 12 |
| Tren linier + penanda Ramadan | 33,16 | 34,21 | 46,23 | 8,67 | 38,98 | 12 |
| Holt-Winters | 61,51 | 67,76 | 72,91 | 12,87 | 61,51 | 7 |

Catatan stabilitas muncul: pada 7 jendela bersama, tren linier hanya 4,11 poin lebih baik dari rata-rata bergerak
dan unggul di 3 dari 7 jendela.

**Data 2000 transaksi** dan **`data/sample/data_contoh.xlsx`** (identik: sheet penghimpunan dibuat dari biji acak dan
jumlah transaksi yang sama) — terpilih: **tren linier sederhana, 98,76%** (SD 39,62; rentang 45,11–180,34%),
dengan peringatan bahwa proyeksi belum dapat diandalkan (> 50%) dan catatan pilihan tidak stabil.

| Metode | Rata-rata | Median | Terburuk | SD | Bersama | Jendela |
|---|---|---|---|---|---|---|
| Rata-rata bergerak 3 bulan | 119,31 | 76,66 | 236,65 | 79,91 | 90,65 | 12 |
| **Tren linier sederhana** | **98,76** | 91,35 | 180,34 | 39,62 | **71,50** | 12 |
| Naif musiman | 170,72 | 141,61 | 249,23 | 63,91 | 121,70 | 12 |
| Tren linier + faktor musiman | 145,89 | 95,12 | 271,82 | 89,61 | 75,43 | 12 |
| Tren linier + penanda Ramadan | 123,65 | 133,72 | 192,33 | 51,44 | 102,17 | 12 |
| Holt-Winters | 82,59 | 72,29 | 153,05 | 33,91 | 82,59 | 7 |

**Mengapa peringkat memakai jendela bersama:** bila rata-rata masing-masing metode dibandingkan langsung, Holt-Winters
"menang" di data 2000 transaksi (82,59%) hanya karena ia dinilai pada 7 jendela terbaru yang lebih mudah. Pada 7 jendela
yang sama, tren linier lebih baik (71,50% vs 82,59%). Peringkat pada jendela bersama menghapus bias itu; MAPE yang
ditampilkan tetap rata-rata seluruh jendela metode terpilih.

Angka acuan awal di permintaan (tren linier 26,07%, rata-rata bergerak 28,60%; data 2000: tren linier 66,25%, Ramadan
73,38%) tidak sama persis dengan hasil di atas, kemungkinan karena pilihan titik awal/horizon yang berbeda; kode tidak
disetel untuk mencocokkannya.

Tanpa statsmodels, Holt-Winters tercatat "tidak tersedia" tanpa angka; jendela bersama 5 metode lainnya menjadi 12 dan
metode terpilih untuk data bawaan tetap tren linier (26,86%).

**Waktu hitung** (`python scripts/ukur_waktu_peramalan.py`, median 5 ulangan): 36 bulan **0,34 detik**, 120 bulan
**0,81 detik** (target < 15 detik). Holt-Winters mendominasi; tanpa statsmodels 0,03–0,05 detik. Tidak perlu cache.

---

## 📌 Memperbarui `constraints.txt`

Hasil peramalan (terutama Holt-Winters) bergantung pada versi statsmodels, numpy, scipy, dan pandas. Contoh nyata:
dengan statsmodels 0.14.4, numpy 2.2.6, dan scipy 1.15.3 (semuanya masih diizinkan `requirements.txt`),
Holt-Winters gagal konvergen di **7 dari 7** titik awal pada data contoh. Dengan versi di `constraints.txt`,
ketujuhnya konvergen. Karena itu semua instalasi resmi (CI, Dockerfile, render.yaml, README) memakai
`pip install -r requirements.txt -c constraints.txt`.

Langkah memperbarui versi dengan aman:

1. **Sebelum mengubah**, di lingkungan dengan constraints lama, simpan hasil acuan:
   ```bash
   python -m pytest -q
   ```
   ```bash
   for a in "" "--transaksi 2000" "--berkas data/sample/data_contoh.xlsx"; do python scripts/bandingkan_metode.py $a; done > /tmp/sebelum.txt
   ```
2. Ubah versi di `constraints.txt`. Pastikan versi itu tersedia untuk **Python 3.11 dan 3.12** (Dockerfile memakai 3.11);
   bila tidak, pakai penanda lingkungan, mis. `numpy==2.5.4; python_version >= "3.12"`.
3. Pasang ulang di venv bersih untuk tiap versi Python, lalu jalankan lagi pytest dan skrip pembanding:
   ```bash
   python3.11 -m venv /tmp/v311 && /tmp/v311/bin/pip install -r requirements.txt -c constraints.txt
   ```
   ```bash
   for a in "" "--transaksi 2000" "--berkas data/sample/data_contoh.xlsx"; do python scripts/bandingkan_metode.py $a; done > /tmp/sesudah.txt
   ```
4. Bandingkan `diff /tmp/sebelum.txt /tmp/sesudah.txt`. Perubahan MAPE, jumlah jendela gagal, atau metode terpilih
   harus dijelaskan di deskripsi PR (bukan disembunyikan); perbarui tabel hasil di README bila berubah.
5. CI menjalankan seluruh tes di Python 3.11 dan 3.12 serta membangun image Docker dengan constraints yang sama.

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
4. **Peramalan — backtest bergulir (rolling origin)**: untuk tiap titik awal t, metode dilatih hanya pada y[:t] dan
   memprediksi y[t:t+H] (diuji dengan uji mutasi: dua cara kebocoran sengaja, keduanya tertangkap tes).
   - **Horizon H = 6 bulan**: sama dengan jendela PR #2 dan setengah dari horizon proyeksi 12 bulan; cukup panjang
     untuk menilai proyeksi jangka menengah, cukup pendek agar masih ada banyak titik awal pada data 3 tahun.
     Untuk data pendek H diperpendek menjadi min(6, n − 4), minimal 3; data < 7 bulan: tanpa backtest
     (rata-rata bergerak, MAPE "tidak tersedia").
   - **Titik awal: maksimal 12 terbaru, langkah 1 bulan**, hanya yang horizon penuhnya tersedia (t + H ≤ n). Dua belas
     jendela mencakup satu siklus tahunan penuh (setiap bulan kalender, termasuk Ramadan, pernah menjadi awal horizon),
     dan menjaga waktu hitung tetap kecil; jendela lama kurang relevan dengan pola terbaru.
   - Syarat minimal data latih tiap metode berlaku per titik awal; metode dengan < 2 titik awal valid tidak diuji.
   - **Peringkat**: rata-rata MAPE pada *jendela bersama* (titik awal yang diuji semua metode yang andal); bila jendela
     bersama < 2, dipakai rata-rata masing-masing. Pemecah seri: urutan kesederhanaan (rata-rata bergerak, tren linier,
     naif musiman, tren + musiman, tren + Ramadan, Holt-Winters). Metode terpilih dilatih ulang pada seluruh data.
     *Penyimpangan dari permintaan:* permintaan menyebut "rata-rata MAPE terkecil lintas titik awal"; dipakai jendela
     bersama karena rata-rata pada jendela berbeda terbukti bias (lihat bagian hasil di atas).
   - **Tidak andal**: metode yang gagal (mis. tidak konvergen) di lebih dari 1/3 titik awal yang dicoba ditandai
     "tidak andal" dan tidak dapat terpilih; statistik jendela yang berhasil tetap ditampilkan.
   - **Tidak stabil**: catatan muncul bila |selisih rata-rata MAPE| dua metode teratas pada jendela dasar peringkat
     < simpangan baku selisih per jendela (berpasangan).
   Syarat data latih minimum: rata-rata bergerak & tren linier 3 bulan; tren + musiman, naif musiman, dan tren + Ramadan
   12 bulan (naif musiman hanya ikut bila data ≥ 24 bulan); Holt-Winters 24 bulan latih (praktis data ≥ 30 bulan).
5. **MAPE**: per jendela = rata-rata |aktual − prediksi| / aktual pada H bulan (bulan dengan aktual 0 dikecualikan;
   jendela dengan semua aktual 0 dilewati). Yang ditampilkan = rata-rata seluruh jendela metode terpilih, beserta SD
   (ddof=1) dan rentang; nilai apa adanya (bisa > 50%). Bila MAPE terpilih > 50%, muncul peringatan bahwa proyeksi
   belum dapat diandalkan. Holt-Winters yang gagal diimpor dicatat "tidak tersedia"; `ConvergenceWarning` dihitung
   sebagai kegagalan pada titik awal itu.
5a. **Penanda Ramadan**: tanggal 1 Ramadan dan 1 Syawal 2015–2030 di `src/kalender_hijriah.py` adalah **perkiraan**
   (dapat berbeda 1–2 hari dari penetapan resmi). Fitur bulanan = porsi hari Ramadan dalam bulan itu (jumlah per
   Ramadan = 1) dan penanda bulan Idulfitri; model = regresi tren linier + kedua fitur. Kandidat dinonaktifkan dengan
   pesan jelas bila data atau 12 bulan proyeksi berada di luar 2015–2030, atau bila periode latih tidak berisi Ramadan.
6. **Selang 80% dari galat backtest**: galat relatif (aktual − prediksi) / prediksi metode terpilih dikumpulkan dari
   semua titik awal dan langkah horizon 1–H; selang = proyeksi × (1 + kuantil 10% dan 90%). Level 80% (bukan 95%)
   dipilih karena dengan ~72 galat kuantil 2,5%/97,5% hanya ditentukan oleh 1–2 nilai ekstrem. Bila galat < 10 atau
   tanpa backtest, selang "tidak tersedia" (kolom batas kosong) beserta alasannya. Batas bawah tidak pernah < 0.
   Bulan proyeksi ke-7–12 memakai sebaran galat horizon 1–6, sehingga selang di sana kemungkinan terlalu sempit.
7. **RFM**: bila banyak nilai recency/monetary kembar sehingga kuantil tidak unik, skor kuantil dihitung dari peringkat
   (sebelumnya kasus ini membuat aplikasi crash).
8. **Grafik PDF** dirender dengan matplotlib (bukan plotly+kaleido) agar tidak memerlukan browser/Chrome di server.
   Teks PDF memakai font inti Latin-1; karakter di luar itu (emoji, dsb.) diganti `?`.
9. **Sesi basis data** memakai `expire_on_commit=False` karena halaman membaca objek setelah sesi ditutup.
10. File `.env` tidak lagi di-mount ke container; Docker Compose tetap membaca `.env` di folder proyek untuk substitusi variabel,
    dan aplikasi membaca konfigurasi dari environment variable.
11. Data contoh di `data/sample/` sepenuhnya sintetis (dibuat `src/sample_data.py`), bukan data donatur asli.
12. **Waktu**: `src/waktu.py::utc_now()` memakai `datetime.now(timezone.utc)` lalu melepas tzinfo. Kolom `DateTime`
    tetap menyimpan UTC *naive* seperti sebelumnya (SQLite tidak menyimpan zona waktu), sehingga data lama tetap
    kompatibel dan perbandingan waktu tidak memicu `TypeError`. Tidak ada migrasi skema.
13. **File `.env`** dimuat otomatis oleh `src/config.py` (python-dotenv) **tanpa menimpa** variabel yang sudah ada di
    environment. Lokasi bisa diubah dengan `APP_ENV_FILE`; string kosong menonaktifkan pemuatan (dipakai di tes dan CI).
    `.dockerignore` mencegah `.env`, `*.db`, dan `uploads/` ikut masuk image Docker.
14. **CI** (`.github/workflows/tests.yml`) menjalankan pytest di Python 3.11 dan 3.12 pada setiap pull request dan pada
    push ke `main` (push ke branch lain tidak memicu job ganda). Job `docker` membangun image dari Dockerfile (tanpa push
    ke registry), menjalankan `validate_config.py` (development lolos, production dengan kunci bawaan ditolak), mengimpor
    semua modul, menjalankan pytest di dalam image tanpa jaringan, dan memeriksa `docker compose config`
    (valid dengan kunci dummy, gagal jelas tanpa `APP_SECRET_KEY`),
    dengan cache pip dan tanpa rahasia apa pun.
15. **Docker**: Dockerfile tidak lagi memasang `gcc` lewat apt karena semua dependensi tersedia sebagai wheel untuk
    Python 3.11 (diverifikasi dengan `pip install --only-binary=:all:`). Saat container start, tabel basis data dibuat
    (`init_db`) sebelum Streamlit berjalan, sehingga healthcheck langsung sehat (sebelumnya container "unhealthy" sampai
    ada pengunjung pertama). Driver PostgreSQL `psycopg[binary]` ditambahkan (sebelumnya tidak ada, sehingga
    `docker compose up` gagal saat menyambung ke Postgres); URL `postgres://` (Render) dan `postgresql://` dinormalkan ke
    `postgresql+psycopg://` di `src/database.py`. Diverifikasi lokal: `docker compose up` dengan Postgres 16 → app dan db
    healthy, `check_health.py` lulus, Streamlit merespons 200.

---

*Dikembangkan dengan ❤️ untuk transparansi dan tata kelola digital filantropi Islam Indonesia.*
