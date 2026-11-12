"""Ukur keberhasilan impor terhadap variasi berkas sintetis dari ``buat_data_kotor.py``.

Kategori per variasi:

- **otomatis**: deteksi berstatus otomatis/tersimpan DAN hasilnya cocok dengan kunci jawaban
  (jumlah baris, total nominal, rentang tanggal, jumlah per kategori, penyaluran bila ada).
- **wizard**: deteksi ragu/gagal, lalu dengan pemetaan yang benar (mensimulasikan pilihan pengguna di
  wizard) hasilnya cocok dengan kunci jawaban.
- **ditolak**: berkas yang memang tidak bisa dibaca ditolak dengan DataFileError yang jelas
  (bahasa Indonesia, tanpa traceback, menyebut penyebabnya).
- **GAGAL**: selain itu, termasuk: hasil terbaca tetapi SALAH, berkas wajar ditolak, berkas rusak
  diterima, exception mentah, atau pesan tolak yang tidak jelas.

Pemakaian:
    python scripts/ukur_impor.py                 # buat variasi (termasuk 100 ribu baris) lalu ukur
    python scripts/ukur_impor.py --tanpa-besar --laporan docs/HASIL_UJI_IMPOR.md
"""
import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))
sys.path.insert(0, str(AKAR / "scripts"))

from src.loader import DataFileError  # noqa: E402
from src.pipeline import periksa_berkas, siapkan_data  # noqa: E402

_KATA_ID = ("berkas", "kolom", "baris", "sheet", "tanggal", "jumlah", "kosong")
_BAU_TEKNIS = re.compile(r"Traceback|File \"|Error:|Exception|\bline \d+|0x[0-9a-f]{6,}")


def cocokkan(hasil: Dict[str, Any], h: Dict[str, Any]) -> List[str]:
    """Daftar ketidakcocokan hasil impor terhadap kunci jawaban (kosong = benar)."""
    salah = []
    df = hasil["df_himpun"]
    if len(df) != h["n"]:
        salah.append(f"baris {len(df)} != {h['n']}")
    total = round(float(df["jumlah"].sum()), 2)
    if abs(total - h["total"]) > 0.01:
        salah.append(f"total {total:,.2f} != {h['total']:,.2f}")
    if len(df):
        tmin, tmaks = df["tanggal"].min().date().isoformat(), df["tanggal"].max().date().isoformat()
        if (tmin, tmaks) != (h["tanggal_min"], h["tanggal_maks"]):
            salah.append(f"tanggal {tmin}..{tmaks} != {h['tanggal_min']}..{h['tanggal_maks']}")
    if "per_bulan" in h and len(df):
        aktual = {str(k): round(float(v), 2)
                  for k, v in df.groupby(df["tanggal"].dt.to_period("M"))["jumlah"].sum().items()}
        beda = sorted(b for b in set(aktual) | set(h["per_bulan"])
                      if abs(aktual.get(b, 0) - h["per_bulan"].get(b, 0)) > 0.01)
        if beda:
            salah.append(f"total per bulan beda di {len(beda)} bulan (mis. {', '.join(beda[:3])})")
    for k in ("jenis_dana", "kanal"):
        if k in h:
            if k not in df.columns:
                salah.append(f"kolom {k} hilang")
                continue
            aktual = {a: int(b) for a, b in df[k].value_counts().items()}
            if aktual != h[k]:
                beda = {x: (aktual.get(x), h[k].get(x)) for x in set(aktual) | set(h[k])
                        if aktual.get(x) != h[k].get(x)}
                salah.append(f"{k} beda (aktual, harapan): {dict(list(beda.items())[:4])}")
    ringkas = hasil["summary_himpun"]
    if "identik" in h:
        if ringkas.get("identik_dipertahankan") != h["identik"]:
            salah.append(f"identik {ringkas.get('identik_dipertahankan')} != {h['identik']}")
        if not any("baris identik dipertahankan karena tidak ada ID transaksi" in w
                   for w in hasil["kualitas"]["peringatan"]):
            salah.append("peringatan baris identik tidak muncul")
    if "duplikat_id" in h and (ringkas.get("alasan") or {}).get("duplikat_id", 0) != h["duplikat_id"]:
        salah.append(f"duplikat ID dibuang {(ringkas.get('alasan') or {}).get('duplikat_id', 0)} != {h['duplikat_id']}")
    if h.get("seluruh_ganda") and not ringkas.get("seluruh_ganda"):
        salah.append("unggahan ganda utuh tidak terdeteksi")
    if "salur_n" in h:
        ds = hasil["df_salur"]
        if len(ds) != h["salur_n"]:
            salah.append(f"penyaluran {len(ds)} baris != {h['salur_n']}")
        elif abs(round(float(ds["jumlah"].sum()), 2) - h["salur_total"]) > 0.01:
            salah.append("total penyaluran beda")
    return salah


def pesan_jelas(pesan: str, kata_kunci: Optional[str]) -> List[str]:
    masalah = []
    if _BAU_TEKNIS.search(pesan):
        masalah.append("pesan memuat detail teknis/traceback")
    if not any(k in pesan.lower() for k in _KATA_ID):
        masalah.append("pesan tidak menjelaskan berkas/kolom/baris")
    if kata_kunci and kata_kunci.lower() not in pesan.lower():
        masalah.append(f"pesan tidak menyebut '{kata_kunci}'")
    return masalah


