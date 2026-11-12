"""Lapisan penyimpanan: kontrak sama untuk lokal & S3, parameter permintaan S3 (Stubber), dan integrasi
dengan unggah, hapus, hapus lembaga, retensi. Tanpa jaringan."""
import io
import uuid
from datetime import timedelta

import pandas as pd
import pytest
from botocore.exceptions import ClientError

from src.config import settings
from src.models.upload import Upload
from src.penyimpanan import (
    GalatPenyimpanan, PenyimpananLokal, PenyimpananS3, atur_penyimpanan, kunci_dari_storage_path, kunci_unggahan,
    validasi_kunci,
)
from src.waktu import utc_now


class KlienS3Tiruan:
    """Klien S3 di memori yang meniru galat botocore (NoSuchKey/404) dan paginasi list_objects_v2."""

    def __init__(self, halaman=2):
        self.objek, self.panggilan, self.halaman = {}, [], halaman

    def _galat(self, kode, op):
        return ClientError({"Error": {"Code": kode, "Message": "x"}}, op)

    def put_object(self, Bucket, Key, Body, **kw):
        self.panggilan.append(("put", Key, kw))
        self.objek[Key] = bytes(Body)

    def get_object(self, Bucket, Key):
        if Key not in self.objek:
            raise self._galat("NoSuchKey", "GetObject")
        return {"Body": io.BytesIO(self.objek[Key])}

    def head_object(self, Bucket, Key):
        if Key not in self.objek:
            raise self._galat("404", "HeadObject")
        return {}

    def delete_object(self, Bucket, Key):
        self.objek.pop(Key, None)

    def head_bucket(self, Bucket):
        return {}

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        kunci = sorted(k for k in self.objek if k.startswith(Prefix))
        mulai = int(ContinuationToken or 0)
        bagian = kunci[mulai:mulai + self.halaman]
        r = {"Contents": [{"Key": k} for k in bagian], "IsTruncated": mulai + self.halaman < len(kunci)}
        if r["IsTruncated"]:
            r["NextContinuationToken"] = str(mulai + self.halaman)
        return r


@pytest.fixture(params=["lokal", "s3"])
def store(request, tmp_path):
    if request.param == "lokal":
        return PenyimpananLokal(tmp_path / "unggahan")
    return PenyimpananS3("bucket-uji", "unggahan", client=KlienS3Tiruan())


# ---------------------------------------------------------------------------
# Kontrak antarmuka (sama untuk lokal & S3)
# ---------------------------------------------------------------------------
def test_simpan_baca_hapus(store):
    store.simpan("t1/a.xlsx", b"isi-a")
    assert store.baca("t1/a.xlsx") == b"isi-a" and store.ada("t1/a.xlsx")
    store.simpan("t1/a.xlsx", b"isi-baru")  # timpa
    assert store.baca("t1/a.xlsx") == b"isi-baru"
    assert store.hapus("t1/a.xlsx") is True
    assert store.hapus("t1/a.xlsx") is False
    with pytest.raises(FileNotFoundError):
        store.baca("t1/a.xlsx")


def test_daftar_dan_hapus_awalan_hanya_lembaga_itu(store):
    for k in ("t1/a.xlsx", "t1/b.csv", "t1/c.xlsx", "t2/a.xlsx", "t10/a.xlsx"):
        store.simpan(k, b"x")
    assert store.daftar("t1/") == ["t1/a.xlsx", "t1/b.csv", "t1/c.xlsx"]  # lintas halaman (S3: 2 per halaman)
    assert store.hapus_awalan("t1") == 3
    assert sorted(store.daftar("")) == ["t10/a.xlsx", "t2/a.xlsx"]  # 't10' tidak ikut walau berawalan 't1'


@pytest.mark.parametrize("kunci", ["../luar.xlsx", "/etc/passwd", "t1/../../x", "t1//a", "", "t1/.tersembunyi",
                                   "t1/a b.xlsx", "a\\b"])
def test_kunci_berbahaya_ditolak(store, kunci):
    with pytest.raises(ValueError):
        store.simpan(kunci, b"x")


def test_kunci_unggahan():
    assert kunci_unggahan("tid", "uid", ".XLSX") == "tid/uid.xlsx"
    assert validasi_kunci("a/b-1_2.csv") == "a/b-1_2.csv"


