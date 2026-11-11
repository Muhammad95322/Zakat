# 📋 Panduan Prompt: Lazismu Insight — Step by Step

> File ini berisi prompt terstruktur untuk membangun project **Lazismu Insight** secara sistematis dari awal hingga selesai. Jalankan setiap langkah secara berurutan ke AI coding assistant.

---

## 🧭 Cara Menggunakan File Ini

1. Baca seluruh file ini terlebih dahulu agar paham alur besarnya.
2. Jalankan **prompt utama (Tahap 0)** terlebih dahulu untuk mendirikan fondasi.
3. Lanjutkan ke **Tahap 1–7** secara berurutan.
4. Setiap tahap memiliki **kriteria selesai (✅ Done When)** — jangan lanjut ke tahap berikutnya sebelum kriteria terpenuhi.
5. Gunakan **prompt verifikasi** di akhir setiap tahap untuk memastikan hasil benar.

---

## ⚙️ PERAN AI (Sertakan di awal setiap sesi baru)

```
Kamu adalah senior full-stack data engineer dan analis data yang membangun produk siap pakai.
Kerjakan dari awal sampai selesai, jalankan sendiri kodenya, uji, dan perbaiki sampai tidak ada error.
Jangan berhenti di tengah dan jangan bertanya kecuali benar-benar buntu; jika ada asumsi, tulis
di README dan lanjutkan.
```

---

## 🗺️ Arsitektur Proyek

```
lazismu-insight/
├── app.py                  ← Entry point Streamlit
├── requirements.txt        ← Semua dependensi
├── README.md               ← Dokumentasi lengkap Bahasa Indonesia
├── src/
│   ├── loader.py           ← Upload, parsing, deteksi kolom
│   ├── cleaning.py         ← Pembersihan & normalisasi data
│   ├── analysis.py         ← Semua kalkulasi & statistik
│   ├── forecasting.py      ← Holt-Winters / SARIMA / fallback
│   ├── rfm.py              ← Segmentasi RFM muzaki
│   ├── charts.py           ← Semua fungsi grafik Plotly
│   ├── report_pdf.py       ← Generate laporan PDF
│   ├── report_excel.py     ← Generate ekspor Excel
│   ├── sample_data.py      ← Generator data sintetis realistis
│   └── utils.py            ← Format rupiah, tanggal, helper
├── tests/
│   ├── test_loader.py
│   ├── test_cleaning.py
│   ├── test_analysis.py
│   ├── test_rfm.py
│   ├── test_forecasting.py
│   └── test_utils.py
└── data/
    ├── sample/             ← File contoh CSV/Excel
    └── template/           ← Template Excel kosong untuk diunduh
```

---

## 📊 Skema Data

### Sheet 1: PENGHIMPUNAN
| Kolom | Keterangan |
|---|---|
| `tanggal` | Tanggal transaksi (berbagai format) |
| `id_muzaki` | ID unik donatur |
| `nama_muzaki` | Nama donatur |
| `jenis_dana` | Zakat Fitrah / Zakat Maal / Zakat Profesi / Infak / Sedekah / Wakaf / Dana Sosial Keagamaan Lainnya |
| `kanal` | Transfer Bank / Tunai / QRIS / Kantor Layanan / Mitra/Online |
| `kabupaten_kota` | Wilayah asal donatur |
| `kampanye` | Nama kampanye (opsional) |
| `jumlah` | Nominal dalam rupiah |

### Sheet 2: PENYALURAN
| Kolom | Keterangan |
|---|---|
| `tanggal` | Tanggal penyaluran |
| `program` | Pendidikan / Kesehatan / Ekonomi / Sosial-Dakwah / Kemanusiaan/Bencana |
| `asnaf` | Fakir / Miskin / Amil / Muallaf / Riqab / Gharimin / Fisabilillah / Ibnu Sabil / Non-Asnaf |
| `jenis_dana_sumber` | Sumber dana yang digunakan |
| `kabupaten_kota` | Wilayah penyaluran |
| `jumlah_penerima` | Jumlah penerima manfaat |
| `jumlah` | Nominal dalam rupiah |

---

---

## 🚀 TAHAP 0 — Setup Fondasi & Struktur Proyek

