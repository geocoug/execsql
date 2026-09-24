"""
Tests for issue #46 — file output under ``execsql.api.run()``.

``WRITE ... TO <file>`` and ``TEE`` hand their output to a FileWriter
subprocess.  Every entry point in :mod:`execsql.utils.fileio` guards on that
subprocess being alive and drops the write when it is not — the guard is
correct, because putting on a queue nothing drains fills the OS pipe buffer and
deadlocks the caller.  Only the CLI ever started the subprocess, so under the
API every file write was discarded, no file appeared, and the run still
reported success.

These tests exercise the real subprocess rather than mocking it: a mocked
writer cannot show that a file exists on disk when ``run()`` returns, which is
the entire claim.
"""

from __future__ import annotations

from execsql import api


def _sqlite_dsn(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'api.db'}"


class TestWriteToFile:
    def test_write_to_file_creates_the_file(self, tmp_path):
        """The regression: the file simply did not exist."""
        out = tmp_path / "out.txt"
        result = api.run(
            sql=f'-- !x! WRITE "hello" to {out}\nselect 1;\n',
            dsn=_sqlite_dsn(tmp_path),
            new_db=True,
        )
        assert result.success, result.errors
        assert out.exists(), "WRITE ... TO <file> produced no file"
        assert out.read_text().rstrip("\n") == "hello"

    def test_file_is_readable_the_moment_run_returns(self, tmp_path):
        """Files are flushed and closed before run() hands back control.

        The writer keeps files open until told otherwise, so without an
        explicit flush the caller can see an empty file even once it exists.
        """
        out = tmp_path / "out.txt"
        api.run(
            sql=f'-- !x! WRITE "first" to {out}\n-- !x! WRITE "second" to {out}\nselect 1;\n',
            dsn=_sqlite_dsn(tmp_path),
            new_db=True,
        )
        assert out.read_text().split() == ["first", "second"]

    def test_two_runs_in_one_process_both_write(self, tmp_path):
        """A second run() reuses the writer started by the first."""
        for name in ("one.txt", "two.txt"):
            out = tmp_path / name
            api.run(
                sql=f'-- !x! WRITE "{name}" to {out}\nselect 1;\n',
                dsn=_sqlite_dsn(tmp_path),
                new_db=True,
            )
            assert out.exists(), f"{name} was dropped"
            assert out.read_text().rstrip("\n") == name

    def test_substitution_variables_reach_the_file(self, tmp_path):
        """api.run() prefixes variable names with $, so the script says !!$site!!."""
        out = tmp_path / "out.txt"
        api.run(
            sql=f'-- !x! WRITE "value is !!$site!!" to {out}\nselect 1;\n',
            dsn=_sqlite_dsn(tmp_path),
            new_db=True,
            variables={"site": "ABC-123"},
        )
        assert "ABC-123" in out.read_text()

    def test_unicode_reaches_the_file(self, tmp_path):
        out = tmp_path / "out.txt"
        api.run(
            sql=f'-- !x! WRITE "café — 日本語 ⚡" to {out}\nselect 1;\n',
            dsn=_sqlite_dsn(tmp_path),
            new_db=True,
        )
        assert out.read_text(encoding="utf-8").rstrip("\n") == "café — 日本語 ⚡"


class TestWriterOwnership:
    def test_a_caller_started_writer_is_left_running(self, tmp_path):
        """A caller who starts their own writer keeps it after run() returns.

        The documented workaround for this bug was to start the writer by hand;
        those callers must not have it shut down underneath them.
        """
        import execsql.utils.fileio as fileio

        fileio.filewriter_end()  # start from a known state
        fileio.filewriter = fileio.FileWriter(
            fileio.fw_input,
            fileio.fw_output,
            file_encoding="utf-8",
            open_timeout=10,
        )
        fileio.filewriter.start()
        mine = fileio.filewriter
        try:
            out = tmp_path / "out.txt"
            api.run(
                sql=f'-- !x! WRITE "hello" to {out}\nselect 1;\n',
                dsn=_sqlite_dsn(tmp_path),
                new_db=True,
            )
            assert out.exists()
            assert fileio.filewriter is mine, "run() replaced the caller's writer"
            assert mine.is_alive(), "run() shut down the caller's writer"
        finally:
            fileio.filewriter_end()

    def test_run_leaves_a_usable_writer_behind(self, tmp_path):
        """The writer run() starts stays up for reuse, as the CLI's does."""
        import execsql.utils.fileio as fileio

        out = tmp_path / "out.txt"
        api.run(
            sql=f'-- !x! WRITE "hello" to {out}\nselect 1;\n',
            dsn=_sqlite_dsn(tmp_path),
            new_db=True,
        )
        assert fileio.filewriter is not None
        assert fileio.filewriter.is_alive()


class TestDroppedWriteIsReported:
    """The issue's fallback ask: a dropped write must not be silent."""

    def test_warns_once_when_no_writer_is_running(self, minimal_conf, monkeypatch):
        import execsql.state as _state
        import execsql.utils.fileio as fileio

        monkeypatch.setattr(fileio, "filewriter", None)
        monkeypatch.setattr(fileio, "_drop_warned", False)
        _state.conf.write_warnings = False  # `always=True` must ignore this

        seen: list[str] = []
        _state.output = type("Hooks", (), {"write": lambda s, m: None, "write_err": lambda s, m: seen.append(m)})()

        for _ in range(5):
            fileio.filewriter_write("/tmp/nowhere.txt", "dropped")

        assert len(seen) == 1, "a script writing many lines must warn once, not per line"
        assert "no file writer" in seen[0]
        assert "nowhere.txt" in seen[0]

    def test_write_still_returns_rather_than_blocking(self, minimal_conf, monkeypatch):
        """The guard must stay: queueing to a drained-by-nobody queue deadlocks."""
        import execsql.utils.fileio as fileio

        monkeypatch.setattr(fileio, "filewriter", None)
        monkeypatch.setattr(fileio, "_drop_warned", True)
        fileio.filewriter_write("/tmp/nowhere.txt", "x")  # must return, not hang
