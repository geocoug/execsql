"""Unit tests for SHOW SCRIPTS / SHOW SCRIPT metacommand handlers and helpers."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest

from execsql.metacommands.debug import (
    _format_script_signature,
    _format_script_source,
    x_show_script,
    x_show_scripts,
)
from execsql.script.ast import ParamDef, ScriptBlock, SourceSpan


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestFormatScriptSignature:
    def test_no_params(self):
        assert _format_script_signature("proc", None) == "proc()"

    def test_empty_list(self):
        assert _format_script_signature("proc", []) == "proc()"

    def test_required_params(self):
        defs = [ParamDef("a"), ParamDef("b")]
        assert _format_script_signature("proc", defs) == "proc(a, b)"

    def test_default_params(self):
        defs = [ParamDef("a"), ParamDef("b", "100")]
        assert _format_script_signature("proc", defs) == "proc(a, b=100)"

    def test_all_defaults(self):
        defs = [ParamDef("x", "1"), ParamDef("y", "2")]
        assert _format_script_signature("proc", defs) == "proc(x=1, y=2)"

    def test_plain_strings_fallback(self):
        """Backward compat: plain strings without .default attribute."""
        assert _format_script_signature("proc", ["a", "b"]) == "proc(a, b)"


class TestFormatScriptSource:
    def test_full_span(self):
        span = SourceSpan("pipeline.sql", 15, 42)
        assert _format_script_source(span) == "pipeline.sql:15-42"

    def test_single_line_span(self):
        span = SourceSpan("test.sql", 10, 10)
        assert _format_script_source(span) == "test.sql:10"

    def test_no_end_line(self):
        span = SourceSpan("test.sql", 5)
        assert _format_script_source(span) == "test.sql:5"

    def test_path_basename(self):
        span = SourceSpan("/long/path/to/script.sql", 1, 10)
        assert _format_script_source(span) == "script.sql:1-10"

    def test_no_start_line(self):
        span = SourceSpan("test.sql", None)
        assert _format_script_source(span) == "test.sql"


# ---------------------------------------------------------------------------
# Handler tests (mock _state)
# ---------------------------------------------------------------------------


def _make_script(name, param_defs=None, doc=None, start=1, end=10):
    return ScriptBlock(
        span=SourceSpan("test.sql", start, end),
        name=name,
        param_defs=param_defs,
        doc=doc,
    )


@pytest.fixture()
def mock_state(monkeypatch):
    """Patch execsql.metacommands.debug._state with a mock."""
    import execsql.metacommands.debug as mod

    state = MagicMock()
    state.output = io.StringIO()
    state.ast_scripts = {}
    monkeypatch.setattr(mod, "_state", state)
    return state


class TestShowScriptsHandler:
    def test_empty(self, mock_state):
        x_show_scripts(metacommandline="SHOW SCRIPTS")
        assert "No scripts registered" in mock_state.output.getvalue()

    def test_lists_scripts(self, mock_state):
        mock_state.ast_scripts = {
            "proc1": _make_script("proc1", [ParamDef("a"), ParamDef("b")]),
            "proc2": _make_script("proc2"),
        }
        x_show_scripts(metacommandline="SHOW SCRIPTS")
        output = mock_state.output.getvalue()
        assert "proc1(a, b)" in output
        assert "proc2()" in output
        assert "Registered scripts (2)" in output

    def test_shows_defaults_in_signature(self, mock_state):
        mock_state.ast_scripts = {
            "load": _make_script("load", [ParamDef("schema"), ParamDef("batch", "1000")]),
        }
        x_show_scripts(metacommandline="SHOW SCRIPTS")
        assert "load(schema, batch=1000)" in mock_state.output.getvalue()


class TestShowScriptHandler:
    def test_not_found(self, mock_state):
        x_show_script(script_id="nonexistent", metacommandline="SHOW SCRIPT nonexistent")
        assert "No script named" in mock_state.output.getvalue()

    def test_detail_no_params(self, mock_state):
        mock_state.ast_scripts = {"proc": _make_script("proc")}
        x_show_script(script_id="proc", metacommandline="SHOW SCRIPT proc")
        output = mock_state.output.getvalue()
        assert "proc()" in output
        assert "Parameters: (none)" in output

    def test_detail_with_params(self, mock_state):
        mock_state.ast_scripts = {
            "load": _make_script("load", [ParamDef("schema"), ParamDef("batch", "1000")]),
        }
        x_show_script(script_id="load", metacommandline="SHOW SCRIPT load")
        output = mock_state.output.getvalue()
        assert "load(schema, batch=1000)" in output
        assert "(required)" in output
        assert "(optional, default: 1000)" in output

    def test_detail_with_doc(self, mock_state):
        mock_state.ast_scripts = {
            "proc": _make_script("proc", doc="This is the docstring.\nSecond line."),
        }
        x_show_script(script_id="proc", metacommandline="SHOW SCRIPT proc")
        output = mock_state.output.getvalue()
        assert "This is the docstring." in output
        assert "Second line." in output

    def test_case_insensitive_lookup(self, mock_state):
        mock_state.ast_scripts = {"myproc": _make_script("myproc")}
        x_show_script(script_id="MYPROC", metacommandline="SHOW SCRIPT MYPROC")
        assert "myproc()" in mock_state.output.getvalue()
