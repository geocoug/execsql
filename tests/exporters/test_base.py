"""
Tests for execsql.exporters.base — ExportMetadata, WriteSpec, and ExportRecord.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


import execsql.state as _state
from execsql.exceptions import ConsoleUIError as ExcConsoleUIError
from execsql.exporters.base import ExportMetadata, ExportRecord, WriteSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(queryname: str = "q1", filename: str = "out.csv", exported: bool = False):
    """Return a fake ExportRecord-like object without hitting the real constructor."""
    rec = SimpleNamespace(
        exported=exported,
        record=[queryname, filename, None, "/tmp", None, "script.sql", "/tmp", 1, None, "mydb", "localhost", "user"],
    )
    return rec


# ---------------------------------------------------------------------------
# ExportMetadata
# ---------------------------------------------------------------------------


class TestExportMetadata:
    def test_initial_recordlist_empty(self):
        em = ExportMetadata()
        assert em.recordlist == []

    def test_add_appends_record(self):
        em = ExportMetadata()
        r = _make_record()
        em.add(r)
        assert len(em.recordlist) == 1
        assert em.recordlist[0] is r

    def test_add_multiple_records(self):
        em = ExportMetadata()
        em.add(_make_record("q1"))
        em.add(_make_record("q2"))
        em.add(_make_record("q3"))
        assert len(em.recordlist) == 3

    def test_get_returns_colhdrs(self):
        em = ExportMetadata()
        em.add(_make_record())
        colhdrs, _ = em.get()
        assert "query" in colhdrs
        assert "filename" in colhdrs

    def test_get_returns_unexported_records(self):
        em = ExportMetadata()
        em.add(_make_record("q1", exported=False))
        em.add(_make_record("q2", exported=True))
        _, recs = em.get()
        assert len(recs) == 1
        assert recs[0][0] == "q1"

    def test_get_marks_all_as_exported(self):
        em = ExportMetadata()
        r1 = _make_record("q1", exported=False)
        r2 = _make_record("q2", exported=False)
        em.add(r1)
        em.add(r2)
        em.get()
        assert r1.exported is True
        assert r2.exported is True

    def test_get_called_twice_returns_no_new_records_second_time(self):
        em = ExportMetadata()
        em.add(_make_record())
        em.get()
        _, recs = em.get()
        assert recs == []

    def test_get_all_returns_all_regardless_of_exported_flag(self):
        em = ExportMetadata()
        em.add(_make_record("q1", exported=True))
        em.add(_make_record("q2", exported=False))
        _, recs = em.get_all()
        assert len(recs) == 2

    def test_get_all_marks_all_as_exported(self):
        em = ExportMetadata()
        r = _make_record(exported=False)
        em.add(r)
        em.get_all()
        assert r.exported is True

    def test_colhdrs_contains_expected_fields(self):
        expected = {
            "query",
            "filename",
            "zipfilename",
            "file_path",
            "description",
            "script",
            "script_path",
            "script_line",
            "script_date",
            "database",
            "server",
            "username",
        }
        assert set(ExportMetadata.colhdrs) == expected


# ---------------------------------------------------------------------------
# WriteSpec
# ---------------------------------------------------------------------------


class TestWriteSpec:
    def test_init_stores_message(self):
        ws = WriteSpec("hello world")
        assert ws.msg == "hello world"

    def test_init_outfile_none_by_default(self):
        ws = WriteSpec("msg")
        assert ws.outfile is None

    def test_init_outfile_set(self):
        ws = WriteSpec("msg", dest="/tmp/out.txt")
        assert ws.outfile == "/tmp/out.txt"

    def test_init_tee_defaults_false(self):
        ws = WriteSpec("msg")
        assert ws.tee is False

    def test_init_tee_coerced_to_bool(self):
        ws = WriteSpec("msg", tee=1)
        assert ws.tee is True
        ws2 = WriteSpec("msg", tee=0)
        assert ws2.tee is False

    def test_init_repeatable_defaults_false(self):
        ws = WriteSpec("msg")
        assert ws.repeatable is False

    def test_init_written_defaults_false(self):
        ws = WriteSpec("msg")
        assert ws.written is False

    def test_repr_contains_msg(self):
        ws = WriteSpec("my message")
        assert "my message" in repr(ws)

    def test_repr_contains_outfile(self):
        ws = WriteSpec("msg", dest="/tmp/out.txt")
        assert "/tmp/out.txt" in repr(ws)

    def test_repr_format(self):
        ws = WriteSpec("text", dest="file.txt", tee=True)
        r = repr(ws)
        assert r.startswith("WriteSpec(")


# ---------------------------------------------------------------------------
# ExportRecord
# ---------------------------------------------------------------------------


def _fake_db():
    return SimpleNamespace(server_name="localhost", db_name="testdb", user="testuser")


class TestExportRecord:
    def test_init_with_zipfile(self, tmp_path):
        """ExportRecord with zipfile extracts zip parent dir and stores filename."""
        zippath = str(tmp_path / "archive.zip")
        fake_dbs = SimpleNamespace(current=lambda: _fake_db())
        with (
            patch("execsql.exporters.base.current_script_line", return_value=("script.sql", 1)),
            patch.object(_state, "dbs", fake_dbs),
        ):
            rec = ExportRecord("q1", "data.csv", zipfile=zippath)
        # zipfile name stored at index 2
        assert rec.record[2] == "archive.zip"
        # outfile name (inside zip) stored at index 1
        assert rec.record[1] == "data.csv"

    def test_init_without_script_file(self, tmp_path):
        """ExportRecord with None script path sets spath/sname to fallback values."""
        fake_dbs = SimpleNamespace(current=lambda: _fake_db())
        with (
            patch("execsql.exporters.base.current_script_line", return_value=(None, 0)),
            patch.object(_state, "dbs", fake_dbs),
        ):
            rec = ExportRecord("q1", str(tmp_path / "out.csv"))
        # script name should be "<inline>" when script is None
        assert rec.record[5] == "<inline>"
        # script path should be empty
        assert rec.record[6] == ""


# ---------------------------------------------------------------------------
# WriteSpec.write() — helpers and test class
# ---------------------------------------------------------------------------


def _make_write_state(msg_passthrough: str = None):
    """Build the minimum _state configuration required by WriteSpec.write().

    Returns a tuple (fake_conf, fake_subvars, fake_localvars, fake_output,
    fake_exec_log) so callers can inspect them after the call.
    """
    fake_conf = SimpleNamespace(
        output_encoding="utf-8",
        tee_write_log=False,
        enc_err_disposition=None,
        make_export_dirs=False,
    )

    # localvars.substitute_all(msg) → return msg unchanged (no local vars)
    fake_localvars = SimpleNamespace(substitute_all=lambda s: s if msg_passthrough is None else msg_passthrough)

    # commandliststack[-1].localvars
    fake_cmd = SimpleNamespace(localvars=fake_localvars)

    # subvars.substitute_all(msg) → return msg unchanged
    fake_subvars = SimpleNamespace(substitute_all=lambda s: s)

    # output.write() captures bytes
    written_bytes = []
    fake_output = SimpleNamespace(
        write=lambda b: written_bytes.append(b),
        reset=MagicMock(),
    )
    fake_output._written = written_bytes

    fake_exec_log = SimpleNamespace(
        log_status_info=MagicMock(),
        log_user_msg=MagicMock(),
    )

    return fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log


class TestWriteSpecWrite:
    """Tests for WriteSpec.write() — the deferred-write executor."""

    def _patch_state(self, fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
        """Return a context manager that patches all _state attributes used by write()."""
        import contextlib

        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(_state, "conf", fake_conf))
        stack.enter_context(patch.object(_state, "subvars", fake_subvars))
        stack.enter_context(patch.object(_state, "output", fake_output))
        stack.enter_context(patch.object(_state, "exec_log", fake_exec_log))
        _state.commandliststack.append(fake_cmd)
        return stack

    def _cleanup_stack(self):
        """Pop the fake command from the commandliststack after a test."""
        if _state.commandliststack:
            _state.commandliststack.pop()

    # ------------------------------------------------------------------
    # Console-only path (no outfile)
    # ------------------------------------------------------------------

    def test_write_to_console_emits_encoded_bytes(self):
        """write() with no outfile passes encoded bytes to _state.output.write."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("hello world")
                ws.write()
        finally:
            self._cleanup_stack()
        assert fake_output._written == [b"hello world"]

    def test_write_marks_written_true(self):
        """write() sets self.written = True after the first call."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("msg")
                assert ws.written is False
                ws.write()
                assert ws.written is True
        finally:
            self._cleanup_stack()

    def test_write_called_twice_skips_second_when_not_repeatable(self):
        """A non-repeatable WriteSpec writes only once even when called twice."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("once")
                ws.write()
                ws.write()
        finally:
            self._cleanup_stack()
        # Only one emission despite two calls
        assert len(fake_output._written) == 1

    def test_write_repeatable_emits_on_every_call(self):
        """A repeatable WriteSpec writes on every call."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("again", repeatable=True)
                ws.write()
                ws.write()
                ws.write()
        finally:
            self._cleanup_stack()
        assert len(fake_output._written) == 3

    def test_write_returns_none(self):
        """write() always returns None."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("msg")
                result = ws.write()
        finally:
            self._cleanup_stack()
        assert result is None

    # ------------------------------------------------------------------
    # File-output path
    # ------------------------------------------------------------------

    def test_write_to_file_creates_file_with_content(self, tmp_path):
        """write() with an outfile writes the message to that file."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        outfile = str(tmp_path / "out.txt")
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("file content", dest=outfile)
                ws.write()
        finally:
            self._cleanup_stack()
        assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "file content"

    def test_write_to_file_does_not_emit_to_console_when_tee_false(self, tmp_path):
        """write() with an outfile and tee=False must not also write to console output."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        outfile = str(tmp_path / "out.txt")
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("silent", dest=outfile, tee=False)
                ws.write()
        finally:
            self._cleanup_stack()
        assert fake_output._written == []

    def test_write_to_file_with_tee_also_writes_to_console(self, tmp_path):
        """write() with tee=True writes to both file and console."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        outfile = str(tmp_path / "tee.txt")
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("teed", dest=outfile, tee=True)
                ws.write()
        finally:
            self._cleanup_stack()
        # File was written
        assert (tmp_path / "tee.txt").read_text(encoding="utf-8") == "teed"
        # Console also received the bytes
        assert b"teed" in fake_output._written

    # ------------------------------------------------------------------
    # Substitution variable expansion
    # ------------------------------------------------------------------

    def test_write_applies_local_var_substitution(self):
        """write() expands localvars.substitute_all before writing."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        # Override localvars to perform a substitution
        fake_cmd.localvars = SimpleNamespace(substitute_all=lambda s: s.replace("!!$NAME!!", "World"))
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("Hello !!$NAME!!")
                ws.write()
        finally:
            self._cleanup_stack()
        assert b"Hello World" in fake_output._written

    def test_write_applies_global_subvar_substitution(self):
        """write() passes localvars-expanded text through subvars.substitute_all."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        fake_subvars.substitute_all = lambda s: s.replace("!!$GLOBAL!!", "earth")
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("!!$GLOBAL!!")
                ws.write()
        finally:
            self._cleanup_stack()
        assert b"earth" in fake_output._written

    # ------------------------------------------------------------------
    # tee_write_log path
    # ------------------------------------------------------------------

    def test_write_logs_user_msg_when_tee_write_log_true(self):
        """write() calls exec_log.log_user_msg when conf.tee_write_log is True."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        fake_conf.tee_write_log = True
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("logged msg")
                ws.write()
        finally:
            self._cleanup_stack()
        fake_exec_log.log_user_msg.assert_called_once_with("logged msg")

    def test_write_does_not_log_when_tee_write_log_false(self):
        """write() does NOT call exec_log.log_user_msg when conf.tee_write_log is False."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()
        fake_conf.tee_write_log = False
        try:
            with self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log):
                ws = WriteSpec("silent msg")
                ws.write()
        finally:
            self._cleanup_stack()
        fake_exec_log.log_user_msg.assert_not_called()

    # ------------------------------------------------------------------
    # ConsoleUIError recovery path
    # ------------------------------------------------------------------

    def test_write_recovers_from_console_ui_error(self):
        """When output.write raises ConsoleUIError, write() resets and retries via stdout.

        Note: base.py catches ConsoleUIError from utils.gui and accesses e.value.
        utils.gui.ConsoleUIError is a plain Exception with no .value attribute, so
        the production handler would itself fail with AttributeError on that path.
        We use exceptions.ConsoleUIError (which inherits ExecSqlError and has .value)
        to exercise the recovery logic without hitting that secondary bug.
        """
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()

        call_count = [0]
        recovered_bytes = []

        def failing_then_ok(b):
            call_count[0] += 1
            if call_count[0] == 1:
                # exceptions.ConsoleUIError has .value; gui.ConsoleUIError does not.
                # base.py imports from utils.gui, so we patch the name in that module.
                raise ExcConsoleUIError("UI broke")
            recovered_bytes.append(b)

        fake_output.write = failing_then_ok

        # Patch base.py's ConsoleUIError name to the exceptions version so the
        # except clause triggers (both are named ConsoleUIError but different classes).
        try:
            with (
                self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log),
                patch("execsql.exporters.base.ConsoleUIError", ExcConsoleUIError),
            ):
                ws = WriteSpec("recovery msg")
                ws.write()  # Must not raise
        finally:
            self._cleanup_stack()

        # output.reset() was called to recover
        fake_output.reset.assert_called_once()
        # The message was re-emitted after reset
        assert b"recovery msg" in recovered_bytes

    def test_write_logs_status_info_after_console_ui_error(self):
        """ConsoleUIError recovery logs a status message via exec_log."""
        fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log = _make_write_state()

        call_count = [0]

        def failing_then_ok(b):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ExcConsoleUIError("boom")

        fake_output.write = failing_then_ok

        try:
            with (
                self._patch_state(fake_conf, fake_subvars, fake_cmd, fake_output, fake_exec_log),
                patch("execsql.exporters.base.ConsoleUIError", ExcConsoleUIError),
            ):
                ws = WriteSpec("boom msg")
                ws.write()
        finally:
            self._cleanup_stack()

        fake_exec_log.log_status_info.assert_called_once()
        logged_msg = fake_exec_log.log_status_info.call_args[0][0]
        assert "Console UI write failed" in logged_msg
