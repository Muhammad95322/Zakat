# DRAF Kebijakan Privasi Zakat Insight

> **PENTING: ini DRAF TEKNIS, bukan kebijakan privasi final dan BUKAN nasihat hukum.**
> Dokumen ini disusun oleh tim teknis dari perilaku aplikasi yang sebenarnya (kode di repositori ini,
> per audit 2026-11-11) agar ahli hukum punya bahan yang akurat. Dokumen ini **HARUS ditinjau dan
> disesuaikan oleh ahli hukum** sebelum dipublikasikan, terutama terkait **Undang-Undang Nomor 27 Tahun
> 2022 tentang Pelindungan Data Pribadi (UU PDP)**, termasuk: dasar pemrosesan, peran pengendali dan
> prosesor, hak subjek data, pemberitahuan kegagalan pelindungan, transfer ke luar negeri, dan data spesifik.
> Bagian bertanda **[PERLU KEPUTUSAN]** belum ditetapkan oleh pemilik platform.

## 1. Pihak-pihak
- **Lembaga** (BAZNAS/LAZ yang mendaftar) mengunggah data donatur (muzaki) dan penyaluran. Untuk data tersebut,
  lembaga kemungkinan berperan sebagai **pengendali data**, sedangkan pengelola platform sebagai **prosesor**
  **[PERLU KEPUTUSAN hukum]**.
- **Pengguna** adalah staf lembaga yang memiliki akun (admin, staf, pembaca).
- **Super Administrator** adalah pengelola platform.

## 2. Data yang disimpan dan lokasinya

| Data | Isi | Lokasi | Catatan |
|---|---|---|---|
| Lembaga | nama, slug, email kontak, telepon, alamat, paket & masa paket | tabel `tenants` | |
| Akun pengguna | email, nama lengkap, peran, status aktif/terverifikasi, waktu login terakhir, jumlah gagal login, waktu kunci | tabel `users` | sandi **tidak** disimpan; hanya hash bcrypt (cost 12) |
| Token akun | token verifikasi email, reset sandi, refresh | tabel `tokens` | hanya **hash SHA-256**; kedaluwarsa 24 jam / 1 jam / 30 hari |
| Undangan | email calon anggota, peran, pengundang | tabel `invitations` | token hanya hash; berlaku 48 jam |
| **Berkas unggahan** | **data donatur dan penyaluran apa adanya**: nama & ID muzaki, tanggal, nominal, jenis dana, kanal, kabupaten/kota, program, asnaf, jumlah penerima | disk server: `UPLOAD_DIR/<id-lembaga>/<uuid>.<ext>`; metadata di tabel `uploads` | data pribadi **pihak ketiga** (donatur); tidak disajikan lewat URL publik |
| Log audit | jenis aksi, waktu, detail ringkas (mis. peran, jumlah), id pengguna/lembaga | tabel `audit_logs` | email tidak lagi dicatat pada log login; IP & user agent saat ini berisi nilai tetap, bukan IP asli |
| Hasil analisis & laporan | KPI, RFM, proyeksi, PDF/Excel | **tidak disimpan**: dihitung di memori saat halaman dibuka; ekspor langsung diunduh pengguna | tabel `analysis_sessions` ada tetapi belum dipakai |
| Sesi | data akun & token akses | memori server Streamlit selama tab terbuka | berakhir saat logout, token kedaluwarsa (8 jam), akun dinonaktifkan, atau sandi diganti |
| Log server | pesan error; **di development** isi email simulasi (termasuk tautan) | stdout container / penyedia hosting | di production isi email tidak dicetak; log SQL hanya bila `SQL_ECHO=true` |
| Backup | salinan seluruh DB + folder unggahan | lokasi pilihan operator (`scripts/backup_db.py`, mode berkas 600) | **[PERLU KEPUTUSAN]** lokasi, enkripsi, dan masa simpan backup |

## 3. Siapa yang dapat mengakses
- **Pengguna lembaga** hanya melihat data lembaganya sendiri; isolasi lembaga diuji otomatis.
  - **Admin:** unggah, hapus unggahan, kelola tim, lihat log audit lembaga.
  - **Staf:** unggah dan analisis.
  - **Pembaca:** lihat analisis.
