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


def test_id_transaksi_dari_isi_kolom():
    baris = [["Tanggal", "Donatur", "Nominal", "Kode Sistem"]]
    baris += [[f"{1 + i % 28:02d}/02/2024", f"D{i % 5}", "10.000", f"SYS{i:05d}"] for i in range(40)]
    baris += [baris[3], baris[4]]
    h = siapkan_data(_csv(baris), "a.csv")
    assert len(h["df_himpun"]) == 40  # 2 salinan utuh (termasuk ID) dibuang
    assert h["summary_himpun"]["alasan"] == {"duplikat_salinan": 2}
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
    assert h["summary_himpun"]["alasan"].get("duplikat_salinan") == 50  # salinan persis yang sengaja disisipkan
    assert h["kualitas"]["id_berbagi"] == 0
    assert h["kualitas"]["identik_dipertahankan"] == 0
    tmpl = openpyxl.load_workbook(Path(__file__).parent.parent / "data" / "template" / "template_zakat.xlsx")
    assert tmpl["Penghimpunan"]["A1"].value == "no_transaksi"


# ---------------------------------------------------------------------------
# Regresi: donasi sah tidak boleh hilang (skenario a-f, angka tepat)
# ---------------------------------------------------------------------------
PESAN_ID = ("baris berbagi ID transaksi yang sama tetapi isinya berbeda (mis. satu kwitansi untuk beberapa pos); "
            "semuanya dipertahankan.")
JUDUL_ID = ["No. Bukti", "Tanggal", "Donatur", "Jenis Dana", "Nominal"]


def _kwitansi_dua_pos(n, awal=1, tanggal="10/03/2024"):
    baris = []
    for k in range(awal, awal + n):
        baris += [[f"KW-{k:03d}", tanggal, f"Donatur {k}", "Zakat Maal", "1.000.000"],
                  [f"KW-{k:03d}", tanggal, f"Donatur {k}", "Infak", "250.000"]]
    return baris


def test_a_kwitansi_dua_pos_dipertahankan():
    h = siapkan_data(_csv([JUDUL_ID] + _kwitansi_dua_pos(15)), "a.csv")
    df = h["df_himpun"]
    assert len(df) == 30
    assert df["jumlah"].sum() == 18_750_000
    assert (df["jenis_dana"] == "Infak").sum() == 15 and (df["jenis_dana"] == "Zakat Maal").sum() == 15
    lap = h["kualitas"]
    assert lap["baris_dibuang"] == 0 and lap["id_berbagi"] == 30
    assert f"30 {PESAN_ID}" in lap["peringatan"]


def test_b_salinan_persis_ber_id_dibuang():
    unik = [[f"TRX-{i:03d}", f"{1 + i % 28:02d}/04/2024", f"D{i}", "infaq", f"{(i + 1) * 10_000}"] for i in range(20)]
    salinan = [unik[i] for i in (0, 0, 5, 7, 7, 19)]
    h = siapkan_data(_csv([JUDUL_ID] + unik + salinan), "a.csv")
    assert len(h["df_himpun"]) == 20
    assert h["summary_himpun"]["alasan"] == {"duplikat_salinan": 6}
    assert h["df_himpun"]["jumlah"].sum() == sum((i + 1) * 10_000 for i in range(20))
    assert h["kualitas"]["id_berbagi"] == 0 and h["kualitas"]["identik_dipertahankan"] == 0


def test_c_id_kosong_sebagian():
    tanpa_nomor = [["", "11/03/2024", "Hamba Allah", "sedekah", "50.000"]] * 10  # kotak amal: identik, tanpa nomor
    h = siapkan_data(_csv([JUDUL_ID] + tanpa_nomor + _kwitansi_dua_pos(10)), "a.csv")
    df = h["df_himpun"]
    assert h["kualitas"]["baris_dibaca"] == 30 and len(df) == 30
    assert df["jumlah"].sum() == 10 * 50_000 + 10 * 1_250_000
    lap = h["kualitas"]
    assert lap["id_berbagi"] == 20 and lap["identik_dipertahankan"] == 10
    assert f"20 {PESAN_ID}" in lap["peringatan"]
    assert any(w.startswith("10 baris identik dipertahankan") for w in lap["peringatan"])


def test_d_nomor_bukti_dipakai_ulang_tiap_tahun():
    baris = [[f"B-{b:02d}", f"{b:02d}/{b:02d}/{th}", f"Donatur {th}-{b}", "zakat mal", f"{th - 2000}{b:02d}000"]
             for th in (2022, 2023, 2024) for b in range(1, 13)]
    total = sum(int(f"{th - 2000}{b:02d}000") for th in (2022, 2023, 2024) for b in range(1, 13))
    h = siapkan_data(_csv([JUDUL_ID] + baris), "a.csv")
    df = h["df_himpun"]
    assert len(df) == 36 and df["jumlah"].sum() == total
    assert sorted(df["tanggal"].dt.year.unique().tolist()) == [2022, 2023, 2024]
    assert h["kualitas"]["id_berbagi"] == 36