### Prompt:
```
Buat struktur proyek lengkap untuk aplikasi web "Lazismu Insight" dengan spesifikasi berikut:

TUJUAN PRODUK:
Bangun aplikasi web "Lazismu Insight": pengguna (staf Lazismu atau lembaga zakat sejenis,
tingkat wilayah/daerah) mengunggah file Excel/CSV berisi data penghimpunan dan penyaluran dana
ZIS (Zakat, Infak, Sedekah, dan dana sosial keagamaan lain). Aplikasi otomatis membersihkan data,
menjalankan analisis, menampilkan dashboard interaktif, dan menghasilkan laporan PDF serta Excel
yang siap dipresentasikan.

TECH STACK:
- Python 3.11+, Streamlit untuk UI
- pandas, numpy, scipy, statsmodels untuk pengolahan dan statistik
- plotly untuk grafik interaktif
- openpyxl/xlsxwriter untuk ekspor Excel; reportlab atau fpdf2 untuk ekspor PDF
- pytest untuk pengujian
- Semua dependensi di requirements.txt; aplikasi harus jalan dengan:
  pip install -r requirements.txt
  streamlit run app.py

YANG HARUS DIBUAT SEKARANG:
1. Buat seluruh struktur folder sesuai arsitektur di atas
2. Buat requirements.txt dengan semua dependensi yang diperlukan (versi terbaru stabil)
3. Buat app.py sebagai kerangka utama Streamlit dengan navigasi tab:
   - Ringkasan, Tren & Peramalan, Muzaki, Penyaluran, Kualitas Data, Laporan
   - Sidebar dengan filter global (rentang tanggal, jenis dana, kanal, kabupaten/kota)
   - Tema hijau-teal profesional via custom CSS
   - State management dengan st.session_state
4. Buat utils.py dengan fungsi: format rupiah (Rp 1.500.000, singkatan jt/M), format tanggal
   Indonesia, dan helper lainnya
5. Buat README.md awal berbahasa Indonesia

Jalankan: pip install -r requirements.txt dan verifikasi tidak ada error instalasi.
```

### ✅ Done When:
- [ ] Semua folder dan file terbuat
- [ ] `pip install -r requirements.txt` selesai tanpa error
- [ ] `streamlit run app.py` jalan dan tampil halaman kosong tanpa error
- [ ] `utils.py` sudah berfungsi

---

## 🎲 TAHAP 1 — Generator Data Sintetis & Loader

### Prompt:
```
Lanjutkan project Lazismu Insight. Sekarang bangun modul src/sample_data.py dan src/loader.py.

src/sample_data.py — Generator Data Sintetis:
Buat data realistis untuk 3 tahun (2022-2024) dengan karakteristik:
- Minimal 5.000 transaksi penghimpunan
- Pola musiman: lonjakan signifikan di bulan Ramadan (bulan ke-3 atau ke-4 tergantung tahun)
  dan akhir tahun (Desember, efek zakat fitrah dan donasi akhir tahun)
- 500+ muzaki unik dengan distribusi realistis (sedikit donatur besar, banyak kecil)
- 5 kabupaten/kota di DIY: Kota Yogyakarta, Sleman, Bantul, Gunungkidul, Kulonprogo
- Semua jenis_dana dan kanal terisi dengan proporsi realistis
- Sengaja masukkan: 50 baris duplikat persis, 30 nilai kosong acak, 20 outlier (donasi
  sangat besar tidak wajar), 15 format tanggal berbeda, 10 format angka Indonesia
  ("1.500.000", "Rp 2jt", "500rb")
- Data penyaluran: 1.500+ transaksi, mencakup semua program dan asnaf
- Simpan ke data/sample/data_contoh.xlsx (2 sheet: Penghimpunan, Penyaluran)
- Simpan juga versi CSV terpisah

src/loader.py — Upload & Deteksi Cerdas:
- Fungsi load_file(file) yang terima .xlsx/.xls/.csv, kembalikan dict berisi dataframe
- Deteksi otomatis kolom dengan toleransi: huruf besar/kecil, spasi, sinonim
  (contoh: "tgl"→tanggal, "nominal"→jumlah, "donatur"→nama_muzaki, "amount"→jumlah)
- Jika ada kolom yang tidak terdeteksi, kembalikan info untuk halaman pemetaan kolom manual
- Fungsi generate_template() yang buat file template Excel kosong dengan header dan contoh 1 baris
- Tambahkan tombol "Gunakan data contoh" dan "Unduh template" di app.py

Jalankan generator dan verifikasi file terbuat. Uji loader dengan file contoh.
Tulis tests/test_loader.py dan jalankan pytest.
```

