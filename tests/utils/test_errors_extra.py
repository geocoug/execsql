"""Additional tests for execsql.utils.errors — exit_now edge cases."""

from __future__ import annotations

import pytest

from execsql.exceptions import ScriptExit

from unittest.mock import MagicMock, patch

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.utils.errors import exception_desc, exit_now


# ---------------------------------------------------------------------------
# exception_desc — edge cases
# ---------------------------------------------------------------------------


class TestExceptionDescEdgeCases:
    def test_a_message_attribute_that_is_not_text_is_ignored(self):
        class BadExc(Exception):
            def __init__(self, text: str) -> None:
                super().__init__(text)
                self.message = object()

        try:
            raise BadExc("the real message")
        except Exception:
            assert exception_desc() == "BadExc: the real message"

    def test_an_exception_that_cannot_be_turned_into_text_is_shown_by_repr(self):
        class BadExc(Exception):
            def __str__(self):
                raise ValueError("can't stringify")

        try:
            raise BadExc()
        except Exception:
            desc = exception_desc()
        assert desc.startswith("BadExc: BadExc(")


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
        with pytest.raises(ScriptExit), patch("execsql.utils.fileio.filewriter_end"):
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
        with pytest.raises(ScriptExit), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, errinfo)
        mock_log.log_status_error.assert_called()

    def test_cancel_halt_writespec_called(self):
        mock_writespec = MagicMock()
        _state.cancel_halt_writespec = mock_writespec

        with pytest.raises(ScriptExit), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(2, None)
        mock_writespec.write.assert_called_once()

    def test_cancel_halt_writespec_failure_logged(self):
        mock_writespec = MagicMock()
        mock_writespec.write.side_effect = RuntimeError("fail")
        _state.cancel_halt_writespec = mock_writespec
        mock_log = MagicMock()
        _state.exec_log = mock_log

        with pytest.raises(ScriptExit), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(2, None)
        mock_log.log_status_error.assert_called()

    def test_err_halt_email_called(self):
        mock_mail = MagicMock()
        _state.err_halt_email = mock_mail
        _state.output = MagicMock()

        errinfo = ErrInfo("error", other_msg="test")
        with pytest.raises(ScriptExit), patch("execsql.utils.fileio.filewriter_end"):
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
        with pytest.raises(ScriptExit), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, errinfo)
        mock_log.log_status_error.assert_called()

    def test_cancel_halt_mailspec_called(self):
        mock_mail = MagicMock()
        _state.cancel_halt_mailspec = mock_mail

        with pytest.raises(ScriptExit), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(2, None)
        mock_mail.send.assert_called_once()

    def test_cancel_halt_mailspec_failure_logged(self):
        mock_mail = MagicMock()
        mock_mail.send.side_effect = RuntimeError("fail")
        _state.cancel_halt_mailspec = mock_mail
        mock_log = MagicMock()
        _state.exec_log = mock_log

        with pytest.raises(ScriptExit), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(2, None)
        mock_log.log_status_error.assert_called()

    def test_err_halt_exec_runs_script(self):
        mock_exec = MagicMock()
        _state.err_halt_exec = mock_exec
        _state.ast_exec_stack = []
        _state.output = MagicMock()

        errinfo = ErrInfo("error", other_msg="test")
        with (
            pytest.raises(ScriptExit),
            patch("execsql.utils.fileio.filewriter_end"),
            patch("execsql.utils.errors._run_deferred_script") as mock_run,
        ):
            exit_now(1, errinfo)
        mock_run.assert_called_once_with(mock_exec)

    def test_cancel_halt_exec_runs_script(self):
        mock_exec = MagicMock()
        _state.cancel_halt_exec = mock_exec
        _state.ast_exec_stack = []

        with (
            pytest.raises(ScriptExit),
            patch("execsql.utils.fileio.filewriter_end"),
            patch("execsql.utils.errors._run_deferred_script") as mock_run,
        ):
            exit_now(2, None)
        mock_run.assert_called_once_with(mock_exec)

    def test_cancel_halt_rolls_back_open_batches_before_its_script(self):
        from execsql.script.control import BatchLevels

        db = MagicMock()
        _state.status = MagicMock(batch=BatchLevels())
        _state.status.batch.new_batch()
        _state.status.batch.using_db(db)
        _state.cancel_halt_exec = MagicMock()
        _state.ast_exec_stack = []

        def script_runs(_spec):
            assert not _state.status.batch.in_batch()
            db.rollback.assert_called_once_with()

        with (
            pytest.raises(ScriptExit),
            patch("execsql.utils.fileio.filewriter_end"),
            patch("execsql.utils.errors._run_deferred_script", side_effect=script_runs) as mock_run,
        ):
            exit_now(2, None)
        mock_run.assert_called_once()
        db.commit.assert_not_called()

    def test_error_halt_leaves_an_autocommit_off_batch_to_the_script(self):
        from execsql.script.control import BatchLevels

        db = MagicMock(autocommit=False)
        _state.status = MagicMock(batch=BatchLevels())
        _state.status.batch.new_batch()
        _state.status.batch.using_db(db)
        _state.output = MagicMock()

        with pytest.raises(ScriptExit), patch("execsql.utils.fileio.filewriter_end"):
            exit_now(1, ErrInfo("error", other_msg="test"))
        assert not _state.status.batch.in_batch()
        db.rollback.assert_not_called()
        db.commit.assert_not_called()

    def test_gui_console_wait_on_error(self):
        _state.output = MagicMock()
        _state.conf = MagicMock()
        _state.conf.gui_wait_on_error_halt = True
        _state.conf.gui_wait_on_exit = False

        errinfo = ErrInfo("error", other_msg="test")
        with (
            pytest.raises(ScriptExit),
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
            pytest.raises(ScriptExit),
            patch("execsql.utils.fileio.filewriter_end"),
            patch("execsql.utils.gui.gui_console_isrunning", return_value=True),
            patch("execsql.utils.gui.gui_console_wait_user") as mock_wait,
            patch("execsql.utils.gui.gui_console_off"),
        ):
            exit_now(0, None)
        mock_wait.assert_called_once()
