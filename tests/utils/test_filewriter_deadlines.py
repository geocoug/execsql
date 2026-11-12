"""A stalled output worker cannot hold callers or start later writes after abandonment."""

from __future__ import annotations

import builtins
import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace

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


@pytest.mark.parametrize("action", ["write", "new", "status", "close"])
def test_public_writer_calls_never_resolve_on_the_caller(tmp_path, monkeypatch, action):
    caller = threading.current_thread()
    caller_resolved = threading.Event()
    real_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        if threading.current_thread() is caller:
            caller_resolved.set()
            raise OSError("filesystem metadata is unavailable on the caller")
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    writer = fileio.FileWriter(open_timeout=1)
    state.filewriter = writer
    writer.start()
    target = str(tmp_path / "out.txt")
    try:
        if action == "write":
            fileio.filewriter_write(target, "line\n")
        elif action == "new":
            fileio.filewriter_open_as_new(target)
        elif action == "status":
            fileio.filewriter_filestatus(target)
        else:
            fileio.filewriter_close(target)
        fileio.filewriter_close_all_after_write(max_wait=1)
        assert not caller_resolved.is_set()
    finally:
        fileio.filewriter_end(writer)
        state.filewriter = None


def test_resolved_aliases_retire_pending_writes_and_share_one_handle(tmp_path):
    (tmp_path / "sub").mkdir()
    target = tmp_path / "out.txt"
    alias = tmp_path / "sub" / ".." / "out.txt"
    writer = fileio.FileWriter(open_timeout=1)
    state.filewriter = writer
    writer.start()
    try:
        for path in (alias, target, alias, target):
            fileio.filewriter_write(str(path), "line\n")
        fileio.filewriter_close_all_after_write(max_wait=1)
        assert target.read_text() == "line\n" * 4
        assert len(writer.files) == 1
        assert not writer._pending
    finally:
        fileio.filewriter_end(writer)
        state.filewriter = None


