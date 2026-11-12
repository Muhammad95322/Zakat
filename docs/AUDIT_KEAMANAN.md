# Audit Keamanan Zakat Insight

- **Tanggal audit:** 2026-11-11
- **Commit yang diaudit:** `044be69` (main)
- **Lingkup:** kode di repositori ini, dijalankan secara lokal (SQLite sementara, `streamlit.testing.AppTest`, Docker lokal).
  Tidak ada pengujian terhadap layanan eksternal mana pun.
- **Status perbaikan:** diperbarui 2026-11-11 di branch `audit-keamanan-deploy` (lihat bagian akhir).
- **Metode:** pembacaan kode; skrip reproduksi; matriks izin 4 peran × 8 halaman lewat AppTest; uji isolasi dua lembaga;
  gitleaks 8.24.3 (seluruh riwayat, 39 commit); bandit 1.9.4 (`src/`); pip-audit 2.10.1 (`requirements.txt` + `constraints.txt`).

Setiap temuan memuat tingkat keparahan, bukti/cara reproduksi, dampak, dan usulan perbaikan. Temuan yang tidak dapat
dibuktikan sepenuhnya ditandai **dugaan**. Kolom *Status* diperbarui saat perbaikan dilakukan (lihat bagian akhir).

---

## Ringkasan

| ID | Keparahan | Judul | Status |
|---|---|---|---|
| T1 | Tinggi | Token verifikasi/reset disimpan mentah dan tercetak ke log (mode email simulasi, bawaan production) | Diperbaiki |
| T2 | Tinggi | Injeksi rumus pada ekspor Excel dan CSV log audit | Diperbaiki |
| S1 | Sedang | Sesi tidak kedaluwarsa dan tidak dicabut (nonaktif, ganti sandi, logout) | Diperbaiki |
| S2 | Sedang | Fungsi keamanan akun tidak ada: ganti sandi, nonaktifkan anggota, ubah peran, undangan (halaman memanggil fungsi yang tidak ada) | Diperbaiki |
| S3 | Sedang | Enumerasi email lewat waktu respons login | Diperbaiki |
| S4 | Sedang | Data pengguna masuk HTML tanpa escape (`unsafe_allow_html`) di dashboard dan template email | Diperbaiki (eksekusi di browser: dugaan, tidak diverifikasi) |
| S5 | Sedang | Log SQL memuat hash sandi dan token saat `APP_ENV=development` (bawaan docker-compose) | Diperbaiki |
| S6 | Sedang | Tidak ada batas dekompresi, jumlah sheet, atau baris untuk xlsx (DoS memori) | Diperbaiki |
| S7 | Sedang | Stack trace ditampilkan ke pengguna (`client.showErrorDetails = full`) | Diperbaiki |
| S8 | Sedang | Container berjalan sebagai root | Diperbaiki |
| S9 | Sedang | Tidak ada migrasi skema; tidak ada backup/restore | Diperbaiki |
| R1 | Rendah | Tidak ada pembatasan per alamat; pembatas per email di memori hilang saat restart | Sebagian (per IP butuh reverse proxy) |
| R2 | Rendah | Kata sandi > 72 byte membuat bcrypt melempar `ValueError` | Diperbaiki |
| R3 | Rendah | Beberapa token reset berlaku bersamaan; reset tidak membatalkan token lain | Diperbaiki |
| R4 | Rendah | Data pribadi di log: email di detail audit login dan di cetakan email simulasi | Diperbaiki |
| R5 | Rendah | Telemetri Streamlit aktif; batas unggah Streamlit 200 MB > batas aplikasi 50 MB | Diperbaiki |
| R6 | Rendah | Berkas xlsx dengan makro (`vbaProject.bin`) diterima | Diperbaiki |
| R7 | Rendah | Kata sandi development pernah tertulis di riwayat git | Dicatat |
| F1 | Fungsional | Halaman Tim crash untuk admin (`'User' object has no attribute 'get'`) | Diperbaiki |
| F2 | Fungsional | Tautan email di-hardcode `http://localhost:8501`; tanpa SMTP, pendaftar tidak dapat verifikasi | Diperbaiki (SMTP sungguhan tetap harus dikonfigurasi pemilik) |
| F3 | Fungsional | Halaman langganan hanya tampilan, kontak penjualan placeholder | Diperbaiki (label) |
| F4 | Fungsional | Tidak ada penghapusan tuntas lembaga/pengguna; retensi log tidak ditegakkan | Diperbaiki |
| S10 | Sedang | Render paket gratis: disk web service sementara, unggahan hilang saat redeploy | Belum (butuh keputusan/biaya pemilik) |
| R8 | Rendah | Log audit tidak mencatat IP/user agent asli (nilai tetap 127.0.0.1) | Belum |
| S3b | Sedang | Lanjutan S3: login ke akun **terkunci** langsung ditolak tanpa bcrypt (0,6 ms vs ~307 ms), sehingga email terdaftar dapat dikenali | Diperbaiki |

