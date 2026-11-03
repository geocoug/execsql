"""A stalled output worker cannot hold callers or start later writes after abandonment."""

from __future__ import annotations

import builtins
import threading
import time
from pathlib import Path

import pytest

import execsql.state as state
import execsql.utils.fileio as fileio
from execsql.exceptions import ErrInfo


class GatedHandle:
    def __init__(self, handle, phase, entered, release, calls):
        self.handle = handle
        self.phase = phase
        self.entered = entered
        self.release = release
        self.calls = calls

    def __getattr__(self, name):
        return getattr(self.handle, name)

    def gate(self, phase):
        self.calls.append(phase)
        if self.phase == phase:
            self.entered.set()
            assert self.release.wait(2), "test failed to release its I/O gate"

    def write(self, text):
        self.gate("write")
        return self.handle.write(text)

    def flush(self):
        self.gate("flush")
        return self.handle.flush()

    def close(self):
        self.gate("close")
        return self.handle.close()


@pytest.mark.parametrize("phase", ["resolve", "open", "write", "flush", "close", "failures"])
def test_flush_deadline_bounds_live_worker_and_prevents_later_output(tmp_path, monkeypatch, phase):
    entered, release = threading.Event(), threading.Event()
    calls = []
    target, later = tmp_path / "blocked.txt", tmp_path / "later.txt"
    real_open = builtins.open
    real_resolve = Path.resolve
    real_failures = fileio.FileWriter.open_failures

    def gated_open(*args, **kwargs):
        filename = kwargs.get("file", args[0] if args else "")
        if str(filename) == str(target):
            calls.append("open")
            if phase == "open":
                entered.set()
                assert release.wait(2)
            return GatedHandle(real_open(*args, **kwargs), phase, entered, release, calls)
        return real_open(*args, **kwargs)

    def failures(self):
        entered.set()
        assert release.wait(2)
        real_failures(self)

    def gated_resolve(path, *args, **kwargs):
        if phase == "resolve" and str(path) == str(target) and threading.current_thread() is writer:
            entered.set()
            assert release.wait(2)
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", gated_resolve)
    monkeypatch.setattr(fileio, "open", gated_open, raising=False)
    if phase == "failures":
        monkeypatch.setattr(fileio.FileWriter, "open_failures", failures)
    writer = fileio.FileWriter(open_timeout=1)
    state.filewriter = writer
    writer.start()
    safety = threading.Timer(0.8, release.set)
    safety.start()
    try:
        fileio.filewriter_write(str(target), "first\n")
        if phase in ("resolve", "open", "write", "flush"):
            assert entered.wait(0.5)
            fileio.filewriter_write(str(target), "second\n")
            fileio.filewriter_write(str(later), "later\n")
        started = time.monotonic()
        with pytest.raises(ErrInfo, match="File output lost") as raised:
            fileio.filewriter_close_all_after_write(max_wait=0.04)
        assert time.monotonic() - started <= 0.29
        assert entered.is_set()
        assert writer.is_alive(), "the blocked thread must not be claimed to have stopped"
        assert writer.abandoned.is_set()
        if phase != "failures":
            assert str(target) in str(raised.value)
        if phase in ("resolve", "open", "write", "flush"):
            assert str(later) in str(raised.value)
        started = time.monotonic()
        fileio.filewriter_end(writer)
        assert time.monotonic() - started <= 0.1
        with pytest.raises(ErrInfo, match="File output lost"):
            # Keep the context pointing at the abandoned writer to prove new
            # submissions fail immediately, even when end has detached it.
            state.filewriter = writer
            fileio.filewriter_write(str(later), "after deadline\n")
        release.set()
        writer.join(2)
        assert not writer.is_alive()
        assert not later.exists()
        if target.exists():
            assert "second" not in target.read_text()
        if phase == "write":
            assert target.read_bytes() == b"", "abandonment must not flush the just-buffered line during close"
        if phase == "open":
            assert calls == ["open", "close"], calls
    finally:
        release.set()
        safety.cancel()
        writer.join(2)
        fileio.filewriter_end(writer)
        state.filewriter = None


