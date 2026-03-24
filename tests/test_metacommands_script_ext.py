"""Unit tests for execsql metacommand handlers in metacommands/script_ext.py.

Tests the handler functions directly with appropriate state mocking.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script import CommandList, ScriptCmd, MetacommandStmt, SqlStmt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_script_cmd(line: str, cmd_type: str = "cmd") -> ScriptCmd:
    """Create a ScriptCmd for testing."""
    if cmd_type == "cmd":
        return ScriptCmd("test.sql", 1, "cmd", MetacommandStmt(line))
    else:
        return ScriptCmd("test.sql", 1, "sql", SqlStmt(line))


def _make_commandlist(name: str, cmds: list[ScriptCmd] | None = None) -> CommandList:
    """Create a CommandList with at least one dummy command."""
    if cmds is None:
        cmds = [_make_script_cmd("LOG test")]
    return CommandList(cmds, name)


# ---------------------------------------------------------------------------
# Tests for x_extendscript
# ---------------------------------------------------------------------------


class TestXExtendScript:
    """Tests for the EXTEND SCRIPT metacommand handler."""

    def test_extend_script_appends_commands(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        cmd1 = _make_script_cmd("LOG msg1")
        cmd2 = _make_script_cmd("LOG msg2")
        s1 = _make_commandlist("source", [cmd1])
        s2 = _make_commandlist("target", [cmd2])
        _state.savedscripts["source"] = s1
        _state.savedscripts["target"] = s2

        x_extendscript(script1="source", script2="target")

        # target should now have cmd2 + cmd1
        assert len(s2.cmdlist) == 2
        assert s2.cmdlist[0] is cmd2
        assert s2.cmdlist[1] is cmd1

    def test_extend_script_merges_params(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        s1 = _make_commandlist("source", [_make_script_cmd("LOG a")])
        s1.paramnames = ["x", "y"]
        s2 = _make_commandlist("target", [_make_script_cmd("LOG b")])
        s2.paramnames = ["y", "z"]
        _state.savedscripts["source"] = s1
        _state.savedscripts["target"] = s2

        x_extendscript(script1="source", script2="target")

        # target params should be ["y", "z", "x"] -- x added, y not duplicated
        assert "x" in s2.paramnames
        assert "y" in s2.paramnames
        assert "z" in s2.paramnames
        assert s2.paramnames.count("y") == 1

    def test_extend_script_creates_params_on_target_if_none(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        s1 = _make_commandlist("source", [_make_script_cmd("LOG a")])
        s1.paramnames = ["p1"]
        s2 = _make_commandlist("target", [_make_script_cmd("LOG b")])
        s2.paramnames = None
        _state.savedscripts["source"] = s1
        _state.savedscripts["target"] = s2

        x_extendscript(script1="source", script2="target")
        assert s2.paramnames == ["p1"]

    def test_extend_script_missing_source_raises(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        s2 = _make_commandlist("target", [_make_script_cmd("LOG b")])
        _state.savedscripts["target"] = s2

        with pytest.raises(ErrInfo):
            x_extendscript(script1="nosuch", script2="target")

    def test_extend_script_missing_target_raises(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        s1 = _make_commandlist("source", [_make_script_cmd("LOG a")])
        _state.savedscripts["source"] = s1

        with pytest.raises(ErrInfo):
            x_extendscript(script1="source", script2="nosuch")


# ---------------------------------------------------------------------------
# Tests for x_extendscript_metacommand
# ---------------------------------------------------------------------------


class TestXExtendScriptMetacommand:
    """Tests for the EXTEND SCRIPT METACOMMAND handler."""

    def test_adds_metacommand_to_script(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript_metacommand

        s = _make_commandlist("myscript", [_make_script_cmd("LOG start")])
        _state.savedscripts["myscript"] = s

        # Need a commandliststack entry for current_script_line()
        mock_cl = MagicMock()
        mock_cl.current_command.return_value = SimpleNamespace(
            current_script_line=lambda: ("test.sql", 10),
        )
        _state.commandliststack = [mock_cl]

        x_extendscript_metacommand(script="myscript", cmd="LOG appended")
        assert len(s.cmdlist) == 2
        assert s.cmdlist[1].command_type == "cmd"

    def test_missing_script_raises(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript_metacommand

        with pytest.raises(ErrInfo):
            x_extendscript_metacommand(script="nosuch", cmd="LOG hello")


# ---------------------------------------------------------------------------
# Tests for x_extendscript_sql
# ---------------------------------------------------------------------------


class TestXExtendScriptSql:
    """Tests for the EXTEND SCRIPT SQL handler."""

    def test_adds_sql_to_script(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript_sql

        s = _make_commandlist("myscript", [_make_script_cmd("LOG start")])
        _state.savedscripts["myscript"] = s

        mock_cl = MagicMock()
        mock_cl.current_command.return_value = SimpleNamespace(
            current_script_line=lambda: ("test.sql", 15),
        )
        _state.commandliststack = [mock_cl]

        x_extendscript_sql(script="myscript", sql="SELECT 1;")
        assert len(s.cmdlist) == 2
        assert s.cmdlist[1].command_type == "sql"

    def test_missing_script_raises(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript_sql

        with pytest.raises(ErrInfo):
            x_extendscript_sql(script="nosuch", sql="SELECT 1;")


# ---------------------------------------------------------------------------
# Tests for x_executescript
# ---------------------------------------------------------------------------


class TestXExecuteScript:
    """Tests for the EXECUTE SCRIPT handler."""

    def test_executescript_missing_with_exists_guard(self, minimal_conf):
        from execsql.metacommands.script_ext import x_executescript

        # When exists="IF EXISTS" is specified and script doesn't exist,
        # it should be a no-op (not raise)
        result = x_executescript(
            exists="IF EXISTS",
            script_id="nosuch",
            script1=None,
            script2=None,
        )
        assert result is None
