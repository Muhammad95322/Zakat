"""Uji Validasi File, Keamanan Path Traversal, dan Rate Limiter."""
import pytest
from src.middleware.security import validasi_file_upload, sanitasi_nama_file, sanitasi_input
from src.middleware.rate_limiter import RateLimiter

class TestSecurityAndValidation:
    def test_file_format_tidak_diizinkan(self):
        konten = b"MZ\x90\x00exe_file"
        ok, msg = validasi_file_upload("malware.exe", konten)
        assert ok is False
        assert "tidak didukung" in msg

    def test_file_melebihi_ukuran_maksimal(self):
        konten = b"a" * (55 * 1024 * 1024) # 55 MB
        ok, msg = validasi_file_upload("laporan.xlsx", konten)
        assert ok is False
        assert "melebihi batas" in msg

    def test_path_traversal_sanitasi(self):
        bahaya = "../../etc/passwd"
        bersih = sanitasi_nama_file(bahaya)
        assert ".." not in bersih
        assert "/" not in bersih
        assert "\\" not in bersih

    def test_sanitasi_input(self):
        kotor = "  Halo \x00 Dunia!  "
        assert sanitasi_input(kotor) == "Halo  Dunia!"

    def test_rate_limiter_lockout(self):
        limiter = RateLimiter()
        key = "test_ip_123"
        limiter.reset(key)
        
        # 4 kali gagal -> masih diizinkan
        for _ in range(4):
            limiter.record_failure(key)
        allowed, _ = limiter.check_rate_limit(key, max_attempts=5, window_seconds=60)
        assert allowed is True
        
        # Percobaan ke-5 -> lockout
        limiter.record_failure(key)
        allowed, wait = limiter.check_rate_limit(key, max_attempts=5, window_seconds=60)
        assert allowed is False
        assert wait > 0

