"""Filter tahun di layar analisis, kalimat perbandingan antartahun, dan keandalan proyeksi. Data sintetis."""
import json
import re

import pandas as pd

from src.models.upload import Upload
from src.pipeline import siapkan_data
from src.services.upload_service import baca_berkas_unggahan
from tests.web.conftest import buat_pengguna, csrf_dari, masuk
from web import format as fmt
from web.analisis import perubahan_tahun

WILAYAH = ["Kota Satu", "Kabupaten Dua"]


def _csv(awal: str, akhir: str, dasar: float = 100e6, naik: float = 2e6, lonjakan_april: float = 10e6) -> bytes:
    """Dua transaksi per bulan; total bulan = dasar + naik*i (+ lonjakan di April). Nominal bulat."""
    baris = ["tanggal,nama_muzaki,jumlah,jenis_dana,kanal,kabupaten_kota"]
    for i, p in enumerate(pd.period_range(awal, akhir, freq="M")):
        total = dasar + naik * i + (lonjakan_april if p.month == 4 else 0)
        for k, w in enumerate(WILAYAH):
            baris.append(f"{p.year}-{p.month:02d}-1{k},Muzaki {i}-{k},{int(total / 2)},Infak,QRIS,{w}")
    return ("\n".join(baris) + "\n").encode()


def _unggah(klien, web_db, lembaga, isi: bytes, nama="rekap.csv") -> str:
    u = buat_pengguna(web_db, lembaga, peran="staf")
    masuk(klien, u.email)
    token = csrf_dari(klien.get("/unggah").text)
    r = klien.post("/unggah", data={"csrf": token}, files={"berkas": (nama, isi, "text/csv")}, follow_redirects=False)
    assert r.status_code == 303, r.text[:500]
    return r.headers["location"]


def _df(web_db):
    up = web_db.query(Upload).one()
    return siapkan_data(baca_berkas_unggahan(up), up.nama_file_asli)["df_himpun"]


def _figur_proyeksi(html: str):
    nilai = re.findall(r"data-figur='([^']*)'", html)[-1]
    return json.loads(nilai.replace("&#34;", '"').replace("&amp;", "&").replace("&#39;", "'"))


def _angka(v):
    """Larik figur: list biasa atau {dtype, bdata} (base64) dari fig.to_json()."""
    if isinstance(v, dict) and "bdata" in v:
        import base64
        import numpy as np
        return np.frombuffer(base64.b64decode(v["bdata"]), dtype=v["dtype"]).tolist()
    return list(v)


def _y_proyeksi(fig):
    return [t["y"] for t in fig["data"] if str(t.get("name", "")).startswith("Proyeksi")]


def test_pilihan_tahun_mengikuti_data(klien, web_db, lembaga_a):
    jalur = _unggah(klien, web_db, lembaga_a, _csv("2023-01", "2025-10"))
    html = klien.get(jalur).text
    blok = html.split('name="tahun"', 1)[1].split("</select>", 1)[0]
    assert re.findall(r'<option value="(\d*)"', blok) == ["", "2025", "2024", "2023"]
    assert "Semua tahun" in blok


def test_filter_tahun_sama_dengan_saring_manual(klien, web_db, lembaga_a):
    jalur = _unggah(klien, web_db, lembaga_a, _csv("2023-01", "2025-10"))
    df = _df(web_db)
    harap = df[df["tanggal"].dt.year == 2024]["jumlah"].sum()
    r = klien.get(jalur, params={"tahun": "2024"})
    assert r.status_code == 200 and fmt.rupiah(harap) in r.text
    assert 'value="2024" selected' in r.text and "Jan 2024 sampai Des 2024" in r.text
    # digabung dengan filter lain
    harap2 = df[(df["tanggal"].dt.year == 2024) & (df["kabupaten_kota"] == "Kota Satu")]["jumlah"].sum()
    r = klien.get(jalur, params={"tahun": "2024", "wilayah": "Kota Satu"})
    assert fmt.rupiah(harap2) in r.text
    # tautan atur ulang membersihkan tahun juga
    assert f'href="{jalur}">Hapus filter' in r.text


def test_tahun_tak_dikenal_tidak_galat(klien, web_db, lembaga_a):
    jalur = _unggah(klien, web_db, lembaga_a, _csv("2023-01", "2025-10"))
    semua = fmt.rupiah(_df(web_db)["jumlah"].sum())
    for nilai in ("1999", "abc", "2024'; drop table", "-1", "99999999999"):
        r = klien.get(jalur, params={"tahun": nilai})
        assert r.status_code == 200, nilai
        assert semua in r.text and "Tahun di alamat halaman tidak ada di berkas ini" in r.text


def test_perbandingan_tahun_penuh_dan_tahun_berjalan(klien, web_db, lembaga_a):
    jalur = _unggah(klien, web_db, lembaga_a, _csv("2023-01", "2025-10"))
    df = _df(web_db)
    th = df["tanggal"].dt.year
    bl = df["tanggal"].dt.month
    # tahun penuh vs tahun penuh
    p = perubahan_tahun(df, 2024)
    assert p.label_kini == "2024" and p.label_lalu == "2023"
    assert p.sekarang == df[th == 2024]["jumlah"].sum() and p.sebelumnya == df[th == 2023]["jumlah"].sum()
    r = klien.get(jalur, params={"tahun": "2024"})
    assert re.search(r"2024 terkumpul Rp [\d,]+ (jt|M), <strong>naik [\d,]+%</strong> dari 2023", r.text)
    # tahun berjalan (Jan-Okt) dibandingkan dengan Jan-Okt tahun sebelumnya, bukan setahun penuh
    p = perubahan_tahun(df, 2025)
    assert p.label_kini == "Jan sampai Okt 2025" and p.label_lalu == "Jan sampai Okt 2024"
    assert p.sebelumnya == df[(th == 2024) & (bl <= 10)]["jumlah"].sum()
    assert "Jan sampai Okt 2025 terkumpul" in klien.get(jalur, params={"tahun": "2025"}).text
    # tahun pertama: tidak ada pembanding
    p = perubahan_tahun(df, 2023)
    assert p.sebelumnya is None and p.arah == "tanpa" and "Belum ada data 2022" in p.catatan
    r = klien.get(jalur, params={"tahun": "2023"})
    assert "Belum ada data 2022 di berkas ini" in r.text and "&#9650;" not in r.text.split("perubahan--")[1][:200]


