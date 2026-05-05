"""Direct unit tests for parser parameter and docstring internals."""

from __future__ import annotations

import pytest

from execsql.exceptions import ErrInfo
from execsql.script.ast import ParamDef
from execsql.script.parser import _parse_param_defs


class TestParseParamDefs:
    """Tests for _parse_param_defs — the parameter definition parser."""

    def test_single_required(self):
        result = _parse_param_defs("a", 1, "test.sql")
        assert result == [ParamDef("a")]

    def test_multiple_required(self):
        result = _parse_param_defs("a, b, c", 1, "test.sql")
        assert result == [ParamDef("a"), ParamDef("b"), ParamDef("c")]

    def test_single_optional(self):
        result = _parse_param_defs("a=100", 1, "test.sql")
        assert result == [ParamDef("a", "100")]

    def test_mixed_required_optional(self):
        result = _parse_param_defs("schema, table, batch=1000, dry_run=false", 1, "test.sql")
        assert result == [
            ParamDef("schema"),
            ParamDef("table"),
            ParamDef("batch", "1000"),
            ParamDef("dry_run", "false"),
        ]

    def test_required_after_optional_raises(self):
        with pytest.raises(ErrInfo, match="Required parameter.*after optional"):
            _parse_param_defs("a=1, b", 5, "bad.sql")

    def test_required_after_optional_names_params(self):
        """Error message includes the parameter names."""
        with pytest.raises(ErrInfo, match="'b'.*'a'"):
            _parse_param_defs("a=1, b", 5, "bad.sql")

    def test_all_optional(self):
        result = _parse_param_defs("x=1, y=2, z=3", 1, "test.sql")
        assert all(p.default is not None for p in result)

    def test_whitespace_handling(self):
        result = _parse_param_defs("  a  ,  b = 100  ", 1, "test.sql")
        assert result == [ParamDef("a"), ParamDef("b", "100")]

    def test_required_property(self):
        defs = _parse_param_defs("a, b=10", 1, "test.sql")
        assert defs[0].required is True
        assert defs[1].required is False


class TestParseParamDefsQuotedDefaults:
    """Quoted default values: surrounding quotes are stripped, spaces and
    commas inside quotes are preserved, and both quote styles are accepted."""

    def test_double_quoted_default_strips_quotes(self):
        """`name="value"` stores `value`, not `"value"`."""
        result = _parse_param_defs('name="Default"', 1, "test.sql")
        assert result == [ParamDef("name", "Default")]

    def test_single_quoted_default_strips_quotes(self):
        result = _parse_param_defs("name='Default'", 1, "test.sql")
        assert result == [ParamDef("name", "Default")]

    def test_quoted_default_with_spaces(self):
        """Embedded spaces are preserved when quoted."""
        result = _parse_param_defs('msg="hello world"', 1, "test.sql")
        assert result == [ParamDef("msg", "hello world")]

    def test_quoted_default_with_comma(self):
        """Embedded commas don't split the token when inside quotes."""
        result = _parse_param_defs('list="a, b, c"', 1, "test.sql")
        assert result == [ParamDef("list", "a, b, c")]

    def test_quoted_default_with_special_chars(self):
        """Slashes, equals, and other special chars survive."""
        result = _parse_param_defs('logfile="/dev/null"', 1, "test.sql")
        assert result == [ParamDef("logfile", "/dev/null")]

    def test_quoted_default_with_empty_string(self):
        """`name=""` stores an empty string."""
        result = _parse_param_defs('name=""', 1, "test.sql")
        assert result == [ParamDef("name", "")]

    def test_unquoted_default_unchanged(self):
        """Unquoted values are stored verbatim — no quote-stripping false positive."""
        result = _parse_param_defs("count=100", 1, "test.sql")
        assert result == [ParamDef("count", "100")]

    def test_mixed_quoted_and_unquoted(self):
        """User's reported case: a real-world signature."""
        result = _parse_param_defs(
            'rows, output_table="std_chem", default_unit_set="Default", logfile="/dev/null"',
            1,
            "test.sql",
        )
        assert result == [
            ParamDef("rows"),
            ParamDef("output_table", "std_chem"),
            ParamDef("default_unit_set", "Default"),
            ParamDef("logfile", "/dev/null"),
        ]

    def test_mismatched_quotes_treated_as_unquoted(self):
        """`name="value` (no closing quote) is rejected as malformed."""
        with pytest.raises(ErrInfo, match="Invalid parameter token"):
            _parse_param_defs('name="value', 1, "test.sql")

    def test_double_quotes_inside_single_quoted(self):
        """Single-quoted value can contain double quotes."""
        result = _parse_param_defs("""msg='say "hi"'""", 1, "test.sql")
        assert result == [ParamDef("msg", 'say "hi"')]

    def test_single_quotes_inside_double_quoted(self):
        """Double-quoted value can contain single quotes (apostrophes)."""
        result = _parse_param_defs("""msg=\"it's\"""", 1, "test.sql")
        assert result == [ParamDef("msg", "it's")]
