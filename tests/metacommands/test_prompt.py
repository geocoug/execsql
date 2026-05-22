"""Unit tests for the interactive prompt metacommand handlers in metacommands/prompt.py.

These handlers normally render Tk/Textual dialogs and block on a return queue
fed by the GUI manager thread.  For tests we replace ``_state.gui_manager_queue``
with a :class:`_FakeManagerQueue` that, on every ``put(spec)``, immediately
delivers a canned response on the return queue embedded in the spec.  That
unblocks the handler synchronously without any real GUI.

Database interactions are mocked through :func:`_setup_db` which installs a
fake pool on ``_state.dbs``.  ``_state.subvars``, ``_state.status``, and
``_state.exec_log`` are replaced with mocks so we can assert handler side
effects.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.metacommands import prompt as _prompt
from execsql.utils.gui import (
    GUI_ACTION,
    GUI_COMPARE,
    GUI_DIRECTORY,
    GUI_DISPLAY,
    GUI_ENTRY,
    GUI_MAP,
    GUI_MSG,
    GUI_OPENFILE,
    GUI_PAUSE,
    GUI_SAVEFILE,
    GUI_SELECTROWS,
    QUERY_CONSOLE,
)


# ---------------------------------------------------------------------------
# Fake GUI queue / state setup
# ---------------------------------------------------------------------------


class _FakeManagerQueue:
    """Stand-in for ``_state.gui_manager_queue``.

    Records every ``GuiSpec`` it receives and pushes the matching pre-canned
    response onto the spec's return queue so the caller's blocking ``.get()``
    returns immediately.
    """

    def __init__(self, responses: dict[int, dict | list[dict]]) -> None:
        # Allow either a single response per kind or a list (consumed FIFO).
        self.responses: dict[int, list[dict]] = {}
        for kind, val in responses.items():
            self.responses[kind] = list(val) if isinstance(val, list) else [val]
        self.specs: list = []

    def put(self, spec) -> None:
        self.specs.append(spec)
        kind = spec.gui_type
        if kind not in self.responses or not self.responses[kind]:
            raise AssertionError(f"No canned response for GuiSpec kind={kind}")
        resp = self.responses[kind].pop(0)
        spec.return_queue.put(resp)


def _setup_state(*, gui_responses: dict | None = None, cancel_halt: bool = True) -> SimpleNamespace:
    """Install fakes for everything the prompt handlers touch.

    Returns a namespace exposing the mocks so tests can assert on them.
    """
    db = MagicMock()
    db.schema_qualified_table_name.side_effect = lambda schema, table: f"{schema}.{table}" if schema else table
    db.select_data.return_value = (["col1", "col2"], [("a", 1), ("b", 2)])
    db.table_exists.return_value = True

    pool = MagicMock()
    pool.current.return_value = db
    pool.aliased_as.return_value = db
    _state.dbs = pool

    subvars = MagicMock()
    subvars.sub_exists.return_value = False
    _state.subvars = subvars

    status = MagicMock()
    status.cancel_halt = cancel_halt
    status.dialog_canceled = False
    _state.status = status

    exec_log = MagicMock()
    _state.exec_log = exec_log

    queue = _FakeManagerQueue(gui_responses or {})
    _state.gui_manager_queue = queue

    # exec stack: ensure innermost scope frame has localvars
    from execsql.state import ExecFrame

    localvars = MagicMock()
    localvars.sub_exists.return_value = False
    top_cmd = ExecFrame(kind="script", localvars=localvars)
    _state.ast_exec_stack = [top_cmd]

    _state.gui_console = None
    _state.gui_manager_thread = None

    return SimpleNamespace(
        db=db,
        pool=pool,
        subvars=subvars,
        status=status,
        exec_log=exec_log,
        queue=queue,
        top_cmd=top_cmd,
    )


@pytest.fixture
def fake_state():
    """Return a factory that installs prompt-state mocks with chosen responses."""
    return _setup_state


@pytest.fixture(autouse=True)
def _patch_script_line():
    """Pin current_script_line() to a known value across this module."""
    with patch("execsql.metacommands.prompt.current_script_line", return_value=("script.sql", 7)):
        yield


@pytest.fixture(autouse=True)
def _patch_enable_gui():
    """Prevent enable_gui() from spawning a real GUI manager."""
    with patch("execsql.metacommands.prompt.enable_gui"):
        yield


@pytest.fixture(autouse=True)
def _patch_exit_now():
    """Replace exit_now with a function that raises a sentinel so we can assert halts."""

    class _Halt(SystemExit):
        pass

    def _raise_halt(code, _msg):
        raise _Halt(code)

    with patch("execsql.metacommands.prompt.exit_now", side_effect=_raise_halt) as m:
        m.HaltExc = _Halt  # type: ignore[attr-defined]
        yield m


# ---------------------------------------------------------------------------
# x_msg / x_reset_dialog_canceled — simplest cases
# ---------------------------------------------------------------------------


class TestXMsg:
    def test_puts_msg_spec_and_returns(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_MSG: {"button": 1}})
        result = _prompt.x_msg(message="hello")
        assert result is None
        assert len(s.queue.specs) == 1
        assert s.queue.specs[0].gui_type == GUI_MSG
        assert s.queue.specs[0].args["message"] == "hello"


class TestXResetDialogCanceled:
    def test_clears_dialog_canceled(self, fake_state) -> None:
        s = fake_state()
        s.status.dialog_canceled = True
        _prompt.x_reset_dialog_canceled()
        assert s.status.dialog_canceled is False


# ---------------------------------------------------------------------------
# x_prompt (DISPLAY)
# ---------------------------------------------------------------------------


class TestXPrompt:
    def test_continue_button_returns_normally(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 1}})
        _prompt.x_prompt(schema="s", table="t", message="hi", help="")
        assert s.db.select_data.called
        assert s.queue.specs[0].gui_type == GUI_DISPLAY
        assert s.queue.specs[0].args["title"] == "t"

    def test_cancel_with_cancel_halt_calls_exit(self, fake_state, _patch_exit_now) -> None:
        fake_state(gui_responses={GUI_DISPLAY: {"button": None}})
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt(schema="", table="t", message="hi", help="")

    def test_cancel_without_cancel_halt_just_returns(self, fake_state) -> None:
        fake_state(gui_responses={GUI_DISPLAY: {"button": None}}, cancel_halt=False)
        # Should not raise
        _prompt.x_prompt(schema="", table="t", message="", help="")


# ---------------------------------------------------------------------------
# x_prompt_enter
# ---------------------------------------------------------------------------


class TestXPromptEnter:
    def _kwargs(self, **over):
        base = {
            "match_str": "myvar",
            "message": "enter",
            "type": "text",
            "case": "any",
            "password": None,
            "schema": None,
            "table": None,
            "initial": None,
            "help": "",
        }
        base.update(over)
        return base

    def test_button_value_sets_subvar(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 1, "return_value": "abc"}})
        _prompt.x_prompt_enter(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("myvar", "abc")
        s.exec_log.log_status_info.assert_called()

    def test_password_logs_password_message(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 1, "return_value": "secret"}})
        _prompt.x_prompt_enter(**self._kwargs(password="P"))
        # Password log message differs from plain
        msg = s.exec_log.log_status_info.call_args[0][0]
        assert "Password" in msg

    def test_local_var_uses_commandliststack(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 1, "return_value": "v"}})
        _prompt.x_prompt_enter(**self._kwargs(match_str="~local"))
        s.top_cmd.localvars.add_substitution.assert_called_with("~local", "v")

    def test_button_none_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state(gui_responses={GUI_DISPLAY: {"button": None, "return_value": None}})
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_enter(**self._kwargs())

    def test_table_loads_rowset(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 1, "return_value": "v"}})
        _prompt.x_prompt_enter(**self._kwargs(table="t", schema=""))
        assert s.db.select_data.called


# ---------------------------------------------------------------------------
# x_prompt_pause
# ---------------------------------------------------------------------------


class TestXPromptPause:
    def _kwargs(self, **over):
        base = {"text": "please wait", "action": "halt", "countdown": None, "timeunit": None}
        base.update(over)
        return base

    def test_no_quit_returns(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_PAUSE: {"quit": False}})
        _prompt.x_prompt_pause(**self._kwargs())
        assert s.queue.specs[0].gui_type == GUI_PAUSE

    def test_countdown_minutes_converted(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_PAUSE: {"quit": False}})
        _prompt.x_prompt_pause(**self._kwargs(countdown=2, timeunit="minutes"))
        assert s.queue.specs[0].args["countdown"] == 120

    def test_quit_with_cancel_halt_calls_exit(self, fake_state, _patch_exit_now) -> None:
        fake_state(gui_responses={GUI_PAUSE: {"quit": True}})
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_pause(**self._kwargs(countdown=5, timeunit="seconds"))


# ---------------------------------------------------------------------------
# x_prompt_map
# ---------------------------------------------------------------------------


class TestXPromptMap:
    def _kwargs(self, **over):
        base = {
            "schema": "",
            "table": "t",
            "message": "m",
            "lat_col": "lat",
            "lon_col": "lon",
            "label_col": None,
            "symbol_col": None,
            "color_col": None,
        }
        base.update(over)
        return base

    def test_continue_returns(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_MAP: {"button": 1}})
        _prompt.x_prompt_map(**self._kwargs())
        assert s.queue.specs[0].gui_type == GUI_MAP

    def test_cancel_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state(gui_responses={GUI_MAP: {"button": None}})
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_map(**self._kwargs())


# ---------------------------------------------------------------------------
# x_prompt_compare / x_prompt_ask_compare
# ---------------------------------------------------------------------------


class TestPromptCompare:
    def _kwargs(self, **over):
        base = {
            "schema1": "",
            "table1": "t1",
            "alias1": None,
            "orient": "beside",
            "schema2": "",
            "table2": "t2",
            "alias2": None,
            "pks": "id",
            "msg": "m",
            "help": "",
        }
        base.update(over)
        return base

    def test_continue_returns(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_COMPARE: {"button": 1}})
        # select_data must return non-empty for both
        s.db.select_data.side_effect = [
            (["id", "v"], [(1, "a")]),
            (["id", "v"], [(1, "a")]),
        ]
        _prompt.x_prompt_compare(**self._kwargs())
        assert s.queue.specs[0].gui_type == GUI_COMPARE

    def test_alias1_lookup_failure_raises(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_COMPARE: {"button": 1}})
        s.pool.aliased_as.side_effect = Exception("no such alias")
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_compare(**self._kwargs(alias1="bogus"))

    def test_empty_rows_raises(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_COMPARE: {"button": 1}})
        s.db.select_data.return_value = (["id"], [])
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_compare(**self._kwargs())

    def test_missing_pk_raises(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_COMPARE: {"button": 1}})
        s.db.select_data.side_effect = [
            (["name"], [(1,)]),
            (["name"], [(1,)]),
        ]
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_compare(**self._kwargs(pks="id"))

    def test_cancel_halts(self, fake_state, _patch_exit_now) -> None:
        s = fake_state(gui_responses={GUI_COMPARE: {"button": None}})
        s.db.select_data.side_effect = [
            (["id"], [(1,)]),
            (["id"], [(1,)]),
        ]
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_compare(**self._kwargs())


class TestXPromptAskCompare:
    def _kwargs(self, **over):
        base = {
            "match": "ans",
            "schema1": "",
            "table1": "t1",
            "alias1": None,
            "orient": "beside",
            "schema2": "",
            "table2": "t2",
            "alias2": None,
            "pks": "id",
            "msg": "m",
            "help": "",
        }
        base.update(over)
        return base

    def test_yes_sets_subvar(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_COMPARE: {"button": 1}})
        s.db.select_data.side_effect = [(["id"], [(1,)]), (["id"], [(1,)])]
        _prompt.x_prompt_ask_compare(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("ans", "Yes")

    def test_no_sets_subvar(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_COMPARE: {"button": 0}})
        s.db.select_data.side_effect = [(["id"], [(1,)]), (["id"], [(1,)])]
        _prompt.x_prompt_ask_compare(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("ans", "No")

    def test_cancel_halts(self, fake_state, _patch_exit_now) -> None:
        s = fake_state(gui_responses={GUI_COMPARE: {"button": None}})
        s.db.select_data.side_effect = [(["id"], [(1,)]), (["id"], [(1,)])]
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_ask_compare(**self._kwargs())


# ---------------------------------------------------------------------------
# x_prompt_ask
# ---------------------------------------------------------------------------


class TestXPromptAsk:
    def _kwargs(self, **over):
        base = {"match": "ans", "schema": None, "table": None, "question": "?", "help": ""}
        base.update(over)
        return base

    def test_yes_records_var(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 1}})
        _prompt.x_prompt_ask(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("ans", "Yes")

    def test_no_records_var(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 0}})
        _prompt.x_prompt_ask(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("ans", "No")

    def test_table_branch_loads_data(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 1}})
        _prompt.x_prompt_ask(**self._kwargs(schema="", table="t"))
        assert s.db.select_data.called

    def test_cancel_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state(gui_responses={GUI_DISPLAY: {"button": None}})
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_ask(**TestXPromptAsk()._kwargs())


# ---------------------------------------------------------------------------
# x_ask (gui_console branch + non-gui branch)
# ---------------------------------------------------------------------------


class TestXAsk:
    def _kwargs(self, **over):
        base = {"question": "really?", "match": "ans"}
        base.update(over)
        return base

    def test_gui_console_yes(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 1}})
        _state.gui_console = object()  # truthy
        _prompt.x_ask(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("ans", "Yes")

    def test_gui_console_no(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DISPLAY: {"button": 0}})
        _state.gui_console = object()
        _prompt.x_ask(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("ans", "No")

    def test_gui_console_cancel_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state(gui_responses={GUI_DISPLAY: {"button": None}})
        _state.gui_console = object()
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_ask(**self._kwargs())

    def test_posix_get_yn_yes(self, fake_state) -> None:
        s = fake_state()
        _state.gui_console = None
        with patch("execsql.metacommands.prompt.os") as os_mock:
            os_mock.name = "posix"
            with patch("execsql.metacommands.prompt.get_yn", return_value="y"):
                _prompt.x_ask(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("ans", "Yes")

    def test_non_posix_get_yn_no(self, fake_state) -> None:
        s = fake_state()
        _state.gui_console = None
        with patch("execsql.metacommands.prompt.os") as os_mock:
            os_mock.name = "nt"
            with patch("execsql.metacommands.prompt.get_yn_win", return_value="n"):
                _prompt.x_ask(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("ans", "No")

    def test_esc_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state()
        _state.gui_console = None
        with (
            patch("execsql.metacommands.prompt.os") as os_mock,
            patch("execsql.metacommands.prompt.get_yn", return_value=chr(27)),
            pytest.raises(_patch_exit_now.HaltExc),
        ):
            os_mock.name = "posix"
            _prompt.x_ask(**self._kwargs())


# ---------------------------------------------------------------------------
# x_pause
# ---------------------------------------------------------------------------


class TestXPause:
    def _kwargs(self, **over):
        base = {"text": "t", "action": "halt", "countdown": None, "timeunit": None}
        base.update(over)
        return base

    def test_console_branch_no_quit(self, fake_state) -> None:
        s = fake_state(gui_responses={QUERY_CONSOLE: {"console_running": False}})
        _state.gui_manager_thread = MagicMock()  # truthy
        _state.conf.gui_level = 0
        with patch("execsql.metacommands.prompt.os") as os_mock:
            os_mock.name = "posix"
            with patch("execsql.metacommands.prompt.pause", return_value=0):
                _prompt.x_pause(**self._kwargs())
        assert s.queue.specs[0].gui_type == QUERY_CONSOLE

    def test_gui_pause_quit_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state(
            gui_responses={
                QUERY_CONSOLE: {"console_running": True},
                GUI_PAUSE: {"quit": True},
            },
        )
        _state.gui_manager_thread = MagicMock()
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_pause(**TestXPause()._kwargs(countdown=10, timeunit="seconds"))

    def test_non_gui_timeout_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state()
        _state.gui_manager_thread = None
        _state.conf.gui_level = 0
        with (
            patch("execsql.metacommands.prompt.os") as os_mock,
            patch("execsql.metacommands.prompt.pause", return_value=2),
            pytest.raises(_patch_exit_now.HaltExc),
        ):
            os_mock.name = "posix"
            _prompt.x_pause(**TestXPause()._kwargs(countdown=5, timeunit="seconds"))

    def test_non_gui_quit_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state()
        _state.gui_manager_thread = None
        _state.conf.gui_level = 0
        with (
            patch("execsql.metacommands.prompt.os") as os_mock,
            patch("execsql.metacommands.prompt.pause_win", return_value=1),
            pytest.raises(_patch_exit_now.HaltExc),
        ):
            os_mock.name = "nt"
            _prompt.x_pause(**TestXPause()._kwargs())

    def test_gui_level_above_zero_uses_gui(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_PAUSE: {"quit": False}})
        _state.gui_manager_thread = None
        _state.conf.gui_level = 2
        _prompt.x_pause(**self._kwargs(countdown=1, timeunit="seconds"))
        assert any(spec.gui_type == GUI_PAUSE for spec in s.queue.specs)


# ---------------------------------------------------------------------------
# x_prompt_savefile / x_prompt_openfile / x_prompt_directory
# ---------------------------------------------------------------------------


class TestXPromptSavefile:
    def _kwargs(self, **over):
        base = {
            "match": "path",
            "fn_match": None,
            "path_match": None,
            "ext_match": None,
            "fnbase_match": None,
            "startdir": "/tmp",
        }
        base.update(over)
        return base

    def test_filename_sets_subvar(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_SAVEFILE: {"filename": "/tmp/out.csv"}})
        _prompt.x_prompt_savefile(**self._kwargs())
        s.subvars.add_substitution.assert_called()

    def test_no_filename_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state(gui_responses={GUI_SAVEFILE: {"filename": None}})
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_savefile(**TestXPromptSavefile()._kwargs())

    def test_all_sub_var_companions(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_SAVEFILE: {"filename": "/tmp/out.csv"}})
        _prompt.x_prompt_savefile(
            **self._kwargs(
                fn_match="fn",
                path_match="pth",
                ext_match="ext",
                fnbase_match="base",
            ),
        )
        # Should have multiple substitutions
        assert s.subvars.add_substitution.call_count >= 3


class TestXPromptOpenfile:
    def _kwargs(self, **over):
        base = {
            "match": "path",
            "fn_match": None,
            "path_match": None,
            "ext_match": None,
            "fnbase_match": None,
            "startdir": None,
        }
        base.update(over)
        return base

    def test_duplicate_sub_var_raises(self, fake_state) -> None:
        fake_state()
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_openfile(**TestXPromptOpenfile()._kwargs(fn_match="path"))

    def test_filename_sets_all_companions(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_OPENFILE: {"filename": "/tmp/data.json"}})
        _prompt.x_prompt_openfile(
            **self._kwargs(
                fn_match="fn",
                path_match="pth",
                ext_match="ext",
                fnbase_match="base",
            ),
        )
        assert s.subvars.add_substitution.call_count >= 3

    def test_no_filename_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state(gui_responses={GUI_OPENFILE: {"filename": None}})
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_openfile(**TestXPromptOpenfile()._kwargs())


class TestXPromptDirectory:
    def _kwargs(self, **over):
        base = {"match": "dir", "fullpath": None, "startdir": "/tmp"}
        base.update(over)
        return base

    def test_dirname_sets_subvar(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DIRECTORY: {"directory": "/tmp/sub"}})
        _prompt.x_prompt_directory(**self._kwargs())
        s.subvars.add_substitution.assert_called()

    def test_fullpath_resolves(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_DIRECTORY: {"directory": "/tmp/sub"}})
        _prompt.x_prompt_directory(**self._kwargs(fullpath="1"))
        s.subvars.add_substitution.assert_called()

    def test_no_directory_halts(self, fake_state, _patch_exit_now) -> None:
        fake_state(gui_responses={GUI_DIRECTORY: {"directory": None}})
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_directory(**TestXPromptDirectory()._kwargs())


# ---------------------------------------------------------------------------
# x_prompt_select_rows
# ---------------------------------------------------------------------------


class TestXPromptSelectRows:
    def _kwargs(self, **over):
        base = {
            "schema1": "",
            "table1": "t1",
            "alias1": None,
            "schema2": "",
            "table2": "t2",
            "alias2": None,
            "msg": "m",
            "help": "",
        }
        base.update(over)
        return base

    def test_continue_returns(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_SELECTROWS: {"button": 1}})
        s.db.select_data.side_effect = [
            (["id", "v"], [(1, "a")]),
            (["id", "v"], [(1, "b")]),
        ]
        _prompt.x_prompt_select_rows(**self._kwargs())
        assert s.queue.specs[0].gui_type == GUI_SELECTROWS

    def test_empty_source_raises(self, fake_state) -> None:
        s = fake_state()
        s.db.select_data.return_value = (["id"], [])
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_select_rows(**TestXPromptSelectRows()._kwargs())

    def test_alias_lookup_failure_raises(self, fake_state) -> None:
        s = fake_state()
        s.pool.aliased_as.side_effect = Exception("bad")
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_select_rows(**TestXPromptSelectRows()._kwargs(alias1="x"))

    def test_missing_target_columns_raises(self, fake_state) -> None:
        s = fake_state()
        s.db.select_data.side_effect = [
            (["id", "extra"], [(1, "z")]),
            (["id"], [(1,)]),
        ]
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_select_rows(**TestXPromptSelectRows()._kwargs())

    def test_cancel_halts(self, fake_state, _patch_exit_now) -> None:
        s = fake_state(gui_responses={GUI_SELECTROWS: {"button": None}})
        s.db.select_data.side_effect = [
            (["id"], [(1,)]),
            (["id"], [(1,)]),
        ]
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_select_rows(**TestXPromptSelectRows()._kwargs())


# ---------------------------------------------------------------------------
# x_prompt_credentials / x_prompt_connect (thin wrappers)
# ---------------------------------------------------------------------------


class TestXPromptCredentials:
    def test_delegates_to_gui_credentials(self, fake_state) -> None:
        fake_state()
        with patch("execsql.metacommands.prompt.gui_credentials") as gc:
            _prompt.x_prompt_credentials(
                message="m",
                user="u",
                pw="p",
                metacommandline="PROMPT CREDENTIALS",
            )
        gc.assert_called_once()


class TestXPromptConnect:
    def test_delegates_to_gui_connect(self, fake_state) -> None:
        fake_state()
        with patch("execsql.metacommands.prompt.gui_connect") as gc:
            _prompt.x_prompt_connect(
                alias="a",
                message="m",
                help="",
                metacommandline="PROMPT CONNECT",
            )
        gc.assert_called_once()


# ---------------------------------------------------------------------------
# x_prompt_entryform (validation paths)
# ---------------------------------------------------------------------------


class TestXPromptEntryform:
    def _kwargs(self, **over):
        base = {
            "schema": "",
            "table": "spec",
            "schemadisp": None,
            "tabledisp": None,
            "message": "fill in",
            "help": "",
            "metacommandline": "PROMPT ENTRY_FORM",
        }
        base.update(over)
        return base

    def _setup_cursor(self, s, colnames, rows) -> None:
        """Mock _state.dbs.current().cursor()'s execute/fetch chain."""
        curs = MagicMock()
        curs.description = [(c,) for c in colnames]
        curs.fetchall.return_value = rows
        s.db.cursor.return_value = curs

    def test_missing_required_columns_raises(self, fake_state) -> None:
        s = fake_state()
        self._setup_cursor(s, ["sub_var"], [("x",)])  # missing 'prompt'
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_entryform(**self._kwargs())

    def test_missing_sub_var_value_raises(self, fake_state) -> None:
        s = fake_state()
        self._setup_cursor(s, ["sub_var", "prompt"], [(None, "p")])
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_entryform(**self._kwargs())

    def test_invalid_sub_var_name_raises(self, fake_state) -> None:
        s = fake_state()
        self._setup_cursor(s, ["sub_var", "prompt"], [("bad name!", "p")])
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_entryform(**self._kwargs())

    def test_missing_prompt_raises(self, fake_state) -> None:
        s = fake_state()
        self._setup_cursor(s, ["sub_var", "prompt"], [("x", None)])
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_entryform(**self._kwargs())

    def test_happy_path_sets_subvar(self, fake_state) -> None:
        s = fake_state(
            gui_responses={
                GUI_ENTRY: {
                    "button": 1,
                    "return_value": [SimpleNamespace(name="x", value="hello")],
                },
            },
        )
        self._setup_cursor(s, ["sub_var", "prompt"], [("x", "Enter value")])
        _prompt.x_prompt_entryform(**self._kwargs())
        s.subvars.add_substitution.assert_called_with("x", "hello")

    def test_cancel_halts(self, fake_state, _patch_exit_now) -> None:
        s = fake_state(gui_responses={GUI_ENTRY: {"button": None, "return_value": []}})
        self._setup_cursor(s, ["sub_var", "prompt"], [("x", "Enter value")])
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_entryform(**TestXPromptEntryform()._kwargs())

    def test_sequence_column_orders(self, fake_state) -> None:
        s = fake_state(
            gui_responses={
                GUI_ENTRY: {
                    "button": 1,
                    "return_value": [SimpleNamespace(name="x", value="v")],
                },
            },
        )
        self._setup_cursor(s, ["sub_var", "prompt", "sequence"], [("x", "p", 1)])
        _prompt.x_prompt_entryform(**self._kwargs())
        # cursor.execute must have been called with the ORDER BY query
        executed = [str(c.args[0]) for c in s.db.cursor.return_value.execute.call_args_list]
        assert any("order by sequence" in q for q in executed)

    def test_initial_value_checkbox(self, fake_state) -> None:
        s = fake_state(
            gui_responses={
                GUI_ENTRY: {
                    "button": 1,
                    "return_value": [SimpleNamespace(name="x", value="true")],
                },
            },
        )
        self._setup_cursor(
            s,
            ["sub_var", "prompt", "initial_value", "entry_type"],
            [("x", "p", "yes", "checkbox")],
        )
        _prompt.x_prompt_entryform(**self._kwargs())

    def test_width_height_column(self, fake_state) -> None:
        s = fake_state(
            gui_responses={
                GUI_ENTRY: {
                    "button": 1,
                    "return_value": [SimpleNamespace(name="x", value="v")],
                },
            },
        )
        self._setup_cursor(
            s,
            ["sub_var", "prompt", "width", "height", "form_column"],
            [("x", "p", "20", "5", "2")],
        )
        _prompt.x_prompt_entryform(**self._kwargs())

    def test_bad_width_raises(self, fake_state) -> None:
        s = fake_state()
        self._setup_cursor(s, ["sub_var", "prompt", "width"], [("x", "p", "abc")])
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_entryform(**self._kwargs())

    def test_display_table_loads(self, fake_state) -> None:
        s = fake_state(
            gui_responses={
                GUI_ENTRY: {
                    "button": 1,
                    "return_value": [SimpleNamespace(name="x", value="v")],
                },
            },
        )
        self._setup_cursor(s, ["sub_var", "prompt"], [("x", "p")])
        _prompt.x_prompt_entryform(**self._kwargs(schemadisp="", tabledisp="td"))


