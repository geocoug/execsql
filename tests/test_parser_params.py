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
