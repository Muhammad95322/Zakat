"""Lapisan penyimpanan berkas unggahan dengan satu antarmuka: simpan / baca / hapus (+ hapus_awalan, daftar).

Implementasi:
- ``PenyimpananLokal``: folder UPLOAD_DIR (development, Docker Compose, atau Render Disk).
- ``PenyimpananS3``: penyimpanan objek kompatibel S3 (AWS S3, Cloudflare R2, Backblaze B2, MinIO, dll.).
  Dipakai di produksi Render karena disk kontainer Render bersifat sementara (lihat docs/PANDUAN_DEPLOY.md).

Kunci objek selalu relatif, mis. ``<tenant_id>/<upload_id>.xlsx``, dan divalidasi ketat (tanpa ``..``,
tanpa awalan ``/``) agar tidak bisa keluar dari folder/awalan lembaga.
"""
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from src.config import settings

_RE_KUNCI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$")


class GalatPenyimpanan(RuntimeError):
    """Gagal membaca/menulis penyimpanan (pesan aman ditampilkan, tanpa detail kredensial)."""


def validasi_kunci(kunci: str) -> str:
    if not kunci or len(kunci) > 400 or ".." in kunci or not _RE_KUNCI.match(kunci):
        raise ValueError(f"Kunci penyimpanan tidak valid: {kunci!r}")
    return kunci


def validasi_awalan(awalan: str) -> str:
    awalan = awalan.rstrip("/")
    validasi_kunci(awalan)
    return awalan + "/"


def kunci_unggahan(tenant_id: str, upload_id: str, ext: str) -> str:
    return validasi_kunci(f"{tenant_id}/{upload_id}.{ext.lstrip('.').lower()}")


class Penyimpanan(ABC):
    nama: str = "abstrak"

    @abstractmethod
    def simpan(self, kunci: str, data: bytes) -> None: ...

    @abstractmethod
    def baca(self, kunci: str) -> bytes:
        """Raises FileNotFoundError bila tidak ada."""

    @abstractmethod
    def hapus(self, kunci: str) -> bool:
        """True bila objek ada dan dihapus. Tidak error bila sudah tidak ada."""

    @abstractmethod
    def daftar(self, awalan: str = "") -> List[str]: ...

    def ada(self, kunci: str) -> bool:
        try:
            self.baca(kunci)
            return True
        except FileNotFoundError:
            return False

    def hapus_awalan(self, awalan: str) -> int:
        """Hapus semua objek dengan awalan (mis. semua berkas satu lembaga). Mengembalikan jumlahnya."""
        n = 0
        for k in self.daftar(validasi_awalan(awalan)):
            n += self.hapus(k)
        return n

    def periksa(self) -> str:
        """Pemeriksaan kesehatan ringan; kembalikan keterangan, lempar GalatPenyimpanan bila gagal."""
        return self.nama


class PenyimpananLokal(Penyimpanan):
    nama = "lokal"

    def __init__(self, akar: Path):
        self.akar = Path(akar)

    def _path(self, kunci: str) -> Path:
        p = (self.akar / validasi_kunci(kunci)).resolve()
        if self.akar.resolve() not in p.parents:
            raise ValueError("Kunci keluar dari folder penyimpanan.")
        return p

    def simpan(self, kunci: str, data: bytes) -> None:
        p = self._path(kunci)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".sementara")
        tmp.write_bytes(data)
        tmp.replace(p)  # atomik: tidak ada berkas setengah jadi bila proses terhenti

    def baca(self, kunci: str) -> bytes:
        p = self._path(kunci)
        if not p.is_file():
            raise FileNotFoundError(kunci)
        return p.read_bytes()

    def hapus(self, kunci: str) -> bool:
        p = self._path(kunci)
        if p.is_file():
            p.unlink()
            return True
        return False

    def daftar(self, awalan: str = "") -> List[str]:
        if not self.akar.exists():
            return []
        akar = self.akar.resolve()
        hasil = []
        for p in akar.rglob("*"):
            if p.is_file() and not p.name.endswith(".sementara"):
                k = p.relative_to(akar).as_posix()
                if k.startswith(awalan):
                    hasil.append(k)
        return sorted(hasil)

    def hapus_awalan(self, awalan: str) -> int:
        n = super().hapus_awalan(awalan)
        folder = self.akar / validasi_awalan(awalan).rstrip("/")
        if folder.is_dir() and not any(folder.rglob("*")):
            folder.rmdir()
        return n

    def periksa(self) -> str:
        self.akar.mkdir(parents=True, exist_ok=True)
        uji = self.akar / ".periksa_tulis"
        try:
            uji.write_bytes(b"ok")
            uji.unlink()
        except OSError as e:
            raise GalatPenyimpanan(f"folder unggahan tidak dapat ditulis ({type(e).__name__})")
        return f"lokal ({self.akar})"