# ---------------------------------------------------------------------------
# x_prompt_action (validation paths)
# ---------------------------------------------------------------------------


class TestXPromptAction:
    def _kwargs(self, **over):
        base = dict(
            schema="",
            table="spec",
            schemadisp=None,
            tabledisp=None,
            message="m",
            compact=None,
            help="",
            **{"continue": None},
            metacommandline="PROMPT ACTION",
        )
        base.update(over)
        return base

    def _setup_cursor(self, s, colnames, rows) -> None:
        curs = MagicMock()
        curs.description = [(c,) for c in colnames]
        curs.fetchall.return_value = rows
        s.db.cursor.return_value = curs

    def test_missing_required_columns_raises(self, fake_state) -> None:
        s = fake_state()
        self._setup_cursor(s, ["label", "prompt"], [("L", "P")])
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_action(**self._kwargs())

    def test_missing_label_raises(self, fake_state) -> None:
        s = fake_state()
        self._setup_cursor(s, ["label", "prompt", "script"], [(None, "P", "S")])
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_action(**self._kwargs())

    def test_missing_prompt_raises(self, fake_state) -> None:
        s = fake_state()
        self._setup_cursor(s, ["label", "prompt", "script"], [("L", None, "S")])
        with pytest.raises(ErrInfo):
            _prompt.x_prompt_action(**self._kwargs())

    def test_happy_path(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_ACTION: {"button": 1}})
        self._setup_cursor(s, ["label", "prompt", "script"], [("L", "P", "S")])
        _prompt.x_prompt_action(**self._kwargs(compact="1", **{"continue": True}))

    def test_cancel_halts(self, fake_state, _patch_exit_now) -> None:
        s = fake_state(gui_responses={GUI_ACTION: {"button": 0}})
        self._setup_cursor(s, ["label", "prompt", "script"], [("L", "P", "S")])
        with pytest.raises(_patch_exit_now.HaltExc):
            _prompt.x_prompt_action(**TestXPromptAction()._kwargs())

    def test_with_sequence_and_display_table(self, fake_state) -> None:
        s = fake_state(gui_responses={GUI_ACTION: {"button": 1}})
        self._setup_cursor(
            s,
            ["label", "prompt", "script", "sequence", "data_required"],
            [("L", "P", "S", 1, True)],
        )
        _prompt.x_prompt_action(**self._kwargs(schemadisp="", tabledisp="td"))
