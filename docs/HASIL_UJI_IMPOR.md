# Hasil Uji Impor Berbagai Format Berkas Lembaga

> Semua berkas uji adalah **data sintetis** buatan `scripts/buat_data_kotor.py` (seed tetap), **bukan data
> donatur asli**. Angka di bawah hanya berlaku untuk variasi yang diuji. Ini **bukan** klaim bahwa
> Zakat Insight mendukung semua format: lihat bagian *Yang belum didukung / belum diuji*.

## Cara mengukur

```bash
python scripts/buat_data_kotor.py --keluar data/sintetis_kotor   # 66 variasi + manifest.json
python scripts/ukur_impor.py --direktori data/sintetis_kotor     # tabel di bawah
```

Setiap variasi punya **kunci jawaban** di `manifest.json`: jumlah baris transaksi sah, total nominal,
tanggal awal/akhir, **total per bulan** (menangkap tanggal yang tertukar hari/bulan), serta jumlah baris
per jenis dana dan per kanal. Hasilnya dikategorikan sebagai berikut:

| Kategori | Arti |
|---|---|
| otomatis | Deteksi berstatus otomatis/tersimpan **dan** hasilnya persis sama dengan kunci jawaban |
| wizard | Deteksi ragu/gagal sehingga UI menampilkan wizard. Dengan pemetaan yang benar (simulasi pilihan pengguna), hasilnya sama dengan kunci jawaban |
| ditolak | Berkas memang tidak bisa dibaca dan ditolak dengan pesan berbahasa Indonesia tanpa traceback yang menyebut penyebabnya |
| GAGAL | Selain itu: terbaca tetapi salah, berkas wajar ditolak, berkas rusak diterima, atau exception mentah |

## Ringkasan

**Dari 66 variasi: 53 terbaca otomatis, 3 lewat wizard, 9 ditolak dengan pesan jelas, 1 gagal.**

| Kelompok | Variasi | Otomatis | Wizard | Ditolak | Gagal |
|---|---|---|---|---|---|
| Judul kolom / urutan / kapitalisasi | 7 | 4 | 3 | 0 | 0 |
| Format tanggal | 9 | 9 | 0 | 0 | 0 |
| Format nominal | 7 | 7 | 0 | 0 | 0 |
| Struktur sheet | 9 | 9 | 0 | 0 | 0 |
| CSV (pemisah, encoding) | 7 | 7 | 0 | 0 | 0 |
| Ejaan kategori | 2 | 2 | 0 | 0 | 0 |
| Ukuran (20 baris, 100 ribu baris CSV & XLSX) | 3 | 3 | 0 | 0 | 0 |
| Kebiasaan sulit | 9 | 8 | 0 | 0 | **1** |
| Duplikat (tanpa ID, ID dari judul, ID dari isi, unggahan ganda utuh) | 4 | 4 | 0 | 0 | 0 |
| Berkas yang harus ditolak | 9 | 0 | 0 | 9 | 0 |

**Variasi yang masih gagal:**

- **`v45_tgl_mdy_ambigu`**: tanggal bergaya bulan/hari (mm/dd/yyyy) yang SEMUA harinya <= 12, misalnya
  `03/04/2024`. Dari isinya saja, format ini tidak bisa dibedakan dari hari/bulan, sehingga dibaca sebagai
  hari/bulan dan tanggalnya tertukar. Laporan kualitas data memberi peringatan *"urutan hari/bulan tidak
  dapat dipastikan ... dibaca sebagai HARI/BULAN"*. Penyelesaian sungguhan membutuhkan pilihan urutan
  tanggal di wizard; ini belum dibuat.

## Aturan duplikat

Dua donasi yang sama persis (orang, hari, nominal, kanal) bisa saja sah, misalnya infak harian yang
dicatat terpisah. Karena itu:

- **Ada kolom ID transaksi** (nomor bukti/kwitansi/referensi/ID transaksi, dikenali dari judul kolom, atau dari
  isinya bila nilainya unik di hampir semua baris dan memuat angka): baris dengan ID yang sama dibuang dan
  dilaporkan jumlahnya.
