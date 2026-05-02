"""Unit tests for execsql metacommand handlers in metacommands/system.py.

Tests the handler functions directly with appropriate state mocking,
focusing on testable behaviour without side effects.
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


def _setup_exec_log():
    """Install a mock exec_log on _state."""
    mock_log = MagicMock()
    _state.exec_log = mock_log
    return mock_log


def _setup_subvars():
    """Install a mock subvars on _state."""
    mock_sv = MagicMock()
    _state.subvars = mock_sv
    return mock_sv


# ---------------------------------------------------------------------------
# Tests for x_log
# ---------------------------------------------------------------------------


class TestXLog:
    """Tests for the LOG metacommand handler."""

    def test_log_delegates_to_exec_log(self, minimal_conf):
        from execsql.metacommands.system import x_log

        mock_log = _setup_exec_log()
        x_log(message="hello world")
        mock_log.log_user_msg.assert_called_once_with("hello world")

    def test_log_empty_message(self, minimal_conf):
        from execsql.metacommands.system import x_log

        mock_log = _setup_exec_log()
        x_log(message="")
        mock_log.log_user_msg.assert_called_once_with("")


# ---------------------------------------------------------------------------
# Tests for x_logwritemessages
# ---------------------------------------------------------------------------


class TestXLogWriteMessages:
    """Tests for the LOG WRITE MESSAGES metacommand handler."""

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
            ("YES", True),
            ("OFF", False),
        ],
    )
    def test_tee_write_log_flag(self, minimal_conf, value, expected):
        from execsql.metacommands.system import x_logwritemessages

        minimal_conf.tee_write_log = not expected
        x_logwritemessages(setting=value)
        assert minimal_conf.tee_write_log is expected


# ---------------------------------------------------------------------------
# Tests for x_log_datavars
# ---------------------------------------------------------------------------


class TestXLogDatavars:
    """Tests for the LOG DATAVARS metacommand handler."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("yes", True),
            ("on", True),
            ("true", True),
            ("1", True),
            ("no", False),
            ("off", False),
        ],
    )
    def test_log_datavars_flag(self, minimal_conf, value, expected):
        from execsql.metacommands.system import x_log_datavars

        minimal_conf.log_datavars = not expected
        x_log_datavars(setting=value)
        assert minimal_conf.log_datavars is expected


# ---------------------------------------------------------------------------
# Tests for x_timer
# ---------------------------------------------------------------------------


class TestXTimer:
    """Tests for the TIMER metacommand handler."""

    def test_timer_on(self, minimal_conf):
        from execsql.metacommands.system import x_timer

        mock_timer = MagicMock()
        _state.timer = mock_timer
        x_timer(onoff="on")
        mock_timer.start.assert_called_once()

    def test_timer_off(self, minimal_conf):
        from execsql.metacommands.system import x_timer

        mock_timer = MagicMock()
        _state.timer = mock_timer
        x_timer(onoff="off")
        mock_timer.stop.assert_called_once()

    def test_timer_case_insensitive(self, minimal_conf):
        from execsql.metacommands.system import x_timer

        mock_timer = MagicMock()
        _state.timer = mock_timer
        x_timer(onoff="ON")
        mock_timer.start.assert_called_once()

        mock_timer.reset_mock()
        x_timer(onoff="Off")
        mock_timer.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Tests for x_system_cmd
# ---------------------------------------------------------------------------


