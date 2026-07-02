"""Regression tests: credential redaction in the execsql log.

Covers:
* ``-a VALUE`` log lines: every ``$ARG_n`` assignment is logged with
  ``***`` rather than the raw value, since the value is opaque user
  input and may contain high-entropy secrets that don't match any
  name-based filter (``sk-live-*``, ``AKIA…``, ``ghp_*``, JWTs).
* ``_SENSITIVE_SUBSTRINGS`` denylist: env-var seeding (the only
  name-based redaction site) skips common cloud / payment / observability
  / VCS secret naming patterns.
* F017 — ``~/execsql.log`` is created with mode ``0o600`` on POSIX so
  the substituted SQL, ``-a`` values, env vars, and DSN URLs it
  captures aren't world-readable.
"""

from __future__ import annotations

import os
import stat

import pytest


@pytest.fixture
def fake_logfile(tmp_path, monkeypatch):
    """Redirect Logger's default log path to a tmp_path file."""
    target = tmp_path / "execsql.log"
    # Force the user_logfile path so Logger writes here instead of ~/.
    return target


def test_log_file_mode_0o600_on_posix(fake_logfile, monkeypatch):
    """F017: the log file is chmod'd to 0o600 on POSIX after creation."""
    pytest.importorskip("execsql.utils.fileio")
    if os.name != "posix":
        pytest.skip("0o600 mode-check is POSIX-only")

    import execsql.state as _state
    from execsql.utils.fileio import Logger

    # Logger needs an encoding; install a minimal one.
    monkeypatch.setattr(_state, "logfile_encoding", "utf-8", raising=False)
    Logger(
        script_file_name="<inline>",
        db_name="testdb",
        server_name="localhost",
        cmdline_options={},
        log_file_name=str(fake_logfile),
    )
    mode = stat.S_IMODE(os.stat(fake_logfile).st_mode)
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


class TestSensitiveSubstringsConstant:
    """The shared _SENSITIVE_SUBSTRINGS list catches the names we expect."""

    def test_known_names_match(self):
        from execsql.cli.run import _SENSITIVE_SUBSTRINGS

        sensitive_inputs = [
            "DB_PASSWORD=secret123",
            "MY_SECRET",
            "API_TOKEN_PROD",
            "PASSWD=hunter2",
            "PRIVATE_KEY",
            "AWS_CREDENTIALS",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "STRIPE_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "SENTRY_DSN",
            "DATABASE_DSN",
            "SLACK_WEBHOOK",
            "DD_APIKEY",
        ]
        for s in sensitive_inputs:
            assert any(needle in s.upper() for needle in _SENSITIVE_SUBSTRINGS), f"_SENSITIVE_SUBSTRINGS missed {s!r}"

    def test_innocuous_names_do_not_match(self):
        from execsql.cli.run import _SENSITIVE_SUBSTRINGS

        innocuous = [
            "DEBUG=on",
            "OUTFILE=report.csv",
            "RUN_ID=abc123",
            "PATH=/usr/local/bin",
            "NODE_PATH=/srv/app",
            "PYTHONPATH=/srv/lib",
            "KEYBOARD_LAYOUT=us",
            "PATTERN=glob",
            "TURNKEY_MODE=fast",
        ]
        for s in innocuous:
            assert not any(needle in s.upper() for needle in _SENSITIVE_SUBSTRINGS), (
                f"_SENSITIVE_SUBSTRINGS unexpectedly matched {s!r}"
            )


