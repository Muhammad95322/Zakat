"""Aplikasi web Zakat Insight (FastAPI + Jinja2), memakai mesin Python dan basis data yang sama.

    uvicorn web.main:app --reload --port 8000

Tahap ini: masuk, beranda, analisis satu berkas, unggah sederhana / data contoh. Halaman lain
didaftar di /segera-hadir.
"""
import io
import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlencode

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.config import settings
from src.database import SessionLocal
from src.middleware.rate_limiter import RateLimiter
from src.services import batas_laju
from src.services.audit_service import catat_log
from src.services.auth_service import login as layanan_login
from src.services.pemetaan_service import daftar_pemetaan
from src.services.tenant_service import get_tenant_stats
from src.services.upload_service import baca_berkas_unggahan, get_upload, get_uploads, simpan_upload
from src.auth.jwt_handler import decode_token
from web import analisis as mesin
from web import keamanan
from web.format import FILTER
from web.grafik import pita_dua_belas_bulan, ramadan_berikutnya
from web.sesi import Pengguna, baca_sesi, buat_sesi, cabut_sesi

logger = logging.getLogger("zakat.web")

AKAR = Path(__file__).resolve().parent
COOKIE_SESI = "__Host-zi_sesi" if settings.is_production else "zi_sesi"
COOKIE_CSRF_MASUK = "__Host-zi_csrf" if settings.is_production else "zi_csrf"
# Sama dengan halaman Streamlit: 5 kegagalan per email per 15 menit (RateLimiter di memori)
BATAS_EMAIL, JENDELA_EMAIL = 5, 900

env = Environment(loader=FileSystemLoader(str(AKAR / "templates")),
                  autoescape=select_autoescape(["html", "xml"], default=True))
env.filters.update(FILTER)
templates = Jinja2Templates(env=env)

@asynccontextmanager
async def _siklus(_app):
    # Sama dengan aplikasi Streamlit: terapkan migrasi Alembic (termasuk 0005 sesi_web) saat mulai
    from src.database import init_db
    init_db()
    yield


app = FastAPI(title="Zakat Insight", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_siklus)
app.add_middleware(keamanan.HeaderKeamanan)
app.mount("/statis", StaticFiles(directory=str(AKAR / "static")), name="statis")


# ---------------------------------------------------------------------------
# Dependensi
# ---------------------------------------------------------------------------
def ambil_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PerluMasuk(Exception):
    pass


class Ditolak(Exception):
    def __init__(self, pesan: str, status: int = 403):
        self.pesan, self.status = pesan, status


def pengguna_opsional(request: Request, db: Session = Depends(ambil_db)) -> Optional[Pengguna]:
    pengguna = baca_sesi(db, request.cookies.get(COOKIE_SESI))
    request.state.pengguna = pengguna  # dipakai halaman galat untuk menampilkan navigasi
    return pengguna


def wajib_masuk(pengguna: Optional[Pengguna] = Depends(pengguna_opsional)) -> Pengguna:
    if pengguna is None:
        raise PerluMasuk()
    return pengguna


def wajib_lembaga(pengguna: Pengguna = Depends(wajib_masuk)) -> Pengguna:
    if not pengguna.tenant_id:
        raise Ditolak("Akun super admin tidak terikat ke satu lembaga. Memilih lembaga untuk dianalisis belum "
                      "tersedia di versi web; untuk sementara gunakan aplikasi lama.")
    return pengguna


def wajib_peran(peran_minimal: str):
    """Padanan ``check_role``: pemeriksaan peran di server untuk setiap rute."""
    def periksa(pengguna: Pengguna = Depends(wajib_lembaga)) -> Pengguna:
        if not pengguna.boleh(peran_minimal):
            raise Ditolak(f"Peran Anda ({pengguna.nama_peran}) hanya dapat melihat data. Minta admin lembaga "
                          "mengubah peran Anda menjadi staf bila Anda perlu mengunggah berkas.")
        return pengguna
    return periksa


def periksa_csrf(request: Request, dikirim: Optional[str], seharusnya: Optional[str]) -> None:
    if not keamanan.asal_sah(request) or not keamanan.token_cocok(dikirim, seharusnya):
        raise Ditolak("Formulir ini sudah kedaluwarsa atau tidak berasal dari halaman ini. Muat ulang halaman, "
                      "lalu kirim lagi.", status=400)


# ---------------------------------------------------------------------------
# Penanganan galat
# ---------------------------------------------------------------------------
def tampil(request: Request, nama: str, konteks: dict, status: int = 200) -> HTMLResponse:
    dasar = {"pengguna": None, "aktif": "", "produksi": settings.is_production}
    dasar.update(konteks)
    return templates.TemplateResponse(request, nama, dasar, status_code=status)