### ✅ Done When:
- [ ] `data/sample/data_contoh.xlsx` terbuat dengan 2 sheet
- [ ] Data contoh memiliki pola musiman yang realistis
- [ ] Loader berhasil deteksi kolom otomatis
- [ ] Template Excel bisa diunduh
- [ ] `pytest tests/test_loader.py` lulus semua

---

## 🧹 TAHAP 2 — Pembersihan Data & Kualitas Data

### Prompt:
```
Lanjutkan project Lazismu Insight. Sekarang bangun src/cleaning.py dan tab "Kualitas Data" di app.py.

src/cleaning.py — Pembersihan Otomatis:
Buat fungsi clean_data(df, sheet_type) yang melakukan:

1. Normalisasi tanggal:
   - Tangani berbagai format: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, "15 Januari 2023",
     "15/01/23", timestamp Excel (angka serial)
   - Catat setiap konversi yang dilakukan

2. Normalisasi angka format Indonesia:
   - "1.500.000" → 1500000
   - "Rp 1,5 jt" → 1500000
   - "500rb" → 500000
   - "2M" → 2000000
   - Tangani tanda titik/koma sebagai pemisah ribuan vs desimal

3. Normalisasi kategori:
   - Trim whitespace, case-insensitive matching
   - Perbaiki typo umum (mis: "Zakat Mal" → "Zakat Maal", "qris" → "QRIS")
   - Catat semua perubahan

4. Hapus duplikat persis (semua kolom sama):
   - Simpan log baris mana yang duplikat

5. Tangani nilai kosong:
   - Kolom wajib (tanggal, jumlah): flag baris, jangan hapus diam-diam
   - Kolom opsional: isi dengan "Tidak Diketahui"

6. Hapus nilai negatif dan nol pada kolom jumlah

7. Deteksi outlier dengan 2 metode:
   - IQR: nilai di luar Q1 - 3*IQR atau Q3 + 3*IQR
   - Z-score robust (median absolute deviation)
   - Tandai sebagai outlier, JANGAN hapus otomatis, biarkan pengguna memutuskan

Output fungsi:
- df_clean: dataframe bersih
- cleaning_log: list of dicts {baris, kolom, nilai_asal, nilai_baru, alasan}
- summary: dict {awal, akhir, duplikat, outlier, missing, diubah}

Tab "Kualitas Data" di app.py:
- Kartu: baris awal, baris akhir, % dibuang, jumlah diperbaiki
- Tabel detail perubahan yang dilakukan
- Tabel baris outlier terdeteksi dengan tombol "Sertakan" / "Kecualikan"
- Tombol unduh log perubahan sebagai Excel
- Pesan harus ramah bahasa Indonesia, tanpa stack trace

Tulis tests/test_cleaning.py dengan kasus:
- Parsing format angka Indonesia semua varian
- Parsing format tanggal semua varian
- Duplikat terdeteksi
- Outlier IQR dan z-score
- Input yang sengaja rusak (teks di kolom angka, sheet kosong)

Jalankan pytest sampai semua lulus.
```

### ✅ Done When:
- [ ] Semua format tanggal dan angka Indonesia berhasil diparse
- [ ] Log perubahan tersedia dan bisa diunduh
- [ ] Outlier ditandai tapi tidak dihapus otomatis
- [ ] Tab Kualitas Data tampil di Streamlit tanpa error
- [ ] `pytest tests/test_cleaning.py` semua lulus

---

## 📊 TAHAP 3 — Analisis Data & Dashboard Utama