def test_lokal_tidak_ada_berkas_sementara_tersisa(tmp_path):
    s = PenyimpananLokal(tmp_path)
    s.simpan("t/a.xlsx", b"x")
    assert sorted(p.name for p in (tmp_path / "t").iterdir()) == ["a.xlsx"]


# ---------------------------------------------------------------------------
# S3: parameter permintaan nyata (botocore Stubber, tanpa jaringan) & galat
# ---------------------------------------------------------------------------
def _klien_boto():
    import boto3
    return boto3.client("s3", region_name="ap-southeast-3", aws_access_key_id="AKIAUJI",
                        aws_secret_access_key="rahasia-uji")


def test_s3_parameter_put_get_list_dengan_stubber():
    from botocore.response import StreamingBody
    from botocore.stub import Stubber
    c = _klien_boto()
    s = PenyimpananS3("zakat-unggahan", "unggahan", client=c, sse="AES256")
    with Stubber(c) as st:
        st.add_response("put_object", {}, {"Bucket": "zakat-unggahan", "Key": "unggahan/t1/a.xlsx", "Body": b"isi",
                                           "ContentType": "application/octet-stream",
                                           "ServerSideEncryption": "AES256"})
        st.add_response("get_object", {"Body": StreamingBody(io.BytesIO(b"isi"), 3)},
                        {"Bucket": "zakat-unggahan", "Key": "unggahan/t1/a.xlsx"})
        st.add_client_error("get_object", "NoSuchKey", http_status_code=404,
                            expected_params={"Bucket": "zakat-unggahan", "Key": "unggahan/t1/b.xlsx"})
        st.add_response("list_objects_v2", {"Contents": [{"Key": "unggahan/t1/a.xlsx"}], "IsTruncated": True,
                                            "NextContinuationToken": "tok"},
                        {"Bucket": "zakat-unggahan", "Prefix": "unggahan/t1/"})
        st.add_response("list_objects_v2", {"Contents": [{"Key": "unggahan/t1/c.xlsx"}], "IsTruncated": False},
                        {"Bucket": "zakat-unggahan", "Prefix": "unggahan/t1/", "ContinuationToken": "tok"})
        s.simpan("t1/a.xlsx", b"isi")
        assert s.baca("t1/a.xlsx") == b"isi"
        with pytest.raises(FileNotFoundError):
            s.baca("t1/b.xlsx")
        assert s.daftar("t1/") == ["t1/a.xlsx", "t1/c.xlsx"]
        st.assert_no_pending_responses()


def test_s3_galat_tanpa_kredensial_di_pesan():
    from botocore.stub import Stubber
    c = _klien_boto()
    s = PenyimpananS3("b", client=c)
    with Stubber(c) as st:
        st.add_client_error("put_object", "AccessDenied", http_status_code=403)
        st.add_client_error("head_bucket", "NoSuchBucket", http_status_code=404)
        with pytest.raises(GalatPenyimpanan) as e:
            s.simpan("t/a.xlsx", b"x")
        assert "AccessDenied" in str(e.value) and "rahasia-uji" not in str(e.value) and "AKIA" not in str(e.value)
        with pytest.raises(GalatPenyimpanan):
            s.periksa()


# ---------------------------------------------------------------------------
# Integrasi: unggah / baca / hapus / hapus lembaga / retensi memakai penyimpanan aktif
# ---------------------------------------------------------------------------
@pytest.fixture
def s3_aktif(monkeypatch):
    klien = KlienS3Tiruan(halaman=1000)
    monkeypatch.setattr(settings, "PENYIMPANAN", "s3")
    st = PenyimpananS3("bucket-uji", "unggahan", client=klien)
    atur_penyimpanan(st)
    yield st, klien
    atur_penyimpanan(None)


def _xlsx():
    df = pd.DataFrame({"tanggal": ["2024-01-05", "2024-02-05"], "jumlah": [100000, 200000]})
    b = io.BytesIO()
    df.to_excel(b, sheet_name="Penghimpunan", index=False)
    return b.getvalue()


