"""Extended unit tests for execsql metacommand handlers.

These tests focus on unit-testing individual handler functions using mocks
rather than running the full CLI pipeline. They target code paths not covered
by the integration tests in test_metacommands.py.

Coverage targets:
- metacommands/data.py
- metacommands/system.py
- metacommands/control.py
- metacommands/debug.py
- metacommands/script_ext.py
- metacommands/io.py (helper functions, parsers, validation logic)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script import (
    SubVarSet,
    LocalSubVarSet,
    CounterVars,
    IfLevels,
    BatchLevels,
)


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _make_subvars() -> SubVarSet:
    """Create a fresh SubVarSet."""
    sv = SubVarSet()
    sv.compile_var_rx()
    return sv


def _mock_commandlist(name: str = "test") -> MagicMock:
    """Return a mock CommandList with a localvars attribute."""
    cl = MagicMock()
    cl.listname = name
    cl.paramnames = None
    cl.cmdptr = 0
    cl.init_if_level = 0
    lv = LocalSubVarSet()
    cl.localvars = lv
    return cl


def _make_state_subvars():
    """Install a fresh SubVarSet in _state.subvars and return it."""
    sv = _make_subvars()
    _state.subvars = sv
    return sv


# ---------------------------------------------------------------------------
# Tests for metacommands/data.py -- flag-setting handlers
# ---------------------------------------------------------------------------


class TestDataFlagSetters:
    """Tests for the simple flag-setting metacommand handlers in data.py."""

    def test_x_empty_strings_yes(self, minimal_conf):
        from execsql.metacommands.data import x_empty_strings

        minimal_conf.empty_strings = False
        x_empty_strings(yesno="yes")
        assert minimal_conf.empty_strings is True

    def test_x_empty_strings_no(self, minimal_conf):
        from execsql.metacommands.data import x_empty_strings

        minimal_conf.empty_strings = True
        x_empty_strings(yesno="no")
        assert minimal_conf.empty_strings is False

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("yes", True),
            ("on", True),
            ("true", True),
            ("1", True),
            ("no", False),
            ("off", False),
            ("false", False),
            ("0", False),
        ],
    )
    def test_x_trim_strings(self, minimal_conf, value, expected):
        from execsql.metacommands.data import x_trim_strings

        x_trim_strings(yesno=value)
        assert minimal_conf.trim_strings is expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("yes", True),
            ("on", True),
            ("true", True),
            ("1", True),
            ("no", False),
            ("off", False),
            ("false", False),
            ("0", False),
        ],
    )
    def test_x_replace_newlines(self, minimal_conf, value, expected):
        from execsql.metacommands.data import x_replace_newlines

        x_replace_newlines(yesno=value)
        assert minimal_conf.replace_newlines is expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("yes", True),
            ("no", False),
            ("on", True),
            ("off", False),
        ],
    )
    def test_x_only_strings(self, minimal_conf, value, expected):
        from execsql.metacommands.data import x_only_strings

        x_only_strings(yesno=value)
        assert minimal_conf.only_strings is expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("yes", True),
            ("no", False),
        ],
    )
    def test_x_boolean_int(self, minimal_conf, value, expected):
        from execsql.metacommands.data import x_boolean_int

        x_boolean_int(yesno=value)
        assert minimal_conf.boolean_int is expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("yes", True),
            ("no", False),
        ],
    )
    def test_x_boolean_words(self, minimal_conf, value, expected):
        from execsql.metacommands.data import x_boolean_words

        x_boolean_words(yesno=value)
        assert minimal_conf.boolean_words is expected

    def test_x_fold_col_hdrs(self, minimal_conf):
        from execsql.metacommands.data import x_fold_col_hdrs

        x_fold_col_hdrs(foldspec="upper")
        assert minimal_conf.fold_col_hdrs == "upper"

    def test_x_trim_col_hdrs(self, minimal_conf):
        from execsql.metacommands.data import x_trim_col_hdrs

        x_trim_col_hdrs(which="Both")
        assert minimal_conf.trim_col_hdrs == "both"

    def test_x_clean_col_hdrs(self, minimal_conf):
        from execsql.metacommands.data import x_clean_col_hdrs

        x_clean_col_hdrs(yesno="yes")
        assert minimal_conf.clean_col_hdrs is True

    def test_x_del_empty_cols(self, minimal_conf):
        from execsql.metacommands.data import x_del_empty_cols

        x_del_empty_cols(yesno="on")
        assert minimal_conf.del_empty_cols is True

    def test_x_create_col_hdrs(self, minimal_conf):
        from execsql.metacommands.data import x_create_col_hdrs

        x_create_col_hdrs(yesno="true")
        assert minimal_conf.create_col_hdrs is True

    def test_x_dedup_col_hdrs(self, minimal_conf):
        from execsql.metacommands.data import x_dedup_col_hdrs

        x_dedup_col_hdrs(yesno="1")
        assert minimal_conf.dedup_col_hdrs is True

    def test_x_import_common_cols_only(self, minimal_conf):
        from execsql.metacommands.data import x_import_common_cols_only

        x_import_common_cols_only(yesno="yes")
        assert minimal_conf.import_common_cols_only is True

    def test_x_quote_all_text(self, minimal_conf):
        from execsql.metacommands.data import x_quote_all_text

        x_quote_all_text(setting="yes")
        assert minimal_conf.quote_all_text is True

    def test_x_max_int(self, minimal_conf):
        from execsql.metacommands.data import x_max_int

        x_max_int(maxint="9999999")
        assert minimal_conf.max_int == 9999999

    def test_x_empty_rows(self, minimal_conf):
        from execsql.metacommands.data import x_empty_rows

        x_empty_rows(yesno="yes")
        assert minimal_conf.empty_rows is True


class TestDataCounterOps:
    """Tests for counter-related metacommands."""

    def setup_method(self):
        """Install fresh CounterVars in _state.counters."""
        _state.counters = CounterVars()

    def teardown_method(self):
        _state.counters = None

    def test_x_reset_counter(self):
        from execsql.metacommands.data import x_reset_counter

        _state.counters.set_counter(1, 42)
        assert _state.counters.counters.get("counter_1") == 42
        x_reset_counter(counter_no="1")
        assert "counter_1" not in _state.counters.counters

    def test_x_reset_counters(self):
        from execsql.metacommands.data import x_reset_counters

        _state.counters.set_counter(1, 1)
        _state.counters.set_counter(2, 2)
        x_reset_counters()
        assert _state.counters.counters == {}

    def test_x_set_counter(self, minimal_conf):
        from execsql.metacommands.data import x_set_counter

        x_set_counter(counter_no="3", value="7")
        assert _state.counters.counters.get("counter_3") == 7

    def test_x_set_counter_expression(self, minimal_conf):
        from execsql.metacommands.data import x_set_counter

        # Expression like "2 + 3" should evaluate to 5
        x_set_counter(counter_no="1", value="2 + 3")
        assert _state.counters.counters.get("counter_1") == 5


class TestDataSubVarOps:
    """Tests for substitution-variable metacommands in data.py."""

    def setup_method(self):
        sv = _make_subvars()
        _state.subvars = sv
        cl = _mock_commandlist()
        _state.commandliststack = [cl]

    def teardown_method(self):
        _state.subvars = None
        _state.commandliststack = []

    def test_x_sub(self):
        from execsql.metacommands.data import x_sub

        with patch("execsql.metacommands.data.get_subvarset", return_value=(_state.subvars, "myvar")):
            x_sub(match="myvar", repl="hello", metacommandline="sub myvar hello")
        assert _state.subvars.varvalue("myvar") == "hello"

    def test_x_sub_empty(self):
        from execsql.metacommands.data import x_sub_empty

        with patch("execsql.metacommands.data.get_subvarset", return_value=(_state.subvars, "emptyvar")):
            x_sub_empty(match="emptyvar", metacommandline="sub_empty emptyvar")
        assert _state.subvars.varvalue("emptyvar") == ""

    def test_x_sub_append_new_var(self):
        from execsql.metacommands.data import x_sub_append

        with patch("execsql.metacommands.data.get_subvarset", return_value=(_state.subvars, "myvar")):
            x_sub_append(match="myvar", repl="first", metacommandline="sub_append myvar first")
        assert _state.subvars.varvalue("myvar") == "first"

    def test_x_sub_append_existing_var(self):
        from execsql.metacommands.data import x_sub_append

        _state.subvars.add_substitution("myvar", "first")
        with patch("execsql.metacommands.data.get_subvarset", return_value=(_state.subvars, "myvar")):
            x_sub_append(match="myvar", repl="second", metacommandline="sub_append myvar second")
        assert _state.subvars.varvalue("myvar") == "first\nsecond"

    def test_x_rm_sub_global(self):
        from execsql.metacommands.data import x_rm_sub

        _state.subvars.add_substitution("delme", "val")
        assert _state.subvars.sub_exists("delme")
        x_rm_sub(match="delme")
        assert not _state.subvars.sub_exists("delme")

    def test_x_rm_sub_local(self):
        from execsql.metacommands.data import x_rm_sub

        lv = _state.commandliststack[-1].localvars
        lv.add_substitution("~localvar", "val")
        assert lv.sub_exists("~localvar")
        x_rm_sub(match="~localvar")
        assert not lv.sub_exists("~localvar")

    def test_x_sub_local_adds_tilde_prefix(self):
        from execsql.metacommands.data import x_sub_local

        lv = _state.commandliststack[-1].localvars
        x_sub_local(match="noprefix", repl="thevalue")
        # The function should prepend ~ if not present
        assert lv.sub_exists("~noprefix")
        assert lv.varvalue("~noprefix") == "thevalue"

    def test_x_sub_local_already_tilde(self):
        from execsql.metacommands.data import x_sub_local

        lv = _state.commandliststack[-1].localvars
        x_sub_local(match="~alreadytilde", repl="val")
        assert lv.varvalue("~alreadytilde") == "val"

    def test_x_sub_querystring(self):
        from execsql.metacommands.data import x_sub_querystring

        x_sub_querystring(qstr="foo=bar&baz=qux")
        assert _state.subvars.varvalue("foo") == "bar"
        assert _state.subvars.varvalue("baz") == "qux"

    def test_x_sub_add(self, minimal_conf):
        from execsql.metacommands.data import x_sub_add

        _state.subvars.add_substitution("mycount", "10")
        with patch("execsql.metacommands.data.get_subvarset", return_value=(_state.subvars, "mycount")):
            x_sub_add(match="mycount", increment="5", metacommandline="sub_add mycount 5")
        assert _state.subvars.varvalue("mycount") == "15"

    def test_x_sub_ini_valid_section(self, tmp_path):
        from execsql.metacommands.data import x_sub_ini

        ini_file = tmp_path / "test.ini"
        ini_file.write_text("[mysection]\nfoo=bar\nbaz=qux\n")
        x_sub_ini(filename=str(ini_file), section="mysection")
        assert _state.subvars.varvalue("foo") == "bar"
        assert _state.subvars.varvalue("baz") == "qux"

    def test_x_sub_ini_missing_section(self, tmp_path):
        from execsql.metacommands.data import x_sub_ini

        ini_file = tmp_path / "test.ini"
        ini_file.write_text("[other]\nfoo=bar\n")
        # No error should be raised, just no variables set
        x_sub_ini(filename=str(ini_file), section="nosection")
        assert not _state.subvars.sub_exists("foo")


# ---------------------------------------------------------------------------
# Tests for metacommands/system.py
# ---------------------------------------------------------------------------


class TestSystemHandlers:
    """Tests for system.py metacommand handlers."""

    def setup_method(self):
        sv = _make_subvars()
        _state.subvars = sv
        _state.exec_log = MagicMock()
        _state.output = MagicMock()
        _state.status = MagicMock()
        _state.status.cancel_halt = False
        _state.commandliststack = [_mock_commandlist()]

    def teardown_method(self):
        _state.subvars = None
        _state.exec_log = None
        _state.output = None
        _state.status = None
        _state.commandliststack = []

    def test_x_log_writes_message(self):
        from execsql.metacommands.system import x_log

        x_log(message="hello world")
        _state.exec_log.log_user_msg.assert_called_once_with("hello world")

    def test_x_logwritemessages_on(self, minimal_conf):
        from execsql.metacommands.system import x_logwritemessages

        x_logwritemessages(setting="on")
        assert minimal_conf.tee_write_log is True

    def test_x_logwritemessages_off(self, minimal_conf):
        from execsql.metacommands.system import x_logwritemessages

        x_logwritemessages(setting="off")
        assert minimal_conf.tee_write_log is False

    def test_x_log_datavars_on(self, minimal_conf):
        from execsql.metacommands.system import x_log_datavars

        x_log_datavars(setting="yes")
        assert minimal_conf.log_datavars is True

    def test_x_log_datavars_off(self, minimal_conf):
        from execsql.metacommands.system import x_log_datavars

        x_log_datavars(setting="no")
        assert minimal_conf.log_datavars is False

    def test_x_timer_on(self):
        from execsql.metacommands.system import x_timer

        _state.timer = MagicMock()
        x_timer(onoff="on")
        _state.timer.start.assert_called_once()

    def test_x_timer_off(self):
        from execsql.metacommands.system import x_timer

        _state.timer = MagicMock()
        x_timer(onoff="off")
        _state.timer.stop.assert_called_once()

    def test_x_consolewait_onerror_on(self, minimal_conf):
        from execsql.metacommands.system import x_consolewait_onerror

        x_consolewait_onerror(onoff="on")
        assert minimal_conf.gui_wait_on_error_halt is True

    def test_x_consolewait_onerror_off(self, minimal_conf):
        from execsql.metacommands.system import x_consolewait_onerror

        x_consolewait_onerror(onoff="off")
        assert minimal_conf.gui_wait_on_error_halt is False

    def test_x_consolewait_whendone_on(self, minimal_conf):
        from execsql.metacommands.system import x_consolewait_whendone

        x_consolewait_whendone(onoff="on")
        assert minimal_conf.gui_wait_on_exit is True

    def test_x_consolewait_whendone_off(self, minimal_conf):
        from execsql.metacommands.system import x_consolewait_whendone

        x_consolewait_whendone(onoff="off")
        assert minimal_conf.gui_wait_on_exit is False

    def test_x_gui_level(self, minimal_conf):
        from execsql.metacommands.system import x_gui_level

        x_gui_level(level="2")
        assert minimal_conf.gui_level == 2

    def test_x_write_warnings_yes(self, minimal_conf):
        from execsql.metacommands.system import x_write_warnings

        x_write_warnings(yesno="yes")
        assert minimal_conf.write_warnings is True

    def test_x_write_warnings_no(self, minimal_conf):
        from execsql.metacommands.system import x_write_warnings

        x_write_warnings(yesno="no")
        assert minimal_conf.write_warnings is False

    def test_x_cancel_halt_on(self):
        from execsql.metacommands.system import x_cancel_halt

        x_cancel_halt(onoff="on", metacommandline="cancel_halt on")
        assert _state.status.cancel_halt is True

    def test_x_cancel_halt_off(self):
        from execsql.metacommands.system import x_cancel_halt

        _state.status.cancel_halt = True
        x_cancel_halt(onoff="off", metacommandline="cancel_halt off")
        assert _state.status.cancel_halt is False

    def test_x_cancel_halt_invalid_flag(self):
        from execsql.metacommands.system import x_cancel_halt

        with pytest.raises(ErrInfo):
            x_cancel_halt(onoff="maybe", metacommandline="cancel_halt maybe")

    def test_x_cancel_halt_write_clear(self):
        from execsql.metacommands.system import x_cancel_halt_write_clear

        _state.cancel_halt_writespec = object()
        x_cancel_halt_write_clear()
        assert _state.cancel_halt_writespec is None

    def test_x_cancel_halt_email_clear(self):
        from execsql.metacommands.system import x_cancel_halt_email_clear

        _state.cancel_halt_mailspec = object()
        x_cancel_halt_email_clear()
        assert _state.cancel_halt_mailspec is None

    def test_x_cancel_halt_exec_clear(self):
        from execsql.metacommands.system import x_cancel_halt_exec_clear

        _state.cancel_halt_exec = object()
        x_cancel_halt_exec_clear()
        assert _state.cancel_halt_exec is None

    def test_x_error_halt_write_clear(self):
        from execsql.metacommands.system import x_error_halt_write_clear

        _state.err_halt_writespec = object()
        x_error_halt_write_clear()
        assert _state.err_halt_writespec is None

    def test_x_error_halt_email_clear(self):
        from execsql.metacommands.system import x_error_halt_email_clear

        _state.err_halt_email = object()
        x_error_halt_email_clear()
        assert _state.err_halt_email is None

    def test_x_error_halt_exec_clear(self):
        from execsql.metacommands.system import x_error_halt_exec_clear

        _state.err_halt_exec = object()
        x_error_halt_exec_clear()
        assert _state.err_halt_exec is None

    def test_x_consoleprogress_with_total(self):
        from execsql.metacommands.system import x_consoleprogress

        with patch("execsql.metacommands.system.gui_console_progress") as mock_progress:
            x_consoleprogress(num="50", total="200")
            # 100 * 50 / 200 = 25.0
            mock_progress.assert_called_once_with(25.0)

    def test_x_consoleprogress_without_total(self):
        from execsql.metacommands.system import x_consoleprogress

        with patch("execsql.metacommands.system.gui_console_progress") as mock_progress:
            x_consoleprogress(num="75.5", total=None)
            mock_progress.assert_called_once_with(75.5)

    def test_x_console_on(self):
        from execsql.metacommands.system import x_console

        with patch("execsql.metacommands.system.gui_console_on") as mock_on:
            x_console(onoff="on")
            mock_on.assert_called_once()

    def test_x_console_off(self):
        from execsql.metacommands.system import x_console

        with patch("execsql.metacommands.system.gui_console_off") as mock_off:
            x_console(onoff="off")
            mock_off.assert_called_once()

    def test_x_console_hideshow_hide(self):
        from execsql.metacommands.system import x_console_hideshow

        with patch("execsql.metacommands.system.gui_console_hide") as mock_hide:
            x_console_hideshow(hideshow="hide")
            mock_hide.assert_called_once()

    def test_x_console_hideshow_show(self):
        from execsql.metacommands.system import x_console_hideshow

        with patch("execsql.metacommands.system.gui_console_show") as mock_show:
            x_console_hideshow(hideshow="show")
            mock_show.assert_called_once()

    def test_x_consolestatus(self):
        from execsql.metacommands.system import x_consolestatus

        with patch("execsql.metacommands.system.gui_console_status") as mock_status:
            x_consolestatus(message="Processing...")
            mock_status.assert_called_once_with("Processing...")

    def test_x_system_cmd_sync(self):
        from execsql.metacommands.system import x_system_cmd

        with (
            patch("execsql.metacommands.system.current_script_line", return_value=("test.sql", 1)),
            patch("execsql.metacommands.system.filewriter_close_all_after_write"),
            patch("subprocess.call", return_value=0) as mock_call,
        ):
            x_system_cmd(command="echo hello", **{"continue": None})
        mock_call.assert_called_once()
        assert _state.subvars.varvalue("$system_cmd_exit_status") == "0"

    def test_x_system_cmd_async(self):
        from execsql.metacommands.system import x_system_cmd

        with (
            patch("execsql.metacommands.system.current_script_line", return_value=("test.sql", 1)),
            patch("execsql.metacommands.system.filewriter_close_all_after_write"),
            patch("subprocess.Popen") as mock_popen,
        ):
            x_system_cmd(command="echo hello", **{"continue": "continue"})
        mock_popen.assert_called_once()

    def test_x_cancel_halt_write(self):
        from execsql.metacommands.system import x_cancel_halt_write

        x_cancel_halt_write(text="message", tee=None, filename="out.txt")
        assert _state.cancel_halt_writespec is not None

    def test_x_error_halt_write(self):
        from execsql.metacommands.system import x_error_halt_write

        x_error_halt_write(text="error msg", tee=None, filename="err.txt")
        assert _state.err_halt_writespec is not None


# ---------------------------------------------------------------------------
# Tests for metacommands/control.py
# ---------------------------------------------------------------------------


class TestControlHandlers:
    """Tests for control-flow metacommand handlers."""

    def setup_method(self):
        sv = _make_subvars()
        _state.subvars = sv
        _state.exec_log = MagicMock()
        _state.output = MagicMock()
        _state.status = MagicMock()
        _state.status.halt_on_err = True
        _state.status.halt_on_metacommand_err = True
        _state.status.batch = BatchLevels()
        _state.if_stack = IfLevels()
        _state.commandliststack = [_mock_commandlist()]
        _state.loopcommandstack = []
        _state.compiling_loop = False

    def teardown_method(self):
        _state.subvars = None
        _state.exec_log = None
        _state.output = None
        _state.status = None
        _state.if_stack = None
        _state.commandliststack = []
        _state.loopcommandstack = []
        _state.compiling_loop = False

    def test_x_error_halt_on(self):
        from execsql.metacommands.control import x_error_halt

        x_error_halt(onoff="on", metacommandline="error_halt on")
        assert _state.status.halt_on_err is True

    def test_x_error_halt_off(self):
        from execsql.metacommands.control import x_error_halt

        x_error_halt(onoff="off", metacommandline="error_halt off")
        assert _state.status.halt_on_err is False

    def test_x_error_halt_invalid(self):
        from execsql.metacommands.control import x_error_halt

        with pytest.raises(ErrInfo):
            x_error_halt(onoff="maybe", metacommandline="error_halt maybe")

    def test_x_metacommand_error_halt_on(self):
        from execsql.metacommands.control import x_metacommand_error_halt

        x_metacommand_error_halt(onoff="on", metacommandline="metacommand_error_halt on")
        assert _state.status.halt_on_metacommand_err is True

    def test_x_metacommand_error_halt_off(self):
        from execsql.metacommands.control import x_metacommand_error_halt

        x_metacommand_error_halt(onoff="off", metacommandline="metacommand_error_halt off")
        assert _state.status.halt_on_metacommand_err is False

    def test_x_metacommand_error_halt_invalid(self):
        from execsql.metacommands.control import x_metacommand_error_halt

        with pytest.raises(ErrInfo):
            x_metacommand_error_halt(onoff="bad", metacommandline="metacommand_error_halt bad")

    def test_x_begin_batch(self):
        from execsql.metacommands.control import x_begin_batch

        assert not _state.status.batch.in_batch()
        x_begin_batch()
        assert _state.status.batch.in_batch()

    def test_x_end_batch(self):
        from execsql.metacommands.control import x_begin_batch, x_end_batch

        x_begin_batch()
        assert _state.status.batch.in_batch()
        x_end_batch()
        assert not _state.status.batch.in_batch()

    def test_x_rollback(self):
        from execsql.metacommands.control import x_begin_batch, x_rollback

        mock_db = MagicMock()
        x_begin_batch()
        _state.status.batch.using_db(mock_db)
        x_rollback()
        mock_db.rollback.assert_called_once()

    def test_x_if_block_true(self):
        from execsql.metacommands.control import x_if_block

        with (
            patch("execsql.state.xcmd_test", return_value=True),
            patch("execsql.script.current_script_line", return_value=("t.sql", 1)),
        ):
            x_if_block(condtest="1 == 1")
        assert _state.if_stack.all_true()
        assert len(_state.if_stack.if_levels) == 1

    def test_x_if_block_false(self):
        from execsql.metacommands.control import x_if_block

        with (
            patch("execsql.state.xcmd_test", return_value=False),
            patch("execsql.script.current_script_line", return_value=("t.sql", 1)),
        ):
            x_if_block(condtest="1 == 2")
        assert not _state.if_stack.all_true()
        assert len(_state.if_stack.if_levels) == 1

    def test_x_if_block_nested_outer_false(self):
        from execsql.metacommands.control import x_if_block

        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            _state.if_stack.nest(False)
            with patch("execsql.state.xcmd_test", return_value=True):
                x_if_block(condtest="1 == 1")
        # Both levels should exist; inner forced to False because outer is False
        assert len(_state.if_stack.if_levels) == 2
        assert not _state.if_stack.if_levels[-1].value()

    def test_x_if_end_unnests(self):
        from execsql.metacommands.control import x_if_end

        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            _state.if_stack.nest(True)
        assert len(_state.if_stack.if_levels) == 1
        x_if_end()
        assert len(_state.if_stack.if_levels) == 0

    def test_x_if_else_inverts(self):
        from execsql.metacommands.control import x_if_else

        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            _state.if_stack.nest(True)
        x_if_else()
        assert not _state.if_stack.if_levels[-1].value()

    def test_x_if_orif_short_circuits_when_all_true(self):
        from execsql.metacommands.control import x_if_orif

        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            _state.if_stack.nest(True)
        with patch("execsql.state.xcmd_test") as mock_test:
            x_if_orif(condtest="anything")
        # Should not even call xcmd_test if all_true
        mock_test.assert_not_called()

    def test_x_if_orif_evaluates_when_current_false(self):
        from execsql.metacommands.control import x_if_orif

        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            _state.if_stack.nest(False)
        with patch("execsql.state.xcmd_test", return_value=True):
            x_if_orif(condtest="something")
        assert _state.if_stack.if_levels[-1].value() is True

    def test_x_if_andif_short_circuits_when_not_all_true(self):
        from execsql.metacommands.control import x_if_andif

        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            _state.if_stack.nest(False)
        with patch("execsql.state.xcmd_test") as mock_test:
            x_if_andif(condtest="anything")
        # Should not evaluate if not all_true
        mock_test.assert_not_called()

    def test_x_if_andif_evaluates_when_all_true(self):
        from execsql.metacommands.control import x_if_andif

        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            _state.if_stack.nest(True)
        with patch("execsql.state.xcmd_test", return_value=False):
            x_if_andif(condtest="something_false")
        assert not _state.if_stack.if_levels[-1].value()

    def test_x_if_elseif_switches_when_only_current_false(self):
        from execsql.metacommands.control import x_if_elseif

        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            _state.if_stack.nest(False)
        with patch("execsql.state.xcmd_test", return_value=True):
            x_if_elseif(condtest="new_condition")
        assert _state.if_stack.if_levels[-1].value() is True

    def test_x_if_elseif_sets_false_when_previously_true(self):
        from execsql.metacommands.control import x_if_elseif

        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            _state.if_stack.nest(True)
        with patch("execsql.state.xcmd_test", return_value=True):
            x_if_elseif(condtest="something")
        # ELSEIF when current is True should set False (only execute one branch)
        assert not _state.if_stack.if_levels[-1].value()

    def test_x_break_with_single_command_list(self):
        from execsql.metacommands.control import x_break

        with (
            patch("execsql.metacommands.control.current_script_line", return_value=("test.sql", 1)),
            patch("execsql.metacommands.control.write_warning") as mock_warn,
        ):
            x_break()
        mock_warn.assert_called_once()
        # Stack should still have one item
        assert len(_state.commandliststack) == 1

    def test_x_break_with_nested_command_list(self):
        from execsql.metacommands.control import x_break

        # Add a second command list to simulate nesting
        second_cl = _mock_commandlist("inner")
        second_cl.init_if_level = 0
        _state.commandliststack.append(second_cl)
        assert len(_state.commandliststack) == 2
        x_break()
        assert len(_state.commandliststack) == 1

    def test_x_loop_while(self):
        from execsql.metacommands.control import x_loop

        x_loop(looptype="WHILE", loopcond="1 == 1")
        assert _state.compiling_loop is True
        assert len(_state.loopcommandstack) == 1

    def test_x_loop_until(self):
        from execsql.metacommands.control import x_loop

        x_loop(looptype="UNTIL", loopcond="1 == 1")
        assert _state.compiling_loop is True
        assert len(_state.loopcommandstack) == 1

    def test_endloop_without_loop_raises(self):
        from execsql.metacommands.control import endloop

        _state.loopcommandstack = []
        with pytest.raises(ErrInfo):
            endloop()


# ---------------------------------------------------------------------------
# Tests for metacommands/debug.py
# ---------------------------------------------------------------------------


class TestDebugHandlers:
    """Tests for debug metacommand handlers."""

    def setup_method(self):
        sv = _make_subvars()
        _state.subvars = sv
        _state.exec_log = MagicMock()
        _state.output = MagicMock()
        _state.commandliststack = [_mock_commandlist()]
        _state.metacommandlist = []

    def teardown_method(self):
        _state.subvars = None
        _state.exec_log = None
        _state.output = None
        _state.commandliststack = []
        _state.metacommandlist = None

    def test_x_debug_commandliststack_writes_output(self):
        from execsql.metacommands.debug import x_debug_commandliststack

        x_debug_commandliststack()
        # Should have written at least "Command List Stack:"
        assert _state.output.write.called

    def test_x_debug_iflevels_empty(self):
        from execsql.metacommands.debug import x_debug_iflevels

        _state.if_stack = IfLevels()
        x_debug_iflevels()
        _state.output.write.assert_called_with("If levels: None\n")

    def test_x_debug_iflevels_with_values(self):
        from execsql.metacommands.debug import x_debug_iflevels

        _state.if_stack = IfLevels()
        with patch("execsql.script.current_script_line", return_value=("test.sql", 1)):
            _state.if_stack.nest(True)
            _state.if_stack.nest(False)
        x_debug_iflevels()
        call_args = _state.output.write.call_args[0][0]
        assert "True" in call_args or "False" in call_args

    def test_x_debug_write_metacommands_to_stdout(self):
        from execsql.metacommands.debug import x_debug_write_metacommands

        mc = MagicMock()
        mc.hitcount = 3
        mc.rx = MagicMock()
        mc.rx.pattern = r"test_pattern"
        _state.metacommandlist = [mc]
        x_debug_write_metacommands(filename=None)
        _state.output.write.assert_called_with("(3)  test_pattern\n")

    def test_x_debug_write_metacommands_to_stdout_string(self):
        from execsql.metacommands.debug import x_debug_write_metacommands

        mc = MagicMock()
        mc.hitcount = 0
        mc.rx = MagicMock()
        mc.rx.pattern = r"abc"
        _state.metacommandlist = [mc]
        x_debug_write_metacommands(filename="stdout")
        _state.output.write.assert_called()

    def test_x_debug_write_metacommands_to_file(self, tmp_path, minimal_conf):
        from execsql.metacommands.debug import x_debug_write_metacommands

        mc = MagicMock()
        mc.hitcount = 1
        mc.rx = MagicMock()
        mc.rx.pattern = r"some_pattern"
        _state.metacommandlist = [mc]
        outfile = tmp_path / "debug_out.txt"
        x_debug_write_metacommands(filename=str(outfile))
        content = outfile.read_text()
        assert "(1)  some_pattern" in content

    def test_x_debug_write_subvars_to_stdout(self):
        from execsql.metacommands.debug import x_debug_write_subvars

        _state.subvars.add_substitution("myvar", "myval")
        x_debug_write_subvars(filename=None, append=None, user=None, local=None)
        assert _state.output.write.called

    def test_x_debug_write_subvars_user_only(self):
        from execsql.metacommands.debug import x_debug_write_subvars

        _state.subvars.add_substitution("myvar", "myval")
        _state.subvars.add_substitution("$sysvar", "sysval")
        x_debug_write_subvars(filename=None, append=None, user="user", local=None)
        # Should only write user variables (those starting with alphanumeric)
        calls = [str(c) for c in _state.output.write.call_args_list]
        assert any("myvar" in c for c in calls)

    def test_x_debug_log_subvars(self):
        from execsql.metacommands.debug import x_debug_log_subvars

        _state.subvars.add_substitution("logvar", "logval")
        x_debug_log_subvars(local=None, user=None)
        assert _state.exec_log.log_status_info.called

    def test_x_debug_write_config_to_stdout(self, minimal_conf):
        from execsql.metacommands.debug import x_debug_write_config

        minimal_conf.script_encoding = "utf-8"
        minimal_conf.import_encoding = "utf-8"
        minimal_conf.gui_level = 0
        x_debug_write_config(filename=None, append=None)
        assert _state.output.write.called


# ---------------------------------------------------------------------------
# Tests for metacommands/script_ext.py
# ---------------------------------------------------------------------------


class TestScriptExtHandlers:
    """Tests for script_ext.py metacommand handlers."""

    def setup_method(self):
        _state.savedscripts = {}
        _state.commandliststack = [_mock_commandlist()]
        _state.exec_log = MagicMock()

    def teardown_method(self):
        _state.savedscripts = {}
        _state.commandliststack = []
        _state.exec_log = None

    def _make_saved_script(self, name: str, cmds: list | None = None) -> MagicMock:
        """Create a mock saved script and register it in _state.savedscripts."""
        sc = MagicMock()
        sc.cmdlist = cmds or []
        sc.paramnames = None
        _state.savedscripts[name] = sc
        return sc

    def test_x_extendscript_both_exist(self):
        from execsql.metacommands.script_ext import x_extendscript

        cmd1 = MagicMock()
        cmd2 = MagicMock()
        _ = self._make_saved_script("s1", [cmd1])
        s2 = self._make_saved_script("s2", [cmd2])
        x_extendscript(script1="s1", script2="s2")
        s2.add.assert_called_once_with(cmd1)

    def test_x_extendscript_missing_script1(self):
        from execsql.metacommands.script_ext import x_extendscript

        self._make_saved_script("s2")
        with pytest.raises(ErrInfo):
            x_extendscript(script1="missing", script2="s2")

    def test_x_extendscript_missing_script2(self):
        from execsql.metacommands.script_ext import x_extendscript

        self._make_saved_script("s1")
        with pytest.raises(ErrInfo):
            x_extendscript(script1="s1", script2="missing")

    def test_x_extendscript_copies_params(self):
        from execsql.metacommands.script_ext import x_extendscript

        s1 = self._make_saved_script("s1")
        s1.paramnames = ["p1", "p2"]
        s2 = self._make_saved_script("s2")
        s2.paramnames = None
        x_extendscript(script1="s1", script2="s2")
        # s2.paramnames should be set from s1
        assert s2.paramnames is not None

    def test_x_extendscript_merges_existing_params(self):
        from execsql.metacommands.script_ext import x_extendscript

        s1 = self._make_saved_script("s1")
        s1.paramnames = ["p1", "p2"]
        s2 = self._make_saved_script("s2")
        s2.paramnames = ["p2", "p3"]
        x_extendscript(script1="s1", script2="s2")
        # p1 should be added, p2 already present
        assert "p1" in s2.paramnames

    def test_x_extendscript_metacommand(self):
        from execsql.metacommands.script_ext import x_extendscript_metacommand

        s = self._make_saved_script("myscript")
        with patch("execsql.metacommands.script_ext.current_script_line", return_value=("test.sql", 10)):
            x_extendscript_metacommand(script="myscript", cmd="sub foo bar")
        s.add.assert_called_once()

    def test_x_extendscript_metacommand_missing_script(self):
        from execsql.metacommands.script_ext import x_extendscript_metacommand

        with pytest.raises(ErrInfo):
            x_extendscript_metacommand(script="missing", cmd="sub foo bar")

    def test_x_extendscript_sql(self):
        from execsql.metacommands.script_ext import x_extendscript_sql

        s = self._make_saved_script("myscript")
        with patch("execsql.metacommands.script_ext.current_script_line", return_value=("test.sql", 5)):
            x_extendscript_sql(script="myscript", sql="select 1;")
        s.add.assert_called_once()

    def test_x_extendscript_sql_missing_script(self):
        from execsql.metacommands.script_ext import x_extendscript_sql

        with pytest.raises(ErrInfo):
            x_extendscript_sql(script="missing", sql="select 1;")

    def test_x_executescript_missing_id_no_exists(self):
        from execsql.metacommands.script_ext import x_executescript

        with patch("execsql.metacommands.script_ext.ScriptExecSpec") as mock_spec_cls:
            mock_spec = MagicMock()
            mock_spec_cls.return_value = mock_spec
            x_executescript(exists=None, script_id="nonexistent")
        mock_spec.execute.assert_called_once()

    def test_x_executescript_exists_flag_and_script_present(self):
        from execsql.metacommands.script_ext import x_executescript

        self._make_saved_script("existing")
        with patch("execsql.metacommands.script_ext.ScriptExecSpec") as mock_spec_cls:
            mock_spec = MagicMock()
            mock_spec_cls.return_value = mock_spec
            x_executescript(exists="exists", script_id="existing")
        mock_spec.execute.assert_called_once()

    def test_x_executescript_exists_flag_and_script_absent(self):
        from execsql.metacommands.script_ext import x_executescript

        with patch("execsql.metacommands.script_ext.ScriptExecSpec") as mock_spec_cls:
            mock_spec = MagicMock()
            mock_spec_cls.return_value = mock_spec
            x_executescript(exists="exists", script_id="doesnotexist")
        # Should NOT execute because script not in savedscripts
        mock_spec.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for metacommands/io.py -- validation logic and error paths
# ---------------------------------------------------------------------------


class TestIoExportValidation:
    """Tests for validation logic in io.py x_export and x_export_query."""

    def test_x_export_zipfile_with_stdout_raises(self):
        from execsql.metacommands.io import x_export

        mock_db = MagicMock()
        mock_db.schema_qualified_table_name.return_value = "mytable"
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = mock_db
        with pytest.raises(ErrInfo) as exc_info:
            x_export(
                schema=None,
                table="mytable",
                filename="stdout",
                description=None,
                tee=None,
                append=None,
                format="csv",
                zipfilename="out.zip",
                metacommandline="export mytable stdout csv zip out.zip",
            )
        assert "stdout" in str(exc_info.value.other).lower()

    def test_x_export_zipfile_with_duckdb_raises(self):
        from execsql.metacommands.io import x_export

        mock_db = MagicMock()
        mock_db.schema_qualified_table_name.return_value = "mytable"
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = mock_db
        with pytest.raises(ErrInfo) as exc_info:
            x_export(
                schema=None,
                table="mytable",
                filename="out.duckdb",
                description=None,
                tee=None,
                append=None,
                format="duckdb",
                zipfilename="out.zip",
                metacommandline="export mytable out.duckdb duckdb zip out.zip",
            )
        assert "duckdb" in str(exc_info.value.other).lower()

    def test_x_export_zipfile_with_sqlite_raises(self):
        from execsql.metacommands.io import x_export

        mock_db = MagicMock()
        mock_db.schema_qualified_table_name.return_value = "mytable"
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = mock_db
        with pytest.raises(ErrInfo) as exc_info:
            x_export(
                schema=None,
                table="mytable",
                filename="out.sqlite",
                description=None,
                tee=None,
                append=None,
                format="sqlite",
                zipfilename="out.zip",
                metacommandline="export mytable out.sqlite sqlite zip out.zip",
            )
        assert "sqlite" in str(exc_info.value.other).lower()

    def test_x_export_zipfile_with_latex_raises(self):
        from execsql.metacommands.io import x_export

        mock_db = MagicMock()
        mock_db.schema_qualified_table_name.return_value = "mytable"
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = mock_db
        with pytest.raises(ErrInfo) as exc_info:
            x_export(
                schema=None,
                table="mytable",
                filename="out.tex",
                description=None,
                tee=None,
                append=None,
                format="latex",
                zipfilename="out.zip",
                metacommandline="export mytable out.tex latex zip out.zip",
            )
        assert "latex" in str(exc_info.value.other).lower()

    def test_x_export_zipfile_with_feather_raises(self):
        from execsql.metacommands.io import x_export

        mock_db = MagicMock()
        mock_db.schema_qualified_table_name.return_value = "mytable"
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = mock_db
        with pytest.raises(ErrInfo) as exc_info:
            x_export(
                schema=None,
                table="mytable",
                filename="out.feather",
                description=None,
                tee=None,
                append=None,
                format="feather",
                zipfilename="out.zip",
                metacommandline="export mytable out.feather feather zip out.zip",
            )
        assert "feather" in str(exc_info.value.other).lower()

    def test_x_export_zipfile_with_ods_raises(self):
        from execsql.metacommands.io import x_export

        mock_db = MagicMock()
        mock_db.schema_qualified_table_name.return_value = "mytable"
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = mock_db
        with pytest.raises(ErrInfo) as exc_info:
            x_export(
                schema=None,
                table="mytable",
                filename="out.ods",
                description=None,
                tee=None,
                append=None,
                format="ods",
                zipfilename="out.zip",
                metacommandline="export mytable out.ods ods zip out.zip",
            )
        assert "ods" in str(exc_info.value.other).lower()

    def test_x_export_query_zipfile_stdout_raises(self):
        from execsql.metacommands.io import x_export_query

        _state.dbs = MagicMock()
        with pytest.raises(ErrInfo):
            x_export_query(
                query="select 1;",
                filename="stdout",
                description=None,
                tee=None,
                append=None,
                format="csv",
                zipfilename="out.zip",
            )

    def test_x_export_query_zipfile_latex_raises(self):
        from execsql.metacommands.io import x_export_query

        _state.dbs = MagicMock()
        with pytest.raises(ErrInfo):
            x_export_query(
                query="select 1;",
                filename="out.tex",
                description=None,
                tee=None,
                append=None,
                format="latex",
                zipfilename="out.zip",
            )

    def test_x_export_query_zipfile_feather_raises(self):
        from execsql.metacommands.io import x_export_query

        _state.dbs = MagicMock()
        with pytest.raises(ErrInfo):
            x_export_query(
                query="select 1;",
                filename="out.feather",
                description=None,
                tee=None,
                append=None,
                format="feather",
                zipfilename="out.zip",
            )

    def test_x_export_query_zipfile_hdf5_raises(self):
        from execsql.metacommands.io import x_export_query

        _state.dbs = MagicMock()
        with pytest.raises(ErrInfo):
            x_export_query(
                query="select 1;",
                filename="out.hdf5",
                description=None,
                tee=None,
                append=None,
                format="hdf5",
                zipfilename="out.zip",
            )

    def test_x_export_query_zipfile_ods_raises(self):
        from execsql.metacommands.io import x_export_query

        _state.dbs = MagicMock()
        with pytest.raises(ErrInfo):
            x_export_query(
                query="select 1;",
                filename="out.ods",
                description=None,
                tee=None,
                append=None,
                format="ods",
                zipfilename="out.zip",
            )


class TestIoImportValidation:
    """Tests for validation logic in io.py x_import and related."""

    def test_x_import_missing_file_raises(self, tmp_path):
        from execsql.metacommands.io import x_import

        _state.dbs = MagicMock()
        _state.exec_log = MagicMock()
        nonexistent = str(tmp_path / "nonexistent.csv")
        with pytest.raises(ErrInfo) as exc_info:
            x_import(
                new=None,
                schema=None,
                table="mytable",
                filename=nonexistent,
                quotechar=None,
                delimchar=None,
                encoding=None,
                skip=None,
                metacommandline="import mytable nonexistent.csv",
            )
        assert "does not exist" in str(exc_info.value.other)

    def test_x_import_file_missing_raises(self, tmp_path):
        from execsql.metacommands.io import x_import_file

        _state.dbs = MagicMock()
        _state.exec_log = MagicMock()
        nonexistent = str(tmp_path / "nonexistent.bin")
        with pytest.raises(ErrInfo) as exc_info:
            x_import_file(
                schema=None,
                table="mytable",
                columnname="data",
                filename=nonexistent,
                metacommandline="import_file mytable data nonexistent.bin",
            )
        assert "does not exist" in str(exc_info.value.other)

    def test_x_import_ods_missing_file_raises(self, tmp_path):
        from execsql.metacommands.io import x_import_ods

        _state.dbs = MagicMock()
        nonexistent = str(tmp_path / "nonexistent.ods")
        with pytest.raises(ErrInfo) as exc_info:
            x_import_ods(
                new=None,
                schema=None,
                table="mytable",
                filename=nonexistent,
                sheetname="Sheet1",
                skip=None,
                metacommandline="import_ods mytable nonexistent.ods Sheet1",
            )
        assert "does not exist" in str(exc_info.value.other)

    def test_x_import_xls_missing_file_raises(self, tmp_path):
        from execsql.metacommands.io import x_import_xls

        _state.dbs = MagicMock()
        nonexistent = str(tmp_path / "nonexistent.xls")
        with pytest.raises(ErrInfo) as exc_info:
            x_import_xls(
                new=None,
                schema=None,
                table="mytable",
                filename=nonexistent,
                sheetname="Sheet1",
                skip=None,
                encoding=None,
                metacommandline="import_xls mytable nonexistent.xls Sheet1",
            )
        assert "does not exist" in str(exc_info.value.other)

    def test_x_import_parquet_missing_file_raises(self, tmp_path):
        from execsql.metacommands.io import x_import_parquet

        _state.dbs = MagicMock()
        _state.exec_log = MagicMock()
        nonexistent = str(tmp_path / "nonexistent.parquet")
        with pytest.raises(ErrInfo) as exc_info:
            x_import_parquet(
                new=None,
                schema=None,
                table="mytable",
                filename=nonexistent,
                metacommandline="import_parquet mytable nonexistent.parquet",
            )
        assert "does not exist" in str(exc_info.value.other)

    def test_x_import_new_replacement(self, tmp_path):
        """Test that is_new is correctly computed for 'replacement' keyword."""
        from execsql.metacommands.io import x_import
        import csv as _csv

        # Create a real CSV file
        csvfile = tmp_path / "test.csv"
        with open(csvfile, "w", newline="") as f:
            w = _csv.writer(f)
            w.writerow(["col1", "col2"])
            w.writerow(["a", "b"])

        mock_db = MagicMock()
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = mock_db
        _state.exec_log = MagicMock()

        with patch("execsql.metacommands.io_import.importtable") as mock_import:
            x_import(
                new="replacement",
                schema=None,
                table="mytable",
                filename=str(csvfile),
                quotechar=None,
                delimchar=None,
                encoding=None,
                skip=None,
                metacommandline="import replacement mytable test.csv",
            )
        mock_import.assert_called_once()

    def test_x_import_delimchar_tab(self, tmp_path):
        """Test that 'tab' delimchar is converted to chr(9)."""
        from execsql.metacommands.io import x_import

        csvfile = tmp_path / "test.tsv"
        csvfile.write_text("col1\tcol2\na\tb\n")

        mock_db = MagicMock()
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = mock_db
        _state.exec_log = MagicMock()

        with patch("execsql.metacommands.io_import.importtable") as mock_import:
            x_import(
                new=None,
                schema=None,
                table="mytable",
                filename=str(csvfile),
                quotechar=None,
                delimchar="tab",
                encoding=None,
                skip=None,
                metacommandline="import mytable test.tsv tab",
            )
        call_kwargs = mock_import.call_args[1]
        assert call_kwargs.get("delimchar") == chr(9)

    def test_x_import_delimchar_unitsep(self, tmp_path):
        """Test that 'unitsep' delimchar is converted to chr(31)."""
        from execsql.metacommands.io import x_import

        csvfile = tmp_path / "test.txt"
        csvfile.write_text(f"col1{chr(31)}col2\na{chr(31)}b\n")

        mock_db = MagicMock()
        _state.dbs = MagicMock()
        _state.dbs.current.return_value = mock_db
        _state.exec_log = MagicMock()

        with patch("execsql.metacommands.io_import.importtable") as mock_import:
            x_import(
                new=None,
                schema=None,
                table="mytable",
                filename=str(csvfile),
                quotechar=None,
                delimchar="unitsep",
                encoding=None,
                skip=None,
                metacommandline="import mytable test.txt unitsep",
            )
        call_kwargs = mock_import.call_args[1]
        assert call_kwargs.get("delimchar") == chr(31)


class TestIoExportMetadata:
    """Tests for x_export_metadata and x_export_metadata_table."""

    def setup_method(self):
        _state.export_metadata = MagicMock()
        _state.dbs = MagicMock()
        _state.exec_log = MagicMock()

    def teardown_method(self):
        _state.export_metadata = None
        _state.dbs = None
        _state.exec_log = None

    def test_x_export_metadata_all_flag(self, minimal_conf):
        from execsql.metacommands.io import x_export_metadata

        _state.export_metadata.get_all.return_value = (["col1"], [("val1",)])
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.prettyprint_rowset") as mock_pp,
        ):
            x_export_metadata(
                filename="stdout",
                append=None,
                all="all",
                zipfilename=None,
                format="txt",
            )
        _state.export_metadata.get_all.assert_called_once()
        mock_pp.assert_called_once()

    def test_x_export_metadata_current(self, minimal_conf):
        from execsql.metacommands.io import x_export_metadata

        _state.export_metadata.get.return_value = (["col1"], [("val1",)])
        with (
            patch("execsql.metacommands.io_export.check_dir"),
            patch("execsql.metacommands.io_export.prettyprint_rowset") as mock_pp,
        ):
            x_export_metadata(
                filename="stdout",
                append=None,
                all=None,
                zipfilename=None,
                format="txt",
            )
        _state.export_metadata.get.assert_called_once()
        mock_pp.assert_called_once()

    def test_x_export_metadata_table_all(self, minimal_conf):
        from execsql.metacommands.io import x_export_metadata_table

        _state.export_metadata.get_all.return_value = (["col1"], [("val1",)])
        with patch("execsql.metacommands.io_export.import_data_table") as mock_import:
            x_export_metadata_table(
                all="all",
                schema=None,
                table="metadata_tbl",
                new=None,
            )
        mock_import.assert_called_once()

    def test_x_export_metadata_table_new_replacement(self, minimal_conf):
        from execsql.metacommands.io import x_export_metadata_table

        _state.export_metadata.get.return_value = (["col1"], [("val1",)])
        with patch("execsql.metacommands.io_export.import_data_table") as mock_import:
            x_export_metadata_table(
                all=None,
                schema=None,
                table="metadata_tbl",
                new="replacement",
            )
        call_args = mock_import.call_args[0]
        # is_new should be 2 for "replacement"
        assert call_args[3] == 2


# ---------------------------------------------------------------------------
# Tests for SubVarSet (script.py) -- more coverage of string operations
# ---------------------------------------------------------------------------


class TestSubVarSet:
    """Unit tests for SubVarSet methods."""

    def test_add_and_get_substitution(self):
        sv = _make_subvars()
        sv.add_substitution("myvar", "hello")
        assert sv.varvalue("myvar") == "hello"

    def test_remove_substitution(self):
        sv = _make_subvars()
        sv.add_substitution("myvar", "hello")
        sv.remove_substitution("myvar")
        assert sv.varvalue("myvar") is None

    def test_sub_exists_true(self):
        sv = _make_subvars()
        sv.add_substitution("x", "1")
        assert sv.sub_exists("x") is True

    def test_sub_exists_false(self):
        sv = _make_subvars()
        assert sv.sub_exists("x") is False

    def test_append_substitution_new(self):
        sv = _make_subvars()
        sv.append_substitution("v", "first")
        assert sv.varvalue("v") == "first"

    def test_append_substitution_existing(self):
        sv = _make_subvars()
        sv.add_substitution("v", "first")
        sv.append_substitution("v", "second")
        assert sv.varvalue("v") == "first\nsecond"

    def test_increment_by_integer(self):
        sv = _make_subvars()
        sv.add_substitution("count", "5")
        sv.increment_by("count", 3)
        assert sv.varvalue("count") == "8"

    def test_increment_by_float(self):
        sv = _make_subvars()
        sv.add_substitution("count", "5")
        sv.increment_by("count", 0.5)
        assert sv.varvalue("count") == "5.5"

    def test_increment_by_new_var(self):
        sv = _make_subvars()
        sv.increment_by("newcount", 1)
        # Should default to 0 + 1 = 1
        assert sv.varvalue("newcount") == "1"

    def test_substitute_all_replaces_variable(self):
        sv = _make_subvars()
        sv.add_substitution("greeting", "hello")
        result, was_subbed = sv.substitute_all("say !!greeting!!")
        assert result == "say hello"
        assert was_subbed is True

    def test_substitute_all_no_match(self):
        sv = _make_subvars()
        result, was_subbed = sv.substitute_all("no vars here")
        assert result == "no vars here"
        assert was_subbed is False

    def test_var_name_ok_valid(self):
        sv = _make_subvars()
        assert sv.var_name_ok("myvar") is True
        assert sv.var_name_ok("$sysvar") is True
        assert sv.var_name_ok("@counter") is True

    def test_var_name_ok_invalid(self):
        sv = _make_subvars()
        assert sv.var_name_ok("has spaces") is False
        assert sv.var_name_ok("has-dash") is False

    def test_check_var_name_raises_on_invalid(self):
        sv = _make_subvars()
        with pytest.raises(ErrInfo):
            sv.check_var_name("has spaces")


# ---------------------------------------------------------------------------
# Tests for IfLevels (script.py)
# ---------------------------------------------------------------------------


class TestIfLevels:
    """Unit tests for IfLevels."""

    def test_all_true_empty(self):
        il = IfLevels()
        assert il.all_true() is True

    def test_all_true_with_trues(self):
        il = IfLevels()
        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            il.nest(True)
            il.nest(True)
        assert il.all_true() is True

    def test_all_true_with_false(self):
        il = IfLevels()
        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            il.nest(True)
            il.nest(False)
        assert il.all_true() is False

    def test_only_current_false_empty(self):
        il = IfLevels()
        assert il.only_current_false() is False

    def test_only_current_false_single_false(self):
        il = IfLevels()
        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            il.nest(False)
        assert il.only_current_false() is True

    def test_only_current_false_single_true(self):
        il = IfLevels()
        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            il.nest(True)
        assert il.only_current_false() is False

    def test_only_current_false_nested_outer_true_inner_false(self):
        il = IfLevels()
        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            il.nest(True)
            il.nest(False)
        assert il.only_current_false() is True

    def test_only_current_false_nested_both_false(self):
        il = IfLevels()
        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            il.nest(False)
            il.nest(False)
        # Both false, not only current
        assert il.only_current_false() is False

    def test_unnest_empty_raises(self):
        il = IfLevels()
        with pytest.raises(ErrInfo):
            il.unnest()

    def test_invert_empty_raises(self):
        il = IfLevels()
        with pytest.raises(ErrInfo):
            il.invert()

    def test_replace_empty_raises(self):
        il = IfLevels()
        with pytest.raises(ErrInfo):
            il.replace(True)

    def test_current_empty_raises(self):
        il = IfLevels()
        with pytest.raises(ErrInfo):
            il.current()

    def test_script_lines(self):
        il = IfLevels()
        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            il.nest(True)
        lines = il.script_lines(1)
        assert len(lines) == 1

    def test_script_lines_invalid_depth_raises(self):
        il = IfLevels()
        with patch("execsql.script.current_script_line", return_value=("t.sql", 1)):
            il.nest(True)
        with pytest.raises(ErrInfo):
            il.script_lines(5)


# ---------------------------------------------------------------------------
# Tests for CounterVars (script.py)
# ---------------------------------------------------------------------------


class TestCounterVars:
    """Unit tests for CounterVars."""

    def test_set_and_substitute(self):
        cv = CounterVars()
        cv.set_counter(1, 0)
        result, changed = cv.substitute("value !!$COUNTER_1!!")
        assert changed is True
        assert result == "value 1"

    def test_substitute_no_match(self):
        cv = CounterVars()
        result, changed = cv.substitute("no counters here")
        assert changed is False

    def test_substitute_all(self):
        cv = CounterVars()
        cv.set_counter(1, 0)
        text, changed = cv.substitute_all("a !!$COUNTER_1!! b !!$COUNTER_1!!")
        assert changed is True
        # Each substitution increments the counter
        assert "1" in text

    def test_remove_counter(self):
        cv = CounterVars()
        cv.set_counter(1, 5)
        cv.remove_counter(1)
        assert "counter_1" not in cv.counters

    def test_remove_nonexistent_counter(self):
        cv = CounterVars()
        # Should not raise
        cv.remove_counter(99)

    def test_remove_all_counters(self):
        cv = CounterVars()
        cv.set_counter(1, 1)
        cv.set_counter(2, 2)
        cv.remove_all_counters()
        assert cv.counters == {}


# ---------------------------------------------------------------------------
# Tests for BatchLevels (script.py)
# ---------------------------------------------------------------------------


class TestBatchLevels:
    """Unit tests for BatchLevels."""

    def test_in_batch_initially_false(self):
        bl = BatchLevels()
        assert bl.in_batch() is False

    def test_new_batch(self):
        bl = BatchLevels()
        bl.new_batch()
        assert bl.in_batch() is True

    def test_using_db(self):
        bl = BatchLevels()
        bl.new_batch()
        mock_db = MagicMock()
        bl.using_db(mock_db)
        assert bl.uses_db(mock_db) is True

    def test_uses_db_not_in_batch(self):
        bl = BatchLevels()
        mock_db = MagicMock()
        assert bl.uses_db(mock_db) is False

    def test_rollback_batch(self):
        bl = BatchLevels()
        bl.new_batch()
        mock_db = MagicMock()
        bl.using_db(mock_db)
        bl.rollback_batch()
        mock_db.rollback.assert_called_once()

    def test_end_batch_commits(self):
        bl = BatchLevels()
        bl.new_batch()
        mock_db = MagicMock()
        bl.using_db(mock_db)
        bl.end_batch()
        mock_db.commit.assert_called_once()
        assert bl.in_batch() is False

    def test_using_db_not_in_batch_does_nothing(self):
        bl = BatchLevels()
        mock_db = MagicMock()
        bl.using_db(mock_db)  # Should not raise
        assert not bl.uses_db(mock_db)

    def test_using_db_not_added_twice(self):
        bl = BatchLevels()
        bl.new_batch()
        mock_db = MagicMock()
        bl.using_db(mock_db)
        bl.using_db(mock_db)  # Second call should not duplicate
        assert bl.batchlevels[-1].dbs_used.count(mock_db) == 1


# ---------------------------------------------------------------------------
# Tests for ErrInfo exception (exceptions.py)
# ---------------------------------------------------------------------------


class TestErrInfo:
    """Unit tests for the ErrInfo exception class."""

    def test_errinfo_type_db(self):
        e = ErrInfo("db", command_text="select 1", exception_msg="syntax error")
        msg = e.eval_err()
        assert "SQL statement" in msg

    def test_errinfo_type_cmd(self):
        e = ErrInfo("cmd", command_text="bad cmd", other_msg="invalid syntax")
        msg = e.eval_err()
        assert "metacommand" in msg.lower()

    def test_errinfo_type_error(self):
        e = ErrInfo("error", other_msg="something went wrong")
        msg = e.eval_err()
        assert "General error" in msg

    def test_errinfo_type_exception(self):
        e = ErrInfo("exception", exception_msg="unhandled exception")
        msg = e.eval_err()
        assert "Exception" in msg

    def test_errinfo_type_unknown(self):
        e = ErrInfo("unknown_type")
        msg = e.eval_err()
        assert "unknown type" in msg

    def test_errinfo_script_info_with_line(self):
        e = ErrInfo("error")
        e.script_file = "test.sql"
        e.script_line_no = 42
        info = e.script_info()
        assert "42" in info
        assert "test.sql" in info

    def test_errinfo_script_info_without_line(self):
        e = ErrInfo("error")
        assert e.script_info() is None

    def test_errinfo_cmd_info_cmd_type(self):
        e = ErrInfo("cmd")
        e.cmdtype = "cmd"
        e.cmd = "sub foo bar"
        info = e.cmd_info()
        assert "Metacommand" in info

    def test_errinfo_cmd_info_sql_type(self):
        e = ErrInfo("db")
        e.cmdtype = "sql"
        e.cmd = "select 1"
        info = e.cmd_info()
        assert "SQL statement" in info

    def test_errinfo_repr(self):
        e = ErrInfo("cmd", command_text="test")
        r = repr(e)
        assert "ErrInfo" in r

    def test_errinfo_is_exception(self):
        e = ErrInfo("error", other_msg="test error")
        with pytest.raises(ErrInfo):
            raise e
