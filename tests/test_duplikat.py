"""Duplikat: tanpa ID transaksi baris identik dipertahankan (+peringatan); dengan ID dibuang berdasarkan ID;
unggahan ganda utuh terdeteksi; pilihan pengguna disimpan bersama pemetaan kolom. Data sintetis."""
import io

import openpyxl
import pandas as pd
import pytest

from src.cleaning import deteksi_kolom_id_isi
from src.kualitas_data import tabel_kualitas
from src.pipeline import periksa_berkas, siapkan_data

PERINGATAN = "baris identik dipertahankan karena tidak ada ID transaksi; periksa apakah ada unggahan ganda."


def _csv(baris):
    return ("\n".join(";".join(map(str, r)) for r in baris) + "\n").encode("utf-8")


def _donasi(n_identik=10):
    baris = [["Tanggal", "Donatur", "Jenis Dana", "Nominal"]]
    baris += [["05/01/2024", "Siti", "infaq", "100.000"]] * n_identik
    baris += [["06/01/2024", "Budi", "zakat mal", "250.000"], ["07/01/2024", "Ani", "sedekah", "50.000"]]
    return baris


def test_sepuluh_donasi_identik_tanpa_id_tetap_sepuluh():
    h = siapkan_data(_csv(_donasi(10)), "a.csv")
    df = h["df_himpun"]
    assert len(df) == 12 and (df["nama_muzaki"] == "Siti").sum() == 10
    assert df["jumlah"].sum() == 10 * 100_000 + 300_000
    lap = h["kualitas"]
    assert lap["identik_dipertahankan"] == 10 and lap["salinan_identik"] == 9
    assert lap["peringatan"][0] == f"10 {PERINGATAN}"
    assert lap["baris_dibuang"] == 0
    tabel = tabel_kualitas(lap).set_index("Butir")["Nilai"]
    assert tabel["ID transaksi"] == "tidak ada; 10 baris identik dipertahankan"


def test_pilihan_buang_duplikat_persis():
    h = siapkan_data(_csv(_donasi(10)), "a.csv", buang_duplikat_persis=True)
    assert len(h["df_himpun"]) == 3
    lap = h["kualitas"]
    assert lap["identik_dipertahankan"] == 0 and lap["buang_duplikat_persis"] is True
    assert {d["alasan"]: d["jumlah"] for d in lap["dibuang"]} == {
        "duplikat persis baris lain (dipilih pengguna: unggahan ganda)": 9}
    assert not any(PERINGATAN in w for w in lap["peringatan"])


def test_id_transaksi_dari_judul_duplikat_dibuang():
    baris = [["No. Kwitansi", "Tanggal", "Donatur", "Nominal"],
             ["KW-001", "05/01/2024", "Siti", "100.000"], ["KW-002", "05/01/2024", "Siti", "100.000"],
             ["KW-003", "06/01/2024", "Budi", "250.000"], ["KW-002", "05/01/2024", "Siti", "100.000"],
             ["kw-003 ", "06/01/2024", "Budi", "250.000"]]  # kapital/spasi berbeda tetap ID yang sama
    h = siapkan_data(_csv(baris), "a.csv")
    assert len(h["df_himpun"]) == 3                  # dua donasi Siti (KW-001 & KW-002) tetap terpisah
    s = h["summary_himpun"]
    assert s["alasan"] == {"duplikat_id": 2} and s["duplikat"] == 2
    assert s["kolom_id_transaksi"] == "No. Kwitansi" and s["sumber_id_transaksi"] == "judul"
    assert h["kualitas"]["identik_dipertahankan"] == 0
    assert "ID transaksi sama" in " ".join(d["alasan"] for d in h["kualitas"]["dibuang"])
    log = " ".join(x["keterangan"] for x in h["log_himpun"])
    assert "Dihapus 2 baris dengan ID transaksi yang sama di kolom 'No. Kwitansi'" in log


def test_id_transaksi_dari_isi_kolom():
    baris = [["Tanggal", "Donatur", "Nominal", "Kode Sistem"]]
    baris += [[f"{1 + i % 28:02d}/02/2024", f"D{i % 5}", "10.000", f"SYS{i:05d}"] for i in range(40)]
    baris += [baris[3], baris[4]]
    h = siapkan_data(_csv(baris), "a.csv")
    assert len(h["df_himpun"]) == 40
    assert h["summary_himpun"]["kolom_id_transaksi"] == "Kode Sistem"
    assert h["summary_himpun"]["sumber_id_transaksi"] == "isi"