### Prompt:
```
Lanjutkan project Lazismu Insight. Sekarang bangun src/analysis.py, src/charts.py,
dan tab "Ringkasan" + "Tren & Peramalan" di app.py.

src/analysis.py — Semua Kalkulasi:

1. Ringkasan Utama (get_summary_stats):
   - Total dana terhimpun, total transaksi, jumlah muzaki unik
   - Rata-rata dan median donasi
   - Pertumbuhan MoM dan YoY terbaru
   - Dana terbesar dalam satu transaksi
   - Semua hasil disertai teks interpretasi bahasa awam (1-3 kalimat)

2. Analisis Tren (get_trend_analysis):
   - Agregasi bulanan, triwulanan, tahunan
   - Hitung pertumbuhan MoM% dan YoY% untuk setiap periode
   - Deteksi musiman: hitung rata-rata per bulan-dalam-tahun, identifikasi bulan puncak
   - Efek Ramadan: bandingkan rata-rata bulan Ramadan vs bulan lain dengan uji t
   - Interpretasi otomatis: "Dana tertinggi terjadi pada bulan X (Rp Y), diduga karena..."

3. Analisis Komposisi (get_composition_analysis):
   - Breakdown per jenis_dana, kanal, kabupaten_kota, kampanye
   - Hitung % kontribusi masing-masing
   - Top 5 untuk setiap dimensi

4. Statistik Inferensial (get_statistical_tests):
   - Uji Kruskal-Wallis: apakah ada perbedaan signifikan rata-rata donasi antar kanal?
   - Uji Mann-Whitney: apakah donasi di bulan Ramadan lebih tinggi secara signifikan?
   - Tampilkan hasil dalam bahasa awam: "Ada perbedaan nyata antara X dan Y (p < 0.05).
     Artinya, donasi melalui [kanal A] secara konsisten lebih besar dari [kanal B]."

src/charts.py — Semua Grafik Plotly:
- Kartu KPI (HTML/plotly indicator)
- Grafik tren garis bulanan dengan tooltip detail
- Bar chart komposisi per jenis dana
- Pie/donut chart komposisi kanal
- Bar chart ranking kabupaten/kota
- Semua grafik: judul Indonesia, label sumbu, format rupiah, warna tema hijau-teal

Tab "Ringkasan" di app.py:
- 4 kartu KPI: Total Dana, Jumlah Transaksi, Muzaki Unik, Rata-rata Donasi
- Grafik tren 12 bulan terakhir
- 2 kolom: komposisi jenis dana | komposisi kanal
- Ranking wilayah (tabel/bar)
- Semua komponen merespons filter sidebar

Tab "Tren & Peramalan" di app.py:
- Grafik tren dengan toggle: Bulanan / Triwulanan / Tahunan
- Tabel pertumbuhan MoM dan YoY
- Heatmap: bulan vs tahun (nilai = total dana)
- Efek Ramadan: grafik perbandingan rata-rata per bulan
- Bagian "Deteksi Anomali": transaksi/bulan yang menyimpang, ditandai di grafik
- Peramalan (placeholder untuk Tahap 4)

Tulis tests/test_analysis.py:
- Hitung YoY manual vs fungsi — harus sama
- Pastikan interpretasi selalu terisi (tidak pernah None)
- Uji dengan data minimal (hanya 1 bulan, hanya 1 muzaki)
- Uji Kruskal-Wallis dengan data yang sudah diketahui hasilnya

Jalankan pytest, buka Streamlit, navigasi semua tab, tidak ada error.
```

### ✅ Done When:
- [ ] KPI cards tampil dengan angka yang benar (verifikasi manual)
- [ ] Grafik tren merespons filter sidebar
- [ ] Uji statistik menghasilkan interpretasi bahasa awam
- [ ] Anomali terdeteksi dan ditandai di grafik
- [ ] `pytest tests/test_analysis.py` semua lulus

---

## 👥 TAHAP 4 — Analisis Muzaki (RFM) & Peramalan