Tidak ada temuan **kritis** yang terbukti (misalnya akses lintas lembaga atau lompat peran tanpa autentikasi).

---

## Yang diperiksa dan terbukti aman

- **Penyimpanan sandi:** bcrypt, cost 12 (`src/auth/hashing.py`). Kebijakan: ≥ 8 karakter, 1 huruf besar, 1 angka.
- **Penguncian per akun:** 5 kali gagal → terkunci 15 menit, disimpan di DB (`users.failed_login_count`,
  `locked_until`), sehingga **bertahan setelah restart**.
- **Pesan login tidak membedakan** email tidak ada / sandi salah / akun belum verifikasi / terkunci: semuanya
  "Email atau kata sandi salah". Halaman reset selalu menampilkan pesan generik.
- **Token reset:** sekali pakai (`used_at`), kedaluwarsa 1 jam. Token verifikasi: 24 jam.
- **Kunci JWT production** wajib kuat (`validate_config.py`, sudah ada sejak PR #1).
- **Matriks izin (AppTest, server-side):**

  | Halaman | admin | staf | pembaca | super_admin |
  |---|---|---|---|---|
  | Tim | **crash (F1)** | ditolak | ditolak | diizinkan |
  | Audit | diizinkan (lembaganya) | ditolak | ditolak | diizinkan (semua) |
  | Super Admin | ditolak | ditolak | ditolak | diizinkan |
  | Unggah (form) | diizinkan + tombol hapus | diizinkan, tanpa hapus | hanya lihat | tanpa lembaga |
  | Langganan / Profil | diizinkan | diizinkan | diizinkan | diizinkan |

  Penolakan terjadi di kode Python di server, bukan hanya disembunyikan di UI. Streamlit hanya menjalankan aksi
  lewat widget yang dirender server, jadi tombol yang tidak dirender tidak dapat dipicu. Mengganti halaman lewat URL
  (`?page=…&token=…`) tetap melewati gerbang login dan pemeriksaan peran tiap halaman.
- **Isolasi lembaga (AppTest, dua lembaga):** pengguna lembaga B yang memaksa `selected_upload_id` milik lembaga A tidak
  melihat berkasnya; riwayat unggahan dan log audit B tidak memuat data A. Semua kueri `Upload` memfilter `tenant_id`.
  Hasil analisis dan ekspor dihitung di memori dan tidak disimpan. Berkas unggahan berada di
  `UPLOAD_DIR/<tenant_uuid>/<uuid>.<ext>` (UUID acak) dan tidak disajikan lewat HTTP.
- **XSRF** aktif (bawaan Streamlit). Tidak ada `eval`/`exec`/SQL mentah di `src/`.
- **pip-audit:** tidak ada kerentanan yang diketahui pada dependensi terkunci.

---

## Rincian temuan

### T1 — Tinggi — Token verifikasi/reset disimpan mentah dan tercetak ke log
- **Bukti:** `auth_service.register_lembaga`/`request_reset_password` menyimpan `secrets.token_urlsafe(32)` apa adanya
  di kolom bernama `token_hash`. Reproduksi: minta reset → baca `tokens.token_hash` → `reset_password(db, token)`
  berhasil. Dengan `EMAIL_ENABLED=false` (bawaan, juga di `render.yaml` production), `kirim_email` mencetak isi email
  termasuk tautan berisi token ke stdout (terbukti: token muncul di keluaran).
- **Dampak:** siapa pun yang dapat membaca log aplikasi atau salinan DB/backup dapat mengambil alih akun yang sedang
  meminta reset atau belum verifikasi.
- **Perbaikan:** simpan SHA-256 token; di production jangan mencetak isi email bila SMTP nonaktif (cukup catat bahwa
  email tidak dikirim); tautan memakai `APP_BASE_URL`.

### T2 — Tinggi — Injeksi rumus pada ekspor
- **Bukti:** nama muzaki `=HYPERLINK("http://contoh.invalid","klik")` di ekspor Excel menjadi sel rumus
  (`data_type='f'` di openpyxl). `pg_audit` menulis CSV log tanpa netralisasi; isinya memuat nama berkas dari pengguna.
- **Dampak:** data donatur sering berasal dari sumber luar (formulir online). Saat pimpinan membuka laporan, rumus
  berjalan: kebocoran data lewat `HYPERLINK`/`WEBSERVICE`, atau DDE pada Excel lama.
- **Perbaikan:** awali sel teks yang dimulai `=`, `+`, `-`, `@`, tab, atau CR dengan `'` di semua ekspor Excel/CSV.

### S1 — Sedang — Sesi tidak kedaluwarsa dan tidak dicabut
- **Bukti:** `is_logged_in()` hanya memeriksa `session_state`; JWT tidak pernah diverifikasi ulang setelah login
  (masa berlaku 8 jam tidak ditegakkan). Logout (`navbar`) hanya menghapus `session_state` dan tidak memanggil
  `auth_service.logout`, sehingga refresh token di DB tidak dicabut. Menonaktifkan akun atau mereset sandi tidak
  mengakhiri sesi yang sedang terbuka.
- **Dampak:** anggota yang dinonaktifkan (atau perangkat yang dicuri) tetap memiliki akses selama tab terbuka.
- **Perbaikan:** validasi sesi di setiap muat halaman (token belum kedaluwarsa, akun aktif, versi sesi cocok);
  `sesi_versi` naik saat sandi diganti/direset atau akun dinonaktifkan; logout mencabut refresh token.

### S2 — Sedang — Fungsi keamanan akun tidak ada
- **Bukti:** halaman memanggil `register_tenant`, `kirim_undangan`, `change_password`, `update_user_role`,
  `deactivate_user`, `get_pending_invitations`, `cancel_invitation`, `update_user_name`, `update_session_user`;
  tidak satu pun ada (`hasattr` = False). `ImportError` ditangkap lalu ditampilkan sebagai "Sistem sedang dalam
  pemeliharaan" beserta detail teknis.
- **Dampak:** admin tidak dapat menonaktifkan anggota atau mengubah peran, pengguna tidak dapat mengganti sandi,
  pendaftaran lembaga lewat UI gagal. Akses tidak dapat dicabut tanpa menyentuh DB langsung.
- **Perbaikan:** implementasikan fungsi tersebut dengan pemeriksaan peran dan lembaga di lapisan layanan, beserta tes.

### S3 — Sedang — Enumerasi email lewat waktu respons
- **Bukti:** median 5 percobaan: email tidak terdaftar 0,3 ms; email terdaftar dengan sandi salah 303,7 ms (bcrypt).
- **Dampak:** penyerang dapat mengetahui email mana yang terdaftar.
- **Perbaikan:** tetap jalankan verifikasi bcrypt terhadap hash tiruan bila email tidak ada.

### S4 — Sedang — HTML tanpa escape
- **Bukti:** `pg_dashboard` memasukkan `nama_user` dan `nama_lembaga` ke f-string `st.markdown(..., unsafe_allow_html=True)`;
  template email memasukkan nama tanpa escape.
- **Dampak:** markup buatan pengguna dirender. Eksekusi skrip di browser **dugaan**: bergantung pada sanitasi
  Streamlit dan tidak diverifikasi di browser sungguhan. Injeksi HTML di email terbukti di tingkat kode.
- **Perbaikan:** `html.escape` untuk semua data pengguna yang masuk HTML.

### S5 — Sedang — Log SQL memuat hash sandi dan token
- **Bukti:** `create_engine(..., echo=settings.APP_ENV == "development")`, sedangkan `docker-compose.yml` memakai
  `APP_ENV=${APP_ENV:-development}`. Log SQL mencetak parameter, termasuk `password_hash` dan token.
- **Perbaikan:** echo hanya bila `SQL_ECHO=true` diset eksplisit.

### S6 — Sedang — Tidak ada batas dekompresi/baris xlsx
- **Bukti:** xlsx 1,7 MB berisi 200.000 baris mengembang menjadi 19,7 MB dan lolos `validasi_file_upload`. Tidak ada
  batas rasio dekompresi, jumlah sheet, atau baris. Bom zip ekstrem tidak dicoba (berpotensi menjatuhkan mesin uji).
- **Perbaikan:** periksa daftar isi zip sebelum diparsing (total dekompresi, rasio, jumlah sheet), batasi jumlah baris.

### S7 — Sedang — Stack trace ditampilkan ke pengguna
- **Bukti:** bawaan Streamlit 1.67 `client.showErrorDetails = "full"`; crash halaman Tim (F1) menampilkan jalur
  berkas server. Tidak ada `.streamlit/config.toml`.
- **Perbaikan:** `.streamlit/config.toml` dengan `showErrorDetails = "none"` (detail tetap di log server).

### S8 — Sedang — Container berjalan sebagai root
- **Bukti:** Dockerfile tidak memiliki `USER`.
- **Perbaikan:** jalankan sebagai pengguna tanpa hak root.

### S9 — Sedang — Tidak ada migrasi skema; tidak ada backup/restore
- **Bukti:** skema dibuat dengan `Base.metadata.create_all`; Alembic ada di requirements tetapi tidak dipakai.
  Perubahan kolom tidak akan diterapkan ke DB yang sudah ada. Tidak ada skrip backup/restore.
- **Perbaikan:** Alembic dengan revisi awal; skrip migrasi yang men-*stamp* DB lama; skrip backup/restore yang diuji.

### R1 — Rendah — Pembatasan percobaan login
- **Bukti:** penguncian per akun di DB (aman), tetapi `RateLimiter` per email hanya di memori (hilang saat restart dan
  tidak dibagi antarproses) dan tidak ada pembatasan per alamat IP. Penguncian per akun juga memungkinkan pihak lain
  mengunci akun korban selama 15 menit.
- **Perbaikan (sebagian):** dicatat; pembatasan per IP butuh reverse proxy/WAF karena Streamlit tidak memberi IP
  klien yang tepercaya ke kode aplikasi.

### R2 — Rendah — Sandi > 72 byte
- **Bukti:** bcrypt 5.0: `hash_password("A1" + "x"*80)` → `ValueError: password cannot be longer than 72 bytes`.
- **Perbaikan:** tolak sandi > 72 byte di validasi dengan pesan jelas.

### R3 — Rendah — Token reset ganda
- **Bukti:** setiap permintaan membuat token baru tanpa membatalkan yang lama; reset tidak mencabut sesi lain.
- **Perbaikan:** batalkan token reset lain dan naikkan `sesi_versi` saat reset berhasil.

### R4 — Rendah — Data pribadi di log
- **Bukti:** `catat_log(..., "login", detail={"email": ...})`; mode email simulasi mencetak alamat penerima dan isi email.
- **Perbaikan:** hapus email dari detail audit login; email simulasi tidak mencetak isi di production.

### R5 — Rendah — Telemetri Streamlit dan batas unggah
- **Bukti:** `browser.gatherUsageStats = True`; `server.maxUploadSize = 200` (MB), sedangkan aplikasi menolak > 50 MB
  setelah berkas dibaca ke memori.
- **Perbaikan:** matikan telemetri; `maxUploadSize = 50`.

### R6 — Rendah — Makro Excel diterima
- **Bukti:** validasi hanya memeriksa ekstensi dan magic bytes ZIP; berkas `.xlsm` yang diganti nama `.xlsx` (memuat
  `xl/vbaProject.bin`) diterima. Makro tidak dieksekusi server dan berkas tidak disajikan ulang, jadi dampaknya kecil.
- **Perbaikan:** tolak arsip yang memuat `vbaProject.bin`.

### R7 — Rendah — Kata sandi development di riwayat git
- **Bukti:** `SuperAdmin123`, `Admin123`, `pgadmin123`, `zakatpass` pernah tertulis di README/compose (riwayat);
  `Admin123`/`SuperAdmin123` masih ada di `scripts/seed_dev.py` (khusus development, ditolak di production sejak PR #1).
  gitleaks hanya menandai kunci dummy CI (positif palsu).
- **Tindakan:** jangan pakai kata sandi tersebut di lingkungan mana pun selain lokal. Tidak menulis ulang riwayat git.

### F1 — Halaman Tim crash untuk admin
- **Bukti:** AppTest: `AttributeError: 'User' object has no attribute 'get'` (`pg_tim.py:49`).

### F2 — Tautan email & pengiriman email
- **Bukti:** tautan di-hardcode `http://localhost:8501`. Tanpa SMTP (`EMAIL_ENABLED=false`) email hanya dicetak, padahal
  login mewajibkan verifikasi email; di production pendaftar baru tidak dapat masuk.

### F3 — Halaman langganan hanya tampilan
- **Bukti:** `pg_langganan` tidak terhubung ke penyedia pembayaran; tombol hanya menampilkan kontak placeholder
  (`sales@zakatinsight.id`, `+62 812-3456-7890`). Paket diubah manual oleh super admin.

### F4 — Penghapusan & retensi
- **Bukti:** tidak ada fungsi penghapusan lembaga/pengguna; `PAKET_LIMITS[...]["audit_retensi_hari"]` tidak dipakai di
  mana pun.

---

## Hal yang tidak dapat diverifikasi tanpa pihak luar
- Perilaku sanitasi HTML Streamlit di browser sungguhan (S4), header HTTP dan TLS di belakang proxy Render.
- Pengiriman email lewat SMTP sungguhan.
- Uji penetrasi menyeluruh oleh pihak ketiga dan tinjauan hukum kebijakan privasi (UU PDP No. 27/2022).

---

## Status perbaikan (branch `audit-keamanan-deploy`)

| Kelompok | Temuan | Tes regresi |
|---|---|---|
| Token & email | T1, R3 | `tests/test_keamanan.py::TestT1*` |
| Injeksi rumus | T2 | `TestT2InjeksiRumus` (nama berisi HYPERLINK/DDE/+/-/@, semua sheet) |
| Akun & sesi | S1, S2, S3, R2, R4, F1 (+ login anggota lembaga nonaktif kini ditolak) | `TestS1Sesi`, `TestS2IzinLayanan`, `TestS3R2R4`, `test_ui_tim_tidak_crash_dan_sesi_nonaktif_keluar` |
| HTML, log, berkas, konfigurasi | S4, S5, S6, R6, S7, R5 | `TestS4EscapeHtml`, `test_s5_*`, `TestS6R6Berkas` (bom zip 50 MB < 1 MB), `test_s7_r5_*` |
| Migrasi & backup | S9 | `tests/test_migrasi.py`, `tests/test_backup.py`; backup/restore Postgres diuji manual di compose |
| Deploy | S8, F2, F3, CI | `test_s8_*`, `test_f2_*`, `test_f3_*`; job CI `keamanan` (pip-audit, bandit) |
| Privasi | F4 | `tests/test_data_pribadi.py` |

**Uji mutasi** (perbaikan sengaja dirusak, lalu dikembalikan):
- T1, token disimpan mentah: 2 tes gagal.
- T2, netralisasi rumus dimatikan: 3 tes gagal.
- S1, pemeriksaan akun aktif dan `sesi_versi` dihapus: 2 tes gagal.

**Verifikasi lokal:**
- `docker build` berhasil; container berjalan sebagai `uid=10001`.
- Production dengan kunci bawaan atau pendek ditolak (kode keluar 1); dengan kunci kuat berjalan (health 200).
- `docker compose` dengan Postgres 16: migrasi ke `0002`; masuk lewat formulir login, unggah, analisis, dan ekspor
  berhasil, tanpa sel rumus dan total KPI cocok; backup → hapus data → restore mengembalikan data.

### Risiko yang masih tersisa
- **S10:** di Render paket gratis, berkas unggahan berada di disk sementara. Butuh persistent disk (berbayar) atau
  object storage.
- **R1:** belum ada pembatasan per alamat IP; perlu reverse proxy/WAF. Penguncian per akun juga dapat disalahgunakan
  untuk mengunci akun orang lain selama 15 menit.
- **R8:** log audit belum mencatat IP asli.
- **S4:** perilaku sanitasi Streamlit di browser belum diverifikasi.
- Email baru benar-benar terkirim bila SMTP dikonfigurasi. Tanpa SMTP, pendaftar baru tidak dapat memverifikasi email.
- Undangan tim dan registrasi lembaga kini berfungsi, tetapi belum diuji dengan SMTP sungguhan.
- Riwayat git masih memuat kata sandi development lama (R7). Riwayat tidak ditulis ulang.

### Rekomendasi sebelum menyimpan data donatur sungguhan
1. **Uji penetrasi oleh pihak ketiga** terhadap lingkungan staging yang identik dengan production.
2. **Tinjauan ahli hukum** atas `docs/DRAFT_KEBIJAKAN_PRIVASI.md` terhadap UU PDP No. 27/2022, termasuk perjanjian
   pemrosesan data dengan lembaga dan lokasi server.
3. Konfigurasi SMTP, persistent storage, backup terenkripsi terjadwal di luar server, dan cron
   `scripts/bersihkan_retensi.py`.

### S3b — Sedang — Oracle waktu pada akun terkunci (ditemukan setelah PR #6)
- **Bukti (sebelum):** median 7 percobaan: email tidak ada 306,5 ms; sandi salah 307,2 ms; **akun terkunci 0,6 ms**.
  Jalur `locked_until > now` di `auth_service.login` mengembalikan `None` sebelum bcrypt. Perbaikan S3 di PR #6 hanya
  menutup jalur email tidak ada dan akun nonaktif.
- **Perbaikan:** jalur terkunci menjalankan `verifikasi_tiruan`; penolakan dicatat hanya di log audit
  (`login_ditolak_terkunci`); hash tiruan dibuat saat modul dimuat (bukan pada panggilan pertama).
- **Sesudah:** 312,3 / 307,7 / 308,1 ms. Pesan di UI identik untuk ketiga jalur (diuji lewat formulir login AppTest).
- **Tes:** `test_waktu_login_seragam_tiga_jalur` (toleransi: yang lebih longgar dari 30% atau 20 ms),
  `test_ui_pesan_identik_tiga_jalur`, `test_akun_terkunci_tercatat_hanya_di_log_audit`. Uji mutasi: menghapus
  `verifikasi_tiruan` dari jalur terkunci membuat tes waktu gagal (terkunci 0,8 ms).
