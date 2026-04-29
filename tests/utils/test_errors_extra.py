"""Additional tests for execsql.utils.errors — exit_now edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_info, exit_now


# ---------------------------------------------------------------------------
# exception_info — edge cases
# ---------------------------------------------------------------------------


class TestExceptionInfoEdgeCases:
    def test_string_exception_message_repr_fallback(self):
        """When str() fails on the message, repr() should be used."""

        class BadStr:
            def __str__(self):
                raise ValueError("can't stringify")

            def __repr__(self):
                return "BadStr()"

        class BadExc(Exception):
            def __init__(self):
                self.message = BadStr()

        try:
            raise BadExc()
        except Exception:
            info = exception_info()
        assert isinstance(info[1], str)


# ---------------------------------------------------------------------------
# exit_now — halt spec paths
# ---------------------------------------------------------------------------


class TestExitNowHaltSpecs:
    def setup_method(self):
        _state.reset()

    def teardown_method(self):
        _state.reset()

    def test_err_halt_writespec_called(self):
        mock_writespec = MagicMock()
        _state.err_halt_writespec = mock_writespec
        _state.output = MagicMock()

        errinfo = ErrInfo("error", other_msg="test")
        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, errinfo)
            mock_writespec.write.assert_called_once()

    def test_err_halt_writespec_failure_logged(self):
        mock_writespec = MagicMock()
        mock_writespec.write.side_effect = RuntimeError("write failed")
        _state.err_halt_writespec = mock_writespec
        _state.output = MagicMock()
        mock_log = MagicMock()
        _state.exec_log = mock_log

        errinfo = ErrInfo("error", other_msg="test")
        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, errinfo)
            mock_log.log_status_error.assert_called()

    def test_cancel_halt_writespec_called(self):
        mock_writespec = MagicMock()
        _state.cancel_halt_writespec = mock_writespec

        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(2, None)
            mock_writespec.write.assert_called_once()

    def test_cancel_halt_writespec_failure_logged(self):
        mock_writespec = MagicMock()
        mock_writespec.write.side_effect = RuntimeError("fail")
        _state.cancel_halt_writespec = mock_writespec
        mock_log = MagicMock()
        _state.exec_log = mock_log

        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(2, None)
            mock_log.log_status_error.assert_called()

    def test_err_halt_email_called(self):
        mock_mail = MagicMock()
        _state.err_halt_email = mock_mail
        _state.output = MagicMock()

        errinfo = ErrInfo("error", other_msg="test")
        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, errinfo)
            mock_mail.send.assert_called_once()

    def test_err_halt_email_failure_logged(self):
        mock_mail = MagicMock()
        mock_mail.send.side_effect = RuntimeError("smtp fail")
        _state.err_halt_email = mock_mail
        _state.output = MagicMock()
        mock_log = MagicMock()
        _state.exec_log = mock_log

        errinfo = ErrInfo("error", other_msg="test")
        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, errinfo)
            mock_log.log_status_error.assert_called()

    def test_cancel_halt_mailspec_called(self):
        mock_mail = MagicMock()
        _state.cancel_halt_mailspec = mock_mail

        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(2, None)
            mock_mail.send.assert_called_once()

    def test_cancel_halt_mailspec_failure_logged(self):
        mock_mail = MagicMock()
        mock_mail.send.side_effect = RuntimeError("fail")
        _state.cancel_halt_mailspec = mock_mail
        mock_log = MagicMock()
        _state.exec_log = mock_log

        with patch("execsql.utils.errors.sys.exit"), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(2, None)
            mock_log.log_status_error.assert_called()

    def test_err_halt_exec_runs_script(self):
        mock_exec = MagicMock()
        _state.err_halt_exec = mock_exec
        _state.commandliststack = []
        _state.output = MagicMock()

        errinfo = ErrInfo("error", other_msg="test")
        with (
            patch("execsql.utils.errors.sys.exit"),
            patch("execsql.utils.fileio.filewriter_end"),
            patch("execsql.utils.errors._run_deferred_script") as mock_run,
        ):
            exit_now(1, errinfo)
            mock_run.assert_called_once_with(mock_exec)

    def test_cancel_halt_exec_runs_script(self):
        mock_exec = MagicMock()
        _state.cancel_halt_exec = mock_exec
        _state.commandliststack = []

        with (
            patch("execsql.utils.errors.sys.exit"),
            patch("execsql.utils.fileio.filewriter_end"),
            patch("execsql.utils.errors._run_deferred_script") as mock_run,
        ):
            exit_now(2, None)
            mock_run.assert_called_once_with(mock_exec)

    def test_gui_console_wait_on_error(self):
        _state.output = MagicMock()
        _state.conf = MagicMock()
        _state.conf.gui_wait_on_error_halt = True
        _state.conf.gui_wait_on_exit = False

        errinfo = ErrInfo("error", other_msg="test")
        with (
            patch("execsql.utils.errors.sys.exit"),
            patch("execsql.utils.fileio.filewriter_end"),
            patch("execsql.utils.gui.gui_console_isrunning", return_value=True),
            patch("execsql.utils.gui.gui_console_wait_user") as mock_wait,
            patch("execsql.utils.gui.gui_console_off"),
        ):
            exit_now(1, errinfo)
            mock_wait.assert_called_once()

    def test_gui_console_wait_on_exit(self):
        _state.conf = MagicMock()
        _state.conf.gui_wait_on_error_halt = False
        _state.conf.gui_wait_on_exit = True

        with (
            patch("execsql.utils.errors.sys.exit"),
            patch("execsql.utils.fileio.filewriter_end"),
            patch("execsql.utils.gui.gui_console_isrunning", return_value=True),
            patch("execsql.utils.gui.gui_console_wait_user") as mock_wait,
            patch("execsql.utils.gui.gui_console_off"),
        ):
            exit_now(0, None)
            mock_wait.assert_called_once()
