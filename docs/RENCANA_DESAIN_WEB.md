# Frontend web (FastAPI): temuan awal dan rencana desain

Dokumen ini ditulis sebelum kode `web/` dan CSS-nya. Bagian "Tinjauan sendiri" mencatat apa yang
diubah setelah rencana pertama diuji terhadap daftar larangan.

## 1. Temuan dari kode yang ada

- **Streamlit ikut termuat lewat paket `src.auth`.** `src/auth/__init__.py` mengimpor `src.auth.session`
  (memakai `st.session_state`) dan `src.auth.decorators`. Akibatnya `import src.services.auth_service`
  (yang hanya butuh `src.auth.hashing` dan `src.auth.jwt_handler`) ikut memuat `streamlit`.
  Perbaikan: `src/auth/__init__.py` diubah menjadi impor malas (PEP 562). `from src.auth import X`
  tetap bekerja persis seperti sebelumnya; hanya waktu impornya yang tertunda.
- **Fungsi yang bergantung pada Streamlit** dan dibuatkan padanan tipis di `web/`:
  - `src/auth/session.py`: `set_current_user`, `get_current_user`, `clear_session`, `get_tenant_id`,
    `get_user_role`, `has_permission`, `validasi_sesi_data`, `require_login` -> `web/sesi.py`.
  - `src/auth/decorators.py`: `check_role` -> `web/sesi.py: wajib_peran`.
  - `src/middleware/ip_klien.py: ip_dan_ua` (membaca `st.context`) -> `web/keamanan.py: ip_dan_ua`
    yang memanggil `ip_klien()` dan `bersihkan_ua()` dari modul yang sama (keduanya murni).
  - `src/middleware/https.py: paksa_https` -> tidak dipakai; cookie `Secure` dan HSTS diatur di `web/`.
  - `src/services/kesehatan.py: status_kesehatan` mengimpor streamlit secara malas; tidak dipakai tahap ini.
- **Login** (`auth_service.login`) sudah menangani penguncian akun, `verifikasi_tiruan` (waktu respons
  sama untuk akun terkunci/tidak ada), audit log, dan menyimpan hash refresh token di tabel `tokens`.
  Halaman Streamlit menambah: batas per IP (`batas_laju`, tahan restart) dan batas per email
  (`RateLimiter`, di memori). Jalur web memakai ketiganya dengan urutan yang sama.
- **Akun terkunci tidak boleh dibocorkan.** Sejak audit S3b, `login()` sengaja mengembalikan `None`
  yang sama untuk sandi salah, akun terkunci, dan email tak dikenal. Layar masuk karena itu tidak
  menulis "akun Anda terkunci"; pesan galatnya menjelaskan *kemungkinan* penguncian (5 kali gagal ->
  15 menit) tanpa memastikan keadaan akun tertentu. Keadaan "terlalu banyak percobaan" (batas per IP
  dan per email) *boleh* ditampilkan karena tidak mengungkap apa pun tentang akun.
- **Sesi.** `tokens.jenis` adalah Enum di basis data (`verifikasi_email`, `reset_password`, `refresh`),
  jadi sesi web tidak bisa disimpan di sana tanpa mengubah tipe kolom. Dibuat tabel baru `sesi_web`
  (migrasi 0005) tanpa foreign key, supaya `hapus_pengguna`/`hapus_lembaga` yang sudah ada tidak gagal
  karena baris sesi. Setiap sesi menautkan baris refresh token yang dibuat `login()`; logout menandai
  baris itu `used_at` (mekanisme pencabutan yang sama dengan `auth_service.logout`) dan mencabut sesi.
  `sesi_versi` pengguna ikut dicek, jadi reset sandi atau penonaktifan anggota langsung mengakhiri
  sesi web juga.
- **Analisis.** `pg_analisis.py` memanggil `siapkan_data` lalu `get_summary_stats`, `get_trend_analysis`,
  `get_composition_analysis`, `forecast_donations(monthly, 12)`. Untuk 2.000 transaksi seluruh rangkaian
  makan sekitar 0,7 detik, cukup untuk dihitung ulang setiap permintaan tanpa cache.