class TestXSystemCmd:
    """Tests for the SYSTEM_CMD / SHELL metacommand handler."""

    def test_system_cmd_blocked_when_disabled(self, minimal_conf):
        """SYSTEM_CMD raises ErrInfo when allow_system_cmd is False."""
        from execsql.metacommands.system import x_system_cmd

        minimal_conf.allow_system_cmd = False
        with pytest.raises(ErrInfo, match="disabled"):
            x_system_cmd(command="echo hello", **{"continue": None}, metacommandline="SYSTEM_CMD (echo hello)")

    def test_system_cmd_runs_subprocess(self, minimal_conf):
        from execsql.metacommands.system import x_system_cmd

        _setup_exec_log()
        mock_sv = _setup_subvars()
        _state.commandliststack = [MagicMock()]
        _state.commandliststack[-1].current_command.return_value = SimpleNamespace(
            current_script_line=lambda: ("test.sql", 1),
        )

        mock_result = SimpleNamespace(returncode=0)
        with (
            patch("execsql.metacommands.system.subprocess.run", return_value=mock_result) as mock_run,
            patch("execsql.metacommands.system.filewriter_close_all_after_write"),
        ):
            x_system_cmd(command="echo hello", **{"continue": None})
            mock_run.assert_called_once()
            # The exit status should be recorded as a substitution variable
            mock_sv.add_substitution.assert_called_once_with("$SYSTEM_CMD_EXIT_STATUS", "0")

    def test_system_cmd_continue_uses_popen(self, minimal_conf):
        from execsql.metacommands.system import x_system_cmd

        _setup_exec_log()
        _setup_subvars()
        _state.commandliststack = [MagicMock()]
        _state.commandliststack[-1].current_command.return_value = SimpleNamespace(
            current_script_line=lambda: ("test.sql", 2),
        )

        with (
            patch("execsql.metacommands.system.subprocess.Popen") as mock_popen,
            patch("execsql.metacommands.system.filewriter_close_all_after_write"),
        ):
            x_system_cmd(command="echo hello", **{"continue": "CONTINUE"})
            mock_popen.assert_called_once()

    def test_system_cmd_continue_sets_pid_subvar(self, minimal_conf):
        """When continue is set, $SYSTEM_CMD_PID must be recorded as a substitution var."""
        from execsql.metacommands.system import x_system_cmd

        _setup_exec_log()
        mock_sv = _setup_subvars()
        _state.commandliststack = [MagicMock()]
        _state.commandliststack[-1].current_command.return_value = SimpleNamespace(
            current_script_line=lambda: ("test.sql", 10),
        )

        fake_proc = MagicMock()
        fake_proc.pid = 54321

        with (
            patch("execsql.metacommands.system.subprocess.Popen", return_value=fake_proc),
            patch("execsql.metacommands.system.filewriter_close_all_after_write"),
        ):
            x_system_cmd(command="sleep 5", **{"continue": "CONTINUE"})
            mock_sv.add_substitution.assert_called_once_with("$SYSTEM_CMD_PID", "54321")

    def test_system_cmd_continue_does_not_set_exit_status(self, minimal_conf):
        """When continue is set, $SYSTEM_CMD_EXIT_STATUS must NOT be recorded."""
        from execsql.metacommands.system import x_system_cmd

        _setup_exec_log()
        mock_sv = _setup_subvars()
        _state.commandliststack = [MagicMock()]
        _state.commandliststack[-1].current_command.return_value = SimpleNamespace(
            current_script_line=lambda: ("test.sql", 11),
        )

        fake_proc = MagicMock()
        fake_proc.pid = 99

        with (
            patch("execsql.metacommands.system.subprocess.Popen", return_value=fake_proc),
            patch("execsql.metacommands.system.filewriter_close_all_after_write"),
        ):
            x_system_cmd(command="sleep 5", **{"continue": "CONTINUE"})
            # Only one subvar call, and it must be for PID — not EXIT_STATUS
            calls = mock_sv.add_substitution.call_args_list
            assert len(calls) == 1
            assert calls[0][0][0] == "$SYSTEM_CMD_PID"
            assert "$SYSTEM_CMD_EXIT_STATUS" not in [c[0][0] for c in calls]

    def test_system_cmd_sync_does_not_set_pid(self, minimal_conf):
        """Without continue, $SYSTEM_CMD_PID must NOT be set."""
        from execsql.metacommands.system import x_system_cmd

        _setup_exec_log()
        mock_sv = _setup_subvars()
        _state.commandliststack = [MagicMock()]
        _state.commandliststack[-1].current_command.return_value = SimpleNamespace(
            current_script_line=lambda: ("test.sql", 12),
        )

        mock_result = SimpleNamespace(returncode=0)
        with (
            patch("execsql.metacommands.system.subprocess.run", return_value=mock_result),
            patch("execsql.metacommands.system.filewriter_close_all_after_write"),
        ):
            x_system_cmd(command="echo hello", **{"continue": None})
            calls = mock_sv.add_substitution.call_args_list
            assert len(calls) == 1
            assert calls[0][0][0] == "$SYSTEM_CMD_EXIT_STATUS"
            assert "$SYSTEM_CMD_PID" not in [c[0][0] for c in calls]

    def test_system_cmd_nonzero_exit_status(self, minimal_conf):
        from execsql.metacommands.system import x_system_cmd

        _setup_exec_log()
        mock_sv = _setup_subvars()
        _state.commandliststack = [MagicMock()]
        _state.commandliststack[-1].current_command.return_value = SimpleNamespace(
            current_script_line=lambda: ("test.sql", 3),
        )

        mock_result = SimpleNamespace(returncode=1)
        with (
            patch("execsql.metacommands.system.subprocess.run", return_value=mock_result),
            patch("execsql.metacommands.system.filewriter_close_all_after_write"),
        ):
            x_system_cmd(command="false", **{"continue": None})
            mock_sv.add_substitution.assert_called_once_with("$SYSTEM_CMD_EXIT_STATUS", "1")


# ---------------------------------------------------------------------------
# Tests for x_write_warnings
# ---------------------------------------------------------------------------


