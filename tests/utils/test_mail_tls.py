"""SMTP over TLS verifies the server's certificate.

``smtplib.SMTP_SSL`` and ``starttls()`` given no context use an unverified
one, so any certificate was accepted and the SMTP password went to whoever
answered.  These tests run a small TLS SMTP server with a self-signed
certificate on localhost.
"""

from __future__ import annotations

import datetime
import socket
import ssl
import threading

import pytest

from execsql.exceptions import ErrInfo


def _self_signed(tmp_path):
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    return cert_file, key_file


class _TlsSmtpServer:
    """Answers just enough SMTP over implicit TLS for Mailer to connect and quit."""

    def __init__(self, cert_file, key_file):
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(cert_file, key_file)
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            try:
                with self.ctx.wrap_socket(conn, server_side=True) as tls:
                    tls.sendall(b"220 localhost ESMTP test\r\n")
                    f = tls.makefile("rb")
                    for line in f:
                        if line.upper().startswith(b"QUIT"):
                            tls.sendall(b"221 bye\r\n")
                            break
                        tls.sendall(b"250 localhost\r\n")
            except (ssl.SSLError, OSError):
                continue  # the client refused the certificate

    def close(self):
        self.sock.close()


@pytest.fixture
def tls_server(tmp_path):
    cert_file, key_file = _self_signed(tmp_path)
    server = _TlsSmtpServer(cert_file, key_file)
    yield server, cert_file
    server.close()


@pytest.fixture
def email_conf(minimal_conf, tls_server):
    server, _ = tls_server
    minimal_conf.smtp_host = "localhost"
    minimal_conf.smtp_port = server.port
    minimal_conf.smtp_ssl = True
    minimal_conf.smtp_tls = False
    minimal_conf.smtp_username = None
    minimal_conf.smtp_password = None
    minimal_conf.smtp_verify_certificate = True
    minimal_conf.smtp_ca_file = None
    return minimal_conf


def test_self_signed_certificate_is_refused(email_conf):
    from execsql.utils.mail import Mailer

    with pytest.raises(ErrInfo) as exc_info:
        Mailer()
    msg = exc_info.value.errmsg()
    assert "certificate" in msg.lower()
    assert "ca_file" in msg and "verify_certificate" in msg


def test_ca_file_trusts_an_internal_certificate(email_conf, tls_server):
    from execsql.utils.mail import Mailer

    _, cert_file = tls_server
    email_conf.smtp_ca_file = str(cert_file)
    with Mailer():
        pass


def test_verification_can_be_turned_off(email_conf):
    from execsql.utils.mail import Mailer

    email_conf.smtp_verify_certificate = False
    with Mailer():
        pass


def test_starttls_gets_a_verifying_context(minimal_conf, monkeypatch):
    """STARTTLS is upgraded with the same verifying context as implicit TLS."""
    import smtplib

    from execsql.utils.mail import Mailer

    seen = {}

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def ehlo_or_helo_if_needed(self):
            pass

        def starttls(self, context=None):
            seen["context"] = context

        def ehlo(self, name=None):
            pass

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    minimal_conf.smtp_host = "mail.example.com"
    minimal_conf.smtp_port = 587
    minimal_conf.smtp_ssl = False
    minimal_conf.smtp_tls = True
    minimal_conf.smtp_username = None
    minimal_conf.smtp_verify_certificate = True
    minimal_conf.smtp_ca_file = None
    with Mailer():
        pass
    ctx = seen["context"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_config_reads_the_tls_settings(tmp_path):
    from execsql.config import ConfigData
    from execsql.script.variables import SubVarSet

    (tmp_path / "execsql.conf").write_text("[email]\nverify_certificate = No\nca_file = /etc/ssl/corp-ca.pem\n")
    conf = ConfigData(str(tmp_path), SubVarSet(), config_file=str(tmp_path / "execsql.conf"))
    assert conf.smtp_verify_certificate is False
    assert conf.smtp_ca_file == "/etc/ssl/corp-ca.pem"


def test_verification_is_on_by_default(tmp_path):
    from execsql.config import ConfigData
    from execsql.script.variables import SubVarSet

    conf = ConfigData(str(tmp_path), SubVarSet())
    assert conf.smtp_verify_certificate is True
    assert conf.smtp_ca_file is None
