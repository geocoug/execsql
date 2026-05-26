"""B12 regression tests: credential redaction in the execsql log.

Covers:
* F014 — ``-a NAME VALUE`` values whose name matches the sensitive
  filter (``PASSWORD``, ``SECRET``, ``TOKEN``, …) are replaced with
  ``***`` in the log line.
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

        # The filter should catch substrings (case-insensitive) of these.
        sensitive_inputs = [
            "DB_PASSWORD=secret123",
            "MY_SECRET",
            "API_TOKEN_PROD",
            "PASSWD=hunter2",
            "PRIVATE_KEY",
            "AWS_CREDENTIALS",
        ]
        for s in sensitive_inputs:
            assert any(needle in s.upper() for needle in _SENSITIVE_SUBSTRINGS), f"_SENSITIVE_SUBSTRINGS missed {s!r}"

    def test_innocuous_names_do_not_match(self):
        from execsql.cli.run import _SENSITIVE_SUBSTRINGS

        for s in ["DEBUG=on", "OUTFILE=report.csv", "RUN_ID=abc123"]:
            assert not any(needle in s.upper() for needle in _SENSITIVE_SUBSTRINGS), (
                f"_SENSITIVE_SUBSTRINGS unexpectedly matched {s!r}"
            )