@pytest.mark.parametrize("entrypoint", ["status", "close"])
def test_public_path_waits_use_the_default_absolute_deadline(tmp_path, monkeypatch, entrypoint):
    entered, release = threading.Event(), threading.Event()
    target = tmp_path / "blocked.txt"
    real_open = builtins.open
    original_deadline = fileio._writer_deadline
    monkeypatch.setattr(fileio, "_writer_deadline", lambda fw, max_wait=None: original_deadline(fw, 0.04))

    def blocked(*args, **kwargs):
        filename = kwargs.get("file", args[0] if args else "")
        if str(filename) == str(target):
            if entrypoint == "status":
                entered.set()
                assert release.wait(2)
            handle = real_open(*args, **kwargs)
            return GatedHandle(handle, "close", entered, release, [])
        return real_open(*args, **kwargs)

    monkeypatch.setattr(fileio, "open", blocked, raising=False)
    writer = fileio.FileWriter(open_timeout=1)
    state.filewriter = writer
    writer.start()
    safety = threading.Timer(0.8, release.set)
    safety.start()
    try:
        fileio.filewriter_write(str(target), "first\n")
        if entrypoint == "status":
            assert entered.wait(0.5)
        started = time.monotonic()
        action = fileio.filewriter_filestatus if entrypoint == "status" else fileio.filewriter_close
        with pytest.raises(ErrInfo, match="File output lost") as raised:
            action(str(target))
        assert time.monotonic() - started <= 0.29
        assert ("open" if entrypoint == "status" else "close") in str(raised.value)
        assert str(target) in str(raised.value)
    finally:
        release.set()
        safety.cancel()
        fileio.filewriter_end(writer)
        writer.join(2)
        state.filewriter = None


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-16-be", "ascii"])
def test_live_writer_flushes_lines_without_changing_encoding(tmp_path, encoding):
    target, expected = tmp_path / "actual.txt", tmp_path / "expected.txt"
    messages = ["café 日本語\n", "second\tline\n"]
    with builtins.open(expected, "a", encoding=encoding, errors="backslashreplace") as handle:
        handle.writelines(messages)
    writer = fileio.FileWriter(file_encoding=encoding, open_timeout=1)
    state.filewriter = writer
    writer.start()
    try:
        for message in messages:
            fileio.filewriter_write(str(target), message)
        assert fileio.filewriter_filestatus(str(target)) == fileio.FileWriter.FileControl.STATUS_OPEN
        assert target.read_bytes() == expected.read_bytes(), "each write is visible before close, with identical bytes"
        assert not writer._pending
        fileio.filewriter_close_all_after_write(max_wait=1)
    finally:
        fileio.filewriter_end(writer)
        state.filewriter = None


def test_status_and_failure_report_share_one_deadline(tmp_path, monkeypatch):
    failure_entered, release = threading.Event(), threading.Event()
    real_failures = fileio.FileWriter.open_failures
    real_reply = fileio._writer_reply
    deadlines = []

    def reply(writer, deadline, wait):
        deadlines.append(deadline)
        return real_reply(writer, deadline, wait)

    def failures(self):
        failure_entered.set()
        assert release.wait(2)
        real_failures(self)

    monkeypatch.setattr(fileio, "_writer_reply", reply)
    monkeypatch.setattr(fileio.FileWriter, "open_failures", failures)
    writer = fileio.FileWriter(open_timeout=1)
    state.filewriter = writer
    writer.start()
    safety = threading.Timer(1.5, release.set)
    safety.start()
    try:
        fileio.filewriter_write(str(tmp_path / "out.txt"), "line\n")
        started = time.monotonic()
        with pytest.raises(ErrInfo, match="File output lost"):
            fileio.filewriter_close_all_after_write(max_wait=0.5)
        assert time.monotonic() - started <= 0.75
        assert failure_entered.is_set()
        assert len(deadlines) == 2
        assert deadlines[0] == deadlines[1], "status and failure collection must reuse the same deadline"
    finally:
        release.set()
        safety.cancel()
        fileio.filewriter_end(writer)
        writer.join(2)
        state.filewriter = None


