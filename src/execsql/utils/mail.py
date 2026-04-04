from __future__ import annotations

"""
Email/SMTP utilities for execsql.

Provides :class:`MailSpec` (specification for a deferred email — to,
subject, body, attachments) and :class:`Mailer` / :func:`send_email`,
which compose and send email via SMTP using settings from
:class:`~execsql.config.ConfigData`.  Used by the ``SEND MAIL``
metacommand and the halt/cancel email-notification hooks.
"""

import re
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import execsql.state as _state
from execsql.exceptions import ErrInfo

__all__ = ["MailSpec", "Mailer"]


class Mailer:
    def __repr__(self) -> str:
        return "Mailer()"

    def __enter__(self) -> Mailer:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
        return None

    def close(self) -> None:
        if hasattr(self, "smtpconn"):
            try:
                self.smtpconn.quit()
            except Exception:
                pass  # Best-effort; connection may already be closed.
            finally:
                del self.smtpconn

    def __del__(self) -> None:
        self.close()

    def __init__(self) -> None:
        conf = _state.conf
        if conf.smtp_host is None:
            raise ErrInfo(type="error", other_msg="Can't send email; the email host is not configured.")
        if conf.smtp_port is None:
            if conf.smtp_ssl:
                self.smtpconn = smtplib.SMTP_SSL(conf.smtp_host)
            else:
                self.smtpconn = smtplib.SMTP(conf.smtp_host)
        else:
            if conf.smtp_ssl:
                self.smtpconn = smtplib.SMTP_SSL(conf.smtp_host, conf.smtp_port)
            else:
                self.smtpconn = smtplib.SMTP(conf.smtp_host, conf.smtp_port)
        self.smtpconn.ehlo_or_hello_if_needed()
        if conf.smtp_tls:
            self.smtpconn.starttls()
            self.smtpconn.ehlo(conf.smtp_host)
        if conf.smtp_username:
            if conf.smtp_password:
                self.smtpconn.login(conf.smtp_username, conf.smtp_password)
            else:
                self.smtpconn.login(conf.smtp_username)

    def sendmail(
        self,
        send_from: str,
        send_to: str,
        subject: str,
        msg_content: str | None,
        content_filename: str | None = None,
        attach_filename: str | None = None,
    ) -> None:
        conf = _state.conf
        if conf.email_format == "html":
            msg = MIMEMultipart("alternative")
        else:
            msg = MIMEMultipart()
        recipients = re.split(r"[;,]", send_to)
        msg["From"] = send_from
        msg["To"] = ",".join(recipients)
        msg["Subject"] = subject
        if conf.email_format == "html":
            msg_body = "<html><head>"
            if conf.email_css is not None:
                msg_body += f"<style>{conf.email_css}</style>"
            msg_body += f"</head><body>{msg_content}" if msg_content else ""
        else:
            msg_body = msg_content if msg_content else ""
        if content_filename is not None:
            with open(content_filename) as content_file:
                msg_body += "\n" + content_file.read()
        if conf.email_format == "html":
            msg_body += "</body></html>"
            msg.attach(MIMEText(msg_body, "html"))
        else:
            msg.attach(MIMEText(msg_body, "plain"))
        if attach_filename is not None:
            with open(attach_filename, "rb") as f:
                fdata = MIMEBase("application", "octet-stream")
                fdata.set_payload(f.read())
            encoders.encode_base64(fdata)
            fdata.add_header("Content-Disposition", "attachment", filename=Path(attach_filename).name)
            msg.attach(fdata)
        self.smtpconn.sendmail(send_from, recipients, msg.as_string())


class MailSpec:
    def __init__(
        self,
        send_from: str,
        send_to: str,
        subject: str,
        msg_content: str | None,
        content_filename: str | None = None,
        attach_filename: str | None = None,
        repeatable: bool = False,
    ) -> None:
        self.send_from = send_from
        self.send_to = send_to
        self.subject = subject
        self.msg_content = msg_content
        self.content_filename = content_filename
        self.attach_filename = attach_filename
        self.repeatable = repeatable
        self.sent = False

    def send(self) -> None:
        if self.repeatable or not self.sent:
            self.sent = True
            send_from = _state.commandliststack[-1].localvars.substitute_all(self.send_from)
            send_from = _state.subvars.substitute_all(send_from)
            send_to = _state.commandliststack[-1].localvars.substitute_all(self.send_to)
            send_to = _state.subvars.substitute_all(send_to)
            subject = _state.commandliststack[-1].localvars.substitute_all(self.subject)
            subject = _state.subvars.substitute_all(subject)
            msg_content = _state.commandliststack[-1].localvars.substitute_all(self.msg_content)
            msg_content = _state.subvars.substitute_all(msg_content)
            content_filename = _state.commandliststack[-1].localvars.substitute_all(self.content_filename)
            content_filename = _state.subvars.substitute_all(content_filename)
            attach_filename = _state.commandliststack[-1].localvars.substitute_all(self.attach_filename)
            attach_filename = _state.subvars.substitute_all(attach_filename)
            with Mailer() as m:
                m.sendmail(send_from, send_to, subject, msg_content, content_filename, attach_filename)
        return None