- **Grafik.** `src/charts.py` memberi figur Plotly bertema teal (`template="plotly_white"`, judul di dalam
  figur). Web memakai figur yang sama lalu hanya menimpa *tata letak* (warna, huruf, judul dihapus,
  format angka) di `web/grafik.py`. Data dan jejak (trace) tidak diubah.
- **Angka.** `src/utils.format_rupiah(singkat=True)` sudah menghasilkan "Rp 1,5 jt", "Rp 2 M", "Rp 3 T",
  "Rp 12 rb". Dipakai apa adanya untuk KPI; sumbu dan tooltip Plotly diberi `separators=",."` dan
  label sumbu buatan dengan singkatan yang sama.
- **Unggah.** `upload_service.simpan_upload` sudah memvalidasi ukuran, ekstensi, isi berkas, dan kuota
  paket, lalu menulis audit log. Halaman Streamlit memuat data contoh dengan
  `generate_sample_data(2000, 500)` ditulis ke xlsx; web memakai cara yang sama.
- **CI** hanya menjalankan `bandit -r src/` (tidak ada linter gaya). `web/` ditambahkan ke perintah bandit.
  Docker image menyalin seluruh repo, jadi `web/` dan tesnya ikut teruji di job docker.

## 2. Subjek

Pengguna: amil di bagian penghimpunan, bendahara, dan pimpinan lembaga yang harus melapor ke dewan
pengawas syariah. Mereka membuka aplikasi beberapa kali sebulan, biasanya menjelang rapat atau saat
menyusun laporan, sering dari ponsel.

Hal yang khas ZIS dan dipakai sebagai bahan desain:

- **Kalender Hijriah dan lonjakan Ramadan.** Penghimpunan memuncak di Ramadan dan menjelang
  Idulfitri (zakat fitrah). Ramadan bergeser sekitar 11 hari tiap tahun Masehi, jadi tidak terlihat di
  sumbu bulan biasa. Grafik tren diberi pita Ramadan dari `src/kalender_hijriah.py`.
- **Kuitansi dan stempel.** Bukti setor zakat di banyak lembaga masih kuitansi berstempel biru-ungu.
  Warna utama diambil dari tinta stempel itu, bukan dari palet SaaS.
- **Laporan ke dewan pengawas.** Bentuk yang akrab bagi pimpinan adalah laporan tertulis: kalimat
  pembuka, angka, lalu catatan. Layar analisis disusun seperti halaman laporan dengan catatan pinggir.
- **Delapan asnaf** belum relevan untuk tiga layar ini (penyaluran tidak ditampilkan); tidak dipaksakan.

## 3. Warna

| Nama | Hex | Dipakai untuk |
|---|---|---|
| Tinta | `#1A2130` | teks utama, garis grafik historis (versi gelap) |
| Kertas | `#F2F4F7` | latar halaman (abu dingin, bukan krem) |
| Stempel | `#3B3F9C` | tautan, tombol utama, garis historis, fokus |
| Kunyit | `#B37400` | pita Ramadan (transparan), garis proyeksi; teks memakai `#7A4E00` |
| Segel | `#A3271F` | galat, penurunan |
| Garis | `#D3D8E0` | pemisah, bingkai tabel |

Ditambah putih `#FFFFFF` untuk lembar laporan dan abu catatan `#566070` untuk teks sekunder.
Kontras diperiksa: Tinta/Kertas 14,6:1; Stempel/putih 8,5:1; Kunyit tua `#7A4E00`/putih 7,0:1;
Segel/putih 7,1:1; abu catatan/putih 6,2:1; putih/Stempel 8,5:1 (tombol). Semua lulus AA.

## 4. Huruf

- **Source Serif 4** (variabel, sumbu wght dan opsz) untuk kalimat pembuka laporan dan angka besar.
  Serif membuat halaman terbaca sebagai laporan, bukan papan kendali.
