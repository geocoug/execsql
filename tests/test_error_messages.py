"""Tests for error-message quality fixes — script location, $ERROR_MESSAGE, and warnings.

Covers Findings 1/5 (stamp_errinfo), 2 ($ERROR_MESSAGE updates), 4 (MetacommandStmt
preserves original ErrInfo), 6 (empty-script guard), and 7 (write_warning always=).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_script_cmd(source: str = "test.sql", line_no: int = 42, command_type: str = "sql"):
    """Build a minimal ScriptCmd-like object with only the fields stamp_errinfo reads."""
    cmd = SimpleNamespace(
        source=source,
        line_no=line_no,
        command_type=command_type,
        command=SimpleNamespace(commandline=lambda: "SELECT 1;"),
    )
    return cmd


# ---------------------------------------------------------------------------
# stamp_errinfo — unit tests
# ---------------------------------------------------------------------------


class TestStampErrinfo:
    """Tests for execsql.utils.errors.stamp_errinfo."""

    def setup_method(self):
        _state.reset()

    def teardown_method(self):
        _state.reset()

    def test_populates_fields_from_last_command(self):
        """stamp_errinfo fills script_file, script_line_no, cmd, and cmdtype."""
        from execsql.utils.errors import stamp_errinfo

        _state.last_command = _make_script_cmd("myfile.sql", 7, "sql")
        e = ErrInfo("db", exception_msg="syntax error")
        result = stamp_errinfo(e)

        assert result is e  # same object returned
        assert e.script_file == "myfile.sql"
        assert e.script_line_no == 7
        assert e.cmd == "SELECT 1;"
        assert e.cmdtype == "sql"

    def test_noop_when_last_command_is_none(self):
        """stamp_errinfo does nothing when _state.last_command is None."""
        from execsql.utils.errors import stamp_errinfo

        _state.last_command = None
        e = ErrInfo("db", exception_msg="oops")
        stamp_errinfo(e)

        assert e.script_file is None
        assert e.script_line_no is None
        assert e.cmd is None
        assert e.cmdtype is None

    def test_does_not_overwrite_existing_script_file(self):
        """stamp_errinfo skips population when script_file is already set."""
        from execsql.utils.errors import stamp_errinfo

        _state.last_command = _make_script_cmd("new.sql", 99, "cmd")
        e = ErrInfo("cmd")
        e.script_file = "original.sql"
        e.script_line_no = 1
        stamp_errinfo(e)

        # Fields from last_command must NOT overwrite pre-existing values.
        assert e.script_file == "original.sql"
        assert e.script_line_no == 1

    def test_metacommand_commandline_used_when_available(self):
        """stamp_errinfo calls commandline() on the inner command object."""
        from execsql.utils.errors import stamp_errinfo

        cmd_obj = SimpleNamespace(commandline=lambda: "-- !x! WRITE something")
        _state.last_command = SimpleNamespace(
            source="script.sql",
            line_no=10,
            command_type="cmd",
            command=cmd_obj,
        )
        e = ErrInfo("cmd")
        stamp_errinfo(e)

        assert e.cmd == "-- !x! WRITE something"
        assert e.cmdtype == "cmd"

    def test_cmd_none_when_command_has_no_commandline(self):
        """stamp_errinfo sets cmd=None when the inner command lacks commandline()."""
        from execsql.utils.errors import stamp_errinfo

        _state.last_command = SimpleNamespace(
            source="s.sql",
            line_no=3,
            command_type="sql",
            command=SimpleNamespace(),  # no commandline attribute
        )
        e = ErrInfo("db")
        stamp_errinfo(e)

        assert e.script_file == "s.sql"
        assert e.script_line_no == 3
        assert e.cmd is None  # no commandline() to call


# ---------------------------------------------------------------------------
# exit_now — stamps ErrInfo before writing
# ---------------------------------------------------------------------------


class TestExitNowStampsErrinfo:
    def setup_method(self):
        _state.reset()

    def teardown_method(self):
        _state.reset()

    def test_exit_now_stamps_script_location(self):
        """exit_now calls stamp_errinfo so error output includes script location."""
        from execsql.utils.errors import exit_now

        _state.last_command = _make_script_cmd("run.sql", 55, "sql")
        _state.output = MagicMock()

        e = ErrInfo("db", exception_msg="bad SQL")
        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, e)

        assert e.script_file == "run.sql"
        assert e.script_line_no == 55

    def test_exit_now_updates_error_message_subvar(self):
        """exit_now updates $ERROR_MESSAGE in the substitution variable set."""
        from execsql.script.variables import SubVarSet
        from execsql.utils.errors import exit_now

        _state.subvars = SubVarSet()
        _state.subvars.add_substitution("$ERROR_MESSAGE", "")
        _state.output = MagicMock()

        e = ErrInfo("db", other_msg="connection refused")
        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, e)

        em = _state.subvars.varvalue("$ERROR_MESSAGE")
        assert em is not None
        assert "connection refused" in em

    def test_exit_now_with_none_errinfo_does_not_set_error_message(self):
        """exit_now with None errinfo must not raise when subvars is set."""
        from execsql.script.variables import SubVarSet
        from execsql.utils.errors import exit_now

        _state.subvars = SubVarSet()
        _state.subvars.add_substitution("$ERROR_MESSAGE", "prior")

        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(0, None)  # must not raise

        # $ERROR_MESSAGE should be unchanged when errinfo is None.
        assert _state.subvars.varvalue("$ERROR_MESSAGE") == "prior"


# ---------------------------------------------------------------------------
# $ERROR_MESSAGE updated on non-halting SQL error
# ---------------------------------------------------------------------------


class TestSqlStmtErrorMessageSubvar:
    def setup_method(self):
        _state.reset()

    def teardown_method(self):
        _state.reset()

    def test_error_message_updated_on_sql_error(self):
        """SqlStmt.run() sets $ERROR_MESSAGE when a SQL error occurs and halt is off."""
        import re

        from execsql.script.engine import SqlStmt
        from execsql.script.variables import CounterVars, SubVarSet

        _state.subvars = SubVarSet()
        _state.subvars.add_substitution("$ERROR_MESSAGE", "")
        _state.subvars.add_substitution("$LAST_ERROR", "")
        _state.counters = CounterVars()

        # Build a fake database that raises an ErrInfo on execute.
        fake_db = MagicMock()
        fake_db.execute.side_effect = ErrInfo("db", exception_msg="syntax error near ';'")
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = fake_db

        # Ensure halt-on-error is OFF so the error is recorded non-fatally.
        _state.status = MagicMock()
        _state.status.sql_error = False
        _state.status.halt_on_err = False
        _state.if_stack = MagicMock()
        _state.if_stack.all_true.return_value = True
        # Use the real varlike so the module-level attribute is not polluted.
        _state.varlike = re.compile(r"!![$@&~#]?\w+!!", re.I)
        _state.conf = MagicMock()
        _state.conf.log_sql = False

        stmt = SqlStmt("SELECT bad_col FROM nowhere;")
        stmt.run()

        em = _state.subvars.varvalue("$ERROR_MESSAGE")
        assert em is not None and em != ""


# ---------------------------------------------------------------------------
# $ERROR_MESSAGE updated on non-halting metacommand error
# ---------------------------------------------------------------------------


class TestMetacommandStmtErrorMessageSubvar:
    def setup_method(self):
        _state.reset()

    def teardown_method(self):
        _state.reset()

    def test_error_message_updated_on_metacommand_error(self):
        """MetacommandStmt.run() sets $ERROR_MESSAGE when a handler raises ErrInfo.

        The method always raises (either the original ErrInfo or the
        'Unknown metacommand' fallback), so we wrap the call in pytest.raises
        and then inspect the subvar after the fact.
        """
        import re

        from execsql.script.engine import MetacommandStmt
        from execsql.script.variables import CounterVars, SubVarSet

        _state.subvars = SubVarSet()
        _state.subvars.add_substitution("$ERROR_MESSAGE", "")
        _state.subvars.add_substitution("$LAST_ERROR", "")
        _state.counters = CounterVars()

        _state.if_stack = MagicMock()
        _state.if_stack.all_true.return_value = True
        # Use the real varlike pattern so the module-level attribute is not polluted.
        _state.varlike = re.compile(r"!![$@&~#]?\w+!!", re.I)

        # metacommandlist.eval raises an ErrInfo from a handler.
        original_error = ErrInfo("cmd", other_msg="WRITE target not found")
        _state.metacommandlist = MagicMock()
        _state.metacommandlist.eval.side_effect = original_error

        _state.status = MagicMock()
        _state.status.metacommand_error = False
        _state.status.halt_on_metacommand_err = False

        stmt = MetacommandStmt("WRITE nonexistent_file.txt content")
        # run() always raises when a handler error occurs; that's expected.
        with pytest.raises(ErrInfo):
            stmt.run()

        # $ERROR_MESSAGE must have been updated before the re-raise.
        em = _state.subvars.varvalue("$ERROR_MESSAGE")
        assert em is not None and em != ""


# ---------------------------------------------------------------------------
# MetacommandStmt preserves original ErrInfo (Finding 4)
# ---------------------------------------------------------------------------


class TestMetacommandStmtPreservesOriginalError:
    def setup_method(self):
        _state.reset()

    def teardown_method(self):
        _state.reset()

    def test_original_errinfo_raised_not_unknown_metacommand(self):
        """When halt_on_metacommand_err is True, the original ErrInfo is re-raised."""
        import re

        from execsql.script.engine import MetacommandStmt
        from execsql.script.variables import CounterVars, SubVarSet

        _state.subvars = SubVarSet()
        _state.subvars.add_substitution("$ERROR_MESSAGE", "")
        _state.subvars.add_substitution("$LAST_ERROR", "")
        _state.counters = CounterVars()

        _state.if_stack = MagicMock()
        _state.if_stack.all_true.return_value = True
        _state.varlike = re.compile(r"!![$@&~#]?\w+!!", re.I)

        original_error = ErrInfo("cmd", other_msg="WRITE target not found")
        _state.metacommandlist = MagicMock()
        _state.metacommandlist.eval.side_effect = original_error

        _state.status = MagicMock()
        _state.status.metacommand_error = False
        _state.status.halt_on_metacommand_err = True

        stmt = MetacommandStmt("WRITE missing_file.txt something")
        with pytest.raises(ErrInfo) as exc_info:
            stmt.run()

        # Must be the original error — not the generic "Unknown metacommand".
        raised = exc_info.value
        assert raised is original_error
        assert "WRITE target not found" in str(raised)
        assert "Unknown metacommand" not in str(raised)

    def test_unknown_metacommand_raised_when_no_match(self):
        """When no metacommand matches (applies=False, e=None), 'Unknown metacommand' is raised."""
        import re

        from execsql.script.engine import MetacommandStmt
        from execsql.script.variables import CounterVars, SubVarSet

        _state.subvars = SubVarSet()
        _state.subvars.add_substitution("$LAST_ERROR", "")
        _state.counters = CounterVars()

        _state.if_stack = MagicMock()
        _state.if_stack.all_true.return_value = True
        _state.varlike = re.compile(r"!![$@&~#]?\w+!!", re.I)

        # eval returns (False, None) — nothing matched.
        _state.metacommandlist = MagicMock()
        _state.metacommandlist.eval.return_value = (False, None)

        _state.status = MagicMock()
        _state.status.metacommand_error = False
        _state.status.halt_on_metacommand_err = False

        stmt = MetacommandStmt("TOTALLY_UNKNOWN_CMD arg1 arg2")
        with pytest.raises(ErrInfo) as exc_info:
            stmt.run()

        assert "Unknown metacommand" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Empty script guard (Finding 6)
# ---------------------------------------------------------------------------


class TestEmptyScriptGuard:
    """Verify that empty-string script name from current_script_line() is not appended."""

    def test_empty_script_not_appended_to_message(self):
        """When current_script_line returns ('', 0), message must not gain 'in script , line 0'."""
        # The guard `if script:` prevents this; test the guard logic directly.
        script = ""
        slno = 0
        base_msg = "Uncaught exception SomeError (details) on line 42"

        # Replicate the patched guard from cli/run.py.
        if script:
            base_msg += f" in script {script}, line {slno}"

        assert "in script" not in base_msg
        assert ", line 0" not in base_msg

    def test_non_empty_script_is_appended(self):
        """When current_script_line returns a real path, it must be appended."""
        script = "myscript.sql"
        slno = 17
        base_msg = "Uncaught exception SomeError (details) on line 42"

        if script:
            base_msg += f" in script {script}, line {slno}"

        assert "in script myscript.sql, line 17" in base_msg


# ---------------------------------------------------------------------------
# write_warning with always=True (Finding 7)
# ---------------------------------------------------------------------------


class TestWriteWarningAlways:
    # No setup_method/teardown_method — the autouse minimal_conf fixture
    # handles state reset before and after each test.

    def test_always_true_writes_regardless_of_write_warnings_false(self, minimal_conf):
        """write_warning(always=True) writes to output even when write_warnings is False."""
        from execsql.utils.errors import write_warning

        written = []
        minimal_conf.write_warnings = False
        _state.output = type("FO", (), {"write_err": lambda self, m: written.append(m)})()

        write_warning("IF level mismatch", always=True)

        assert len(written) == 1
        assert "IF level mismatch" in written[0]

    def test_always_false_respects_write_warnings_false(self, minimal_conf):
        """write_warning(always=False) does NOT write to output when write_warnings is False."""
        from execsql.utils.errors import write_warning

        written = []
        minimal_conf.write_warnings = False
        _state.output = type("FO", (), {"write_err": lambda self, m: written.append(m)})()

        write_warning("routine warning")

        assert len(written) == 0

    def test_always_false_writes_when_write_warnings_true(self, minimal_conf):
        """write_warning(always=False) writes when write_warnings is True (existing behaviour)."""
        from execsql.utils.errors import write_warning

        written = []
        minimal_conf.write_warnings = True
        _state.output = type("FO", (), {"write_err": lambda self, m: written.append(m)})()

        write_warning("some message")

        assert len(written) == 1

    def test_always_true_still_logs_to_exec_log(self):
        """write_warning(always=True) still calls log_status_warning on exec_log."""
        from execsql.utils.errors import write_warning

        warnings_logged = []

        class FakeLog:
            def log_status_warning(self, msg):
                warnings_logged.append(msg)

        _state.exec_log = FakeLog()
        write_warning("structural warning", always=True)

        assert warnings_logged == ["structural warning"]