- **Super Administrator** melihat daftar lembaga (nama, slug, email kontak, paket), statistik jumlah, dan log audit
  semua lembaga. Super admin dapat menonaktifkan atau menghapus lembaga. Lewat UI ia tidak membuka isi unggahan
  lembaga.
- **Operator infrastruktur** (pemegang akses server, basis data, backup, dan penyedia hosting) secara teknis dapat
  mengakses seluruh data. **[PERLU KEPUTUSAN]** daftar personel, perjanjian kerahasiaan, dan log akses.
- **Pihak ketiga:**
  - **Penyedia SMTP**, bila email diaktifkan: menerima alamat email dan isi email (tautan bertoken).
  - **Penyedia hosting** (mis. Render): menyimpan DB dan berkas, lokasi server dapat di luar Indonesia
    **[PERLU KEPUTUSAN: transfer data ke luar negeri, Pasal 56 UU PDP]**.
  - Telemetri Streamlit **dimatikan**.

## 4. Berapa lama disimpan (retensi)
- **Log audit:** sesuai paket: Pro 30 hari, Enterprise 365 hari, bawaan 90 hari bila paket tidak menetapkan. Log
  tingkat platform (tanpa lembaga) disimpan 365 hari. Pembersihan berjalan lewat `scripts/bersihkan_retensi.py`
  (harus dijadwalkan operator, mis. harian).
- **Token dan undangan kedaluwarsa** dihapus 30 hari setelah kedaluwarsa.
- **Berkas unggahan dan akun** disimpan **sampai dihapus** oleh admin lembaga / super admin. Tidak ada penghapusan
  otomatis **[PERLU KEPUTUSAN: masa simpan maksimum data donatur]**.
- **Backup** mengikuti kebijakan operator; data yang sudah dihapus dari aplikasi tetap ada di backup lama sampai
  backup itu dirotasi **[PERLU KEPUTUSAN]**.

## 5. Cara penghapusan
- **Satu berkas unggahan:** admin lembaga, menu Unggah → Hapus. Baris DB dan berkas di disk dihapus.
- **Satu pengguna:** admin lembaga, menu Tim (setelah anggota dinonaktifkan) → "Hapus data".
  - Akun, token, dan undangan yang dikirimnya dihapus.
  - Log auditnya dianonimkan (id pengguna dikosongkan, detail yang memuat emailnya dibersihkan).
  - Unggahan yang pernah dibuatnya tetap ada karena merupakan data lembaga, lalu dialihkan ke admin yang menghapus.
- **Satu lembaga:** super admin, panel Super Admin → "Hapus permanen" (konfirmasi slug). Lembaga, semua pengguna,
  token, undangan, unggahan (baris dan berkas), sesi analisis, dan log auditnya dihapus.
- **Permintaan subjek data (donatur):** tidak ada fitur untuk menghapus satu donatur di dalam berkas unggahan.
  Lembaga harus mengunggah ulang berkas tanpa donatur tersebut lalu menghapus berkas lama
  **[PERLU KEPUTUSAN: prosedur hak subjek data, Pasal 5–15 UU PDP]**.

## 6. Keamanan (ringkas)
- Sandi disimpan dengan bcrypt, token sebagai hash, akun terkunci setelah 5 kali gagal login, dan sesi dicabut saat
  akun dinonaktifkan atau sandi diganti.
- Akses dibatasi per peran dan per lembaga; ekspor dinetralkan dari injeksi rumus; unggahan diperiksa (ukuran, tipe,
  makro, bom zip, jumlah baris).
- Kunci rahasia production wajib kuat; container berjalan tanpa hak root.
- Rincian dan risiko yang tersisa ada di `docs/AUDIT_KEAMANAN.md`. Disarankan **uji penetrasi oleh pihak ketiga**
  sebelum menyimpan data donatur sungguhan.

## 7. Kontak dan pemberitahuan insiden
**[PERLU KEPUTUSAN]** kontak pejabat pelindungan data, kanal permintaan subjek data, dan prosedur pemberitahuan
kegagalan pelindungan data pribadi (UU PDP Pasal 46: pemberitahuan tertulis paling lambat 3×24 jam).
