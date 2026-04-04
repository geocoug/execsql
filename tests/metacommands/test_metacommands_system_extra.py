"""Additional unit tests for metacommands/system.py — console, halt specs, execute."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_exec_log():
    mock_log = MagicMock()
    _state.exec_log = mock_log
    return mock_log


# ---------------------------------------------------------------------------
# Console handlers
# ---------------------------------------------------------------------------


class TestXConsole:
    def test_console_on(self, minimal_conf):
        from execsql.metacommands.system import x_console

        with patch("execsql.metacommands.system.gui_console_on") as mock_on:
            x_console(onoff="on")
            mock_on.assert_called_once()

    def test_console_off(self, minimal_conf):
        from execsql.metacommands.system import x_console

        with patch("execsql.metacommands.system.gui_console_off") as mock_off:
            x_console(onoff="off")
            mock_off.assert_called_once()


class TestXConsoleProgress:
    def test_progress_direct(self, minimal_conf):
        from execsql.metacommands.system import x_consoleprogress

        with patch("execsql.metacommands.system.gui_console_progress") as mock_prog:
            x_consoleprogress(num="50", total=None)
            mock_prog.assert_called_once_with(50.0)

    def test_progress_with_total(self, minimal_conf):
        from execsql.metacommands.system import x_consoleprogress

        with patch("execsql.metacommands.system.gui_console_progress") as mock_prog:
            x_consoleprogress(num="25", total="50")
            mock_prog.assert_called_once_with(50.0)


class TestXConsoleWait:
    def test_consolewait(self, minimal_conf):
        from execsql.metacommands.system import x_consolewait

        with patch("execsql.metacommands.system.gui_console_wait_user") as mock_wait:
            x_consolewait(message="Press any key")
            mock_wait.assert_called_once_with("Press any key")


class TestXConsoleHideShow:
    def test_hide(self, minimal_conf):
        from execsql.metacommands.system import x_console_hideshow

        with patch("execsql.metacommands.system.gui_console_hide") as mock_hide:
            x_console_hideshow(hideshow="hide")
            mock_hide.assert_called_once()

    def test_show(self, minimal_conf):
        from execsql.metacommands.system import x_console_hideshow

        with patch("execsql.metacommands.system.gui_console_show") as mock_show:
            x_console_hideshow(hideshow="show")
            mock_show.assert_called_once()


class TestXConsoleWidth:
    def test_sets_width(self, minimal_conf):
        from execsql.metacommands.system import x_consolewidth

        with patch("execsql.metacommands.system.gui_console_width") as mock_w:
            x_consolewidth(width="120")
            assert minimal_conf.gui_console_width == 120
            mock_w.assert_called_once_with("120")


class TestXConsoleHeight:
    def test_sets_height(self, minimal_conf):
        from execsql.metacommands.system import x_consoleheight

        with patch("execsql.metacommands.system.gui_console_height") as mock_h:
            x_consoleheight(height="40")
            assert minimal_conf.gui_console_height == 40
            mock_h.assert_called_once_with("40")


class TestXConsoleStatus:
    def test_sets_status(self, minimal_conf):
        from execsql.metacommands.system import x_consolestatus

        with patch("execsql.metacommands.system.gui_console_status") as mock_s:
            x_consolestatus(message="Running...")
            mock_s.assert_called_once_with("Running...")


class TestXConsoleSave:
    def test_save_no_append(self, minimal_conf):
        from execsql.metacommands.system import x_consolesave

        with patch("execsql.metacommands.system.gui_console_save") as mock_save:
            x_consolesave(filename="log.txt", append=None)
            mock_save.assert_called_once_with("log.txt", False)

    def test_save_with_append(self, minimal_conf):
        from execsql.metacommands.system import x_consolesave

        with patch("execsql.metacommands.system.gui_console_save") as mock_save:
            x_consolesave(filename="log.txt", append="APPEND")
            mock_save.assert_called_once_with("log.txt", True)


# ---------------------------------------------------------------------------
# Halt email/exec specs
# ---------------------------------------------------------------------------


class TestCancelHaltEmail:
    def test_sets_mailspec(self, minimal_conf):
        from execsql.metacommands.system import x_cancel_halt_email

        x_cancel_halt_email(
            **{
                "from": "a@b.com",
                "to": "c@d.com",
                "subject": "Cancel",
                "msg": "Canceled",
                "msg_file": None,
                "att_file": None,
            },
        )
        assert _state.cancel_halt_mailspec is not None

    def test_clear_mailspec(self, minimal_conf):
        from execsql.metacommands.system import x_cancel_halt_email, x_cancel_halt_email_clear

        x_cancel_halt_email(
            **{
                "from": "a@b.com",
                "to": "c@d.com",
                "subject": "Cancel",
                "msg": "Canceled",
                "msg_file": None,
                "att_file": None,
            },
        )
        x_cancel_halt_email_clear()
        assert _state.cancel_halt_mailspec is None


class TestCancelHaltExec:
    def test_sets_exec_spec(self, minimal_conf):
        from execsql.metacommands.system import x_cancel_halt_exec

        _state.savedscripts = {"myscript": MagicMock()}
        x_cancel_halt_exec(script_id="myscript", argexp=None, looptype=None, loopcond=None, metacommandline="...")
        assert _state.cancel_halt_exec is not None

    def test_clear_exec_spec(self, minimal_conf):
        from execsql.metacommands.system import x_cancel_halt_exec_clear

        _state.cancel_halt_exec = MagicMock()
        x_cancel_halt_exec_clear()
        assert _state.cancel_halt_exec is None


class TestErrorHaltEmail:
    def test_sets_mailspec(self, minimal_conf):
        from execsql.metacommands.system import x_error_halt_email

        x_error_halt_email(
            **{
                "from": "a@b.com",
                "to": "c@d.com",
                "subject": "Error",
                "msg": "Error occurred",
                "msg_file": None,
                "att_file": None,
            },
        )
        assert _state.err_halt_email is not None

    def test_clear_mailspec(self, minimal_conf):
        from execsql.metacommands.system import x_error_halt_email, x_error_halt_email_clear

        x_error_halt_email(
            **{
                "from": "a@b.com",
                "to": "c@d.com",
                "subject": "Error",
                "msg": "Error occurred",
                "msg_file": None,
                "att_file": None,
            },
        )
        x_error_halt_email_clear()
        assert _state.err_halt_email is None


class TestErrorHaltExec:
    def test_sets_exec_spec(self, minimal_conf):
        from execsql.metacommands.system import x_error_halt_exec

        _state.savedscripts = {"errscript": MagicMock()}
        x_error_halt_exec(script_id="errscript", argexp=None, looptype=None, loopcond=None, metacommandline="...")
        assert _state.err_halt_exec is not None

    def test_clear_exec_spec(self, minimal_conf):
        from execsql.metacommands.system import x_error_halt_exec_clear

        _state.err_halt_exec = MagicMock()
        x_error_halt_exec_clear()
        assert _state.err_halt_exec is None


# ---------------------------------------------------------------------------
# x_email
# ---------------------------------------------------------------------------


class TestXEmail:
    def test_email_delegates_to_mailer(self, minimal_conf):
        from execsql.metacommands.system import x_email

        with patch("execsql.metacommands.system.Mailer") as MockMailer:
            mock_mailer = MagicMock()
            # x_email uses `with Mailer() as m:`, so __enter__ must return the mock
            mock_mailer.__enter__ = MagicMock(return_value=mock_mailer)
            mock_mailer.__exit__ = MagicMock(return_value=None)
            MockMailer.return_value = mock_mailer
            x_email(
                **{
                    "from": "a@b.com",
                    "to": "c@d.com",
                    "subject": "Test",
                    "msg": "Body",
                    "msg_file": None,
                    "att_file": None,
                },
            )
            mock_mailer.sendmail.assert_called_once_with(
                "a@b.com",
                "c@d.com",
                "Test",
                "Body",
                None,
                None,
            )


# ---------------------------------------------------------------------------
# x_log_sql
# ---------------------------------------------------------------------------


class TestXLogSql:
    @pytest.mark.parametrize(
        "value,expected",
        [("yes", True), ("on", True), ("true", True), ("1", True), ("no", False), ("off", False)],
    )
    def test_log_sql_flag(self, minimal_conf, value, expected):
        from execsql.metacommands.system import x_log_sql

        minimal_conf.log_sql = not expected
        x_log_sql(setting=value)
        assert minimal_conf.log_sql is expected


# ---------------------------------------------------------------------------
# x_execute
# ---------------------------------------------------------------------------


class TestXExecute:
    def test_execute_delegates_to_db(self, minimal_conf):
        from execsql.metacommands.system import x_execute

        mock_db = MagicMock()
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        x_execute(queryname="SELECT 1")
        mock_db.exec_cmd.assert_called_once_with("SELECT 1")
        mock_db.commit.assert_called_once()

    def test_execute_errinfo_reraised(self, minimal_conf):
        from execsql.metacommands.system import x_execute

        mock_db = MagicMock()
        mock_db.exec_cmd.side_effect = ErrInfo("db", command_text="bad sql")
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        with pytest.raises(ErrInfo):
            x_execute(queryname="bad sql")

    def test_execute_generic_exception_wraps_errinfo(self, minimal_conf):
        from execsql.metacommands.system import x_execute

        mock_db = MagicMock()
        mock_db.exec_cmd.side_effect = RuntimeError("boom")
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        with pytest.raises(ErrInfo):
            x_execute(queryname="SELECT 1")