@pytest.mark.parametrize("halt", [False, True])
def test_api_reports_blocked_writer_as_output_error_and_keeps_other_runs_local(tmp_path, monkeypatch, halt):
    from execsql import api
    from execsql.db.sqlite import SQLiteDatabase

    entered, release = threading.Event(), threading.Event()
    target, later = tmp_path / "blocked.txt", tmp_path / "later.txt"
    real_open, original_deadline = builtins.open, fileio._writer_deadline
    real_start = api._start_filewriter
    writers, deadlines, wait_started = [], [], []

    def start(ctx, conf):
        real_start(ctx, conf)
        writers.append(ctx.filewriter)

    def deadline(fw, max_wait=None):
        deadlines.append(max_wait)
        wait_started.append(time.monotonic())
        return original_deadline(fw, 0.04)

    def blocked(*args, **kwargs):
        filename = kwargs.get("file", args[0] if args else "")
        if str(filename) == str(target):
            entered.set()
            assert release.wait(2)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(api, "_start_filewriter", start)
    monkeypatch.setattr(fileio, "open", blocked, raising=False)
    monkeypatch.setattr(fileio, "_writer_deadline", deadline)
    safety = threading.Timer(1, release.set)
    safety.start()
    db = SQLiteDatabase(":memory:")
    try:
        sql = f'-- !x! WRITE "first" TO "{target}"\n-- !x! WRITE "later" TO "{later}"\n'
        sql += "SELECT * FROM missing_table;" if halt else "SELECT 1;"
        result = api.run(sql=sql, connection=db)
        assert time.monotonic() - wait_started[0] <= 0.29
        assert not result.success
        output_errors = [
            error for error in result.errors if error.source == "<output>" and "File output lost" in error.message
        ]
        assert len(output_errors) == 1, result.errors
        if halt:
            from execsql.utils.errors import HALT_FLUSH_SECONDS

            assert HALT_FLUSH_SECONDS in deadlines
            assert any("missing_table" in error.message for error in result.errors)
        assert writers[0].abandoned.is_set()
        healthy = tmp_path / "healthy.txt"
        monkeypatch.setattr(fileio, "_writer_deadline", original_deadline)
        result = api.run(sql=f'-- !x! WRITE "healthy" TO "{healthy}"', connection=db)
        assert result.success, result.errors
        assert healthy.read_text() == "healthy\n"
        release.set()
        writers[0].join(2)
        assert not writers[0].is_alive()
        assert not later.exists()
    finally:
        release.set()
        safety.cancel()
        for writer in writers:
            fileio.filewriter_end(writer)
            writer.join(2)
        db.close()


def test_cli_timeout_reports_failure_and_exits_without_waiting_for_daemon(tmp_path):
    import os
    import subprocess
    import sys
    import textwrap

    script = tmp_path / "script.sql"
    script.write_text('-- !x! WRITE "lost" TO blocked.txt\nSELECT 1;\n')
    home = tmp_path / "home"
    home.mkdir()
    code = textwrap.dedent("""\
        import builtins, sys, threading
        import execsql.utils.fileio as fileio
        real_open = builtins.open
        real_deadline = fileio._writer_deadline
        def blocked(*args, **kwargs):
            filename = kwargs.get('file', args[0] if args else '')
            if str(filename).endswith('blocked.txt'):
                threading.Event().wait(30)
            return real_open(*args, **kwargs)
        fileio.open = blocked
        fileio._writer_deadline = lambda fw, max_wait=None: real_deadline(fw, 0.05)
        sys.argv = ['execsql', 'run', '-t', 'l', '-n', 'script.sql', 't.db']
        from execsql.cli import app
        app()
    """)
    env = os.environ.copy()
    env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), XDG_CONFIG_HOME=str(home / ".config"))
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert "File output lost" in result.stdout + result.stderr
    assert "blocked.txt" in result.stdout + result.stderr


@pytest.mark.parametrize("max_wait,expected", [(None, 6.0), (20, 6.0), (0.02, 0.02), (0, 0)])
def test_wait_policy_caps_one_deadline_at_open_timeout_plus_margin(max_wait, expected):
    writer = fileio.FileWriter(open_timeout=1)
    before = time.monotonic()
    deadline, wait = fileio._writer_deadline(writer, max_wait)
    after = time.monotonic()
    assert wait == expected
    assert before + expected <= deadline <= after + expected


def test_failed_write_command_retires_its_pending_destination(tmp_path, monkeypatch):
    target = tmp_path / "unavailable.txt"
    real_resolve = Path.resolve
    writer = fileio.FileWriter(open_timeout=1)

    def resolve(path, *args, **kwargs):
        if str(path) == str(target) and threading.current_thread() is writer:
            raise OSError("metadata unavailable")
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    state.filewriter = writer
    writer.start()
    try:
        fileio.filewriter_write(str(target), "lost\n")
        with pytest.raises(ErrInfo, match="metadata unavailable") as raised:
            fileio.filewriter_close_all_after_write(max_wait=1)
        assert "1 line(s)" in str(raised.value)
        assert not writer._pending
        assert not writer.abandoned.is_set(), "ordinary failures leave the writer available"
    finally:
        fileio.filewriter_end(writer)
        state.filewriter = None