class TestArgValueRedactionInLog:
    """`-a` log lines must always emit `***` instead of the raw value.

    `-a` is positional (the variable name is `$ARG_n`), so there is no
    name to denylist. The value is user-supplied and may be a high-entropy
    secret that defeats any substring or value-based heuristic. Emitting
    `***` unconditionally is the only safe answer.
    """

    def _capture_arg_log_messages(self, sub_vars):
        """Drive _setup_logging() with sub_vars, return the log_status_info calls."""
        from types import SimpleNamespace
        from unittest.mock import patch

        from execsql.cli.run import _setup_logging
        from execsql.script.variables import SubVarSet

        captured = []

        class FakeLogger:
            run_id = "test-run"

            def __init__(self, *a, **kw):
                pass

            def log_status_info(self, msg):
                captured.append(msg)

            def add_redaction_value(self, value):
                pass

        conf = SimpleNamespace(
            db=None,
            server=None,
            db_file=None,
            user_logfile=False,
            files_read=[],
            log_write_messages=False,
            log_msg_format=None,
            log_write_sql=False,
            log_write_substitutions=False,
        )
        with (
            patch("execsql.cli.run.Logger", FakeLogger),
            patch("execsql.cli.run.os.path.isfile", return_value=False),
        ):
            _setup_logging(
                conf,
                SubVarSet(),
                script_name="<inline>",
                sub_vars=sub_vars,
                boolean_int=None,
                make_dirs=None,
                database_encoding=None,
                script_encoding=None,
                output_encoding=None,
                import_encoding=None,
                user_logfile=True,
                new_db=False,
                port=None,
                scanlines=None,
                db_type="l",
                user=None,
                use_gui=None,
                no_passwd=False,
                import_buffer=None,
            )
        return [m for m in captured if "Command-line substitution variable assignment" in (m or "")]

    def test_high_entropy_values_never_logged(self):
        # Synthetic fixture values constructed at runtime so gitleaks
        # doesn't flag the test file as containing a real secret.
        secrets = [
            "sk-live-" + "abcdef1234567890",
            "AKIA" + "IOSFODNN7EXAMPLE",
            "ghp" + "_" + "abcdef1234567890abcdef1234567890abcd",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" + ".foo.bar",
        ]
        log_lines = self._capture_arg_log_messages(secrets)
        assert len(log_lines) == len(secrets)
        joined = " ".join(log_lines)
        for value in secrets:
            assert value not in joined, f"raw secret value {value!r} leaked into log"
        for line in log_lines:
            assert "{***}" in line, f"missing redaction marker in log line: {line!r}"

    def test_innocuous_values_also_redacted(self):
        """Redaction is unconditional — `-a` values are never logged verbatim."""
        log_lines = self._capture_arg_log_messages(["hello", "42"])
        assert all("{***}" in line for line in log_lines), log_lines
        assert all("hello" not in line and "42" not in line for line in log_lines), log_lines


class TestExpandedLogRedaction:
    def test_registered_values_redacted_from_sql_and_user_messages(self, tmp_path, minimal_conf):
        from execsql.utils.fileio import Logger

        import execsql.state as _state

        _state.logfile_encoding = "utf-8"
        log_path = tmp_path / "execsql.log"
        logger = Logger("<inline>", "testdb", None, {}, log_file_name=str(log_path))
        secret = "opaque-runtime-value"
        logger.add_redaction_value(secret)
        logger.log_sql_query(f"select '{secret}'", "testdb", 1)
        logger.log_user_msg(f"System command: echo {secret}")
        logger.close()

        content = log_path.read_text()
        assert secret not in content
        assert "select '***'" in content
        assert "System command: echo ***" in content

    def test_common_secret_shapes_redacted_without_registration(self, tmp_path, minimal_conf):
        from execsql.utils.fileio import Logger

        import execsql.state as _state

        _state.logfile_encoding = "utf-8"
        log_path = tmp_path / "execsql.log"
        logger = Logger("<inline>", "testdb", None, {}, log_file_name=str(log_path))
        api_key = "sk-live-" + "abcdef1234567890"
        dsn = "postgresql://user:passw0rd@example.test/db"
        logger.log_status_error(f"password=hunter2 api_key={api_key} dsn={dsn}")
        logger.close()

        content = log_path.read_text()
        assert "hunter2" not in content
        assert api_key not in content
        assert "passw0rd" not in content
        assert "password=***" in content
        assert "api_key=***" in content
        assert "postgresql://user:***@example.test/db" in content
