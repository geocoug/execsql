"""
Tests for execsql.utils.mail — MailSpec construction and Mailer config validation.

Mailer.__init__ establishes an SMTP connection.  Configuration tests mock
smtplib (always with a spec, so an assertion cannot name a method smtplib
does not have); the round-trip tests drive Mailer against a real in-process
SMTP server on loopback.  MailSpec is a pure data class needing no mocking.
"""

from __future__ import annotations

import base64
import smtplib
import socket
import socketserver
import threading
from typing import cast
from unittest.mock import create_autospec, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.utils.mail import Mailer, MailSpec

# Captured before any @patch("smtplib.SMTP") swaps the real class for a mock —
# create_autospec() cannot spec a Mock, and a spec'd connection is the whole
# point: it rejects an assertion naming a method smtplib does not have.
_REAL_SMTP = smtplib.SMTP
_REAL_SMTP_SSL = smtplib.SMTP_SSL


# ---------------------------------------------------------------------------
# MailSpec — construction and attributes
# ---------------------------------------------------------------------------


class TestMailSpec:
    def test_basic_construction(self):
        ms = MailSpec(
            send_from="a@b.com",
            send_to="c@d.com",
            subject="Test",
            msg_content="Hello",
        )
        assert ms.send_from == "a@b.com"
        assert ms.send_to == "c@d.com"
        assert ms.subject == "Test"
        assert ms.msg_content == "Hello"
        assert ms.content_filename is None
        assert ms.attach_filename is None
        assert ms.repeatable is False
        assert ms.sent is False

    def test_optional_fields(self):
        ms = MailSpec(
            send_from="a@b.com",
            send_to="c@d.com",
            subject="Sub",
            msg_content=None,
            content_filename="/tmp/body.txt",
            attach_filename="/tmp/file.zip",
            repeatable=True,
        )
        assert ms.content_filename == "/tmp/body.txt"
        assert ms.attach_filename == "/tmp/file.zip"
        assert ms.repeatable is True

    def test_none_msg_content(self):
        ms = MailSpec(
            send_from="a@b.com",
            send_to="c@d.com",
            subject="Sub",
            msg_content=None,
        )
        assert ms.msg_content is None


# ---------------------------------------------------------------------------
# Mailer — config validation (mocked SMTP)
# ---------------------------------------------------------------------------


class TestMailerConfigValidation:
    def test_raises_when_smtp_host_not_configured(self, minimal_conf):
        _state.conf.smtp_host = None
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        with pytest.raises(ErrInfo, match="email host is not configured"):
            Mailer()

    @patch("smtplib.SMTP")
    def test_creates_smtp_connection(self, mock_smtp_cls, minimal_conf):
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_smtp_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        m = Mailer()
        mock_smtp_cls.assert_called_once_with("mail.example.com", timeout=30)
        mock_conn.ehlo_or_helo_if_needed.assert_called_once()
        # Clean up to avoid __del__ issues
        del m.smtpconn

    @patch("smtplib.SMTP")
    def test_creates_smtp_connection_with_port(self, mock_smtp_cls, minimal_conf):
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_smtp_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = 587
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        m = Mailer()
        mock_smtp_cls.assert_called_once_with("mail.example.com", 587, timeout=30)
        del m.smtpconn

    @patch("smtplib.SMTP_SSL")
    def test_creates_smtp_ssl_connection(self, mock_smtp_ssl_cls, minimal_conf):
        mock_conn = create_autospec(_REAL_SMTP_SSL, instance=True)
        mock_smtp_ssl_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = True
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        m = Mailer()
        mock_smtp_ssl_cls.assert_called_once_with("mail.example.com", timeout=30)
        del m.smtpconn

    @patch("smtplib.SMTP")
    def test_starttls_called_when_tls_enabled(self, mock_smtp_cls, minimal_conf):
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_smtp_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = True
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        m = Mailer()
        mock_conn.starttls.assert_called_once()
        del m.smtpconn

    @patch("smtplib.SMTP")
    def test_login_called_with_credentials(self, mock_smtp_cls, minimal_conf):
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_smtp_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = "user"
        _state.conf.smtp_password = "pass"
        m = Mailer()
        mock_conn.login.assert_called_once_with("user", "pass")
        del m.smtpconn

    @patch("smtplib.SMTP")
    def test_username_without_password_raises(self, mock_smtp_cls, minimal_conf):
        """smtplib.login() has no single-argument form, so this must be reported, not attempted."""
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_smtp_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = "user"
        _state.conf.smtp_password = None
        with pytest.raises(ErrInfo, match="username is configured but no password"):
            Mailer()
        mock_conn.login.assert_not_called()