### Prompt:
```
Lanjutkan project Lazismu Insight. Sekarang bangun src/rfm.py, src/forecasting.py,
dan tab "Muzaki" + lengkapi "Tren & Peramalan" di app.py.

src/rfm.py — Segmentasi RFM:

Implementasi RFM (Recency, Frequency, Monetary):
- Recency: berapa hari sejak donasi terakhir (lebih kecil = lebih baik)
- Frequency: berapa kali donasi dalam periode analisis
- Monetary: total nilai donasi

Scoring (1-5 untuk tiap dimensi):
- Gunakan quintile/kuantil berbasis data aktual, bukan hardcode
- Hitung RFM Score gabungan

Segmentasi otomatis berdasarkan kombinasi skor:
- 🌟 Muzaki Setia (R≥4, F≥4): donatur aktif dan loyal
- 💎 Muzaki Potensial (R≥3, F≥3, M≥4): bernilai tinggi, cukup aktif
- 🆕 Muzaki Baru (F=1, R≥4): baru bergabung
- 😴 Muzaki Tidur (R=2-3, F≥2): pernah aktif, mulai jarang
- ⚠️ Muzaki Berisiko (R=1-2, F≥3): dulu loyal, sekarang tidak aktif
- 👋 Muzaki Hilang (R=1, F=1): hanya sekali dan sudah lama
- Tambahkan label lain jika perlu

Analisis Retensi & Churn:
- Kohort per tahun pertama donasi
- Hitung % yang masih donasi di tahun berikutnya (retensi)
- Visualisasi matriks kohort

Konsentrasi Donasi:
- Hitung berapa % muzaki menyumbang 80% dana (Pareto)
- Hitung koefisien Gini untuk ketimpangan donasi
- Plot kurva Lorenz

src/forecasting.py — Peramalan:

Fungsi forecast_donations(monthly_series, periods=12):
1. Periksa panjang data:
   - < 12 bulan: gunakan rata-rata bergerak sederhana, tampilkan peringatan keras
   - 12-23 bulan: gunakan Holt-Winters additive, peringatan bahwa hasil kurang akurat
   - ≥ 24 bulan: coba SARIMA(1,1,1)(1,1,1,12) dulu, fallback ke Holt-Winters jika gagal

2. Output:
   - DataFrame: tanggal, forecast, lower_bound, upper_bound (interval kepercayaan 95%)
   - Metrik: MAPE pada data historis (rolling cross-validation)
   - Teks penjelasan metode yang digunakan

3. Deteksi Anomali (tambahkan ke analysis.py):
   - Hitung residual dari tren baseline
   - Tandai bulan dengan residual > 2 standar deviasi
   - Jelaskan: "Bulan X memiliki penerimaan jauh di atas/bawah normal (Rp Y vs ekspektasi Rp Z)"

Tab "Muzaki" di app.py:
- Tabel distribusi segmen RFM dengan warna per segmen
- Bar chart jumlah muzaki per segmen
- Scatter plot: Recency vs Monetary (ukuran titik = Frequency)
- Matriks retensi kohort (heatmap)
- Kurva Lorenz + nilai Gini + teks interpretasi
- Detail muzaki per segmen (tabel filterable)

Lengkapi Tab "Tren & Peramalan":
- Grafik historis + proyeksi 12 bulan ke depan
- Area shaded untuk interval kepercayaan
- Badge: metode yang digunakan, nilai MAPE
- Peringatan jika data terlalu pendek
- Tabel angka proyeksi per bulan

Tulis tests/test_rfm.py dan tests/test_forecasting.py:
- RFM: verifikasi scoring konsisten, semua muzaki masuk satu segmen
- Gini: nilai 0 untuk distribusi merata, nilai mendekati 1 untuk sangat terkonsentrasi
- Peramalan: jalankan dengan data 6 bulan, 18 bulan, 36 bulan — pastikan tiap skenario
  menggunakan metode yang benar dan tidak error
- Edge case: data kosong, hanya 1 muzaki, semua donasi sama

Jalankan pytest semua. Buka Streamlit dan navigasi tab Muzaki.
```

### ✅ Done When:
- [ ] Semua muzaki tersegmentasi ke dalam kategori RFM
- [ ] Kurva Lorenz dan koefisien Gini tampil dengan interpretasi
- [ ] Peramalan menggunakan metode yang tepat sesuai panjang data
- [ ] Interval kepercayaan tampil di grafik
- [ ] `pytest tests/test_rfm.py tests/test_forecasting.py` semua lulus

---

## 📤 TAHAP 5 — Tab Penyaluran & Ekspor Laporan