def test_e_sepuluh_identik_tanpa_id():
    identik = [["05/01/2024", "Siti", "infaq", "100.000"]] * 10
    lain = [[f"{6 + i:02d}/01/2024", f"D{i}", "sedekah", f"{(i + 1) * 5_000}"] for i in range(10)]
    h = siapkan_data(_csv([["Tanggal", "Donatur", "Jenis Dana", "Nominal"]] + identik + lain), "a.csv")
    lap = h["kualitas"]
    assert lap["baris_dibaca"] == 20 and len(h["df_himpun"]) == 20
    assert lap["identik_dipertahankan"] == 10
    assert "10 baris identik dipertahankan karena tidak ada ID transaksi; periksa apakah ada unggahan ganda." \
        in lap["peringatan"]


def test_f_unggahan_ganda_utuh(db, sample_tenant, admin_user, tmp_path, monkeypatch):
    data = [["05/01/2024", "Siti", "infaq", "100.000"], ["06/01/2024", "Budi", "zakat mal", "250.000"],
            ["07/01/2024", "Ani", "sedekah", "50.000"]]
    judul = ["Tanggal", "Donatur", "Jenis Dana", "Nominal"]
    # (1) isi berkas tertempel dua kali di berkas yang sama
    h = siapkan_data(_csv([judul] + data + data), "ganda.csv")
    assert len(h["df_himpun"]) == 6 and h["kualitas"]["seluruh_ganda"] is True
    assert any("unggahan ganda utuh" in w for w in h["kualitas"]["peringatan"])
    # dengan kolom ID: salinan utuh dibuang dan tetap diperingatkan
    ber_id = [[f"KW-{i}"] + r for i, r in enumerate(data)]
    h = siapkan_data(_csv([["No. Bukti"] + judul] + ber_id + ber_id), "ganda_id.csv")
    assert len(h["df_himpun"]) == 3 and h["summary_himpun"]["alasan"] == {"duplikat_salinan": 3}
    assert any("unggahan ganda utuh" in w for w in h["kualitas"]["peringatan"])
    # (2) berkas yang sama diunggah dua kali
    from src.config import settings
    from src.services.unggahan_kembar import cari_unggahan_kembar
    from src.services.upload_service import simpan_upload
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    isi = _csv([judul] + data)
    pertama, _ = simpan_upload(db, sample_tenant.id, admin_user.id, isi, "januari.csv")
    assert cari_unggahan_kembar(db, sample_tenant.id, isi).id == pertama.id


def test_pilihan_id_unik_opsional_dan_disimpan(db, sample_tenant, admin_user):
    from src.services.pemetaan_service import daftar_pemetaan, simpan_pemetaan
    isi = _csv([JUDUL_ID] + _kwitansi_dua_pos(15))
    h = siapkan_data(isi, "a.csv")
    assert h["pemetaan"]["opsi"]["id_transaksi_unik"] is False          # tidak aktif secara bawaan
    paksa = siapkan_data(isi, "a.csv", id_transaksi_unik=True)
    assert len(paksa["df_himpun"]) == 15 and paksa["summary_himpun"]["alasan"] == {"duplikat_id": 15}
    assert paksa["kualitas"]["id_berbagi"] == 0
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, h["kolom"], h["pemetaan"]["pemetaan"],
                    opsi={"id_transaksi_unik": True})
    lembaga = daftar_pemetaan(db, sample_tenant.id)
    assert lembaga[0]["opsi"] == {"id_transaksi_unik": True}
    assert len(siapkan_data(isi, "a.csv", pemetaan_lembaga=lembaga)["df_himpun"]) == 15
    tabel = tabel_kualitas(siapkan_data(isi, "a.csv", pemetaan_lembaga=lembaga)["kualitas"]).set_index("Butir")
    assert "ID dianggap unik" in tabel.loc["ID transaksi", "Nilai"]


def test_id_tetap_dikenali_dengan_pemetaan_tersimpan_atau_wizard(db, sample_tenant, admin_user):
    """Regresi: pemetaan tersimpan/wizard (tanpa bidang ID) dulu membuat kolom 'No. Bukti' diabaikan."""
    from src.services.pemetaan_service import daftar_pemetaan, simpan_pemetaan
    simpan_pemetaan(db, sample_tenant.id, admin_user.id, ["Tanggal", "Donatur", "Jenis Dana", "Nominal"],
                    {"tanggal": "Tanggal", "jumlah": "Nominal", "nama_muzaki": "Donatur", "jenis_dana": "Jenis Dana"})
    isi = _csv([JUDUL_ID] + _kwitansi_dua_pos(5))
    h = siapkan_data(isi, "a.csv", pemetaan_lembaga=daftar_pemetaan(db, sample_tenant.id))
    assert h["pemetaan"]["status"] == "tersimpan"
    assert h["summary_himpun"]["kolom_id_transaksi"] == "No. Bukti" and h["kualitas"]["id_berbagi"] == 10
    w = siapkan_data(isi, "a.csv", pemetaan={"tanggal": "Tanggal", "jumlah": "Nominal"})
    assert w["summary_himpun"]["kolom_id_transaksi"] == "No. Bukti" and len(w["df_himpun"]) == 10
