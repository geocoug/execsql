"""Unit tests for execsql metacommand handlers in metacommands/script_ext.py.

Tests the AST-backed handler functions directly. EXTEND SCRIPT operates on
``_state.ast_scripts`` (the registry of :class:`ScriptBlock` AST nodes),
not the legacy ``CommandList`` data structure.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script.ast import (
    MetaCommandStatement,
    ParamDef,
    ScriptBlock,
    SourceSpan,
    SqlStatement,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _span(line: int = 1) -> SourceSpan:
    return SourceSpan(file="test.sql", start_line=line, end_line=line)


def _meta(text: str, line: int = 1) -> MetaCommandStatement:
    return MetaCommandStatement(span=_span(line), command=text)


def _sql(text: str, line: int = 1) -> SqlStatement:
    return SqlStatement(span=_span(line), text=text)


def _make_script(name: str, body: list | None = None, params: list[str] | None = None) -> ScriptBlock:
    """Register a fresh ScriptBlock in ``_state.ast_scripts``."""
    param_defs = [ParamDef(name=p, default=None) for p in params] if params else None
    block = ScriptBlock(span=_span(), name=name, param_defs=param_defs, body=list(body) if body else [])
    _state.ast_scripts[name] = block
    return block


# ---------------------------------------------------------------------------
# Tests for x_extendscript
# ---------------------------------------------------------------------------


class TestXExtendScript:
    """Tests for the EXTEND SCRIPT metacommand handler."""

    def setup_method(self):
        _state.ast_scripts = {}

    def teardown_method(self):
        _state.ast_scripts = {}

    def test_extend_script_appends_commands(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        _make_script("source", [_meta("LOG msg1")])
        target = _make_script("target", [_meta("LOG msg2")])

        x_extendscript(script1="source", script2="target")

        assert len(target.body) == 2
        assert target.body[0].command == "LOG msg2"
        assert target.body[1].command == "LOG msg1"

    def test_extend_script_merges_params(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        _make_script("source", [_meta("LOG a")], params=["x", "y"])
        target = _make_script("target", [_meta("LOG b")], params=["y", "z"])

        x_extendscript(script1="source", script2="target")

        names = [p.name for p in target.param_defs]
        assert names == ["y", "z", "x"]

    def test_extend_script_creates_params_on_target_if_none(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        _make_script("source", [_meta("LOG a")], params=["p1"])
        target = _make_script("target", [_meta("LOG b")])  # no params

        x_extendscript(script1="source", script2="target")
        assert [p.name for p in target.param_defs] == ["p1"]

    def test_extend_script_missing_source_raises(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        _make_script("target")
        with pytest.raises(ErrInfo):
            x_extendscript(script1="nosuch", script2="target")

    def test_extend_script_missing_target_raises(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript

        _make_script("source")
        with pytest.raises(ErrInfo):
            x_extendscript(script1="source", script2="nosuch")


# ---------------------------------------------------------------------------
# Tests for x_extendscript_metacommand
# ---------------------------------------------------------------------------


class TestXExtendScriptMetacommand:
    """Tests for the EXTEND SCRIPT METACOMMAND handler."""

    def setup_method(self):
        _state.ast_scripts = {}

    def teardown_method(self):
        _state.ast_scripts = {}

    def test_adds_metacommand_to_script(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript_metacommand

        block = _make_script("myscript", [_meta("LOG start")])

        with patch("execsql.metacommands.script_ext.current_script_line", return_value=("test.sql", 10)):
            x_extendscript_metacommand(script="myscript", cmd="LOG appended")

        assert len(block.body) == 2
        assert isinstance(block.body[1], MetaCommandStatement)
        assert block.body[1].command == "LOG appended"

    def test_missing_script_raises(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript_metacommand

        with pytest.raises(ErrInfo):
            x_extendscript_metacommand(script="nosuch", cmd="LOG hello")


# ---------------------------------------------------------------------------
# Tests for x_extendscript_sql
# ---------------------------------------------------------------------------


class TestXExtendScriptSql:
    """Tests for the EXTEND SCRIPT SQL handler."""

    def setup_method(self):
        _state.ast_scripts = {}

    def teardown_method(self):
        _state.ast_scripts = {}

    def test_adds_sql_to_script(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript_sql

        block = _make_script("myscript", [_meta("LOG start")])

        with patch("execsql.metacommands.script_ext.current_script_line", return_value=("test.sql", 15)):
            x_extendscript_sql(script="myscript", sql="SELECT 1;")

        assert len(block.body) == 2
        assert isinstance(block.body[1], SqlStatement)
        assert block.body[1].text == "SELECT 1;"

    def test_missing_script_raises(self, minimal_conf):
        from execsql.metacommands.script_ext import x_extendscript_sql

        with pytest.raises(ErrInfo):
            x_extendscript_sql(script="nosuch", sql="SELECT 1;")


# ---------------------------------------------------------------------------
# Tests for x_executescript
# ---------------------------------------------------------------------------


class TestXExecuteScript:
    """Tests for the EXECUTE SCRIPT handler (now handled by AST executor)."""

    def test_x_executescript_raises_in_ast_mode(self, minimal_conf):
        """x_executescript raises because EXECUTE SCRIPT is handled by the AST executor."""
        from execsql.metacommands.script_ext import x_executescript

        with pytest.raises(ErrInfo, match="AST executor"):
            x_executescript(exists=None, script_id="anything")