- **Tidak ada kolom ID:** semua baris **dipertahankan**. Laporan kualitas dan halaman unggah menampilkan
  "N baris identik dipertahankan karena tidak ada ID transaksi; periksa apakah ada unggahan ganda." Bila setiap
  baris muncul tepat dua kali, ada peringatan tambahan "unggahan ganda utuh". Pengguna bisa memilih
  **Buang duplikat persis**; pilihan ini disimpan bersama pemetaan kolom lembaga dan dipakai untuk unggahan
  berikutnya dengan susunan kolom yang sama.
- **Berkas yang sama persis diunggah dua kali** (byte demi byte) diperingatkan di halaman unggah.

Variasi uji: `v54` (10 donasi identik tanpa ID, tetap 10 baris), `v55` (5 kwitansi kembar, dibuang), `v56`
(ID dikenali dari isi kolom 'Kode Sistem'), `v57` (isi berkas tertempel dua kali, terbaca utuh + peringatan).

Sebelum aturan ini, baris identik selalu dibuang. Data contoh resmi (`data/sample/data_contoh.xlsx`) kini
memiliki kolom `no_transaksi`, sehingga 50 duplikat sengajanya dibuang lewat ID dan hasil analisisnya
identik dengan sebelumnya. Template Excel juga mendapat kolom `no_transaksi`.

## Riwayat angka (tidak disetel agar terlihat bagus)

| Tahap | N | Otomatis | Wizard | Ditolak | Gagal |
|---|---|---|---|---|---|
| Pengukuran pertama, set awal 50 variasi | 50 | 38 | 2 | 8 | 2 (tanpa baris judul, mm/dd) |
| Setelah 2 perbaikan | 50 | 39 | 3 | 8 | 0 |
| + 9 variasi "sulit" dan pemeriksa diperketat dengan total per bulan | 59 | 43 | 3 | 8 | 5 |
| Setelah perbaikan satuan ribuan, bug lokal Excel, judul Inggris, kolom Tahun/Bulan | 59 | 47 | 3 | 8 | 1 |
| + 2 berkas 100 ribu baris, + rekap pivot | 62 | 49 | 3 | 9 | 1 |
| Akhir: aturan duplikat baru (+ 4 variasi duplikat) | 66 | 53 | 3 | 9 | 1 |

Pada set awal, pemeriksa hanya membandingkan tanggal awal/akhir, sehingga `v45` sempat lolos padahal
tanggalnya tertukar. Pemeriksa kemudian diperketat dengan total per bulan. Setelah itu `v45` dan
`v48` (bug lokal Excel) tercatat gagal. `v48` diperbaiki, sedangkan `v45` tetap gagal karena memang
tidak dapat dibedakan.

## Yang belum didukung / belum diuji

- **Ditolak dengan pesan:** `.xls` (Excel 97-2003) dan Excel bersandi (keduanya kontainer OLE2), berkas biner,
  rekap pivot (bulan sebagai kolom), dan berkas tanpa kolom tanggal.
- **Belum diuji:** `.ods` (tidak diterima pengunggah), PDF/hasil pindai, tanggal Hijriah sebagai satu-satunya
  tanggal, judul kolom bertingkat yang maknanya hanya ada di baris atas, sel nominal berupa rumus yang
  disimpan program lain tanpa nilai tersimpan (Excel sendiri menyimpan nilainya), berkas berisi beberapa
  tabel berbeda dalam satu sheet, mata uang selain rupiah.
- **Wizard** hanya memetakan kolom. Urutan tanggal (hari/bulan) dan lembar gabungan masuk/keluar belum bisa
  diatur dari wizard dan hanya dideteksi otomatis.
- Variasi sintetis meniru kebiasaan yang umum, tetapi **bukan sampel berkas lembaga sungguhan**. Uji dengan
  berkas nyata (setelah dianonimkan dan disetujui lembaga) tetap disarankan sebelum klaim keterbacaan dibuat
  ke pelanggan.

## Waktu baca

CSV 100 ribu baris dibaca dalam sekitar 1,6 detik, XLSX 100 ribu baris sekitar 11 detik (didominasi
parser openpyxl). Angka ini diukur di container pengembangan, bukan di server produksi.

