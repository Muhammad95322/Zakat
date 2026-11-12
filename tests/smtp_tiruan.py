"""Server SMTP tiruan (hanya untuk tes, hanya mendengar di 127.0.0.1) dengan STARTTLS/TLS & sertifikat buatan."""
import base64
import datetime as _dt
import socket
import socketserver
import ssl
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


def buat_sertifikat(folder: Path) -> tuple:
    """Sertifikat CA uji + sertifikat server untuk 'localhost'/127.0.0.1. Kembalikan (ca, cert, key)."""
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    sekarang = _dt.datetime.now(_dt.timezone.utc)
    k_ca = ec.generate_private_key(ec.SECP256R1())
    nama_ca = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA Uji Zakat Insight")])
    ca = (x509.CertificateBuilder().subject_name(nama_ca).issuer_name(nama_ca).public_key(k_ca.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(sekarang - _dt.timedelta(minutes=5))
          .not_valid_after(sekarang + _dt.timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                       content_commitment=False, key_encipherment=False, data_encipherment=False,
                                       key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(k_ca.public_key()), critical=False)
          .sign(k_ca, hashes.SHA256()))
    k_srv = ec.generate_private_key(ec.SECP256R1())
    srv = (x509.CertificateBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
           .issuer_name(nama_ca).public_key(k_srv.public_key()).serial_number(x509.random_serial_number())
           .not_valid_before(sekarang - _dt.timedelta(minutes=5)).not_valid_after(sekarang + _dt.timedelta(days=1))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                       x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                          critical=False)
           .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(k_ca.public_key()), critical=False)
           .add_extension(x509.SubjectKeyIdentifier.from_public_key(k_srv.public_key()), critical=False)
           .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
           .sign(k_ca, hashes.SHA256()))
    folder.mkdir(parents=True, exist_ok=True)
    p_ca, p_crt, p_key = folder / "ca.pem", folder / "srv.pem", folder / "srv.key"
    p_ca.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    p_crt.write_bytes(srv.public_bytes(serialization.Encoding.PEM))
    p_key.write_bytes(k_srv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
    return p_ca, p_crt, p_key


@dataclass
class Catatan:
    pesan: List[bytes] = field(default_factory=list)
    perintah: List[tuple] = field(default_factory=list)   # (perintah, sudah_tls)
    login: List[tuple] = field(default_factory=list)      # (user, sandi, sudah_tls)


class ServerSMTPTiruan:
    """mode: 'starttls' | 'ssl' | 'tanpa_tls' (tidak menawarkan STARTTLS) | 'diam' (tidak pernah menjawab)."""

    def __init__(self, cert: Path, key: Path, mode: str = "starttls", user: str = "uji", sandi: str = "rahasia"):
        self.mode, self.user, self.sandi = mode, user, sandi
        self.catatan = Catatan()
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(str(cert), str(key))
        induk = self

        class Penangan(socketserver.StreamRequestHandler):
            def handle(self):
                try:
                    induk._layani(self)
                except (OSError, ssl.SSLError, ValueError):
                    pass  # klien memutus/menolak TLS: memang skenario yang diuji

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

            def get_request(self):
                sock, addr = super().get_request()
                if induk.mode == "ssl":
                    sock = induk.ctx.wrap_socket(sock, server_side=True)
                return sock, addr

        self.server = Server(("127.0.0.1", 0), Penangan)
        self.port = self.server.server_address[1]
        self._t = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()

    # --- protokol minimal ---
    def _layani(self, h):
        if self.mode == "diam":
            try:
                h.request.settimeout(10)
                h.request.recv(1)
            except Exception:
                pass
            return
        sock = h.request
        tls = self.mode == "ssl"
        f = sock.makefile("rwb")

        def kirim(baris: str):
            f.write((baris + "\r\n").encode())
            f.flush()

        kirim("220 smtp-tiruan siap")
        while True:
            baris = f.readline()
            if not baris:
                return
            cmd = baris.decode(errors="replace").strip()
            atas = cmd.upper()
            self.catatan.perintah.append((atas.split(" ")[0], tls))
            if atas.startswith(("EHLO", "HELO")):
                fitur = ["250-smtp-tiruan"]
                if self.mode == "starttls" and not tls:
                    fitur.append("250-STARTTLS")
                fitur.append("250 AUTH PLAIN LOGIN")
                for x in fitur:
                    kirim(x)
            elif atas == "STARTTLS" and self.mode == "starttls" and not tls:
                kirim("220 mulai TLS")
                f.close()
                sock = self.ctx.wrap_socket(sock, server_side=True)
                f = sock.makefile("rwb")
                tls = True
            elif atas.startswith("AUTH PLAIN"):
                bagian = cmd.split(" ", 2)
                data = base64.b64decode(bagian[2]) if len(bagian) > 2 else b""
                _, u, p = (data.split(b"\0") + [b"", b"", b""])[:3]
                self.catatan.login.append((u.decode(), p.decode(), tls))
                kirim("235 ok" if (u.decode(), p.decode()) == (self.user, self.sandi) else "535 ditolak")
            elif atas.startswith("AUTH LOGIN"):
                kirim("334 VXNlcm5hbWU6")
                u = base64.b64decode(f.readline().strip()).decode()
                kirim("334 UGFzc3dvcmQ6")
                p = base64.b64decode(f.readline().strip()).decode()
                self.catatan.login.append((u, p, tls))
                kirim("235 ok" if (u, p) == (self.user, self.sandi) else "535 ditolak")
            elif atas.startswith(("MAIL FROM", "RCPT TO", "RSET", "NOOP")):
                kirim("250 ok")
            elif atas == "DATA":
                kirim("354 lanjut")
                isi = []
                while True:
                    b = f.readline()
                    if b in (b".\r\n", b".\n", b""):
                        break
                    isi.append(b)
                self.catatan.pesan.append(b"".join(isi))
                kirim("250 diterima")
            elif atas == "QUIT":
                kirim("221 sampai jumpa")
                return
            else:
                kirim("502 tidak dikenal")


def port_tertutup() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p