### Prompt:
```
Lanjutkan project Lazismu Insight. Sekarang bangun tab "Penyaluran" dan modul ekspor.

Tab "Penyaluran" di app.py:
(Aktif hanya jika data penyaluran tersedia; jika tidak ada, tampilkan pesan informatif)

Analisis (tambahkan ke analysis.py get_distribution_analysis):
- Rasio penyaluran vs penghimpunan (overall dan per periode)
- Dana yang belum tersalurkan = total penghimpunan - total penyaluran (saldo)
- Breakdown per program: Pendidikan, Kesehatan, Ekonomi, Sosial-Dakwah, Kemanusiaan
- Breakdown per asnaf dengan penjelasan asnaf itu apa
- Efisiensi: biaya per penerima manfaat = jumlah penyaluran / jumlah_penerima per program
- Peringatan otomatis (sebagai informasi, bukan penghakiman):
  * Jika porsi amil > 12.5% total penyaluran: tampilkan info batas PSAK 109
  * Jika rasio penyaluran < 70%: tampilkan info bahwa dana masih besar di kas
  * Jika penyaluran > penghimpunan periode tertentu: informasikan penggunaan saldo sebelumnya

Visualisasi:
- Stacked bar: penghimpunan vs penyaluran per bulan
- Treemap: penyaluran per program
- Donut: penyaluran per asnaf
- Tabel efisiensi program (biaya per penerima, ranking)
- Grafik saldo kumulatif

src/report_pdf.py — Laporan PDF:
Gunakan reportlab atau fpdf2. Buat generate_pdf_report(summary, charts, df_clean):
- Halaman cover: logo placeholder, nama lembaga, periode data, tanggal dibuat
- Ringkasan Eksekutif: 1 halaman, 5-7 poin temuan utama dalam bahasa awam
- Halaman KPI: kartu-kartu angka penting
- Grafik utama: tren, komposisi, peramalan (export plotly ke PNG dulu)
- Tabel ringkasan: 10 baris terbesar, top wilayah
- Interpretasi: 1 paragraf per bagian
- Halaman terakhir: catatan metode (IQR, RFM, SARIMA, dll.) dan asumsi
- Output: bytes yang bisa langsung di-download via st.download_button

src/report_excel.py — Ekspor Excel:
Gunakan openpyxl. Buat generate_excel_report(df_clean, summary, rfm_df, forecast_df):
- Sheet 1 "Data Bersih": seluruh data setelah cleaning, format rupiah, lebar kolom otomatis
- Sheet 2 "Ringkasan": tabel KPI dan komposisi, header berwarna hijau
- Sheet 3 "RFM Muzaki": tabel lengkap hasil segmentasi, berwarna per segmen
- Sheet 4 "Peramalan": tabel forecast 12 bulan + interval kepercayaan
- Sheet 5 "Log Pembersihan": log semua perubahan data
- Format: angka rupiah dengan Rp prefix, tanggal dd/mm/yyyy, lebar kolom auto-fit
- Output: bytes untuk st.download_button

Tab "Laporan" di app.py:
- Tombol "⬇️ Unduh Laporan PDF" → generate dan download PDF
- Tombol "⬇️ Unduh Laporan Excel" → generate dan download Excel
- Preview ringkasan eksekutif di halaman (teks)
- Spinner saat generate (bisa lambat)
- Pesan sukses / error dalam bahasa Indonesia

Uji manual:
- Download PDF, buka, pastikan semua halaman tampil benar
- Download Excel, buka, pastikan semua sheet ada dan format rapi
- Verifikasi angka di laporan sama dengan yang di dashboard

Pastikan tidak ada error di semua tab.
```

### ✅ Done When:
- [ ] Tab Penyaluran tampil dan merespons filter
- [ ] Peringatan rasio amil dan rasio penyaluran muncul dengan benar
- [ ] PDF bisa diunduh dan dibuka, semua halaman ada
- [ ] Excel bisa diunduh, semua 5 sheet ada dengan format rapi
- [ ] Angka di laporan konsisten dengan dashboard

---

## 🧪 TAHAP 6 — Pengujian Menyeluruh & Ketangguhan