# ---------------------------------------------------------------------------
# Mailer.sendmail — message construction (mocked SMTP)
# ---------------------------------------------------------------------------


class TestMailerSendmail:
    @patch("smtplib.SMTP")
    def _make_mailer(self, mock_smtp_cls):
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_smtp_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        m = Mailer()
        return m, mock_conn

    def test_sendmail_plain_text(self, minimal_conf):
        _state.conf.email_format = "text"
        _state.conf.email_css = None
        m, mock_conn = self._make_mailer()
        m.sendmail("from@a.com", "to@b.com", "Subject", "Body text")
        mock_conn.sendmail.assert_called_once()
        args = mock_conn.sendmail.call_args
        assert args[0][0] == "from@a.com"
        assert args[0][1] == ["to@b.com"]
        del m.smtpconn

    def test_sendmail_html_format(self, minimal_conf):
        _state.conf.email_format = "html"
        _state.conf.email_css = "body { color: red; }"
        m, mock_conn = self._make_mailer()
        m.sendmail("from@a.com", "to@b.com", "Subject", "<p>Hello</p>")
        mock_conn.sendmail.assert_called_once()
        msg_str = mock_conn.sendmail.call_args[0][2]
        assert "<style>body { color: red; }</style>" in msg_str
        assert "<p>Hello</p>" in msg_str
        del m.smtpconn

    def test_sendmail_multiple_recipients(self, minimal_conf):
        _state.conf.email_format = "text"
        _state.conf.email_css = None
        m, mock_conn = self._make_mailer()
        m.sendmail("from@a.com", "to@b.com;cc@c.com,dd@d.com", "Sub", "Body")
        args = mock_conn.sendmail.call_args
        assert args[0][1] == ["to@b.com", "cc@c.com", "dd@d.com"]
        del m.smtpconn

    def test_sendmail_with_content_file(self, minimal_conf, tmp_path):
        _state.conf.email_format = "text"
        _state.conf.email_css = None
        content_file = tmp_path / "content.txt"
        content_file.write_text("File content here")
        m, mock_conn = self._make_mailer()
        m.sendmail("from@a.com", "to@b.com", "Sub", "Body", content_filename=str(content_file))
        msg_str = mock_conn.sendmail.call_args[0][2]
        assert "File content here" in msg_str
        del m.smtpconn

    def test_sendmail_with_attachment(self, minimal_conf, tmp_path):
        _state.conf.email_format = "text"
        _state.conf.email_css = None
        attach_file = tmp_path / "data.csv"
        attach_file.write_bytes(b"col1,col2\n1,2\n")
        m, mock_conn = self._make_mailer()
        m.sendmail("from@a.com", "to@b.com", "Sub", "Body", attach_filename=str(attach_file))
        msg_str = mock_conn.sendmail.call_args[0][2]
        assert 'filename="data.csv"' in msg_str
        del m.smtpconn


# ---------------------------------------------------------------------------
# Mailer — context manager protocol
# ---------------------------------------------------------------------------


def _smtp_conf(conf):
    """Add SMTP attributes to a minimal_conf namespace."""
    conf.smtp_host = "localhost"
    conf.smtp_port = None
    conf.smtp_ssl = False
    conf.smtp_tls = False
    conf.smtp_username = None
    conf.smtp_password = None


