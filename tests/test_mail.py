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