class TestXWriteWarnings:
    """Tests for the WRITE WARNINGS metacommand handler."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("yes", True),
            ("on", True),
            ("true", True),
            ("1", True),
            ("no", False),
            ("off", False),
        ],
    )
    def test_write_warnings_flag(self, minimal_conf, value, expected):
        from execsql.metacommands.system import x_write_warnings

        minimal_conf.write_warnings = not expected
        x_write_warnings(yesno=value)
        assert minimal_conf.write_warnings is expected


# ---------------------------------------------------------------------------
# Tests for x_gui_level
# ---------------------------------------------------------------------------


class TestXGuiLevel:
    """Tests for the GUI LEVEL metacommand handler."""

    def test_gui_level_sets_conf(self, minimal_conf):
        from execsql.metacommands.system import x_gui_level

        x_gui_level(level="3")
        assert minimal_conf.gui_level == 3

    def test_gui_level_zero(self, minimal_conf):
        from execsql.metacommands.system import x_gui_level

        minimal_conf.gui_level = 5
        x_gui_level(level="0")
        assert minimal_conf.gui_level == 0


# ---------------------------------------------------------------------------
# Tests for x_cancel_halt
# ---------------------------------------------------------------------------


class TestXCancelHalt:
    """Tests for the CANCEL HALT metacommand handler."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("on", True),
            ("yes", True),
            ("true", True),
            ("off", False),
            ("no", False),
            ("false", False),
        ],
    )
    def test_cancel_halt_valid_flags(self, minimal_conf, value, expected):
        from execsql.metacommands.system import x_cancel_halt

        _state.status = SimpleNamespace(cancel_halt=not expected, batch=MagicMock())
        x_cancel_halt(onoff=value, metacommandline="CANCEL HALT ON")
        assert _state.status.cancel_halt is expected

    def test_cancel_halt_invalid_flag_raises(self, minimal_conf):
        from execsql.metacommands.system import x_cancel_halt

        _state.status = SimpleNamespace(cancel_halt=False, batch=MagicMock())
        with pytest.raises(ErrInfo):
            x_cancel_halt(onoff="maybe", metacommandline="CANCEL HALT maybe")


# ---------------------------------------------------------------------------
# Tests for x_consolewait_onerror / x_consolewait_whendone
# ---------------------------------------------------------------------------


class TestConsoleWaitFlags:
    """Tests for CONSOLE WAIT ON ERROR and CONSOLE WAIT WHEN DONE handlers."""

    @pytest.mark.parametrize(
        "value,expected",
        [("on", True), ("yes", True), ("true", True), ("1", True), ("off", False), ("no", False)],
    )
    def test_consolewait_onerror(self, minimal_conf, value, expected):
        from execsql.metacommands.system import x_consolewait_onerror

        x_consolewait_onerror(onoff=value)
        assert minimal_conf.gui_wait_on_error_halt is expected

    @pytest.mark.parametrize(
        "value,expected",
        [("on", True), ("yes", True), ("off", False), ("no", False)],
    )
    def test_consolewait_whendone(self, minimal_conf, value, expected):
        from execsql.metacommands.system import x_consolewait_whendone

        x_consolewait_whendone(onoff=value)
        assert minimal_conf.gui_wait_on_exit is expected


# ---------------------------------------------------------------------------
# Tests for x_cancel_halt_write / x_cancel_halt_write_clear
# ---------------------------------------------------------------------------


class TestCancelHaltWrite:
    """Tests for CANCEL HALT WRITE and CANCEL HALT WRITE CLEAR handlers."""

    def test_cancel_halt_write_sets_writespec(self, minimal_conf):
        from execsql.metacommands.system import x_cancel_halt_write

        x_cancel_halt_write(text="error occurred", tee=None, filename="out.txt")
        assert _state.cancel_halt_writespec is not None
        assert _state.cancel_halt_writespec.msg == "error occurred\n"
        assert _state.cancel_halt_writespec.outfile == "out.txt"

    def test_cancel_halt_write_clear(self, minimal_conf):
        from execsql.metacommands.system import x_cancel_halt_write, x_cancel_halt_write_clear

        x_cancel_halt_write(text="msg", tee=None, filename="out.txt")
        assert _state.cancel_halt_writespec is not None
        x_cancel_halt_write_clear()
        assert _state.cancel_halt_writespec is None


# ---------------------------------------------------------------------------
# Tests for x_error_halt_write / x_error_halt_write_clear
# ---------------------------------------------------------------------------


class TestErrorHaltWrite:
    """Tests for ERROR HALT WRITE and ERROR HALT WRITE CLEAR handlers."""

    def test_error_halt_write_sets_writespec(self, minimal_conf):
        from execsql.metacommands.system import x_error_halt_write

        x_error_halt_write(text="fatal error", tee="TEE", filename="err.log")
        assert _state.err_halt_writespec is not None
        assert _state.err_halt_writespec.msg == "fatal error\n"
        assert _state.err_halt_writespec.outfile == "err.log"

    def test_error_halt_write_clear(self, minimal_conf):
        from execsql.metacommands.system import x_error_halt_write, x_error_halt_write_clear

        x_error_halt_write(text="msg", tee=None, filename="err.log")
        x_error_halt_write_clear()
        assert _state.err_halt_writespec is None