### Prompt:
```
Lanjutkan project Lazismu Insight. Sekarang lakukan pengujian menyeluruh dan perbaikan.

BAGIAN A — Lengkapi Test Suite:

Jalankan seluruh pytest dengan coverage. Target: semua test lulus, coverage ≥ 70%.

Tambahkan test yang belum ada di tests/test_cleaning.py:
- File dengan semua kolom hilang
- Sheet kosong (0 baris data)
- Semua nilai di kolom jumlah adalah teks
- Tanggal tidak valid (teks acak di kolom tanggal)

Tambahkan tests/test_utils.py:
- format_rupiah(1500000) == "Rp 1.500.000"
- format_rupiah(1500000, singkat=True) == "Rp 1,5 jt"
- format_rupiah(2000000000, singkat=True) == "Rp 2 M"
- format_rupiah(0) == "Rp 0"
- format_rupiah(-1000) → handle negatif

BAGIAN B — Uji Ketangguhan (Graceful Failure):
Jalankan Streamlit dan upload file-file berikut, verifikasi aplikasi TIDAK crash,
melainkan menampilkan pesan error ramah bahasa Indonesia:
1. File Excel dengan hanya 1 sheet (tidak ada sheet Penyaluran)
2. File CSV dengan kolom nama berbeda semua (harus muncul halaman pemetaan kolom)
3. File Excel tapi isinya kosong (0 baris)
4. File gambar (.jpg) yang di-rename jadi .xlsx
5. File Excel dengan kolom jumlah berisi teks semua
6. Data hanya 2 bulan (peramalan harus pakai metode sederhana + peringatan)
7. Semua muzaki hanya donasi 1 kali (RFM tetap jalan)

BAGIAN C — Verifikasi Akurasi:
Gunakan data contoh. Hitung manual dengan pandas di luar aplikasi:
- Total dana penghimpunan 2023
- Rata-rata donasi per transaksi 2023
- Muzaki dengan donasi terbesar
- Bulan dengan penghimpunan tertinggi
Bandingkan hasilnya dengan yang tampil di dashboard. Harus sama persis.

BAGIAN D — UX & Bahasa:
Pastikan:
- Tidak ada teks bahasa Inggris yang terlihat pengguna (label, pesan, tooltip, error)
- Tidak ada stack trace yang muncul ke pengguna
- Semua angka dalam format rupiah yang benar
- Semua tanggal dalam format Indonesia
- Semua grafik punya judul, label sumbu, dan satuan

Perbaiki semua masalah yang ditemukan. Jalankan pytest final. Laporkan hasilnya.
```

### ✅ Done When:
- [ ] `pytest --tb=short` semua lulus (0 failed)
- [ ] Semua 7 kasus file rusak ditangani dengan pesan ramah
- [ ] Angka dashboard terverifikasi akurat vs kalkulasi manual
- [ ] Tidak ada teks bahasa Inggris yang terlihat pengguna
- [ ] Tidak ada stack trace yang muncul

---

## 📝 TAHAP 7 — Dokumentasi Final & Polish

