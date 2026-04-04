"""
Tests for execsql.utils.mail — MailSpec construction and Mailer config validation.

Mailer.__init__ establishes an SMTP connection, so all Mailer tests mock smtplib.
MailSpec is a pure data class that can be tested without mocking.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.utils.mail import Mailer, MailSpec


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
        mock_conn = MagicMock()
        mock_smtp_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        m = Mailer()
        mock_smtp_cls.assert_called_once_with("mail.example.com")
        mock_conn.ehlo_or_hello_if_needed.assert_called_once()
        # Clean up to avoid __del__ issues
        del m.smtpconn

    @patch("smtplib.SMTP")
    def test_creates_smtp_connection_with_port(self, mock_smtp_cls, minimal_conf):
        mock_conn = MagicMock()
        mock_smtp_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = 587
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        m = Mailer()
        mock_smtp_cls.assert_called_once_with("mail.example.com", 587)
        del m.smtpconn

    @patch("smtplib.SMTP_SSL")
    def test_creates_smtp_ssl_connection(self, mock_smtp_ssl_cls, minimal_conf):
        mock_conn = MagicMock()
        mock_smtp_ssl_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = True
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = None
        _state.conf.smtp_password = None
        m = Mailer()
        mock_smtp_ssl_cls.assert_called_once_with("mail.example.com")
        del m.smtpconn

    @patch("smtplib.SMTP")
    def test_starttls_called_when_tls_enabled(self, mock_smtp_cls, minimal_conf):
        mock_conn = MagicMock()
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
        mock_conn = MagicMock()
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
    def test_login_without_password(self, mock_smtp_cls, minimal_conf):
        mock_conn = MagicMock()
        mock_smtp_cls.return_value = mock_conn
        _state.conf.smtp_host = "mail.example.com"
        _state.conf.smtp_port = None
        _state.conf.smtp_ssl = False
        _state.conf.smtp_tls = False
        _state.conf.smtp_username = "user"
        _state.conf.smtp_password = None
        m = Mailer()
        mock_conn.login.assert_called_once_with("user")
        del m.smtpconn


# ---------------------------------------------------------------------------
# Mailer.sendmail — message construction (mocked SMTP)
# ---------------------------------------------------------------------------


class TestMailerSendmail:
    @patch("smtplib.SMTP")
    def _make_mailer(self, mock_smtp_cls):
        mock_conn = MagicMock()
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
        mock_smtp_cls.return_value = MagicMock()
        _smtp_conf(minimal_conf)
        with Mailer() as m:
            assert isinstance(m, Mailer)

    @patch("smtplib.SMTP")
    def test_context_manager_exit_calls_close(self, mock_smtp_cls, minimal_conf):
        """__exit__ must call close(), which removes smtpconn."""
        mock_conn = MagicMock()
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
        mock_conn = MagicMock()
        mock_smtp_cls.return_value = mock_conn
        _smtp_conf(minimal_conf)
        with Mailer() as m:
            captured = m  # keep a reference for post-block inspection
        # After the block, smtpconn should have been deleted via close()
        assert not hasattr(captured, "smtpconn")

    @patch("smtplib.SMTP")
    def test_close_is_idempotent(self, mock_smtp_cls, minimal_conf):
        """Calling close() twice must not raise."""
        mock_smtp_cls.return_value = MagicMock()
        _smtp_conf(minimal_conf)
        m = Mailer()
        m.close()
        m.close()  # second call — must not raise

    @patch("smtplib.SMTP")
    def test_close_calls_quit_on_smtpconn(self, mock_smtp_cls, minimal_conf):
        """close() should call smtpconn.quit() when a connection is open."""
        mock_conn = MagicMock()
        mock_smtp_cls.return_value = mock_conn
        _smtp_conf(minimal_conf)
        m = Mailer()
        m.close()
        mock_conn.quit.assert_called_once()

    @patch("smtplib.SMTP")
    def test_close_survives_quit_raising(self, mock_smtp_cls, minimal_conf):
        """close() must not propagate exceptions from smtpconn.quit()."""
        mock_conn = MagicMock()
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
        mock_smtp_cls.return_value = MagicMock()
        _smtp_conf(minimal_conf)
        m = Mailer()
        m.close()
        m.__del__()  # already closed — must not raise

    @patch("smtplib.SMTP")
    def test_context_manager_exit_suppresses_no_exceptions(self, mock_smtp_cls, minimal_conf):
        """__exit__ returns None, so exceptions inside the block propagate normally."""
        mock_smtp_cls.return_value = MagicMock()
        _smtp_conf(minimal_conf)
        with pytest.raises(ValueError, match="deliberate"), Mailer():
            raise ValueError("deliberate")