@pytest.mark.parametrize("judul, nilai", [
    ("No HP", lambda i: f"08123{i:06d}"),          # nomor HP unik bukan ID transaksi
    ("Rekening", lambda i: f"0123{i:08d}"),
    ("Catatan", lambda i: "infaq rutin"),          # tidak unik
    ("Kode", lambda i: f"ABC{i % 3}"),             # sedikit nilai
])
def test_bukan_kolom_id(judul, nilai):
    df = pd.DataFrame({"tanggal": ["2024-01-01"] * 30, "jumlah": [1] * 30, judul: [nilai(i) for i in range(30)]})
    assert deteksi_kolom_id_isi(df, list(df.columns)) is None


def test_unggahan_ganda_utuh_dalam_satu_berkas():
    data = _donasi(1)[1:] + [["08/01/2024", "Dodi", "wakaf", "75.000"]]
    baris = [_donasi(1)[0]] + data + data  # seluruh isi tertempel dua kali
    h = siapkan_data(_csv(baris), "a.csv")
    lap = h["kualitas"]
    assert len(h["df_himpun"]) == 8 and lap["seluruh_ganda"] is True
    assert any("unggahan ganda utuh" in w for w in lap["peringatan"])
    assert lap["peringatan"][0] == f"8 {PERINGATAN}"


def test_berkas_sama_diunggah_dua_kali_terdeteksi(db, sample_tenant, admin_user, tmp_path, monkeypatch):
    from src.config import settings
    from src.services.unggahan_kembar import cari_unggahan_kembar
    from src.services.upload_service import simpan_upload
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    isi = _csv(_donasi(2))
    assert cari_unggahan_kembar(db, sample_tenant.id, isi) is None
    pertama, _ = simpan_upload(db, sample_tenant.id, admin_user.id, isi, "januari.csv")
    kembar = cari_unggahan_kembar(db, sample_tenant.id, isi)
    assert kembar is not None and kembar.id == pertama.id
    assert cari_unggahan_kembar(db, sample_tenant.id, isi + b"06/02/2024;X;infaq;1\n") is None
    assert cari_unggahan_kembar(db, sample_tenant.id, isi, kecuali_id=pertama.id) is None


def test_pilihan_disimpan_bersama_pemetaan_dan_dipakai_ulang(db, sample_tenant, admin_user):
    from src.services.pemetaan_service import daftar_pemetaan, simpan_pemetaan
    isi = _csv(_donasi(10))
    h = siapkan_data(isi, "a.csv")
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, h["kolom"], h["pemetaan"]["pemetaan"],
                    opsi={"buang_duplikat_persis": True})
    lembaga = daftar_pemetaan(db, sample_tenant.id)
    assert lembaga[0]["opsi"] == {"buang_duplikat_persis": True}
    assert "_opsi" not in lembaga[0]["pemetaan"]
    assert periksa_berkas(isi, "a.csv", lembaga).status == "tersimpan"
    assert len(siapkan_data(isi, "a.csv", pemetaan_lembaga=lembaga)["df_himpun"]) == 3
    # menyimpan ulang pemetaan tanpa opsi (mis. dari wizard) tidak menghapus pilihan
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, h["kolom"], h["pemetaan"]["pemetaan"])
    assert daftar_pemetaan(db, sample_tenant.id)[0]["opsi"] == {"buang_duplikat_persis": True}
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, h["kolom"], h["pemetaan"]["pemetaan"],
                    opsi={"buang_duplikat_persis": False})
    assert len(siapkan_data(isi, "a.csv", pemetaan_lembaga=daftar_pemetaan(db, sample_tenant.id))["df_himpun"]) == 12


def test_opsi_asing_tidak_disimpan(db, sample_tenant, admin_user):
    from src.services.pemetaan_service import daftar_pemetaan, simpan_pemetaan
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, ["T", "N"], {"tanggal": "T", "jumlah": "N"},
                    opsi={"buang_duplikat_persis": True, "<script>": 1})
    assert daftar_pemetaan(db, sample_tenant.id)[0]["opsi"] == {"buang_duplikat_persis": True}


def test_data_contoh_resmi_punya_id_transaksi_dan_tanpa_peringatan_identik():
    from pathlib import Path
    isi = (Path(__file__).parent.parent / "data" / "sample" / "data_contoh.xlsx").read_bytes()
    h = siapkan_data(isi, "data_contoh.xlsx")
    assert h["summary_himpun"]["kolom_id_transaksi"] == "no_transaksi"
    assert h["summary_himpun"]["alasan"].get("duplikat_id") == 50
    assert h["kualitas"]["identik_dipertahankan"] == 0
    tmpl = openpyxl.load_workbook(Path(__file__).parent.parent / "data" / "template" / "template_zakat.xlsx")
    assert tmpl["Penghimpunan"]["A1"].value == "no_transaksi"