### Prompt:
```
Lanjutkan project Lazismu Insight. Ini tahap terakhir: dokumentasi final dan polish.

README.md — Tulis ulang secara lengkap dalam bahasa Indonesia:

1. ## Tentang Lazismu Insight
   Deskripsi singkat dan tujuan aplikasi

2. ## Fitur Utama
   Daftar fitur dengan emoji, jelas dan mudah dipahami

3. ## Cara Instalasi
   - Prasyarat (Python 3.11+)
   - Clone repo
   - pip install -r requirements.txt
   - streamlit run app.py

4. ## Cara Menggunakan
   - Upload file / gunakan data contoh
   - Format data yang diharapkan (tabel)
   - Navigasi tab
   - Ekspor laporan

5. ## Format Data
   - Tabel skema kolom untuk Penghimpunan dan Penyaluran
   - Daftar nilai yang diterima untuk tiap kolom kategori
   - Contoh format angka dan tanggal yang didukung

6. ## Daftar Analisis & Metode
   | Analisis | Metode | Pustaka |
   - Pembersihan outlier (IQR + MAD)
   - Segmentasi muzaki (RFM Scoring)
   - Peramalan (Holt-Winters / SARIMA)
   - Konsentrasi donasi (Koefisien Gini)
   - Uji statistik (Kruskal-Wallis, Mann-Whitney)
   - Anomali (Z-score residual)

7. ## Asumsi & Keterbatasan
   - Asumsi yang dibuat selama pembangunan
   - Keterbatasan analisis saat ini

8. ## Saran Pengembangan Selanjutnya
   - Login multi-pengguna dan role (admin, viewer)
   - Penyimpanan database (PostgreSQL)
   - Deploy ke cloud (Streamlit Cloud, Railway, Heroku)
   - Integrasi API pembayaran (untuk tracking donasi online real-time)
   - Notifikasi otomatis (email/WA) jika target tidak tercapai
   - Perbandingan antar cabang/wilayah
   - Dukungan multi-bahasa

Polish Terakhir:
1. Pastikan semua custom CSS sudah rapi: tema hijau-teal, font konsisten, mobile-friendly
2. Tambahkan favicon (emoji 🕌 atau 💚) via st.set_page_config
3. Tambahkan footer: "Lazismu Insight v1.0 | Dibuat dengan ❤️ untuk lembaga zakat Indonesia"
4. Pastikan loading state: semua proses berat pakai st.spinner dengan pesan bahasa Indonesia
5. Pastikan pesan "empty state" ketika belum ada data upload (ramah, ajak upload)
6. Update app.py dengan versi final yang bersih

Jalankan aplikasi sekali lagi end-to-end:
- Upload data contoh
- Buka semua 6 tab
- Gunakan semua filter sidebar
- Download PDF + Excel
- Verifikasi semua berjalan mulus

Buat ringkasan akhir berformat:
=== RINGKASAN PEMBANGUNAN LAZISMU INSIGHT ===
✅ Yang Selesai Dibangun: [daftar]
🧪 Hasil Pengujian: [X test lulus, Y test gagal]
📊 Verifikasi Akurasi: [hasil]
⚠️ Keterbatasan yang Diketahui: [jika ada]
🚀 Saran Pengembangan Berikutnya: [daftar prioritas]
```

### ✅ Done When:
- [ ] README.md lengkap, informatif, semua bagian terisi
- [ ] Tampilan aplikasi konsisten dan profesional
- [ ] Empty state yang ramah saat belum ada data
- [ ] Aplikasi berjalan mulus end-to-end dengan data contoh
- [ ] Ringkasan akhir pembangunan tersedia

---

## 🔄 Perintah Git — Push Setelah Setiap Tahap

Jalankan setelah setiap tahap selesai:

```bash
# Setelah Tahap 0
git add . && git commit -m "feat: setup project structure and utilities"

# Setelah Tahap 1
git add . && git commit -m "feat: sample data generator and smart file loader"

# Setelah Tahap 2
git add . && git commit -m "feat: data cleaning module and quality report tab"

# Setelah Tahap 3
git add . && git commit -m "feat: analysis engine and main dashboard tabs"

# Setelah Tahap 4
git add . && git commit -m "feat: RFM segmentation and forecasting module"

# Setelah Tahap 5
git add . && git commit -m "feat: distribution tab and PDF/Excel export"

# Setelah Tahap 6
git add . && git commit -m "test: comprehensive test suite and robustness fixes"

# Setelah Tahap 7
git add . && git commit -m "docs: complete README and final UI polish"

git push origin main
```

---

## 📌 Referensi Cepat

| Komponen | File | Tahap |
|---|---|---|
| Entry point UI | `app.py` | 0 |
| Format rupiah/tanggal | `src/utils.py` | 0 |
| Generate & load data | `src/sample_data.py`, `src/loader.py` | 1 |
| Pembersihan data | `src/cleaning.py` | 2 |
| Analisis statistik | `src/analysis.py` | 3 |
| Grafik Plotly | `src/charts.py` | 3 |
| Segmentasi RFM | `src/rfm.py` | 4 |
| Peramalan | `src/forecasting.py` | 4 |
| Laporan PDF | `src/report_pdf.py` | 5 |
| Laporan Excel | `src/report_excel.py` | 5 |
| Semua pengujian | `tests/` | 6 |

---

*Dibuat: November 2026 | Project: Lazismu Insight | GitHub: Muhammad95322/Zakat*
