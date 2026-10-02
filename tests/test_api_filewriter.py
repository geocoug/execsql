"""
File output under ``execsql.api.run()`` (issue #46, and per-run writers).

``WRITE ... TO <file>`` and ``TEE`` hand their output to the active run's
FileWriter thread.  Every entry point in :mod:`execsql.utils.fileio` drops the
write when no writer is running.  Only the CLI used to start one, so under the
API every file write was discarded, no file appeared, and the run still
reported success.  Each ``run()`` now owns a writer, so concurrent runs in
different threads neither share files nor lose output when one of them halts.

These tests exercise the real writer rather than mocking it: a mocked writer
cannot show that a file exists on disk when ``run()`` returns, which is the
entire claim.
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


def _numbered_lines_sql(out, count: int) -> str:
    return (
        "-- !x! SUB i 0\n"
        f"-- !x! LOOP WHILE (IS_GT({count}, !!i!!))\n"
        "-- !x! SUB_ADD i 1\n"
        f'-- !x! WRITE "line !!i!!" TO {out}\n'
        "-- !x! END LOOP\n"
    )


class TestWriterPerRun:
    def test_run_stops_its_writer_before_returning(self, tmp_path):
        import threading

        out = tmp_path / "out.txt"
        result = api.run(
            sql=f'-- !x! WRITE "hello" to {out}\nselect 1;\n',
            dsn=_sqlite_dsn(tmp_path),
            new_db=True,
        )
        assert result.success, result.errors
        assert out.read_text() == "hello\n"
        assert not [t for t in threading.enumerate() if t.name == "execsql-filewriter"]

    def test_run_leaves_the_callers_writer_alone(self, tmp_path):
        """A writer already active in this thread (a CLI run calling run()) keeps running."""
        import execsql.state as _state
        from execsql.utils.fileio import FileWriter, filewriter_end

        mine = FileWriter(file_encoding="utf-8", open_timeout=10)
        mine.start()
        _state.filewriter = mine
        try:
            out = tmp_path / "out.txt"
            api.run(sql=f'-- !x! WRITE "hello" to {out}\nselect 1;\n', dsn=_sqlite_dsn(tmp_path), new_db=True)
            assert out.exists()
            assert _state.filewriter is mine, "run() replaced the caller's writer"
            assert mine.is_alive(), "run() shut down the caller's writer"
        finally:
            filewriter_end(mine)

    def test_concurrent_runs_write_complete_files_and_a_halt_stays_local(self, tmp_path):
        """Two threads write their own files; one halts mid-run, the other loses nothing."""
        import threading
        import time

        steady_out, halting_out = tmp_path / "steady.txt", tmp_path / "halting.txt"
        results: dict = {}

        def steady():
            results["steady"] = api.run(
                sql=_numbered_lines_sql(steady_out, 2000),
                dsn=f"sqlite:///{tmp_path / 'steady.db'}",
                new_db=True,
            )

        def halting():
            results["halting"] = api.run(
                sql=_numbered_lines_sql(halting_out, 50) + "select * from no_such_table;\n",
                dsn=f"sqlite:///{tmp_path / 'halting.db'}",
                new_db=True,
            )

        a = threading.Thread(target=steady)
        a.start()
        deadline = time.monotonic() + 30
        while not steady_out.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        b = threading.Thread(target=halting)
        b.start()
        b.join(timeout=60)
        a.join(timeout=60)
        assert not a.is_alive() and not b.is_alive()

        assert results["steady"].success, results["steady"].errors
        assert not results["halting"].success
        assert steady_out.read_text().splitlines() == [f"line {n}" for n in range(1, 2001)]
        assert halting_out.read_text().splitlines() == [f"line {n}" for n in range(1, 51)]


class TestDroppedWriteIsReported:
    """The issue's fallback ask: a dropped write must not be silent."""

    def test_warns_once_when_no_writer_is_running(self, minimal_conf, monkeypatch):
        import execsql.state as _state
        import execsql.utils.fileio as fileio

        monkeypatch.setattr(_state, "filewriter", None)
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
        """With no writer the write is dropped at once, never queued to wait forever."""
        import execsql.state as _state
        import execsql.utils.fileio as fileio

        monkeypatch.setattr(_state, "filewriter", None)
        monkeypatch.setattr(fileio, "_drop_warned", True)
        fileio.filewriter_write("/tmp/nowhere.txt", "x")  # must return, not hang


class TestLostOutputIsAnError:
    def test_unopenable_output_file_fails_the_run(self, tmp_path):
        """A WRITE target that never opens is reported, not silently dropped."""
        target = tmp_path / "is_a_directory"
        target.mkdir()
        conf = tmp_path / "execsql.conf"
        conf.write_text("[output]\noutfile_open_timeout=1\n")
        result = api.run(
            sql=f'-- !x! WRITE "lost" to {target}\nselect 1;\n',
            dsn=_sqlite_dsn(tmp_path),
            new_db=True,
            config_file=conf,
        )
        assert not result.success
        assert any("is_a_directory" in e.message for e in result.errors), result.errors


class TestRelativePaths:
    def test_write_after_cd_lands_in_the_new_directory(self, tmp_path, monkeypatch):
        """A relative WRITE path follows CD, as EXPORT and IMPORT already do."""
        (tmp_path / "sub").mkdir()
        monkeypatch.chdir(tmp_path)
        result = api.run(
            sql='-- !x! WRITE "before cd" TO out.txt\n-- !x! CD sub\n-- !x! WRITE "after cd" TO out.txt\n',
            dsn=_sqlite_dsn(tmp_path),
            new_db=True,
        )
        assert result.success, result.errors
        assert (tmp_path / "out.txt").read_text() == "before cd\n"
        assert (tmp_path / "sub" / "out.txt").read_text() == "after cd\n"