def test_tahun_sebelumnya_tidak_lengkap_tidak_dibandingkan(klien, web_db, lembaga_a):
    jalur = _unggah(klien, web_db, lembaga_a, _csv("2023-06", "2024-12"))
    df = _df(web_db)
    p = perubahan_tahun(df, 2024)
    assert p.sebelumnya is None and "hanya mencakup Jun sampai Des 2023" in p.catatan
    r = klien.get(jalur, params={"tahun": "2024"})
    assert "hanya mencakup Jun sampai Des 2023" in r.text and "% dari" not in r.text


def test_proyeksi_tidak_berubah_saat_tahun_dipilih(klien, web_db, lembaga_a):
    jalur = _unggah(klien, web_db, lembaga_a, _csv("2022-01", "2024-12"))
    tanpa = klien.get(jalur, params={"wilayah": "Kota Satu"}).text
    dengan = klien.get(jalur, params={"wilayah": "Kota Satu", "tahun": "2023"}).text
    assert _y_proyeksi(_figur_proyeksi(tanpa)) == _y_proyeksi(_figur_proyeksi(dengan))
    total = re.search(r"Sekitar <strong>([^<]+)</strong>", tanpa).group(1)
    assert f"Sekitar <strong>{total}</strong>" in dengan
    assert "Proyeksi memakai seluruh riwayat, bukan hanya tahun yang dipilih." in dengan
    assert "Proyeksi memakai seluruh riwayat" not in tanpa
    # filter lain tetap memengaruhi proyeksi
    semua = klien.get(jalur).text
    assert _y_proyeksi(_figur_proyeksi(semua)) != _y_proyeksi(_figur_proyeksi(tanpa))


def test_proyeksi_andal_tampil_sebagai_perkiraan(klien, web_db, lembaga_a):
    jalur = _unggah(klien, web_db, lembaga_a, _csv("2022-01", "2024-12"))
    html = klien.get(jalur).text
    assert re.search(r'class="proyeksi-ringkas">Sekitar <strong>Rp', html)
    assert "Data belum cukup stabil" not in html and 'class="keandalan-utama"' not in html
    assert "label-kasar" not in html and "grafik--redup" not in html


def test_proyeksi_tidak_andal_tidak_disajikan_sebagai_perkiraan(klien, web_db, lembaga_a):
    u = buat_pengguna(web_db, lembaga_a, peran="staf")
    masuk(klien, u.email)
    r = klien.post("/unggah/contoh", data={"csrf": csrf_dari(klien.get("/beranda").text)}, follow_redirects=False)
    html = klien.get(r.headers["location"]).text
    # data contoh sintetis: MAPE backtest > 50% (lihat peringatan mesin)
    judul = html.split('class="proyeksi-ringkas', 1)[1].split("</p>", 1)[0]
    assert "Data belum cukup stabil untuk perkiraan yang bisa dipegang" in judul and "Rp" not in judul
    utama = html.split('class="keandalan-utama"', 1)[1].split("</div>", 1)[0]
    assert "Proyeksi belum dapat diandalkan" in utama
    assert '<span class="label-kasar">Kasar</span>' in html and "grafik--redup" in html
    assert "Sekitar <strong>" not in html


def test_grafik_proyeksi_skala_area_proyeksi_dan_titik_tinggi_ditandai():
    from web.grafik import figur_proyeksi
    per = pd.period_range("2022-01", "2024-12", freq="M")
    nilai = [100e6 + (900e6 if str(p) == "2024-04" else 0) for p in per]  # satu lonjakan Ramadan
    m = pd.DataFrame({"periode": per, "periode_str": per.astype(str), "total_dana": nilai, "jumlah_transaksi": 10})
    depan = pd.period_range("2025-01", "2025-12", freq="M").astype(str)
    f = pd.DataFrame({"periode": depan, "proyeksi": 110e6, "batas_bawah": 90e6, "batas_atas": 130e6,
                      "status_selang": "tersedia"})
    fig = figur_proyeksi(m, f, {"selang_label": "Selang 80%"})
    atas = fig["layout"]["yaxis"]["range"][1]
    assert 130e6 <= atas < 400e6  # skala mengikuti area proyeksi, bukan puncak Rp 1 M
    catatan = fig["layout"]["annotations"]
    assert len(catatan) == 1 and "Rp 1 M" in catatan[0]["text"] and catatan[0]["x"].startswith("2024-04")
    riwayat = [t for t in fig["data"] if t.get("name") == "Terkumpul (data)"][0]
    assert len(riwayat["x"]) == 12 and max(_angka(riwayat["y"])) == 1000e6  # titik tinggi tetap ada di data grafik
    # tanpa lonjakan: tidak ada yang ditandai
    m2 = m.assign(total_dana=100e6)
    assert figur_proyeksi(m2, f, {"selang_label": "Selang 80%"})["layout"].get("annotations", []) == []
