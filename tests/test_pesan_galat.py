"""Pesan galat untuk pengguna tidak memuat nama kelas exception atau detail teknis (mis. "(BadZipFile)")."""
import ast
import importlib.util
import io
import re
import sys
import zipfile
from pathlib import Path

import pytest

from src.loader import DataFileError
from src.pipeline import siapkan_data

AKAR = Path(__file__).parent.parent

# Nama kelas gaya CamelCase (BadZipFile, KeyError, InvalidFileException) atau berakhiran Error/Exception
POLA_KELAS = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b|\b\w*(?:Error|Exception|Warning)\b|Traceback")


def _zip_bukan_excel() -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("dokumen.txt", "bukan workbook")
    return b.getvalue()


def _csv_kolom_raksasa() -> bytes:
    return b"Tanggal,Nominal\n2024-01-01,\"" + b"x" * 200_000 + b"\n"


KASUS = {
    "kosong.xlsx": b"",
    "rusak.xlsx": b"PK\x03\x04bukan-zip",
    "zip_bukan_excel.xlsx": _zip_bukan_excel(),
    "ole2.xlsx": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100,
    "biner.csv": b"\x89PNG\r\n\x1a\n\x00\x00garbage",
    "hanya_judul.csv": b"Tanggal,Nominal\n",
    "tanpa_tanggal.csv": b"Nama,Nominal\nA,1000\nB,2000\n",
    "nilai_rusak.csv": b"Tanggal,Nominal\nkemarin,abc\n31/02/2024,xyz\n",
    "satu_kolom.csv": b"hanya satu kolom\nnilai\n",
    "kutip_raksasa.csv": _csv_kolom_raksasa(),
}


def _pesan(isi: bytes, nama: str) -> str:
    with pytest.raises(DataFileError) as e:
        siapkan_data(isi, nama)
    return str(e.value)


@pytest.mark.parametrize("nama", sorted(KASUS))
def test_pesan_tanpa_nama_kelas_exception(nama):
    pesan = _pesan(KASUS[nama], nama)
    assert pesan.strip()
    assert not POLA_KELAS.search(pesan), f"{nama}: {pesan}"


def test_pesan_variasi_tolak_generator_tanpa_nama_kelas():
    spec = importlib.util.spec_from_file_location("buat_data_kotor", AKAR / "scripts" / "buat_data_kotor.py")
    gen = importlib.util.module_from_spec(spec)
    sys.modules["buat_data_kotor"] = gen
    spec.loader.exec_module(gen)
    tolak = [v for v in gen.semua_variasi(besar=False) if v["harus_ditolak"]]
    assert len(tolak) >= 8
    for v in tolak:
        pesan = _pesan(v["isi"], v["berkas"])
        assert not POLA_KELAS.search(pesan), f"{v['kode']}: {pesan}"


def test_pola_menangkap_contoh_teknis():
    for teknis in ("(BadZipFile)", "KeyError", "InvalidFileException", "csv.Error: x", "Traceback (most"):
        assert POLA_KELAS.search(teknis), teknis
    for wajar in ("Berkas Excel 'data.xlsx' rusak", "Simpan Sebagai 'Excel Workbook (.xlsx)'", "CSV UTF-8",
                  "kolom 'Tanggal' baris 5", "sheet 'Penghimpunan'"):
        assert not POLA_KELAS.search(wajar), wajar


def _dari_exception(node: ast.AST, nama_exc: set) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and n.attr == "__name__":
            return True
        if isinstance(n, ast.FormattedValue) and isinstance(n.value, ast.Name) and n.value.id in nama_exc:
            return True
    return False


def test_sumber_tidak_menyisipkan_exception_ke_pesan_pengguna():
    """Analisis statis: DataFileError(...) & st.error/st.warning/st.caption tidak memuat __name__ atau {e}."""
    temuan = []
    for f in (AKAR / "src").rglob("*.py"):
        pohon = ast.parse(f.read_text(encoding="utf-8"))
        nama_exc = {h.name for h in ast.walk(pohon) if isinstance(h, ast.ExceptHandler) and h.name}
        nama_exc -= {"ValueError_ok"}
        for n in ast.walk(pohon):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            nama = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            pengguna = nama == "DataFileError" or (isinstance(fn, ast.Attribute) and nama in ("error", "warning", "caption")
                                                   and isinstance(fn.value, ast.Name) and fn.value.id == "st")
            if not pengguna:
                continue
            for a in n.args:
                if _dari_exception(a, nama_exc):
                    temuan.append(f"{f.relative_to(AKAR)}:{n.lineno}")
    # Pengecualian yang disengaja: pesan ValueError/PermissionError buatan kita sendiri (bukan pustaka)
    diizinkan = {"src/pages/pg_tim.py", "src/pages/pg_upload.py", "src/pages/pg_analisis.py",
                 "src/pages/pg_profil.py", "src/pages/pg_superadmin.py"}
    temuan = [t for t in temuan if t.split(":")[0] not in diizinkan]
    assert temuan == []


def test_tidak_ada_caption_detail_teknis():
    for f in (AKAR / "src" / "pages").glob("*.py"):
        assert "Detail teknis" not in f.read_text(encoding="utf-8"), f.name