class TestMailerContextManager:
    @patch("smtplib.SMTP")
    def test_context_manager_returns_mailer_instance(self, mock_smtp_cls, minimal_conf):
        """__enter__ should return the Mailer itself."""
        mock_smtp_cls.return_value = create_autospec(_REAL_SMTP, instance=True)
        _smtp_conf(minimal_conf)
        with Mailer() as m:
            assert isinstance(m, Mailer)

    @patch("smtplib.SMTP")
    def test_context_manager_exit_calls_close(self, mock_smtp_cls, minimal_conf):
        """__exit__ must call close(), which removes smtpconn."""
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_smtp_cls.return_value = mock_conn
        _smtp_conf(minimal_conf)
        m = Mailer()
        assert hasattr(m, "smtpconn")
        m.__exit__(None, None, None)
        assert not hasattr(m, "smtpconn")
        mock_conn.quit.assert_called_once()

    @patch("smtplib.SMTP")
    def test_context_manager_exit_called_on_with_block_exit(self, mock_smtp_cls, minimal_conf):
        """Leaving a `with` block must trigger __exit__ and remove smtpconn."""
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_smtp_cls.return_value = mock_conn
        _smtp_conf(minimal_conf)
        with Mailer() as m:
            captured = m  # keep a reference for post-block inspection
        # After the block, smtpconn should have been deleted via close()
        assert not hasattr(captured, "smtpconn")

    @patch("smtplib.SMTP")
    def test_close_is_idempotent(self, mock_smtp_cls, minimal_conf):
        """Calling close() twice must not raise."""
        mock_smtp_cls.return_value = create_autospec(_REAL_SMTP, instance=True)
        _smtp_conf(minimal_conf)
        m = Mailer()
        m.close()
        m.close()  # second call — must not raise

    @patch("smtplib.SMTP")
    def test_close_calls_quit_on_smtpconn(self, mock_smtp_cls, minimal_conf):
        """close() should call smtpconn.quit() when a connection is open."""
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_smtp_cls.return_value = mock_conn
        _smtp_conf(minimal_conf)
        m = Mailer()
        m.close()
        mock_conn.quit.assert_called_once()

    @patch("smtplib.SMTP")
    def test_close_survives_quit_raising(self, mock_smtp_cls, minimal_conf):
        """close() must not propagate exceptions from smtpconn.quit()."""
        mock_conn = create_autospec(_REAL_SMTP, instance=True)
        mock_conn.quit.side_effect = OSError("connection already closed")
        mock_smtp_cls.return_value = mock_conn
        _smtp_conf(minimal_conf)
        m = Mailer()
        m.close()  # must not raise even though quit() raises

    def test_del_does_not_raise_when_smtpconn_missing(self, minimal_conf):
        """__del__ must be safe even if smtpconn was never set (e.g. init failed)."""
        m = object.__new__(Mailer)  # bypass __init__ entirely
        # No smtpconn attribute on m — __del__ should still be safe
        m.__del__()  # must not raise

    @patch("smtplib.SMTP")
    def test_del_does_not_raise_on_normal_instance(self, mock_smtp_cls, minimal_conf):
        """__del__ on a fully initialised (and already closed) Mailer must not raise."""
        mock_smtp_cls.return_value = create_autospec(_REAL_SMTP, instance=True)
        _smtp_conf(minimal_conf)
        m = Mailer()
        m.close()
        m.__del__()  # already closed — must not raise

    @patch("smtplib.SMTP")
    def test_context_manager_exit_suppresses_no_exceptions(self, mock_smtp_cls, minimal_conf):
        """__exit__ returns None, so exceptions inside the block propagate normally."""
        mock_smtp_cls.return_value = create_autospec(_REAL_SMTP, instance=True)
        _smtp_conf(minimal_conf)
        with pytest.raises(ValueError, match="deliberate"), Mailer():
            raise ValueError("deliberate")


# ---------------------------------------------------------------------------
# Mailer — against a real in-process SMTP server
#
# No mock can catch a call to a method smtplib does not have, or a reply the
# protocol does not allow.  These tests drive Mailer over a loopback socket
# against a minimal SMTP responder, so the whole connect/EHLO/MAIL/RCPT/DATA
# path is exercised as the stdlib actually implements it.
# ---------------------------------------------------------------------------


