from __future__ import annotations

"""
Email/SMTP utilities for execsql.

Provides :class:`MailSpec` (specification for a deferred email — to,
subject, body, attachments) and :class:`Mailer` / :func:`send_email`,
which compose and send email via SMTP using settings from
:class:`~execsql.config.ConfigData`.  Used by the ``SEND MAIL``
metacommand and the halt/cancel email-notification hooks.
"""

import io
import os
import re
from typing import List, Optional

import execsql.state as _state
from execsql.exceptions import ErrInfo


class Mailer:
    def __repr__(self) -> str:
        return "Mailer()"

    def __del__(self) -> None:
        if hasattr(self, "smtpconn"):
            self.smtpconn.quit()

    def __init__(self) -> None:
        global smtplib
        global MIMEMultipart
        global MIMEText
        global MIMEBase
        global encoders
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

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
        msg_content: Optional[str],
        content_filename: Optional[str] = None,
        attach_filename: Optional[str] = None,
    ) -> None:
        global smtplib
        global MIMEMultipart
        global MIMEText
        global MIMEBase
        global encoders

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
                msg_body += "<style>%s</style>" % conf.email_css
            msg_body += "</head><body>%s" % msg_content if msg_content else ""
        else:
            msg_body = msg_content if msg_content else ""
        if content_filename is not None:
            msg_body += "\n" + io.open(content_filename, "rt").read()
        if conf.email_format == "html":
            msg_body += "</body></html>"
            msg.attach(MIMEText(msg_body, "html"))
        else:
            msg.attach(MIMEText(msg_body, "plain"))
        if attach_filename is not None:
            f = io.open(attach_filename, "rb")
            fdata = MIMEBase("application", "octet-stream")
            fdata.set_payload(f.read())
            f.close()
            encoders.encode_base64(fdata)
            fdata.add_header("Content-Disposition", "attachment", filename=os.path.basename(attach_filename))
            msg.attach(fdata)
        self.smtpconn.sendmail(send_from, recipients, msg.as_string())


class MailSpec:
    def __init__(
        self,
        send_from: str,
        send_to: str,
        subject: str,
        msg_content: Optional[str],
        content_filename: Optional[str] = None,
        attach_filename: Optional[str] = None,
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
            Mailer().sendmail(send_from, send_to, subject, msg_content, content_filename, attach_filename)
        return None