class PenyimpananS3(Penyimpanan):
    nama = "s3"

    def __init__(self, bucket: str, awalan: str = "", client=None, sse: str = ""):
        self.bucket = bucket
        self.awalan = (awalan.strip("/") + "/") if awalan.strip("/") else ""
        self.sse = sse
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                region_name=settings.S3_REGION or None,
                aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
                aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
                config=Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 3, "mode": "standard"},
                              signature_version="s3v4"),
            )
        return self._client

    def _k(self, kunci: str) -> str:
        return self.awalan + validasi_kunci(kunci)

    def _galat(self, e: Exception, aksi: str) -> GalatPenyimpanan:
        kode = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
        return GalatPenyimpanan(f"penyimpanan objek gagal saat {aksi} ({kode})")

    def simpan(self, kunci: str, data: bytes) -> None:
        extra = {"ServerSideEncryption": self.sse} if self.sse else {}
        k = self._k(kunci)  # validasi di luar try: kunci berbahaya -> ValueError, sama seperti lokal
        try:
            self.client.put_object(Bucket=self.bucket, Key=k, Body=data,
                                   ContentType="application/octet-stream", **extra)
        except Exception as e:
            raise self._galat(e, "menyimpan") from None

    def baca(self, kunci: str) -> bytes:
        k = self._k(kunci)
        try:
            r = self.client.get_object(Bucket=self.bucket, Key=k)
            return r["Body"].read()
        except Exception as e:
            kode = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if kode in ("NoSuchKey", "404", "NotFound"):
                raise FileNotFoundError(kunci) from None
            raise self._galat(e, "membaca") from None

    def hapus(self, kunci: str) -> bool:
        k = self._k(kunci)
        try:
            ada = True
            try:
                self.client.head_object(Bucket=self.bucket, Key=k)
            except Exception as e:
                if getattr(e, "response", {}).get("Error", {}).get("Code", "") in ("404", "NoSuchKey", "NotFound"):
                    ada = False
                else:
                    raise
            if ada:
                self.client.delete_object(Bucket=self.bucket, Key=k)
            return ada
        except GalatPenyimpanan:
            raise
        except Exception as e:
            raise self._galat(e, "menghapus") from None

    def daftar(self, awalan: str = "") -> List[str]:
        hasil: List[str] = []
        token: Optional[str] = None
        if awalan:
            validasi_awalan(awalan)
        try:
            while True:
                arg = {"Bucket": self.bucket, "Prefix": self.awalan + awalan}
                if token:
                    arg["ContinuationToken"] = token
                r = self.client.list_objects_v2(**arg)
                hasil += [o["Key"][len(self.awalan):] for o in r.get("Contents", [])]
                if not r.get("IsTruncated"):
                    break
                token = r.get("NextContinuationToken")
        except Exception as e:
            raise self._galat(e, "mendaftar") from None
        return hasil

    def periksa(self) -> str:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception as e:
            raise self._galat(e, "memeriksa bucket") from None
        return f"s3 (bucket {self.bucket})"


_aktif: Optional[Penyimpanan] = None


def penyimpanan() -> Penyimpanan:
    """Penyimpanan sesuai PENYIMPANAN (lokal | s3). Di-cache per proses; ``atur_penyimpanan`` untuk tes."""
    global _aktif
    jenis = settings.PENYIMPANAN
    if _aktif is not None and (_aktif.nama == jenis and (jenis != "lokal"
                                                        or Path(_aktif.akar) == Path(settings.UPLOAD_DIR))):
        return _aktif
    if jenis == "s3":
        _aktif = PenyimpananS3(settings.S3_BUCKET, settings.S3_AWALAN, sse=settings.S3_SSE)
    elif jenis == "lokal":
        _aktif = PenyimpananLokal(settings.UPLOAD_DIR)
    else:
        raise ValueError("PENYIMPANAN harus 'lokal' atau 's3'.")
    return _aktif


def atur_penyimpanan(p: Optional[Penyimpanan]) -> None:
    global _aktif
    _aktif = p


def kunci_dari_storage_path(storage_path: str) -> str:
    """Upload lama menyimpan path absolut di UPLOAD_DIR; yang baru menyimpan kunci relatif."""
    p = Path(storage_path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(Path(settings.UPLOAD_DIR).resolve()).as_posix()
        except ValueError:
            return p.name
    return storage_path