class _CapturingSMTPHandler(socketserver.StreamRequestHandler):
    """Minimal SMTP responder: enough of RFC 5321 for smtplib to send a message."""

    def handle(self) -> None:
        self._reply("220 localhost execsql test server")
        envelope: dict[str, object] = {"rcpt": []}
        while True:
            line = self.rfile.readline()
            if not line:
                return
            command = line.decode("ascii", "replace").rstrip("\r\n")
            verb = command.split(None, 1)[0].upper() if command else ""
            if verb == "EHLO":
                self._reply("250-localhost\r\n250-8BITMIME\r\n250 HELP")
            elif verb == "HELO":
                self._reply("250 localhost")
            elif verb == "MAIL":
                envelope["mail_from"] = command
                self._reply("250 OK")
            elif verb == "RCPT":
                cast(list, envelope["rcpt"]).append(command)
                self._reply("250 OK")
            elif verb == "DATA":
                self._reply("354 End data with <CR><LF>.<CR><LF>")
                envelope["data"] = self._read_data()
                self.server.received.append(envelope)  # type: ignore[attr-defined]
                self._reply("250 OK")
            elif verb == "QUIT":
                self._reply("221 Bye")
                return
            elif verb == "RSET":
                self._reply("250 OK")
            else:
                self._reply("502 Command not implemented")

    def _reply(self, text: str) -> None:
        self.wfile.write(text.encode("ascii") + b"\r\n")
        self.wfile.flush()

    def _read_data(self) -> str:
        lines: list[str] = []
        while True:
            line = self.rfile.readline()
            if not line or line in (b".\r\n", b".\n"):
                break
            decoded = line.decode("utf-8", "replace").rstrip("\r\n")
            # Undo dot-stuffing.
            lines.append(decoded[1:] if decoded.startswith("..") else decoded)
        return "\n".join(lines)


class _SMTPTestServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _CapturingSMTPHandler)
        self.received: list[dict[str, object]] = []


@pytest.fixture
def smtp_server(minimal_conf):
    """A loopback SMTP server, with _state.conf pointed at it."""
    server = _SMTPTestServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _state.conf.smtp_host, _state.conf.smtp_port = server.server_address[:2]
    _state.conf.smtp_ssl = False
    _state.conf.smtp_tls = False
    _state.conf.smtp_username = None
    _state.conf.smtp_password = None
    _state.conf.email_format = "text"
    _state.conf.email_css = None
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class TestMailerAgainstRealServer:
    def test_plain_text_message_round_trip(self, smtp_server):
        with Mailer() as m:
            m.sendmail("from@a.com", "to@b.com", "Round trip", "Body text")
        assert len(smtp_server.received) == 1
        envelope = smtp_server.received[0]
        assert "from@a.com" in cast(str, envelope["mail_from"])
        assert any("to@b.com" in r for r in cast(list, envelope["rcpt"]))
        data = cast(str, envelope["data"])
        assert "Subject: Round trip" in data
        assert "Body text" in data

    def test_multiple_recipients_each_get_an_rcpt(self, smtp_server):
        with Mailer() as m:
            m.sendmail("from@a.com", "b@x.com;c@x.com,d@x.com", "Sub", "Body")
        rcpt = cast(list, smtp_server.received[0]["rcpt"])
        assert len(rcpt) == 3

    def test_content_file_and_attachment(self, smtp_server, tmp_path):
        content_file = tmp_path / "body.txt"
        content_file.write_text("Appended body line")
        attach_file = tmp_path / "data.csv"
        attach_file.write_bytes(b"col1,col2\n1,2\n")
        with Mailer() as m:
            m.sendmail(
                "from@a.com",
                "to@b.com",
                "With files",
                "Body",
                content_filename=str(content_file),
                attach_filename=str(attach_file),
            )
        data = cast(str, smtp_server.received[0]["data"])
        assert "Appended body line" in data
        assert 'filename="data.csv"' in data
        # The attachment is base64-encoded, so the raw bytes must not appear.
        assert base64.b64encode(b"col1,col2\n1,2\n").decode() in data.replace("\n", "")

    def test_html_format_message(self, smtp_server):
        _state.conf.email_format = "html"
        _state.conf.email_css = "body { color: red; }"
        with Mailer() as m:
            m.sendmail("from@a.com", "to@b.com", "HTML", "<p>Hello</p>")
        data = cast(str, smtp_server.received[0]["data"])
        assert "Content-Type: text/html" in data

    def test_unreachable_host_raises_oserror(self, minimal_conf):
        """A closed port must surface as a connection error, not hang."""
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            dead_port = probe.getsockname()[1]
        _state.conf.smtp_host = "127.0.0.1"
        _state.conf.smtp_port = dead_port
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        with pytest.raises(OSError):
            Mailer()