@app.exception_handler(PerluMasuk)
async def _perlu_masuk(request: Request, exc: PerluMasuk):
    return RedirectResponse("/masuk", status_code=303)


@app.exception_handler(Ditolak)
async def _ditolak(request: Request, exc: Ditolak):
    pengguna = getattr(request.state, "pengguna", None)
    judul = "Formulir tidak dapat diproses" if exc.status == 400 else "Halaman ini tidak tersedia untuk akun Anda"
    return tampil(request, "galat.html", {"pengguna": pengguna, "judul": judul, "pesan": exc.pesan},
                  status=exc.status)


@app.exception_handler(StarletteHTTPException)
async def _http(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        pengguna = getattr(request.state, "pengguna", None)
        return tampil(request, "galat.html", {
            "pengguna": pengguna, "judul": "Halaman atau berkas tidak ditemukan",
            "pesan": "Alamatnya mungkin salah, atau berkas sudah dihapus. Buka beranda untuk melihat berkas "
                     "yang tersedia bagi lembaga Anda."}, status=404)
    return Response(status_code=exc.status_code)


def tidak_ditemukan():
    raise StarletteHTTPException(status_code=404)


# ---------------------------------------------------------------------------
# Masuk & keluar
# ---------------------------------------------------------------------------
def _set_cookie(resp: Response, nama: str, nilai: str) -> None:
    resp.set_cookie(nama, nilai, httponly=True, samesite="lax", secure=settings.is_production, path="/")


def _layar_masuk(request: Request, galat: Optional[str] = None, email: str = "", status: int = 200,
                 info: Optional[str] = None) -> HTMLResponse:
    csrf = request.cookies.get(COOKIE_CSRF_MASUK)
    if not csrf or len(csrf) > 128:
        csrf = keamanan.token_baru()
    hari_ini = date.today()
    resp = tampil(request, "masuk.html", {
        "csrf": csrf, "galat": galat, "email": email, "info": info,
        "ramadan": ramadan_berikutnya(hari_ini), "pita": pita_dua_belas_bulan(hari_ini),
        "maks_gagal": settings.LOGIN_MAX_ATTEMPTS, "menit_kunci": settings.LOGIN_LOCKOUT_MINUTES,
    }, status=status)
    _set_cookie(resp, COOKIE_CSRF_MASUK, csrf)
    return resp


@app.get("/", include_in_schema=False)
def akar(pengguna: Optional[Pengguna] = Depends(pengguna_opsional)):
    return RedirectResponse("/beranda" if pengguna else "/masuk", status_code=303)


@app.get("/masuk", response_class=HTMLResponse)
def masuk(request: Request, keluar: Optional[str] = None,
          pengguna: Optional[Pengguna] = Depends(pengguna_opsional)):
    if pengguna:
        return RedirectResponse("/beranda", status_code=303)
    return _layar_masuk(request, info="Anda sudah keluar. Sesi di perangkat ini telah diakhiri." if keluar else None)


@app.post("/masuk", response_class=HTMLResponse)
def kirim_masuk(request: Request, email: str = Form(""), sandi: str = Form(""), csrf: str = Form(""),
                db: Session = Depends(ambil_db)):
    periksa_csrf(request, csrf, request.cookies.get(COOKIE_CSRF_MASUK))
    email = email.strip()[:200]
    if not email or not sandi:
        return _layar_masuk(request, "Isi email dan kata sandi terlebih dahulu.", email, status=400)
    ip, ua = keamanan.ip_dan_ua(request)

    boleh_ip, tunggu_ip = batas_laju.periksa(db, "login", ip)
    if not boleh_ip:
        pesan = batas_laju.pesan_terlalu_sering(tunggu_ip).replace("⚠️", "").strip()
        return _layar_masuk(request, pesan, email, status=429)

    kunci_email = f"login:{email.lower()}"
    limiter = RateLimiter()
    boleh_email, tunggu_email = limiter.check_rate_limit(kunci_email, BATAS_EMAIL, JENDELA_EMAIL)
    if not boleh_email:
        menit = max(1, (tunggu_email + 59) // 60)
        return _layar_masuk(request, f"Terlalu banyak percobaan gagal untuk email ini. Coba lagi dalam {menit} menit.",
                            email, status=429)

    hasil = layanan_login(db, email, sandi, ip=ip, ua=ua)
    if not hasil:
        limiter.record_failure(kunci_email)
        batas_laju.catat(db, "login", ip, ua=ua)
        catat_log(db, None, "login_gagal", ip=ip, ua=ua)  # tanpa email & sandi, sama dengan versi Streamlit
        return _layar_masuk(request, "Email atau kata sandi tidak cocok.", email, status=401)

    access, refresh = hasil
    data = decode_token(access) or {}
    limiter.reset(kunci_email)
    lama = request.cookies.get(COOKIE_SESI)
    if lama:
        cabut_sesi(db, lama)
    mentah = buat_sesi(db, data.get("sub"), refresh)
    resp = RedirectResponse("/beranda", status_code=303)
    _set_cookie(resp, COOKIE_SESI, mentah)
    resp.delete_cookie(COOKIE_CSRF_MASUK, path="/", secure=settings.is_production, httponly=True, samesite="lax")
    return resp


@app.post("/keluar")
def keluar(request: Request, csrf: str = Form(""), pengguna: Pengguna = Depends(wajib_masuk),
           db: Session = Depends(ambil_db)):
    periksa_csrf(request, csrf, pengguna.csrf)
    ip, ua = keamanan.ip_dan_ua(request)
    cabut_sesi(db, request.cookies.get(COOKIE_SESI), ip=ip, ua=ua)
    resp = RedirectResponse("/masuk?keluar=1", status_code=303)
    resp.delete_cookie(COOKIE_SESI, path="/", secure=settings.is_production, httponly=True, samesite="lax")
    return resp


# ---------------------------------------------------------------------------
# Beranda
# ---------------------------------------------------------------------------
@app.get("/beranda", response_class=HTMLResponse)
def beranda(request: Request, pengguna: Pengguna = Depends(wajib_masuk), db: Session = Depends(ambil_db)):
    hari_ini = date.today()
    berkas, stats = [], {}
    if pengguna.tenant_id:
        berkas = get_uploads(db, pengguna.tenant_id)
        stats = get_tenant_stats(db, pengguna.tenant_id)
    return tampil(request, "beranda.html", {
        "pengguna": pengguna, "aktif": "beranda", "berkas": berkas[:6], "jumlah_berkas": len(berkas),
        "stats": stats, "ramadan": ramadan_berikutnya(hari_ini), "pita": pita_dua_belas_bulan(hari_ini),
        "boleh_unggah": pengguna.boleh("staf") and bool(pengguna.tenant_id),
    })


# ---------------------------------------------------------------------------
# Analisis
# ---------------------------------------------------------------------------
@app.get("/analisis", response_class=HTMLResponse)
def analisis_awal(request: Request, berkas: Optional[str] = None, pengguna: Pengguna = Depends(wajib_lembaga),
                  db: Session = Depends(ambil_db)):
    daftar = get_uploads(db, pengguna.tenant_id)
    if berkas:
        if not get_upload(db, berkas, pengguna.tenant_id):
            tidak_ditemukan()
        return RedirectResponse(f"/analisis/{berkas}", status_code=303)
    if daftar:
        return RedirectResponse(f"/analisis/{daftar[0].id}", status_code=303)
    return tampil(request, "analisis_kosong.html", {
        "pengguna": pengguna, "aktif": "analisis", "boleh_unggah": pengguna.boleh("staf")})


@app.get("/analisis/{upload_id}", response_class=HTMLResponse)
def analisis_berkas(request: Request, upload_id: str, wilayah: Optional[str] = None, dana: Optional[str] = None,
                    kanal: Optional[str] = None, pengguna: Pengguna = Depends(wajib_lembaga),
                    db: Session = Depends(ambil_db)):
    # tenant_id SELALU dari sesi; berkas lembaga lain tidak cocok filter ini -> 404
    upload = get_upload(db, upload_id, pengguna.tenant_id)
    if upload is None:
        tidak_ditemukan()
    daftar = get_uploads(db, pengguna.tenant_id)
    konteks = {"pengguna": pengguna, "aktif": "analisis", "upload": upload, "daftar": daftar,
               "boleh_unggah": pengguna.boleh("staf"), "galat": None, "hasil": None}
    try:
        isi = baca_berkas_unggahan(upload)
    except FileNotFoundError:
        konteks["galat"] = ("Berkas fisiknya tidak ditemukan di penyimpanan. Unggah ulang berkas ini, atau pilih "
                            "berkas lain di atas.")
        return tampil(request, "analisis.html", konteks, status=200)
    except Exception:
        logger.exception("gagal membaca berkas dari penyimpanan")
        konteks["galat"] = "Penyimpanan berkas sedang tidak dapat diakses. Coba lagi beberapa saat lagi."
        return tampil(request, "analisis.html", konteks, status=503)
    try:
        siap = mesin.siapkan(isi, upload.nama_file_asli, daftar_pemetaan(db, pengguna.tenant_id))
    except mesin.BerkasTidakBisaDianalisis as e:
        konteks["galat"] = f"Berkas ini tidak dapat dianalisis. {e}"
        return tampil(request, "analisis.html", konteks)
    hasil = mesin.analisis(siap, {"wilayah": wilayah, "dana": dana, "kanal": kanal})
    konteks["hasil"] = hasil
    konteks["tautan_reset"] = f"/analisis/{upload.id}"
    konteks["query_aktif"] = urlencode({k: v for k, v in hasil.filter_aktif.items() if v})
    return tampil(request, "analisis.html", konteks)


# ---------------------------------------------------------------------------
# Unggah (paling sederhana) & data contoh
# ---------------------------------------------------------------------------
def _layar_unggah(request: Request, pengguna: Pengguna, db: Session, galat: Optional[str] = None,
                  status: int = 200) -> HTMLResponse:
    stats = get_tenant_stats(db, pengguna.tenant_id)
    return tampil(request, "unggah.html", {"pengguna": pengguna, "aktif": "unggah", "galat": galat, "stats": stats,
                                           "maks_mb": settings.MAX_UPLOAD_SIZE_MB}, status=status)


@app.get("/unggah", response_class=HTMLResponse)
def unggah(request: Request, pengguna: Pengguna = Depends(wajib_peran("staf")), db: Session = Depends(ambil_db)):
    return _layar_unggah(request, pengguna, db)


@app.post("/unggah", response_class=HTMLResponse)
def kirim_unggah(request: Request, berkas: UploadFile = File(None), csrf: str = Form(""),
                 pengguna: Pengguna = Depends(wajib_peran("staf")), db: Session = Depends(ambil_db)):
    periksa_csrf(request, csrf, pengguna.csrf)
    if berkas is None or not berkas.filename:
        return _layar_unggah(request, pengguna, db, "Pilih berkas Excel (.xlsx) atau CSV terlebih dahulu.", 400)
    batas = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    isi = berkas.file.read(batas + 1)
    if len(isi) > batas:
        return _layar_unggah(request, pengguna, db, f"Berkas lebih besar dari {settings.MAX_UPLOAD_SIZE_MB} MB. "
                             "Pisahkan per tahun lalu unggah satu per satu.", 413)
    hasil, pesan = simpan_upload(db, pengguna.tenant_id, pengguna.id, isi, berkas.filename,
                                 pemetaan_lembaga=daftar_pemetaan(db, pengguna.tenant_id))
    if hasil is None:
        return _layar_unggah(request, pengguna, db, pesan, 400)
    return RedirectResponse(f"/analisis/{hasil.id}", status_code=303)


@app.post("/unggah/contoh")
def muat_contoh(request: Request, csrf: str = Form(""), pengguna: Pengguna = Depends(wajib_peran("staf")),
                db: Session = Depends(ambil_db)):
    periksa_csrf(request, csrf, pengguna.csrf)
    from src.sample_data import generate_sample_data
    df_h, df_s = generate_sample_data(2000, 500)  # sama dengan tombol data contoh di aplikasi Streamlit
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_h.to_excel(w, sheet_name="Penghimpunan", index=False)
        df_s.to_excel(w, sheet_name="Penyaluran", index=False)
    hasil, pesan = simpan_upload(db, pengguna.tenant_id, pengguna.id, buf.getvalue(), "data_contoh_zis_3tahun.xlsx")
    if hasil is None:
        return _layar_unggah(request, pengguna, db, pesan, 400)
    return RedirectResponse(f"/analisis/{hasil.id}", status_code=303)


# ---------------------------------------------------------------------------
# Segera hadir
# ---------------------------------------------------------------------------
SEGERA = [
    ("Tim dan undangan", "Undang anggota, ubah peran admin, staf, dan pembaca."),
    ("Jejak audit", "Siapa masuk, mengunggah, dan menghapus apa, kapan."),
    ("Paket dan kuota", "Batas berkas, penyimpanan, dan anggota per paket."),
    ("Profil dan kata sandi", "Ganti nama, ganti sandi, keluar dari semua perangkat."),
    ("Daftar lembaga baru", "Pendaftaran lembaga dan verifikasi email."),
    ("Atur ulang kata sandi", "Tautan atur ulang lewat email."),
    ("Kelola lembaga (super admin)", "Daftar semua lembaga, ubah paket, nonaktifkan."),
    ("Pemetaan kolom", "Mencocokkan kolom berkas yang formatnya tidak dikenali otomatis."),
    ("Muzaki, penyaluran, dan ekspor laporan", "Segmentasi RFM, penyaluran per program, PDF dan Excel."),
]


@app.get("/segera-hadir", response_class=HTMLResponse)
def segera_hadir(request: Request, pengguna: Pengguna = Depends(wajib_masuk)):
    return tampil(request, "segera.html", {"pengguna": pengguna, "aktif": "segera", "daftar": SEGERA})
