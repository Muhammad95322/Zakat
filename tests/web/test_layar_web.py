"""Isi layar web: analisis memakai mesin yang ada, filter, keadaan kosong/galat, format angka Indonesia."""
import io
import json
import re
from datetime import date

import pandas as pd

from src.analysis import get_summary_stats
from src.config import settings
from src.forecasting import forecast_donations
from src.analysis import get_trend_analysis
from src.models.upload import Upload
from src.pipeline import siapkan_data
from src.services.upload_service import baca_berkas_unggahan
from src.utils import format_rupiah
from tests.web.conftest import buat_pengguna, csrf_dari, masuk
from web import format as fmt
from web.grafik import figur_tren, pita_dua_belas_bulan, ramadan_berikutnya


def _staf_dengan_contoh(klien, web_db, lembaga):
    u = buat_pengguna(web_db, lembaga, peran="staf")
    masuk(klien, u.email)
    token = csrf_dari(klien.get("/beranda").text)
    r = klien.post("/unggah/contoh", data={"csrf": token}, follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"]


def _figur(html, urutan=0):
    nilai = re.findall(r"data-figur='([^']*)'", html)[urutan]
    return json.loads(nilai.replace("&#34;", '"').replace("&amp;", "&"))


def test_analisis_menjawab_empat_pertanyaan(klien, web_db, lembaga_a):
    jalur = _staf_dengan_contoh(klien, web_db, lembaga_a)
    r = klien.get(jalur)
    assert r.status_code == 200
    up = web_db.query(Upload).one()
    hasil = siapkan_data(baca_berkas_unggahan(up), up.nama_file_asli)
    stats = get_summary_stats(hasil["df_himpun"])
    # berapa terkumpul (angka dari get_summary_stats, format rb/jt/M)
    assert format_rupiah(stats["total_dana"], singkat=True) in r.text
    assert fmt.rupiah(stats["total_dana"]) in r.text
    # naik/turun, dari mana, ke depan
    assert re.search(r"12 bulan terakhir .* (naik|turun|hampir sama)", r.text, re.S)
    assert "Dari mana dana datang" in r.text and "Jenis dana" in r.text and "Kanal" in r.text
    assert "Perkiraan 12 bulan ke depan" in r.text
    # peringatan keandalan proyeksi dari mesin peramalan tampil apa adanya, tidak tersembunyi di <details>
    _, meta = forecast_donations(get_trend_analysis(hasil["df_himpun"])["monthly"], 12)
    if meta.get("peringatan_keandalan"):
        bagian = r.text.split('class="keandalan-utama"', 1)[1].split("</div>", 1)[0]
        assert meta["peringatan_keandalan"] in bagian
    assert len(re.findall(r"data-figur='", r.text)) == 2


def test_filter_diterapkan_dan_nilai_asing_diabaikan(klien, web_db, lembaga_a):
    jalur = _staf_dengan_contoh(klien, web_db, lembaga_a)
    up = web_db.query(Upload).one()
    df = siapkan_data(baca_berkas_unggahan(up), up.nama_file_asli)["df_himpun"]
    kanal = sorted(df["kanal"].dropna().unique())[0]
    harap = get_summary_stats(df[df["kanal"] == kanal])["total_dana"]
    r = klien.get(jalur, params={"kanal": kanal})
    assert fmt.rupiah(harap) in r.text and f'value="{kanal}" selected' in r.text
    semua = get_summary_stats(df)["total_dana"]
    r = klien.get(jalur, params={"kanal": "<script>x</script>", "wilayah": "Tidak Ada"})
    assert r.status_code == 200 and fmt.rupiah(semua) in r.text and "<script>x" not in r.text


def test_kombinasi_filter_tanpa_transaksi(klien, web_db, lembaga_a):
    jalur = _staf_dengan_contoh(klien, web_db, lembaga_a)
    up = web_db.query(Upload).one()
    df = siapkan_data(baca_berkas_unggahan(up), up.nama_file_asli)["df_himpun"]
    pasangan = df.groupby(["kabupaten_kota", "kanal"]).size()
    semua = {(w, k) for w in df["kabupaten_kota"].unique() for k in df["kanal"].unique()}
    kosong = sorted(semua - set(pasangan.index))
    if not kosong:
        return  # data contoh kebetulan mengisi semua kombinasi
    w, k = kosong[0]
    r = klien.get(jalur, params={"wilayah": w, "kanal": k})
    assert "Tidak ada transaksi untuk pilihan ini" in r.text and "Hapus filter" in r.text


def test_analisis_tanpa_berkas_memberi_arahan(klien, web_db, lembaga_a):
    staf = buat_pengguna(web_db, lembaga_a, peran="staf")
    masuk(klien, staf.email)
    r = klien.get("/analisis")
    assert r.status_code == 200 and "Belum ada berkas" in r.text and "Muat data contoh" in r.text
    klien.cookies.clear()
    pembaca = buat_pengguna(web_db, lembaga_a, peran="pembaca")
    masuk(klien, pembaca.email)
    r = klien.get("/analisis")
    assert "Minta staf atau admin" in r.text and "Muat data contoh" not in r.text


def test_berkas_fisik_hilang(klien, web_db, lembaga_a):
    jalur = _staf_dengan_contoh(klien, web_db, lembaga_a)
    up = web_db.query(Upload).one()
    (settings.UPLOAD_DIR / up.storage_path).unlink()
    r = klien.get(jalur)
    assert r.status_code == 200 and "tidak ditemukan di penyimpanan" in r.text and "unggah ulang" in r.text


def test_unggah_berkas_rusak_dan_terlalu_besar(klien, web_db, lembaga_a, monkeypatch):
    u = buat_pengguna(web_db, lembaga_a, peran="staf")
    masuk(klien, u.email)
    token = csrf_dari(klien.get("/unggah").text)
    r = klien.post("/unggah", data={"csrf": token}, files={"berkas": ("rusak.xlsx", b"bukan excel", "application/octet-stream")})
    assert r.status_code == 400 and "Berkas belum tersimpan" in r.text
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    r = klien.post("/unggah", data={"csrf": token}, files={"berkas": ("besar.csv", b"a" * (1024 * 1024 + 10), "text/csv")})
    assert r.status_code == 413 and "lebih besar dari 1 MB" in r.text
    r = klien.post("/unggah", data={"csrf": token})
    assert r.status_code == 400 and "Pilih berkas" in r.text
    assert web_db.query(Upload).count() == 0


def test_unggah_csv_sederhana_langsung_ke_analisis(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a, peran="staf")
    masuk(klien, u.email)
    token = csrf_dari(klien.get("/unggah").text)
    baris = [f"{t}-{b:02d}-10,Muzaki {b % 7},{150000 + b * 1000},Infak,QRIS,Sleman"
             for t in (2023, 2024) for b in range(1, 13)]
    isi = ("tanggal,nama_muzaki,jumlah,jenis_dana,kanal,kabupaten_kota\n" + "\n".join(baris)).encode()
    r = klien.post("/unggah", data={"csrf": token}, files={"berkas": ("rekap.csv", isi, "text/csv")},
                   follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/analisis/")
    assert "terkumpul dari 24 transaksi" in klien.get(r.headers["location"]).text


def test_segera_hadir_tidak_berisi_halaman_kosong(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a)
    masuk(klien, u.email)
    r = klien.get("/segera-hadir")
    assert r.status_code == 200 and "Tim dan undangan" in r.text and "aplikasi lama" in r.text
    assert klien.get("/tim").status_code == 404


def test_format_angka_indonesia():
    assert fmt.rupiah(1500000) == "Rp 1.500.000"
    assert fmt.rupiah_singkat(1_500_000) == "Rp 1,5 jt"
    assert fmt.rupiah_singkat(2_300_000_000) == "Rp 2,3 M"
    assert fmt.rupiah_singkat(12_000) == "Rp 12 rb"
    assert fmt.rupiah_singkat(4_000_000_000_000) == "Rp 4 T"
    assert fmt.bilangan(12345) == "12.345"
    assert fmt.persen(13.456) == "13,5%" and fmt.persen(38.0) == "38%"
    assert fmt.desimal(2048.5) == "2.048,5" and fmt.desimal(0.10) == "0,1"
    assert fmt.bulan_tahun("2024-10") == "Okt 2024"
    assert fmt.tanggal(date(2027, 2, 8)) == "8 Februari 2027"


def test_grafik_tren_berlabel_indonesia_dan_pita_ramadan():
    monthly = pd.DataFrame({"periode_str": [f"2024-{b:02d}" for b in range(1, 13)],
                            "total_dana": [1_000_000_000.0 + b * 1e8 for b in range(12)],
                            "jumlah_transaksi": [10] * 12})
    fig = figur_tren(monthly)
    teks = fig["layout"]["yaxis"]["ticktext"]
    assert any(t.endswith(" M") for t in teks) and not any("G" in t or "k" in t for t in teks)
    assert all(not t.startswith("Oct") for t in fig["layout"]["xaxis"]["ticktext"])
    pita = fig["layout"]["shapes"]
    assert len(pita) == 1 and pita[0]["x0"] == "2024-03-12" and "1445 H" in pita[0]["label"]["text"]
    assert fig["data"][0]["x"][0] == "2024-01-15"  # titik di tengah bulan
    assert "Rp 1 M" in fig["data"][0]["customdata"][0]


def test_hitung_mundur_ramadan():
    r = ramadan_berikutnya(date(2026, 11, 13))
    assert r["mulai"] == date(2027, 2, 8) and r["hari_lagi"] == 87 and r["tahun_h"] == 1448
    assert ramadan_berikutnya(date(2027, 2, 20))["sedang"] is True
    pita = pita_dua_belas_bulan(date(2026, 11, 13))
    assert [b["label"] for b in pita if b["ramadan"]] == ["Feb", "Mar"]