## Rincian per variasi

| Kode | Variasi | Deteksi | Hasil | Waktu (dtk) | Catatan |
|---|---|---|---|---|---|
| v01_kanonik | Template standar (pembanding) | otomatis | **otomatis** | 0.2 | 300/300 baris valid |
| v02_tgl_nominal_muzaki | Judul 'Tgl', 'Nominal', 'Muzaki', 'Jenis', 'Via', 'Kota' | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v03_judul_panjang_acak | Judul 'Tanggal Transaksi', 'Jumlah (Rp)', 'Donatur'; urutan kolom acak | otomatis | **otomatis** | 0.09 | 300/300 baris valid |
| v04_kapital_spasi_acak | Huruf besar/kecil & spasi acak pada judul, urutan acak | otomatis | **otomatis** | 0.07 | 300/300 baris valid |
| v05_judul_tak_dikenal | Judul kolom tidak lazim ('Kapan', 'Berapa', 'Siapa', ...) | ragu | **wizard** | 0.09 | 300/300 baris valid; alasan wizard: Kolom tanggal ditebak dari isinya: 'Kapan'. Kolom jumlah ditebak dari isinya: 'Berapa'. |
| v06_dua_kolom_nominal | Dua kandidat kolom nominal ('Nominal' dan 'Total' = nominal + biaya) | ragu | **wizard** | 0.07 | 300/300 baris valid; alasan wizard: Kolom jumlah punya beberapa kandidat: 'Nominal', 'Total'. |
| v07_tanpa_baris_judul | Tanpa baris judul kolom sama sekali (langsung data) | ragu | **wizard** | 0.07 | 300/300 baris valid; alasan wizard: Kolom tanggal ditebak dari isinya: 'Kolom A'. Kolom jumlah ditebak dari isinya: 'Kolom F'. |
| v08_tgl_iso | Tanggal ISO 2024-01-12 (teks) | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v09_tgl_dmy | Tanggal dd/mm/yyyy (teks) | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v10_tgl_indonesia | Tanggal '12 Januari 2024' | otomatis | **otomatis** | 0.07 | 300/300 baris valid |
| v11_tgl_singkat | Tanggal '12-Jan-24' / '12-Agu-24' | otomatis | **otomatis** | 0.06 | 300/300 baris valid |
| v12_tgl_serial_excel | Tanggal sebagai nomor seri Excel (angka 45303) | otomatis | **otomatis** | 0.06 | 300/300 baris valid |
| v13_tgl_campuran | Tujuh format tanggal bercampur dalam satu kolom | otomatis | **otomatis** | 0.07 | 300/300 baris valid |
| v14_tgl_mdy_amerika | Tanggal mm/dd/yyyy (gaya Amerika) konsisten | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v15_tgl_dengan_jam | Tanggal dengan jam '2024-01-12 14:30:00' | otomatis | **otomatis** | 0.04 | 300/300 baris valid |
| v16_tgl_campuran_csv | Format tanggal bercampur di CSV (termasuk seri Excel sebagai teks) | otomatis | **otomatis** | 0.08 | 300/300 baris valid |
| v17_nominal_rp_kuitansi | Nominal 'Rp 1.500.000,-' | otomatis | **otomatis** | 0.11 | 300/300 baris valid |
| v18_nominal_koma_ribuan | Nominal '1,500,000' | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v19_nominal_titik_ribuan | Nominal '1.500.000' (teks) | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v20_nominal_desimal | Nominal '1500000.50' | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v21_nominal_spasi | Nominal berspasi/NBSP '  1 500 000 ' | otomatis | **otomatis** | 0.09 | 300/300 baris valid |
| v22_nominal_campuran | Enam format nominal bercampur | otomatis | **otomatis** | 0.09 | 300/300 baris valid |
| v23_nominal_nol_negatif_teks | Ada baris nominal 0, negatif, teks, dan tanggal kosong | otomatis | **otomatis** | 0.09 | 300/304 baris valid |
| v24_judul_di_atas_header | Judul laporan & baris kosong di atas header | otomatis | **otomatis** | 0.07 | 300/300 baris valid |
| v25_sel_digabung | Sel judul digabung & sel tanggal digabung vertikal per hari | otomatis | **otomatis** | 0.06 | 300/300 baris valid |
| v26_baris_total | Baris kosong + baris 'TOTAL' di bawah data | otomatis | **otomatis** | 0.05 | 300/301 baris valid |
| v27_kolom_baris_kosong | Kolom kosong di sela kolom data & baris kosong di tengah | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v28_sheet_petunjuk | Sheet petunjuk di depan, data di sheet 'Data 2024' | otomatis | **otomatis** | 0.06 | 300/300 baris valid |
| v29_sheet_per_tahun | Satu sheet per tahun (2022, 2023, 2024), struktur sama | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v30_sheet_gabungan_jenis | Satu sheet gabungan penghimpunan+penyaluran (kolom 'Jenis Transaksi') | otomatis | **otomatis** | 0.07 | 300/300 baris valid |
| v31_buku_kas_masuk_keluar | Buku kas: kolom 'Masuk' dan 'Keluar' dalam satu sheet + baris jumlah | otomatis | **otomatis** | 0.05 | 300/301 baris valid |
| v32_sheet_nama_tak_lazim | Sheet 'Pemasukan 2024' & 'Pentasyarufan' (nama tidak standar) | otomatis | **otomatis** | 0.08 | 300/300 baris valid |
| v33_csv_koma | CSV pemisah koma, UTF-8 | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v34_csv_titik_koma | CSV pemisah titik koma (gaya Excel Indonesia) | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v35_csv_tab | CSV pemisah tab | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v36_csv_utf8_bom | CSV UTF-8 dengan BOM | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v37_csv_windows1252 | CSV Windows-1252 (huruf beraksen & tanda pisah en) | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v38_csv_desimal_koma | CSV titik koma dengan nominal desimal koma '1500000,50' | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v39_csv_judul_di_atas | CSV dengan baris keterangan di atas header (jumlah kolom tidak rata) | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v40_ejaan_kategori | Ejaan jenis dana & kanal beragam (infaq/infak, shodaqoh/sedekah, TF/trf BSI) | otomatis | **otomatis** | 0.04 | 300/300 baris valid |
| v41_kategori_tak_dikenal | Jenis dana di luar daftar ('Kurban', 'Hibah', 'Titipan Lainnya') | otomatis | **otomatis** | 0.04 | 300/300 baris valid |
| v42_kecil_20_baris | Berkas kecil: 20 baris, 8 bulan | otomatis | **otomatis** | 0.02 | 20/20 baris valid |
| v43_besar_100rb_csv | CSV besar: 100.000 baris | otomatis | **otomatis** | 1.62 | 100000/100000 baris valid |
| v44_besar_100rb_xlsx | Excel besar: 100.000 baris | otomatis | **otomatis** | 9.78 | 100000/100000 baris valid |
| v45_tgl_mdy_ambigu | Tanggal mm/dd/yyyy tetapi semua hari <= 12 (tidak bisa dibedakan dari dd/mm) | otomatis | **GAGAL** | 0.03 | TERBACA SALAH: total per bulan beda di 36 bulan (mis. 2022-01, 2022-02, 2022-03) |
| v46_judul_dua_baris | Judul dua baris (kelompok digabung horizontal + sub-judul) | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v47_nominal_dalam_ribuan | Nominal dalam ribuan rupiah (judul 'Jumlah (Rp ribu)', isi 1500) | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v48_tgl_tertukar_lokal_excel | Bug lokal Excel: sebagian tanggal jadi sel tanggal tertukar hari/bulan, sisanya teks dd/mm/yyyy | otomatis | **otomatis** | 0.05 | 300/300 baris valid |
| v49_catatan_kaki | Catatan kaki teks di bawah data | otomatis | **otomatis** | 0.05 | 300/302 baris valid |
| v50_judul_bahasa_inggris | Judul berbahasa Inggris ('Date', 'Amount', 'Donor', 'Fund Type', ...) | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v51_tahun_bulan_hari_terpisah | Tanggal dipecah ke kolom 'Tahun', 'Bulan' (nama), 'Tgl' (angka) | otomatis | **otomatis** | 0.07 | 300/300 baris valid |
| v52_csv_kutip_baris_baru | CSV dengan sel berkutip berisi pemisah & baris baru | otomatis | **otomatis** | 0.03 | 300/300 baris valid |
| v53_total_rumus | Baris 'Total' berisi rumus =SUM() tanpa nilai tersimpan | otomatis | **otomatis** | 0.05 | 300/301 baris valid |
| v54_identik_tanpa_id | 10 donasi identik tanpa kolom ID transaksi (semua dipertahankan) | otomatis | **otomatis** | 0.06 | 309/309 baris valid |
| v55_duplikat_id_kwitansi | Kolom 'No. Kwitansi'; 5 baris dengan nomor kwitansi kembar | otomatis | **otomatis** | 0.03 | 300/305 baris valid |
| v56_id_dari_isi | Kolom ID berjudul tak lazim ('Kode Sistem'), dikenali dari isinya; 2 kembar | otomatis | **otomatis** | 0.05 | 300/302 baris valid |
| v57_unggahan_ganda_utuh | Seluruh isi berkas tertempel dua kali tanpa ID (peringatan) | otomatis | **otomatis** | 0.07 | 600/600 baris valid |
| t01_berkas_kosong | Berkas 0 byte | - | **ditolak** | 0.0 | Berkas 't01_berkas_kosong.xlsx' kosong (0 byte). Unggah berkas yang berisi data. |
| t02_excel_rusak | Berkas .xlsx rusak (bukan zip valid) | - | **ditolak** | 0.0 | Berkas Excel 't02_excel_rusak.xlsx' rusak atau bukan file Excel yang valid. Buka dan simpan ulang berkas di Excel, lalu unggah kembali. |
| t03_hanya_judul | Hanya baris judul, tanpa data | - | **ditolak** | 0.0 | Berkas CSV 't03_hanya_judul.csv' tidak berisi baris data (hanya judul kolom). |
| t04_tanpa_kolom_tanggal | Tidak ada kolom tanggal sama sekali | gagal | **ditolak** | 0.02 | Sheet Penghimpunan tidak memiliki kolom wajib: 'tanggal' (nama judul yang dikenali: tanggal, tgl, date, waktu, tanggal transaksi, tgl transaksi, tgl trx, trans  |
| t05_nominal_huruf | Semua nominal ditulis dengan huruf | ragu | **ditolak** | 0.05 | Tidak ada baris penghimpunan yang valid setelah pembersihan. Rincian: 300 baris nominal bukan angka di kolom 'jumlah' (contoh: baris 2 ('lima ratus ribu'); bari |
| t06_tanggal_rusak | Semua tanggal tidak valid ('31/02/2024', 'kemarin') | ragu | **ditolak** | 0.03 | Tidak ada baris penghimpunan yang valid setelah pembersihan. Rincian: 300 baris tanggal tidak dikenali di kolom 'tanggal' (contoh: baris 2 ('31/02/2024'); baris |
| t07_biner_bernama_csv | Berkas biner (gambar) diberi nama .csv | - | **ditolak** | 0.0 | Berkas CSV 't07_biner_bernama_csv.csv' hanya terbaca sebagai satu kolom. Pastikan nilai dipisah koma, titik koma, atau tab, dan setiap baris memiliki jumlah kol |
| t08_xls_lama_atau_bersandi | Kontainer OLE2 (.xls lama / Excel bersandi) | - | **ditolak** | 0.0 | Berkas 't08_xls_lama_atau_bersandi.xlsx' berformat Excel lama (.xls 97-2003) atau dilindungi kata sandi. Format ini belum didukung: buka di Excel, hapus kata sa |
| t09_rekap_pivot_bulan | Rekap pivot: baris jenis dana, kolom Januari..Desember (bukan transaksi) | gagal | **ditolak** | 0.03 | Sheet Penghimpunan tidak memiliki kolom wajib: 'tanggal' (nama judul yang dikenali: tanggal, tgl, date, waktu, tanggal transaksi, tgl transaksi, tgl trx, trans  |