- **Plus Jakarta Sans** (variabel, wght) untuk antarmuka, label, tabel. Dirancang untuk identitas kota
  Jakarta oleh Tokotype; dekat dengan pengguna dan jelas di ukuran kecil.
- Keduanya punya fitur `tnum`; semua nominal memakai `font-variant-numeric: tabular-nums`.
- Skala (rasio sekitar 1,25, dibulatkan): 13 / 15 / 17 / 21 / 28 / 44 px. Angka utama 44 px serif,
  kalimat pembuka 28 px serif, teks dasar 15–17 px sans. Tidak ada label huruf kapital berjarak.
- Berkas `woff2` subset latin disajikan dari `web/static/fonts/` (lisensi OFL ikut disertakan).

## 5. Tata letak

### Layar analisis: tiga konsep

```
A. Sidebar filter + KPI + grafik           B. Laporan dengan catatan pinggir       C. Tumpukan kuitansi
+------+---------------------------+       +--------------------------------+      +-----------+
|filter| [KPI][KPI][KPI][KPI]      |       | Berkas ▾   Wilayah ▾ Dana ▾ ...|      | kuitansi 1|
|      | [  grafik tren          ] |       +---------------------+----------+      |  total    |
|      | [donut]   [donut]         |       | Rp 4,2 M terkumpul  | catatan: |      +-----------+
|      | [  proyeksi             ] |       | naik 8% dari 12 bln | 2.000    |      | kuitansi 2|
+------+---------------------------+       | sebelumnya.         | baris... |      |  tren     |
                                           | [tren + pita Ramadan]          |      +-----------+
                                           | Dari mana   |  catatan       |      | kuitansi 3|
                                           | ===== QRIS  |                |      +-----------+
                                           | [proyeksi]  | PERINGATAN     |
                                           |             | keandalan      |
                                           +--------------------------------+
```

- **A** adalah persis yang ditolak pemilik produk (dan bentuk halaman Streamlit sekarang). Ditolak.
- **C** terasa khas ZIS tetapi kolom sempit membuang lebar layar untuk grafik 36 bulan. Ditolak untuk
  analisis; bentuk "kuitansi" dipakai hanya pada daftar berkas di beranda.
- **B dipilih.** Pertanyaan lima detik dijawab berurutan dari atas: berapa (angka besar), naik/turun
  (kalimat di bawahnya), dari mana (rincian), ke depan (proyeksi). Kolom kanan berisi catatan pinggir
  seperti di laporan dewan pengawas: kualitas data dan peringatan keandalan proyeksi. Di layar sempit
  catatan pinggir turun tepat di bawah bagian yang dicatatinya, bukan dikumpulkan di akhir.

### Beranda

```
+-----------------------------------------------------------+
| Lembaga X                                 Ramadan 1448 H   |
| 3 berkas, 2,1 dari 100 MB                  perkiraan 8 Feb |
|                                            87 hari lagi    |
| Berkas                                    [pita 12 bulan]  |
| +-----------------------------------------+                |
| | data_contoh.xlsx   Jan 2022 – Des 2024  |  Buka analisis |
| | 2.000 baris        diunggah 12 Nov       |                |
| +-----------------------------------------+                |
| [Unggah berkas]  [Muat data contoh]                       |
+-----------------------------------------------------------+
```

### Masuk

Dua bidang: kiri form; kanan pita dua belas bulan ke depan dengan bulan Ramadan berikutnya disorot
dan hitung mundur dalam hari. Di ponsel pita menjadi satu baris di atas form.

### Navigasi

Desktop: satu baris atas berisi nama produk, nama lembaga (karena SaaS multi-lembaga, ini yang paling
penting dikenali), tautan Beranda/Analisis/Unggah, "Segera hadir", nama pengguna, tombol Keluar
(form POST). Ponsel (<= 720 px): baris atas hanya nama lembaga; navigasi pindah ke bilah bawah tetap
berisi tiga tautan teks dan "Lainnya" yang membuka lembar (`<details>`, tanpa JavaScript) berisi
Segera hadir dan Keluar. Tidak ada ikon emoji; tautan aktif ditandai garis bawah tebal Stempel.

