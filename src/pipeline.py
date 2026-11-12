"""Alur impor: baca berkas -> petakan kolom -> (pisahkan lembar gabungan) -> bersihkan -> laporan kualitas.

Dua pintu masuk:

- :func:`periksa_berkas` dipakai UI unggah untuk memutuskan apakah wizard pemetaan kolom perlu
  ditampilkan (status ``ragu``/``gagal``) atau berkas bisa langsung diproses (``otomatis``/``tersimpan``).
- :func:`siapkan_data` menghasilkan data bersih + laporan kualitas, memakai pemetaan dari pengguna,
  pemetaan tersimpan lembaga, atau deteksi otomatis (berurutan).

Semua kegagalan yang bisa dijelaskan dilempar sebagai :class:`DataFileError` berbahasa Indonesia.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from src.cleaning import ALASAN, clean_data
from src.kualitas_data import buat_laporan
from src.loader import BerkasTerbaca, DataFileError, baca_berkas, pesan_kolom_hilang
from src.pemetaan import (
    KOLOM_LOKASI, LABEL_BIDANG, HasilDeteksi, deteksi_pemetaan, tanda_kolom, terapkan_pemetaan,
    terapkan_tersimpan, validasi_pemetaan_pengguna,
)
from src.tanggal_impor import FORMAT_DITERIMA
from src.utils import parse_angka_indonesia

_KATA_MASUK = ("masuk", "terima", "penerimaan", "himpun", "penghimpunan", "debet", "debit", "pemasukan",
               "donasi", "setor", "setoran", "in", "inflow", "zis")
_KATA_KELUAR = ("keluar", "salur", "penyaluran", "distribusi", "kredit", "pengeluaran", "bantuan", "out",
                "outflow", "tasaruf", "tasyaruf", "pendayagunaan", "pentasyarufan")


@dataclass
class HasilPeriksa:
    status: str                      # tersimpan | otomatis | ragu | gagal
    deteksi: HasilDeteksi
    kolom: List[str]
    pratinjau: pd.DataFrame          # 5 baris pertama (judul kolom asli)
    info: Dict[str, Any]
    tanda: str
    berkas: Optional[BerkasTerbaca] = None   # hasil baca, dipakai ulang oleh siapkan_data

    @property
    def perlu_wizard(self) -> bool:
        return self.status in ("ragu", "gagal")


def _tentukan_pemetaan(df: pd.DataFrame, pemetaan: Optional[Dict[str, Optional[str]]],
                       pemetaan_lembaga: Optional[Iterable[Dict[str, Any]]]) -> HasilDeteksi:
    if pemetaan:
        bersih, galat = validasi_pemetaan_pengguna(df, pemetaan)
        if galat:
            raise DataFileError("Pemetaan kolom belum benar: " + " ".join(galat))
        return _lengkapi(df, HasilDeteksi(pemetaan=bersih, status="pengguna",
                                          alasan=["Pemetaan kolom dipilih pengguna."],
                                          keyakinan={b: 1.0 for b in bersih}, sumber={b: "pengguna" for b in bersih}))
    if pemetaan_lembaga:
        t = terapkan_tersimpan(df, pemetaan_lembaga)
        if t is not None:
            return _lengkapi(df, t)
    return deteksi_pemetaan(df, "Penghimpunan")


# Bidang yang tidak ditawarkan wizard / mungkin belum ada saat pemetaan disimpan, tetapi aman dikenali dari judul
_BIDANG_PELENGKAP = ("id_transaksi",)


def _lengkapi(df: pd.DataFrame, det: HasilDeteksi) -> HasilDeteksi:
    """Pemetaan pengguna/tersimpan menentukan bidang yang dikonfirmasi; kolom lain yang dikenali YAKIN dari
    judulnya (mis. 'No. Kwitansi' -> ID transaksi) ikut dipetakan, selama kolomnya belum dipakai."""
    otomatis = deteksi_pemetaan(df, "Penghimpunan")
    dipakai = set(det.pemetaan.values())
    for b in _BIDANG_PELENGKAP:
        k = otomatis.pemetaan.get(b)
        if b not in det.pemetaan and k and k not in dipakai and otomatis.sumber.get(b) == "judul":
            det.pemetaan[b] = k
            det.sumber[b] = "judul"
            dipakai.add(k)
    return det


def periksa_berkas(file_bytes: bytes, filename: str,
                   pemetaan_lembaga: Optional[Iterable[Dict[str, Any]]] = None) -> HasilPeriksa:
    """Baca berkas dan nilai pemetaan kolomnya tanpa membersihkan (untuk wizard UI)."""
    berkas = baca_berkas(file_bytes, filename)
    df = berkas.tabel["Penghimpunan"]
    det = _tentukan_pemetaan(df, None, pemetaan_lembaga)
    kolom = [c for c in df.columns if c != KOLOM_LOKASI]
    return HasilPeriksa(status=det.status, deteksi=det, kolom=kolom,
                        pratinjau=df[kolom].head(5).copy(), info=berkas.info, tanda=tanda_kolom(kolom),
                        berkas=berkas)


def _token(v: Any) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", str(v).lower()) if t]


def _arah(v: Any) -> Optional[str]:
    tok = _token(v)
    if any(t.startswith(k) if len(k) > 3 else t == k for t in tok for k in _KATA_KELUAR):
        return "keluar"
    if any(t.startswith(k) if len(k) > 3 else t == k for t in tok for k in _KATA_MASUK):
        return "masuk"
    return None


def _contoh(df: pd.DataFrame, mask: pd.Series, kolom: Optional[str] = None) -> List[str]:
    out = []
    for i in mask[mask].index[:5]:
        teks = str(df.at[i, KOLOM_LOKASI])
        if kolom is not None:
            teks += f" ({str(df.at[i, kolom])[:40]!r})"
        out.append(teks)
    return out


def _pisah_gabungan(df: pd.DataFrame, pem: Dict[str, str]) -> Tuple[pd.DataFrame, Optional[pd.DataFrame],
                                                                        Dict[str, str], Optional[Dict[str, str]],
                                                                        Dict[str, Dict[str, Any]]]:
    """Pisahkan lembar gabungan penghimpunan+penyaluran.

    Returns:
        (df penghimpunan, df penyaluran|None, pemetaan himpun, pemetaan salur|None, dibuang_pra)
    """
    pra: Dict[str, Dict[str, Any]] = {}
    inti = {b: k for b, k in pem.items() if b not in ("arus", "masuk", "keluar")}
    if "arus" in pem and "jumlah" in pem:
        arah = df[pem["arus"]].map(_arah)
        tak = arah.isna()
        if tak.all():
            # kolom "jenis transaksi" ternyata bukan penanda masuk/keluar: abaikan
            return df, None, inti, None, pra
        if tak.any():
            pra["arus_tak_dikenal"] = {"jumlah": int(tak.sum()), "contoh": _contoh(df, tak, pem["arus"])}
        himpun = df[arah == "masuk"].reset_index(drop=True)
        salur = df[arah == "keluar"].reset_index(drop=True)
        return himpun, (salur if len(salur) else None), inti, inti, pra
    if "masuk" in pem and "jumlah" not in pem:
        masuk = df[pem["masuk"]].map(parse_angka_indonesia)
        keluar = df[pem["keluar"]].map(parse_angka_indonesia) if "keluar" in pem else pd.Series(None, index=df.index)
        ada_masuk = masuk.notna() & (masuk != 0)
        ada_keluar = keluar.notna() & (keluar != 0)
        kosong = ~(ada_masuk | ada_keluar)
        if kosong.any():
            pra["masuk_keluar_kosong"] = {"jumlah": int(kosong.sum()), "contoh": _contoh(df, kosong)}
        himpun = df[ada_masuk].reset_index(drop=True)
        salur = df[ada_keluar].reset_index(drop=True)
        ph = {**inti, "jumlah": pem["masuk"]}
        ps = {**inti, "jumlah": pem["keluar"]} if "keluar" in pem else None
        return himpun, (salur if len(salur) else None), ph, ps, pra
    return df, None, inti, None, pra


def _pemetaan_salur_gabungan(df: pd.DataFrame, ph: Dict[str, str], ps: Dict[str, str]) -> Dict[str, str]:
    """Pemetaan untuk baris penyaluran dari lembar gabungan: tanggal/jumlah/wilayah dari lembar,
    kolom khas penyaluran (program, asnaf, ...) dideteksi dari judul."""
    det = deteksi_pemetaan(df, "Penyaluran")
    hasil = {b: k for b, k in det.pemetaan.items()
             if b in ("program", "asnaf", "jenis_dana_sumber", "jumlah_penerima")}
    for b in ("tanggal", "jumlah", "kabupaten_kota"):
        if b in ps:
            hasil[b] = ps[b]
    if "jenis_dana" in ph and "jenis_dana_sumber" not in hasil:
        hasil["jenis_dana_sumber"] = ph["jenis_dana"]
    dipakai: Dict[str, str] = {}
    for b, k in list(hasil.items()):
        if k in dipakai.values() and b not in ("tanggal", "jumlah"):
            del hasil[b]
        else:
            dipakai[b] = k
    return hasil


def _pesan_tanpa_baris_valid(summary: Dict[str, Any], nama_asli: Dict[str, str]) -> str:
    bagian = []
    for kunci, n in (summary.get("alasan") or {}).items():
        label = ALASAN[kunci][1]
        if kunci.startswith("jumlah"):
            label += f" di kolom '{nama_asli.get('jumlah', 'jumlah')}'"
        elif kunci.startswith("tanggal"):
            label += f" di kolom '{nama_asli.get('tanggal', 'tanggal')}'"
        contoh = (summary.get("contoh") or {}).get(kunci)
        bagian.append(f"{n} baris {label}" + (f" (contoh: {'; '.join(contoh[:3])})" if contoh else ""))
    alasan = "; ".join(bagian) or "-"
    return ("Tidak ada baris penghimpunan yang valid setelah pembersihan. Rincian: " + alasan + ". "
            f"Yang diharapkan: kolom '{nama_asli.get('jumlah', 'jumlah')}' berisi angka nominal (contoh: 1500000, "
            f"1.500.000, 'Rp 1.500.000,-', 'Rp 2,5 jt') dan kolom '{nama_asli.get('tanggal', 'tanggal')}' "
            f"berisi tanggal ({FORMAT_DITERIMA}).")


def siapkan_data(
    file_bytes: bytes,
    filename: str,
    pemetaan: Optional[Dict[str, Optional[str]]] = None,
    pemetaan_lembaga: Optional[Iterable[Dict[str, Any]]] = None,
    berkas: Optional[BerkasTerbaca] = None,
    buang_duplikat_persis: Optional[bool] = None,
    id_transaksi_unik: Optional[bool] = None,
) -> Dict[str, Any]:
    """Muat berkas, petakan kolom, bersihkan, dan susun laporan kualitas data.

    Args:
        pemetaan: pemetaan pilihan pengguna {bidang standar: judul kolom asli} (dari wizard).
        pemetaan_lembaga: daftar pemetaan tersimpan lembaga (lihat ``pemetaan_service``).
        buang_duplikat_persis: bila berkas tanpa kolom ID transaksi, buang baris identik (unggahan ganda).
            None = ikuti pilihan yang tersimpan bersama pemetaan lembaga (bawaan: dipertahankan).
        id_transaksi_unik: anggap ID transaksi unik dan buang baris ber-ID sama walau isinya berbeda.
            None = ikuti pilihan tersimpan (bawaan: TIDAK; satu kwitansi bisa memuat beberapa pos).
        berkas: hasil :func:`baca_berkas` untuk berkas yang sama (mis. dari ``periksa_berkas``) agar
            berkas besar tidak dibaca dua kali.

    Returns:
        dict berisi df_himpun, log_himpun, summary_himpun, df_salur, log_salur, kualitas, pemetaan, info

    Raises:
        DataFileError: pesan yang aman dan jelas untuk ditampilkan ke pengguna.
    """
    berkas = berkas or baca_berkas(file_bytes, filename)
    raw = berkas.tabel["Penghimpunan"]
    det = _tentukan_pemetaan(raw, pemetaan, pemetaan_lembaga)
    if det.status == "gagal":
        raise DataFileError(pesan_kolom_hilang(raw, det.kolom_wajib_hilang(), "Penghimpunan"))

    df_h, df_s_gab, ph, ps, pra = _pisah_gabungan(raw, det.pemetaan)
    if df_h.empty:
        raise DataFileError(
            f"Tidak ada baris penghimpunan (masuk) di berkas '{filename}'. Kolom "
            f"'{det.pemetaan.get('arus') or det.pemetaan.get('masuk')}' tidak berisi transaksi masuk yang dikenali.")
    df_mapped, nama_asli = terapkan_pemetaan(df_h, ph)
    if buang_duplikat_persis is None:
        buang_duplikat_persis = bool(det.opsi.get("buang_duplikat_persis"))
    det.opsi["buang_duplikat_persis"] = bool(buang_duplikat_persis)
    if id_transaksi_unik is None:
        id_transaksi_unik = bool(det.opsi.get("id_transaksi_unik"))
    det.opsi["id_transaksi_unik"] = bool(id_transaksi_unik)
    df_himpun, log_himpun, summary = clean_data(df_mapped, "Penghimpunan", sudah_dipetakan=True,
                                                buang_duplikat_persis=buang_duplikat_persis,
                                                id_transaksi_unik=id_transaksi_unik,
                                                nama_asli=nama_asli)
    if df_himpun.empty:
        raise DataFileError(_pesan_tanpa_baris_valid(summary, nama_asli))
    for kunci, v in pra.items():
        log_himpun.insert(0, {"aksi": "Hapus Baris Gabungan Tak Dikenal", "jumlah_baris": v["jumlah"],
                              "keterangan": f"Dihapus {v['jumlah']} baris: {kunci.replace('_', ' ')}. "
                                            f"Contoh: {'; '.join(v['contoh'])}."})

    df_salur, log_salur, summary_salur = pd.DataFrame(), [], None
    if df_s_gab is not None and ps is not None:
        pem_s = _pemetaan_salur_gabungan(df_s_gab, ph, ps)
        dm, na = terapkan_pemetaan(df_s_gab, pem_s)
        df_salur, log_salur, summary_salur = clean_data(dm, "Penyaluran", sudah_dipetakan=True, nama_asli=na)
    else:
        raw_salur = berkas.tabel.get("Penyaluran", pd.DataFrame())
        if not raw_salur.empty:
            det_s = deteksi_pemetaan(raw_salur, "Penyaluran")
            if det_s.status == "gagal":
                # penyaluran opsional: abaikan dengan catatan, jangan gagalkan analisis
                log_salur = [{"aksi": "Sheet Penyaluran Diabaikan", "jumlah_baris": len(raw_salur),
                              "keterangan": pesan_kolom_hilang(raw_salur, det_s.kolom_wajib_hilang(), "Penyaluran")}]
            else:
                dm, na = terapkan_pemetaan(raw_salur, {b: k for b, k in det_s.pemetaan.items()
                                                       if b not in ("arus", "masuk", "keluar")})
                df_salur, log_salur, summary_salur = clean_data(dm, "Penyaluran", sudah_dipetakan=True,
                                                                nama_asli=na)

    det_dict = det.sebagai_dict()
    kualitas = buat_laporan(filename, berkas.info, det_dict, summary, df_himpun, summary_salur, df_salur, pra)
    return {
        "df_himpun": df_himpun,
        "log_himpun": log_himpun,
        "summary_himpun": summary,
        "df_salur": df_salur,
        "log_salur": log_salur,
        "kualitas": kualitas,
        "pemetaan": det_dict,
        "kolom": [c for c in raw.columns if c != KOLOM_LOKASI],
        "info": berkas.info,
    }


__all__ = ["DataFileError", "HasilPeriksa", "periksa_berkas", "siapkan_data", "LABEL_BIDANG"]
