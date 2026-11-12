"""Laporan kualitas data sebelum analisis: baris valid, alasan pembuangan, kategori tak dikenal,
rentang tanggal, dan peringatan (mis. data < 24 bulan membatasi peramalan)."""
from typing import Any, Dict, List, Optional

import pandas as pd

from src.cleaning import ALASAN
from src.pemetaan import LABEL_BIDANG

BULAN_MINIMUM_PERAMALAN = 24

_BULAN = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

LABEL_ALASAN_TAMBAHAN = {
    "arus_tak_dikenal": "jenis transaksi bukan masuk/keluar",
    "masuk_keluar_kosong": "nominal masuk dan keluar kosong/nol",
}


def _tgl(t: Optional[pd.Timestamp]) -> str:
    if t is None or pd.isna(t):
        return "-"
    return f"{t.day} {_BULAN[t.month]} {t.year}"


def _persen(a: int, b: int) -> float:
    return round(a / b * 100, 1) if b else 0.0


def buat_laporan(
    nama_berkas: str,
    info_baca: Dict[str, Any],
    deteksi: Dict[str, Any],
    summary_himpun: Dict[str, Any],
    df_himpun: pd.DataFrame,
    summary_salur: Optional[Dict[str, Any]] = None,
    df_salur: Optional[pd.DataFrame] = None,
    dibuang_pra: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Susun laporan kualitas data penghimpunan (dan ringkasan penyaluran bila ada)."""
    dibuang_pra = dibuang_pra or {}
    pra_n = sum(v["jumlah"] for v in dibuang_pra.values())
    dibaca = int(summary_himpun.get("awal", len(df_himpun))) + pra_n
    valid = int(len(df_himpun))

    dibuang: List[Dict[str, Any]] = []
    for kunci, v in dibuang_pra.items():
        dibuang.append({"alasan": LABEL_ALASAN_TAMBAHAN.get(kunci, kunci), "jumlah": int(v["jumlah"]),
                        "persen": _persen(int(v["jumlah"]), dibaca), "contoh": "; ".join(v.get("contoh", []))})
    for kunci, n in (summary_himpun.get("alasan") or {}).items():
        dibuang.append({"alasan": ALASAN[kunci][1], "jumlah": int(n), "persen": _persen(int(n), dibaca),
                        "contoh": "; ".join((summary_himpun.get("contoh") or {}).get(kunci, []))})

    tmin = tmaks = None
    rentang = bulan_berdata = 0
    if valid and "tanggal" in df_himpun.columns:
        tmin, tmaks = df_himpun["tanggal"].min(), df_himpun["tanggal"].max()
        rentang = (tmaks.year - tmin.year) * 12 + tmaks.month - tmin.month + 1
        bulan_berdata = int(df_himpun["tanggal"].dt.to_period("M").nunique())

    info_tgl = summary_himpun.get("info_tanggal") or {}
    tak_dikenal = summary_himpun.get("kategori_tak_dikenal") or {}

    peringatan: List[str] = []
    if valid and rentang < BULAN_MINIMUM_PERAMALAN:
        peringatan.append(
            f"Data hanya mencakup {rentang} bulan (kurang dari {BULAN_MINIMUM_PERAMALAN} bulan): peramalan "
            "terbatas. Pola musiman tahunan (mis. Ramadan, akhir tahun) belum bisa dipelajari dari dua siklus "
            "penuh, sehingga proyeksi dan selangnya kurang andal.")
    if valid and bulan_berdata < rentang:
        peringatan.append(f"{rentang - bulan_berdata} bulan dalam rentang tanggal tidak memiliki transaksi sama sekali.")
    if dibaca and _persen(valid, dibaca) < 90:
        peringatan.append(f"{100 - _persen(valid, dibaca):.1f}% baris dibuang. Periksa rincian alasan di bawah "
                          "sebelum menarik kesimpulan.")
    for k, nilai in tak_dikenal.items():
        n = sum(nilai.values())
        peringatan.append(
            f"{len(nilai)} nilai {LABEL_BIDANG.get(k, k)} tidak dikenali ({n} baris), dipertahankan apa adanya: "
            + ", ".join(f"'{v}' ({c})" for v, c in list(nilai.items())[:6]) + (" ..." if len(nilai) > 6 else ""))
    urutan = str(info_tgl.get("urutan", "-"))
    if "PERINGATAN" in urutan:
        peringatan.append("Kolom tanggal mencampur urutan hari/bulan dan bulan/hari; sebagian tanggal dibuang.")
    elif urutan.startswith("bulan/hari"):
        peringatan.append("Tanggal numerik dibaca sebagai BULAN/HARI/TAHUN (gaya Amerika) karena ada nilai "
                          "seperti 01/31/2024. Pastikan ini sesuai berkas asli.")
    elif "diasumsikan" in urutan and (info_tgl.get("jenis_format") or {}).get("numerik"):
        peringatan.append("Urutan hari/bulan pada tanggal numerik (mis. 05/04/2024) tidak dapat dipastikan dari "
                          "isinya karena tidak ada nilai di atas 12; dibaca sebagai HARI/BULAN. Bila berkas memakai "
                          "urutan bulan/hari, tanggal akan tertukar.")
    if info_tgl.get("tertukar_diperbaiki"):
        peringatan.append(f"{info_tgl['tertukar_diperbaiki']} sel tanggal tampak tertukar hari/bulan oleh pengaturan "
                          "lokal Excel (sel tanggal hanya berhari <= 12 sementara sel teks bergaya hari/bulan) dan "
                          "sudah dibalik. Periksa beberapa baris di berkas asli.")
    if summary_himpun.get("satuan_nominal"):
        peringatan.append(f"Nominal dikonversi dari satuan {summary_himpun['satuan_nominal']} rupiah sesuai judul "
                          "kolomnya.")
    identik = int(summary_himpun.get("identik_dipertahankan") or 0)
    id_berbagi = int(summary_himpun.get("id_berbagi") or 0)
    awal: List[str] = []
    if summary_himpun.get("seluruh_ganda"):
        awal.append("Setiap baris data muncul tepat dua kali: kemungkinan seluruh isi berkas tertempel atau "
                    "terunggah dua kali (unggahan ganda utuh).")
    if identik:
        awal.append(f"{identik} baris identik dipertahankan karena tidak ada ID transaksi; periksa apakah ada "
                    "unggahan ganda.")
    if id_berbagi:
        awal.append(f"{id_berbagi} baris berbagi ID transaksi yang sama tetapi isinya berbeda (mis. satu kwitansi "
                    "untuk beberapa pos); semuanya dipertahankan.")
    peringatan[:0] = awal
    if deteksi.get("status") == "ragu":
        peringatan.append("Pemetaan kolom tidak sepenuhnya yakin: " + " ".join(deteksi.get("alasan", [])))

    salur = None
    if summary_salur is not None:
        salur = {"baris_dibaca": int(summary_salur.get("awal", 0)),
                 "baris_valid": int(len(df_salur)) if df_salur is not None else 0}
        salur["persen_valid"] = _persen(salur["baris_valid"], salur["baris_dibaca"])

    return {
        "berkas": nama_berkas,
        "sumber": {k: v for k, v in (info_baca or {}).items()},
        "status_pemetaan": deteksi.get("status", "-"),
        "pemetaan": {b: str(k) for b, k in (deteksi.get("pemetaan") or {}).items() if k},
        "baris_dibaca": dibaca,
        "baris_valid": valid,
        "persen_valid": _persen(valid, dibaca),
        "baris_dibuang": dibaca - valid,
        "dibuang": dibuang,
        "kategori_tak_dikenal": tak_dikenal,
        "tanggal_min": None if tmin is None else tmin.date().isoformat(),
        "tanggal_maks": None if tmaks is None else tmaks.date().isoformat(),
        "rentang_tanggal": f"{_tgl(tmin)} s.d. {_tgl(tmaks)}",
        "rentang_bulan": rentang,
        "bulan_berdata": bulan_berdata,
        "urutan_tanggal": urutan,
        "format_tanggal": info_tgl.get("jenis_format", {}),
        "penyaluran": salur,
        "peringatan": peringatan,
        "peramalan_terbatas": bool(valid and rentang < BULAN_MINIMUM_PERAMALAN),
        "identik_dipertahankan": identik,
        "salinan_identik": int(summary_himpun.get("salinan_identik") or 0),
        "contoh_identik": list(summary_himpun.get("contoh_identik") or []),
        "seluruh_ganda": bool(summary_himpun.get("seluruh_ganda")),
        "kolom_id_transaksi": summary_himpun.get("kolom_id_transaksi"),
        "id_berbagi": id_berbagi,
        "contoh_id_berbagi": list(summary_himpun.get("contoh_id_berbagi") or []),
        "id_transaksi_unik": bool((deteksi.get("opsi") or {}).get("id_transaksi_unik")),
        "sumber_id_transaksi": summary_himpun.get("sumber_id_transaksi"),
        "buang_duplikat_persis": bool((deteksi.get("opsi") or {}).get("buang_duplikat_persis")),
    }


_STATUS = {"otomatis": "terdeteksi otomatis", "tersimpan": "memakai pemetaan tersimpan lembaga",
           "pengguna": "dipilih pengguna (wizard)", "ragu": "tebakan otomatis (perlu dicek)"}


def _teks_id(lap: Dict[str, Any]) -> str:
    if lap.get("kolom_id_transaksi"):
        asal = "dari isi kolom" if lap.get("sumber_id_transaksi") == "isi" else "dari judul kolom"
        teks = f"kolom '{lap['kolom_id_transaksi']}' ({asal}); salinan utuh dibuang"
        if lap.get("id_transaksi_unik"):
            return teks + "; baris ber-ID sama juga dibuang (pilihan lembaga: ID dianggap unik)"
        if lap.get("id_berbagi"):
            teks += f"; {lap['id_berbagi']} baris berbagi ID dengan isi berbeda dipertahankan"
        if lap.get("identik_dipertahankan"):
            teks += f"; {lap['identik_dipertahankan']} baris tanpa ID yang identik dipertahankan"
        return teks
    if lap.get("buang_duplikat_persis"):
        return "tidak ada; duplikat persis dibuang (pilihan lembaga)"
    n = lap.get("identik_dipertahankan") or 0
    return f"tidak ada; {n} baris identik dipertahankan" if n else "tidak ada"


def tabel_kualitas(lap: Dict[str, Any]) -> pd.DataFrame:
    """Laporan kualitas sebagai tabel dua kolom (Butir, Nilai) untuk UI, Excel, dan PDF."""
    s = lap.get("sumber") or {}
    baris = [
        ("Berkas", lap.get("berkas", "-")),
        ("Baris data dibaca", f"{lap['baris_dibaca']:,}".replace(",", ".")),
        ("Baris valid", f"{lap['baris_valid']:,} ({lap['persen_valid']:.1f}%)".replace(",", ".")),
        ("Baris dibuang", f"{lap['baris_dibuang']:,}".replace(",", ".")),
    ]
    for d in lap.get("dibuang", []):
        teks = f"{d['jumlah']:,} ({d['persen']:.1f}%)".replace(",", ".")
        if d.get("contoh"):
            teks += f"; contoh: {d['contoh']}"
        baris.append((f"  Dibuang: {d['alasan']}", teks))
    baris += [
        ("Rentang tanggal", lap.get("rentang_tanggal", "-")),
        ("Rentang bulan", f"{lap.get('rentang_bulan', 0)} bulan ({lap.get('bulan_berdata', 0)} bulan berisi transaksi)"),
        ("Urutan tanggal numerik", lap.get("urutan_tanggal", "-")),
        ("ID transaksi", _teks_id(lap)),
    ]
    for k, nilai in (lap.get("kategori_tak_dikenal") or {}).items():
        baris.append((f"Tidak dikenali: {LABEL_BIDANG.get(k, k)}",
                      ", ".join(f"{v} ({c})" for v, c in nilai.items())))
    pem = lap.get("pemetaan") or {}
    if pem:
        baris.append(("Pemetaan kolom", f"{_STATUS.get(lap.get('status_pemetaan'), lap.get('status_pemetaan'))}: "
                      + "; ".join(f"{LABEL_BIDANG.get(b, b)} = '{k}'" for b, k in pem.items() if k)))
    if s.get("jenis") == "CSV":
        baris.append(("Format berkas", f"CSV, encoding {s.get('encoding')}, pemisah {s.get('pemisah')}"))
    elif s.get("jenis"):
        teks = "Excel, sheet " + ", ".join(s.get("sheet_penghimpunan") or [])
        if s.get("baris_judul"):
            teks += f", judul kolom di baris {s['baris_judul']}"
        baris.append(("Format berkas", teks))
    for c in s.get("catatan") or []:
        baris.append(("Catatan pembacaan", c))
    if lap.get("penyaluran"):
        p = lap["penyaluran"]
        baris.append(("Penyaluran", f"{p['baris_valid']:,} dari {p['baris_dibaca']:,} baris valid "
                                    f"({p['persen_valid']:.1f}%)".replace(",", ".")))
    for w in lap.get("peringatan", []):
        baris.append(("PERINGATAN", w))
    return pd.DataFrame(baris, columns=["Butir", "Nilai"])