def test_unggah_baca_hapus_lewat_s3(db, sample_tenant, admin_user, s3_aktif):
    from src.services.upload_service import baca_berkas_unggahan, hapus_upload, simpan_upload
    st, klien = s3_aktif
    up, msg = simpan_upload(db, sample_tenant.id, admin_user.id, _xlsx(), "data.xlsx")
    assert up is not None, msg
    assert up.storage_path == f"{sample_tenant.id}/{up.id}.xlsx"
    assert f"unggahan/{up.storage_path}" in klien.objek
    assert baca_berkas_unggahan(up) == _xlsx()
    assert hapus_upload(db, up.id, sample_tenant.id, admin_user.id)
    assert klien.objek == {}


def test_hapus_lembaga_menghapus_semua_berkasnya_di_s3(db, sample_tenant, sample_tenant_2, admin_user, s3_aktif):
    from src.services import data_pribadi as dp
    st, klien = s3_aktif
    st.simpan(f"{sample_tenant.id}/a.xlsx", b"x")
    st.simpan(f"{sample_tenant.id}/b.csv", b"x")
    st.simpan(f"{sample_tenant_2.id}/c.xlsx", b"x")
    hasil = dp.hapus_lembaga(db, sample_tenant.id, {"id": None, "peran": "super_admin"}, sample_tenant.slug)
    assert hasil["berkas"] == 2
    assert st.daftar("") == [f"{sample_tenant_2.id}/c.xlsx"]


def test_retensi_berkas_yatim_dan_umur_unggahan(db, sample_tenant, admin_user, s3_aktif, monkeypatch):
    from src.services import data_pribadi as dp
    st, klien = s3_aktif
    st.simpan(f"{uuid.uuid4()}/yatim.xlsx", b"x")  # lembaga sudah tidak ada
    lama = Upload(id=str(uuid.uuid4()), tenant_id=sample_tenant.id, user_id=admin_user.id, nama_file_asli="l.xlsx",
                  storage_path=f"{sample_tenant.id}/lama.xlsx", status="siap", created_at=utc_now() - timedelta(days=400))
    baru = Upload(id=str(uuid.uuid4()), tenant_id=sample_tenant.id, user_id=admin_user.id, nama_file_asli="b.xlsx",
                  storage_path=f"{sample_tenant.id}/baru.xlsx", status="siap")
    db.add_all([lama, baru])
    db.commit()
    st.simpan(lama.storage_path, b"x")
    st.simpan(baru.storage_path, b"x")
    monkeypatch.setattr(settings, "RETENSI_UNGGAHAN_HARI", 365)
    hasil = dp.bersihkan_retensi(db)
    assert hasil["berkas_yatim"] >= 1 and hasil["unggahan_kedaluwarsa"] == 1
    assert sorted(st.daftar(f"{sample_tenant.id}/")) == [baru.storage_path]
    assert db.query(Upload).filter(Upload.id == lama.id).count() == 0


def test_retensi_bawaan_tidak_menghapus_unggahan(db, sample_tenant, admin_user, s3_aktif):
    from src.services import data_pribadi as dp
    st, _ = s3_aktif
    up = Upload(id=str(uuid.uuid4()), tenant_id=sample_tenant.id, user_id=admin_user.id, nama_file_asli="l.xlsx",
                storage_path=f"{sample_tenant.id}/x.xlsx", status="siap", created_at=utc_now() - timedelta(days=4000))
    db.add(up)
    db.commit()
    st.simpan(up.storage_path, b"x")
    assert settings.RETENSI_UNGGAHAN_HARI == 0
    dp.bersihkan_retensi(db)
    assert st.ada(up.storage_path)


def test_path_lama_absolut_tetap_terbaca(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(settings, "PENYIMPANAN", "lokal")
    atur_penyimpanan(None)
    (tmp_path / "t1").mkdir()
    (tmp_path / "t1" / "a.xlsx").write_bytes(b"lama")
    assert kunci_dari_storage_path(str(tmp_path / "t1" / "a.xlsx")) == "t1/a.xlsx"
    from src.services.upload_service import baca_berkas_unggahan
    assert baca_berkas_unggahan(Upload(storage_path=str(tmp_path / "t1" / "a.xlsx"))) == b"lama"
    atur_penyimpanan(None)