def nilai_variasi(v: Dict[str, Any], isi: bytes) -> Dict[str, Any]:
    out = {"kode": v["kode"], "deskripsi": v["deskripsi"], "kelompok": v["kelompok"], "status_deteksi": "-",
           "kategori": "GAGAL", "catatan": ""}
    t0 = time.perf_counter()
    try:
        try:
            p = periksa_berkas(isi, v["berkas"])
            out["status_deteksi"] = p.status
        except DataFileError as e:
            if v["harus_ditolak"]:
                m = pesan_jelas(str(e), v.get("alasan_tolak"))
                out["kategori"], out["catatan"] = ("ditolak", str(e)[:160]) if not m else ("GAGAL", "; ".join(m))
            else:
                out["catatan"] = f"ditolak padahal seharusnya terbaca: {str(e)[:200]}"
            return out
        pakai_wizard = p.status in ("ragu", "gagal")
        try:
            if pakai_wizard and not v["harus_ditolak"]:
                if not v.get("pemetaan_benar"):
                    out["catatan"] = "perlu wizard, tetapi wizard tidak bisa memetakan struktur ini: " + \
                        " ".join(p.deteksi.alasan)[:200]
                    return out
                hasil = siapkan_data(isi, v["berkas"], pemetaan=v["pemetaan_benar"], berkas=p.berkas)
            else:
                hasil = siapkan_data(isi, v["berkas"], berkas=p.berkas)
        except DataFileError as e:
            if v["harus_ditolak"]:
                m = pesan_jelas(str(e), v.get("alasan_tolak"))
                out["kategori"], out["catatan"] = ("ditolak", str(e)[:160]) if not m else ("GAGAL", "; ".join(m))
            else:
                out["catatan"] = f"ditolak padahal seharusnya terbaca: {str(e)[:200]}"
            return out
        if v["harus_ditolak"]:
            out["catatan"] = f"diterima padahal seharusnya ditolak ({len(hasil['df_himpun'])} baris)"
            return out
        salah = cocokkan(hasil, v["harapan"])
        if salah:
            out["catatan"] = "TERBACA SALAH: " + "; ".join(salah)
            return out
        out["kategori"] = "wizard" if pakai_wizard else "otomatis"
        lap = hasil["kualitas"]
        out["catatan"] = f"{lap['baris_valid']}/{lap['baris_dibaca']} baris valid"
        if pakai_wizard:
            out["catatan"] += "; alasan wizard: " + " ".join(p.deteksi.alasan)[:150]
        return out
    except Exception as e:  # exception mentah = kegagalan serius
        out["catatan"] = f"EXCEPTION {type(e).__name__}: {str(e)[:200]}"
        return out
    finally:
        out["detik"] = round(time.perf_counter() - t0, 2)


def ukur(direktori: Path) -> List[Dict[str, Any]]:
    manifest = json.loads((direktori / "manifest.json").read_text(encoding="utf-8"))
    return [nilai_variasi(v, (direktori / v["berkas"]).read_bytes()) for v in manifest]


def ringkas(hasil: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(hasil)
    hit = {k: sum(r["kategori"] == k for r in hasil) for k in ("otomatis", "wizard", "ditolak", "GAGAL")}
    return {"N": n, **hit, "gagal": [r["kode"] for r in hasil if r["kategori"] == "GAGAL"]}


def markdown(hasil: List[Dict[str, Any]]) -> str:
    r = ringkas(hasil)
    baris = [
        f"Dari **{r['N']} variasi berkas sintetis**: **{r['otomatis']} terbaca otomatis**, "
        f"**{r['wizard']} terbaca lewat wizard** pemetaan kolom, **{r['ditolak']} ditolak dengan pesan jelas**, "
        f"**{r['GAGAL']} gagal**.",
        "",
        "| Kode | Variasi | Deteksi | Hasil | Waktu (dtk) | Catatan |",
        "|---|---|---|---|---|---|",
    ]
    for x in hasil:
        cat = x["catatan"].replace("|", "/").replace("\n", " ")
        baris.append(f"| {x['kode']} | {x['deskripsi']} | {x['status_deteksi']} | **{x['kategori']}** | "
                     f"{x['detik']} | {cat} |")
    return "\n".join(baris)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ukur keterbacaan variasi berkas sintetis")
    ap.add_argument("--direktori", help="direktori hasil buat_data_kotor.py (default: buat baru sementara)")
    ap.add_argument("--tanpa-besar", action="store_true")
    ap.add_argument("--laporan", help="tulis tabel markdown ke berkas ini")
    a = ap.parse_args(argv)
    if a.direktori:
        d = Path(a.direktori)
    else:
        from buat_data_kotor import tulis_semua
        d = Path(tempfile.mkdtemp(prefix="impor_"))
        tulis_semua(d, besar=not a.tanpa_besar)
    hasil = ukur(d)
    md = markdown(hasil)
    print(md)
    if a.laporan:
        Path(a.laporan).write_text(md + "\n", encoding="utf-8")
    return 0 if not ringkas(hasil)["GAGAL"] else 1


if __name__ == "__main__":
    sys.exit(main())
