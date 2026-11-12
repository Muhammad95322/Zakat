# Panduan Deploy Zakat Insight ke Render (untuk non-teknis)

> Panduan ini ditulis November 2026. Informasi tentang Render (paket gratis, harga, pemblokiran SMTP) diambil dari
> hasil pencarian web pada 12 November 2026, **bukan** dibaca langsung dari situs Render, karena situs itu tidak
> dapat dibuka dari lingkungan penulis. Render pernah mengubah harga beberapa kali pada 2026. **Selalu cek
> [render.com/pricing](https://render.com/pricing) dan [render.com/docs/free](https://render.com/docs/free)
> sebelum memutuskan.**

## 1. Gambaran singkat

Yang akan Anda buat:

| Komponen | Di mana | Untuk apa |
|---|---|---|
| Aplikasi web | Render, paket **Starter** | Halaman Zakat Insight |
| Basis data | Render Postgres, paket berbayar **basic-256mb** | Akun, lembaga, log audit |
| Penyimpanan berkas unggahan | Penyimpanan objek kompatibel S3 (mis. Cloudflare R2 atau AWS S3 Jakarta) | Berkas Excel/CSV yang diunggah lembaga |
| Email | Penyedia email transaksional (SMTP) | Verifikasi akun, reset kata sandi, undangan |
| Pembersihan harian | Render Cron Job | Retensi log, anonimisasi IP, berkas yatim |

### Mengapa tidak memakai paket gratis Render?

Menurut dokumentasi Render (lewat hasil pencarian):

- **Web gratis tidur otomatis** setelah 15 menit tanpa pengunjung. Saat ada pengunjung, butuh sekitar 1 menit
  untuk bangun. Kuota 750 jam instance gratis per workspace per bulan.
  ([Deploy for Free](https://render.com/docs/free), [Your First Deploy](https://render.com/docs/your-first-deploy))
- **Web gratis tidak bisa mengirim email lewat SMTP**: lalu lintas keluar ke port 25, 465, dan 587 diblokir sejak
  akhir September 2025. Port 25 diblokir untuk semua paket.
  ([Changelog Render](https://render.com/changelog/free-web-services-will-no-longer-allow-outbound-traffic-to-smtp-ports))
  Tanpa email, pendaftar tidak bisa memverifikasi akun dan reset sandi tidak berfungsi.
- **Postgres gratis kedaluwarsa 30 hari setelah dibuat** (untuk basis data yang dibuat sejak 20 Mei 2024).
  Setelah itu ada masa tenggang 14 hari untuk upgrade; lewat dari itu basis data **dihapus beserta semua data**.
  Satu workspace hanya boleh punya satu Postgres gratis.
  ([Changelog Render](https://render.com/changelog/free-postgresql-instances-now-expire-after-30-days-previously-90))
- **Disk permanen tidak bisa dipasang ke web gratis.** Disk kontainer Render bersifat sementara: berkas yang
  disimpan di sana hilang setiap kali deploy ulang atau restart.

Untuk produk yang dijual ke lembaga zakat, ketiga hal di atas tidak dapat diterima. Paket gratis hanya cocok untuk
mencoba-coba, dan tanpa email aplikasi ini memang menolak start di mode production.

### Mengapa penyimpanan objek (S3), bukan Render Disk?

Kami memilih **(b) penyimpanan objek kompatibel S3**. Alasannya:

1. **Tidak terikat satu server.** Render Disk hanya bisa dipasang ke satu instans dan membuat layanan tidak bisa
   di-deploy tanpa jeda. Penyimpanan objek bisa dipakai beberapa instans sekaligus bila nanti perlu ditambah.
2. **Pilihan lokasi data.** AWS S3 punya region Jakarta (`ap-southeast-3`). Ini relevan untuk pertimbangan UU PDP
   tentang transfer data pribadi ke luar negeri. Render tidak memiliki region di Indonesia; basis data tetap di
   region Render pilihan Anda (mis. Singapura). Konsultasikan dengan ahli hukum.
3. **Biaya kecil untuk volume kecil.** Contoh: Cloudflare R2 memberi 10 GB penyimpanan gratis per bulan tanpa
   biaya transfer keluar (menurut beberapa sumber pihak ketiga, cek situs Cloudflare).
4. **Cadangan lebih mudah.** Versioning bucket menyimpan versi lama berkas yang terhapus/tertimpa.

Kekurangannya: perlu satu akun tambahan (penyedia penyimpanan). Bila Anda tetap ingin Render Disk, set
`PENYIMPANAN=lokal`, pasang Disk di `/app/uploads`, set `UPLOAD_DIR=/app/uploads` dan
`PENYIMPANAN_LOKAL_PERMANEN=true`. Kodenya mendukung keduanya.

## 2. Yang perlu disiapkan

1. Akun **GitHub** yang berisi repo Zakat Insight (fork atau repo Anda sendiri).
2. **Domain** sendiri (mis. `zakat.lembaga-anda.id`), untuk alamat aplikasi dan alamat pengirim email. Opsional
   tetapi sangat disarankan.
3. Akun **penyedia email transaksional** yang mendukung SMTP dengan TLS, misalnya Brevo, Mailgun, Postmark,
   SendGrid, atau Amazon SES. Untuk skala kecil (puluhan email per hari: verifikasi, reset, undangan), paket
   gratis/termurah penyedia-penyedia ini biasanya cukup. **Cek sendiri batas harian dan harganya**; kami tidak
   memverifikasinya. Anda butuh: host SMTP, port (587), nama pengguna, kata sandi/API key SMTP, dan **domain
   pengirim yang sudah diverifikasi** (SPF/DKIM) supaya email tidak masuk spam.
4. Akun **penyimpanan objek**: buat satu bucket **privat** (jangan publik), aktifkan versioning bila ada, lalu
   buat access key yang hanya boleh mengakses bucket itu.
   - Cloudflare R2: endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`, region `auto`.
   - AWS S3 Jakarta: region `ap-southeast-3`, endpoint dikosongkan, `S3_SSE=AES256`.

## 3. Langkah demi langkah

### Langkah 1: Buat akun Render
1. Buka [dashboard.render.com](https://dashboard.render.com) lalu daftar, sebaiknya **dengan akun GitHub**.
2. Workspace "Hobby" cukup untuk mulai.
3. Tambahkan kartu pembayaran (Billing). Paket berbayar membutuhkannya.

### Langkah 2: Hubungkan repo lewat Blueprint
1. Di dashboard: **New → Blueprint**.
2. Pilih repo Zakat Insight. Render membaca berkas `render.yaml` dan menampilkan rencana pembuatan:
   - layanan web `zakat-insight`;
   - cron job `zakat-insight-retensi`;
   - basis data `zakat-insight-db`;
   - grup variabel `zakat-insight-bersama`.
3. Pilih **region** (mis. Singapore, yang terdekat ke Indonesia), lalu klik **Apply**.

### Langkah 3: Isi variabel lingkungan
Render akan meminta nilai yang bertanda `sync: false`. Isi sebagai berikut:

| Variabel | Isi | Contoh |
|---|---|---|
| `APP_BASE_URL` | Alamat publik aplikasi, **harus https** | `https://zakat-insight.onrender.com` atau `https://zakat.lembaga-anda.id` |
| `EMAIL_SMTP_HOST` | Host SMTP penyedia email | `smtp-relay.contoh-penyedia.com` |
| `EMAIL_SMTP_USER` | Nama pengguna SMTP | dari penyedia |
| `EMAIL_SMTP_PASS` | Kata sandi / API key SMTP | dari penyedia |
| `EMAIL_FROM` | Alamat pengirim di domain terverifikasi | `noreply@lembaga-anda.id` |
| `S3_BUCKET` | Nama bucket | `zakat-insight-unggahan` |
| `S3_ENDPOINT_URL` | Kosong untuk AWS; isi untuk R2/B2 | `https://<id>.r2.cloudflarestorage.com` |
| `S3_REGION` | Region bucket | `ap-southeast-3` / `auto` |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Kunci akses bucket | dari penyedia |
| `SENTRY_DSN` | Opsional (pemantau galat) | kosongkan bila tidak dipakai |

Yang **sudah otomatis**:
- `APP_SECRET_KEY` dibuat acak oleh Render;
- `DATABASE_URL` diambil dari basis data;
- `APP_ENV=production`, `PENYIMPANAN=s3`, `PROXY_TEPERCAYA=render`, `EMAIL_ENABLED=true`.

**Jangan pernah** menaruh nilai rahasia di berkas repo. Isi hanya di dashboard Render.

> Bila ada yang salah atau kosong, aplikasi **menolak start**. Log deploy menampilkan daftar lengkapnya, mis.
> `❌ Startup dibatalkan: ... - EMAIL_FROM masih bawaan ...`. Nilai rahasia tidak pernah dicetak di log.
> Perbaiki variabelnya, lalu klik **Manual Deploy → Deploy latest commit**.

### Langkah 4: Tunggu deploy pertama
Urutannya: build, lalu `validate_config.py` (memeriksa konfigurasi), lalu migrasi basis data, lalu aplikasi
berjalan. Status layanan menjadi **Live**.

### Langkah 5: Buat Super Admin pertama
1. Buka layanan `zakat-insight` → tab **Shell**. Shell tersedia di paket berbayar; bila tidak muncul, cek
   dokumentasi Render terbaru.
2. Jalankan:
   ```bash
   python scripts/create_superadmin.py
   ```
3. Masukkan email, nama, dan kata sandi kuat (minimal 8 karakter, 1 huruf besar, 1 angka).
4. Buka aplikasi dan masuk dengan akun tersebut.

### Langkah 6: Cek kesehatan
1. Buka `https://<alamat-aplikasi>/?page=kesehatan`. Semua baris harus ✅: Basis data, Penyimpanan unggahan,
   Email (terkonfigurasi), dan Konfigurasi.
2. Buka bagian **Diagnosis IP**. "IP Anda menurut aplikasi" harus sama dengan IP publik Anda (bandingkan dengan
   situs "what is my ip"). Bila yang tampil adalah IP lain (mis. alamat 10.x atau IP Cloudflare), pembatasan
   per IP tidak akan bekerja dengan benar. Laporkan ke pengembang sebelum membuka layanan untuk umum.
3. Render juga memantau `/_stcore/health` (sudah diatur di `render.yaml`) dan me-restart layanan bila tidak
   sehat.
4. Uji email: daftarkan lembaga uji dengan email Anda sendiri. Email verifikasi harus masuk dalam beberapa menit.
   Uji juga **Lupa kata sandi**. Bila email tidak masuk:
   - buka log layanan dan cari `email gagal dikirim`; kolom `alasan` (mis. `autentikasi`, `timeout`,
     `tls_tidak_didukung`) menunjukkan penyebabnya;
   - halaman **Log Audit** juga mencatat `email_gagal_kirim`.

### Langkah 7: Domain sendiri (opsional)
Layanan → **Settings → Custom Domains**. Tambahkan domain Anda dan ikuti instruksi DNS. Render menyediakan
sertifikat HTTPS otomatis. Setelah aktif, ubah `APP_BASE_URL` ke domain baru.

## 4. Cadangan dan pemulihan

- **Basis data:** buka basis data `zakat-insight-db` → tab **Recovery/Backups** di dashboard Render untuk melihat
  fitur cadangan yang tersedia pada paket Anda. Kami tidak memverifikasi fitur per paket.
- **Cadangan manual** dari komputer Anda (butuh `pg_dump`). Gunakan **External Database URL** dari dashboard;
  jangan simpan URL ini di repo.
  ```bash
  pg_dump "EXTERNAL_DATABASE_URL" -Fc -f zakat-$(date +%Y%m%d).dump
  ```
- **Memulihkan** ke basis data (hati-hati, ini **menimpa** data):
  ```bash
  pg_restore -d "EXTERNAL_DATABASE_URL" --clean --if-exists --no-owner zakat-YYYYMMDD.dump
  ```
- **Berkas unggahan** ada di bucket. Aktifkan **versioning**, dan bila tersedia **replikasi**, di penyedia
  penyimpanan. Untuk menyalin seluruh bucket ke komputer, pakai alat penyedia (mis. `aws s3 sync` atau
  `rclone`).
- Simpan file cadangan **terenkripsi** (berisi data pribadi donatur) dan tentukan masa simpannya; lihat
  `docs/DRAFT_KEBIJAKAN_PRIVASI.md`.
- Latih pemulihan minimal sekali sebelum go-live: pulihkan ke basis data uji, lalu buka `?page=kesehatan`.

## 5. Perkiraan biaya bulanan

Angka ini **perkiraan** (USD, dari hasil pencarian 12 November 2026); harga Render berubah beberapa kali pada 2026.

| Item | Paket | Perkiraan/bulan | Sumber |
|---|---|---|---|
| Web service | Starter (512 MB RAM, 0,5 CPU) | ±$7 | [render.com/pricing](https://render.com/pricing) |
| Postgres | basic-256mb + 1 GB penyimpanan | ±$6 + ±$0,30 | [render.com/pricing](https://render.com/pricing) |
| Cron job retensi | Starter, berjalan ±1 menit/hari | **belum terverifikasi**; tarif per menit sangat kecil, cek halaman harga | [render.com/pricing](https://render.com/pricing) |
| Workspace | Hobby | $0; bandwidth di atas kuota dikenakan biaya (sumber pihak ketiga menyebut 5 GB, lalu $0,15/GB) | sumber pihak ketiga |
| Penyimpanan objek | Cloudflare R2, < 10 GB | $0 (kuota gratis) | sumber pihak ketiga tentang R2 |
| Email | Paket gratis/termurah penyedia | $0 - beberapa dolar | cek penyedia |
| Sentry (opsional) | Paket gratis/developer | $0 | cek Sentry |
| **Total minimum** | | **± $13-15 per bulan** | |

Biaya naik bila: data Postgres membesar (per GB), trafik besar (bandwidth), atau Anda menaikkan paket web karena
memori kurang. Analisis berkas besar (100 ribu baris) memakan memori, jadi pantau grafik memori di dashboard.

## 6. Privasi dan retensi data (ringkas)

- **Log audit** mencatat IP dan user agent hanya untuk peristiwa keamanan: login, gagal login, penguncian, reset
  sandi, pendaftaran, dan batas laju. Email dan kata sandi **tidak pernah** dicatat.
- **IP dan user agent dikosongkan otomatis setelah 90 hari** (`IP_RETENSI_HARI`) oleh cron harian, walaupun baris
  lognya masih disimpan sesuai retensi paket (UU PDP: simpan seperlunya).
- **Tabel pembatasan laju** tidak menyimpan IP mentah (hanya HMAC) dan dibersihkan setelah 1 hari.
- **Unggahan** disimpan sampai dihapus admin. Retensi otomatis bisa diaktifkan lewat `RETENSI_UNGGAHAN_HARI`.
  Menghapus lembaga ikut menghapus semua berkasnya di bucket.
- **Log aplikasi** (di Render) dibersihkan dari email, nomor HP, NIK, dan token. Pesan galat tidak dicatat, hanya
  jenis dan lokasi kodenya.

## 7. Bila ada masalah

| Gejala | Penyebab umum | Tindakan |
|---|---|---|
| Deploy gagal, log berisi `Startup dibatalkan` | Variabel belum diisi/salah | Baca daftar di log, perbaiki, deploy ulang |
| Halaman "Basis data tidak dapat dihubungi" | DB belum siap / kedaluwarsa | Cek status basis data di dashboard |
| Email tidak masuk | SMTP salah, domain pengirim belum diverifikasi, atau masuk spam | Cek log `email gagal dikirim` dan alasannya |
| Semua pengguna kena "Terlalu banyak percobaan" bersamaan | IP klien terbaca sebagai IP proxy | Cek **Diagnosis IP** di `?page=kesehatan` |
| "Penyimpanan berkas sedang tidak dapat diakses" | Kunci S3 salah / bucket tidak ada | Cek variabel S3 dan izin access key |

## 8. Yang belum diverifikasi di lingkungan nyata

Hal-hal berikut **tidak dapat** diuji penulis karena tidak memiliki akun Render, SMTP, atau S3 sungguhan. Uji di
staging sebelum go-live:

1. Perilaku header `X-Forwarded-For` / `CF-Connecting-IP` / `X-Forwarded-Proto` di Render. Dokumentasi resmi
   Render tidak menjelaskannya. Sumber komunitas menyebut proxy Render **menambahkan** IP ke X-Forwarded-For
   (tidak menyaring nilai dari klien), dan lalu lintas melewati Cloudflare. Kode membaca X-Forwarded-For dari
   kanan dan hanya memercayai jaringan privat serta rentang IP Cloudflare. **Wajib dicek** lewat Diagnosis IP.
2. Pengiriman email nyata lewat penyedia SMTP. Tes memakai server SMTP tiruan lokal dengan TLS.
3. Penyimpanan S3/R2 nyata. Tes memakai klien tiruan dan `botocore Stubber`.
4. Nama paket di `render.yaml` (`starter`, `basic-256mb`), cron job, dan env group sesuai skema Blueprint terbaru.
5. Tab Shell dan fitur cadangan Postgres pada paket yang dipilih.
6. Harga yang tercantum di bagian 5.