def test_relative_write_keeps_its_directory_until_worker_resolution(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.chdir(first)
    entered, release = threading.Event(), threading.Event()
    real_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        if threading.current_thread() is writer:
            entered.set()
            assert release.wait(2)
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    writer = fileio.FileWriter(open_timeout=1)
    state.filewriter = writer
    writer.start()
    try:
        fileio.filewriter_write("out.txt", "first\n")
        assert entered.wait(1)
        monkeypatch.chdir(second)
        release.set()
        fileio.filewriter_close_all_after_write(max_wait=1)
        assert (first / "out.txt").read_text() == "first\n"
        assert not (second / "out.txt").exists()
        assert not writer._pending
    finally:
        release.set()
        fileio.filewriter_end(writer)
        writer.join(2)
        state.filewriter = None


@pytest.mark.parametrize("phase", ["resolve", "open", "write", "flush", "close", "failures"])
def test_flush_deadline_bounds_live_worker_and_prevents_later_output(tmp_path, monkeypatch, phase):
    entered, release = threading.Event(), threading.Event()
    calls = []
    target, later = tmp_path / "blocked.txt", tmp_path / "later.txt"
    real_open = builtins.open
    real_resolve = Path.resolve
    real_failures = fileio.FileWriter.open_failures
    real_reply = fileio._writer_reply
    reply_count = 0

    def reply(fw, deadline, wait):
        nonlocal reply_count
        if phase == "close" or (phase == "failures" and reply_count == 1):
            assert entered.wait(2), "worker did not reach the selected I/O gate"
        reply_count += 1
        return real_reply(fw, deadline, wait)

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
    monkeypatch.setattr(fileio, "_writer_reply", reply)
    if phase == "failures":
        monkeypatch.setattr(fileio.FileWriter, "open_failures", failures)
    writer = fileio.FileWriter(open_timeout=1)
    state.filewriter = writer
    writer.start()
    try:
        fileio.filewriter_write(str(target), "first\n")
        if phase in ("resolve", "open", "write", "flush"):
            assert entered.wait(2)
            fileio.filewriter_write(str(target), "second\n")
            fileio.filewriter_write(str(later), "later\n")
        # Exact deadline budgets are checked with a controlled clock below.
        # This live test proves return while the I/O gate is still held.
        with pytest.raises(ErrInfo, match="File output lost") as raised:
            fileio.filewriter_close_all_after_write(max_wait=0.04)
        assert entered.is_set()
        assert writer.is_alive(), "the blocked thread must not be claimed to have stopped"
        assert writer.abandoned.is_set()
        if phase != "failures":
            assert str(target) in str(raised.value)
        if phase in ("resolve", "open", "write", "flush"):
            assert str(later) in str(raised.value)
        # Detaching an abandoned worker must not join it for a second wait.
        joins = []
        with monkeypatch.context() as patch:
            patch.setattr(writer, "join", lambda *args, **kwargs: joins.append((args, kwargs)))
            fileio.filewriter_end(writer)
        assert not joins
        assert state.filewriter is None
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
        writer.join(2)
        fileio.filewriter_end(writer)
        state.filewriter = None


@pytest.mark.parametrize("blocked_at", ["closed_status", "status_open", "failure_report"])
def test_flush_uses_one_absolute_deadline_without_waiting_past_it(monkeypatch, blocked_at):
    writer = fileio.FileWriter(open_timeout=1)
    now = 100.0
    waits, deadlines = [], []
    real_reply = fileio._writer_reply
    writer.current_op = (blocked_at, "blocked.txt", now)

    def advance(seconds):
        nonlocal now
        now += seconds

    def reply(fw, deadline, wait):
        deadlines.append(deadline)
        return real_reply(fw, deadline, wait)

    def get(timeout):
        assert len(waits) < 20, "flush reset its deadline instead of expiring"
        assert timeout > 0
        assert timeout <= 100.04 - now + 1e-9, "a reply wait exceeded the remaining deadline"
        waits.append(timeout)
        if len(waits) == 1:
            if blocked_at == "status_open":
                return fileio.FileWriter.FileControl.STATUS_OPEN
            if blocked_at == "failure_report":
                return fileio.FileWriter.FileControl.STATUS_CLOSED
        advance(timeout)
        raise queue.Empty

    monkeypatch.setattr(fileio, "time", SimpleNamespace(monotonic=lambda: now, sleep=advance))
    monkeypatch.setattr(fileio, "_active_writer", lambda: writer)
    monkeypatch.setattr(writer, "is_alive", lambda: True)
    monkeypatch.setattr(writer.return_msg_queue, "get", get)
    monkeypatch.setattr(fileio, "_writer_reply", reply)
    with pytest.raises(ErrInfo, match="File output lost"):
        fileio.filewriter_close_all_after_write(max_wait=0.04)
    assert now == pytest.approx(100.04)
    assert all(deadline == pytest.approx(100.04) for deadline in deadlines)
    assert writer.abandoned.is_set()


@pytest.mark.parametrize("entrypoint", ["status", "close"])
def test_public_path_waits_use_the_default_absolute_deadline(tmp_path, monkeypatch, entrypoint):
    # A controlled clock checks the actual six-second default, without making
    # scheduler latency on a loaded CI runner part of the assertion.
    target = str(tmp_path / "blocked.txt")
    writer = fileio.FileWriter(open_timeout=1)
    now = 100.0
    waits, defaults = [], []
    original_deadline = fileio._writer_deadline

    def advance(seconds):
        nonlocal now
        now += seconds

    def deadline(fw, max_wait=None):
        defaults.append(max_wait)
        return original_deadline(fw, max_wait)

    def reply(timeout):
        waits.append(timeout)
        assert len(waits) < 200, "the public call reset its deadline while polling"
        if entrypoint == "close" and len(waits) == 1:
            return fileio.FileWriter.FileControl.STATUS_OPEN
        advance(timeout)
        raise queue.Empty

    writer.current_op = ("open" if entrypoint == "status" else "close", target, now)
    monkeypatch.setattr(fileio, "time", SimpleNamespace(monotonic=lambda: now, sleep=advance))
    monkeypatch.setattr(fileio, "_active_writer", lambda: writer)
    monkeypatch.setattr(writer, "is_alive", lambda: True)
    monkeypatch.setattr(writer.return_msg_queue, "get", reply)
    monkeypatch.setattr(fileio, "_writer_deadline", deadline)
    action = fileio.filewriter_filestatus if entrypoint == "status" else fileio.filewriter_close
    with pytest.raises(ErrInfo, match="File output lost") as raised:
        action(target)
    assert defaults == [None], "the public call must use one default deadline"
    assert now == pytest.approx(106.0)
    assert all(0 < wait <= 0.05 for wait in waits)
    assert writer.abandoned.is_set()
    assert ("open" if entrypoint == "status" else "close") in str(raised.value)
    assert target in str(raised.value)


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
        if deadlines:
            assert failure_entered.wait(2), "worker did not reach failure reporting"
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
    try:
        fileio.filewriter_write(str(tmp_path / "out.txt"), "line\n")
        with pytest.raises(ErrInfo, match="File output lost"):
            fileio.filewriter_close_all_after_write(max_wait=0.5)
        assert failure_entered.is_set()
        assert len(deadlines) == 2
        assert deadlines[0] == deadlines[1], "status and failure collection must reuse the same deadline"
    finally:
        release.set()
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
    writers, deadlines = [], []

    def start(ctx, conf):
        real_start(ctx, conf)
        writers.append(ctx.filewriter)

    def deadline(fw, max_wait=None):
        deadlines.append(max_wait)
        assert entered.wait(2), "worker did not reach the blocked output file"
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
    db = SQLiteDatabase(":memory:")
    try:
        sql = f'-- !x! WRITE "first" TO "{target}"\n-- !x! WRITE "later" TO "{later}"\n'
        sql += "SELECT * FROM missing_table;" if halt else "SELECT 1;"
        result = api.run(sql=sql, connection=db)
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
        assert writers[0].is_alive(), "the API must return while its writer is blocked"
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