### Satu hal berani per layar

- **Masuk:** hitung mundur ke Ramadan berikutnya pada pita dua belas bulan; satu-satunya hiasan,
  dan ia informasi (kapan lonjakan berikutnya datang).
- **Beranda:** berkas ditampilkan sebagai kuitansi bertepi sobek (CSS `mask`), berisi periode dan
  jumlah baris, bukan tabel generik.
- **Analisis:** angka terkumpul 44 px serif sebagai kalimat pembuka laporan, dan pita Ramadan pada
  grafik tren, sehingga lonjakan langsung terbaca sebagai lonjakan Ramadan.

## 6. Tinjauan sendiri (apa yang diganti)

Rencana pertama diuji dengan pertanyaan "bagian mana yang sama saja dengan dashboard lain?":

1. **Deretan empat KPI** (total, transaksi, muzaki, rata-rata) di draf pertama sama dengan semua
   dashboard. Diganti: satu angka besar plus kalimat; tiga angka lain masuk ke satu baris "neraca"
   dengan angka tabular, tanpa kotak.
2. **Donut komposisi** dari `chart_komposisi_donut`. Donut sulit dibandingkan dan tidak menjawab "dari
   mana" dalam lima detik. Diganti: rincian terurut (nama, nominal, persen, batang tipis) dari data
   `get_composition_analysis` yang sama, sebagai tabel HTML. Ini satu-satunya grafik `charts.py` yang
   tidak dipakai; alasannya dicatat di laporan PR.
3. **Peringatan proyeksi sebagai kotak kuning berikon.** Diganti: catatan pinggir bergaris kiri Kunyit
   tepat di samping grafik proyeksi, memakai kalimat dari mesin peramalan apa adanya. Tidak bisa ditutup.
4. **Sidebar kiri** untuk filter (bentuk Streamlit). Diganti: baris filter di atas laporan, berupa form
   GET biasa sehingga tautan bisa dibagikan dan tombol kembali browser bekerja.
5. **Banner sambutan** "Selamat datang, Nama!" di beranda (versi Streamlit). Dihapus. Beranda dibuka
   dengan nama lembaga dan keadaan berkasnya.
6. **Warna teal** bawaan `charts.py` ditimpa di lapisan web (Stempel untuk data historis, Kunyit untuk
   proyeksi dan Ramadan) agar grafik menyatu dengan halaman.

Gerak: hanya sebagai jawaban tindakan (tombol ditekan, lembar navigasi dibuka), 120 ms, dan dimatikan
oleh `prefers-reduced-motion`. Tidak ada animasi masuk.

### Setelah meninjau tangkapan layar (docs/tangkapan-layar/)

7. **Label bulan sumbu-x grafik tren hilang** karena margin bawah figur 8 px. Dinaikkan ke 40 px.
8. **Tombol cadangan "Buka" dan "Terapkan" tetap tampil** walau JavaScript aktif: `display` milik
   `.tombol` mengalahkan atribut `hidden`. Ditambah aturan `[hidden] { display: none !important; }`.
9. **Di ponsel, empat pilihan bertumpuk menghabiskan layar pertama**, sehingga angka terkumpul baru
   terlihat setelah menggulir (gagal uji lima detik). Tiga filter kini berjajar dalam satu baris;
   angka, arah naik/turun, dan neraca muat di layar pertama 390x844.
10. **Di ponsel, label "Ramadan 1445 H" terpotong dan label bulan saling tindih.** Pada lebar grafik
    di bawah 520 px label pita disingkat "R" (dijelaskan di catatan pinggir) dan label bulan dijarangkan.
11. **Nama berkas di pemilih terpotong** oleh tanggal panjang. Tanggal di opsi kini singkat ("13 Nov 2026").
