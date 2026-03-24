"""
Tests for the expression parsers in execsql.parser.

NumericParser is fully self-contained and is tested here comprehensively.
CondParser requires the metacommand dispatch table (conditionallist) for leaf
evaluation, so only structural / error-path tests are included here;
end-to-end conditional tests belong in integration tests.
"""

from __future__ import annotations

import pytest

from execsql.exceptions import NumericParserError
from execsql.parser import (
    CondAstNode,
    CondParser,
    CondTokens,
    NumericAstNode,
    NumericParser,
    NumTokens,
    SourceString,
)


# ---------------------------------------------------------------------------
# SourceString
# ---------------------------------------------------------------------------


class TestSourceString:
    def test_eoi_on_empty(self):
        ss = SourceString("")
        assert ss.eoi() is True

    def test_eoi_on_nonempty(self):
        ss = SourceString("hello")
        assert ss.eoi() is False

    def test_match_str_success(self):
        ss = SourceString("AND rest")
        result = ss.match_str("AND")
        assert result == "AND"
        assert ss.remainder() == " rest"

    def test_match_str_case_insensitive(self):
        ss = SourceString("and rest")
        assert ss.match_str("AND") == "and"

    def test_match_str_failure(self):
        ss = SourceString("OR rest")
        assert ss.match_str("AND") is None
        # Pointer should be unchanged
        assert ss.remainder() == "OR rest"

    def test_match_str_skips_whitespace(self):
        ss = SourceString("   AND rest")
        assert ss.match_str("AND") == "AND"

    def test_remainder_after_match(self):
        ss = SourceString("hello world")
        ss.match_str("hello")
        assert ss.remainder() == " world"

    def test_match_regex(self):
        import re

        ss = SourceString("  42 rest")
        rx = re.compile(r"(?P<num>\d+)")
        result = ss.match_regex(rx)
        assert result == {"num": "42"}

    def test_match_regex_failure(self):
        import re

        ss = SourceString("abc")
        rx = re.compile(r"(?P<num>\d+)")
        assert ss.match_regex(rx) is None

    def test_match_regex_at_eoi_returns_none(self):
        """match_regex returns None when source string is at end of input (line 68)."""
        import re

        ss = SourceString("")
        rx = re.compile(r"(?P<num>\d+)")
        assert ss.match_regex(rx) is None


# ---------------------------------------------------------------------------
# NumericParser
# ---------------------------------------------------------------------------


class TestNumericParser:
    def _eval(self, expr: str):
        return NumericParser(expr).parse().eval()

    def test_integer_literal(self):
        assert self._eval("42") == 42

    def test_float_literal(self):
        assert abs(self._eval("3.14") - 3.14) < 1e-9

    def test_addition(self):
        assert self._eval("2 + 3") == 5

    def test_subtraction(self):
        assert self._eval("10 - 4") == 6

    def test_multiplication(self):
        assert self._eval("3 * 4") == 12

    def test_division(self):
        assert abs(self._eval("10 / 4") - 2.5) < 1e-9

    def test_operator_precedence_mul_before_add(self):
        # 2 + 3 * 4 should be 14 (right-recursive grammar means 2 + (3*4))
        result = self._eval("2 + 3 * 4")
        assert result == 14

    def test_parentheses(self):
        assert self._eval("(2 + 3) * 4") == 20

    def test_negative_number(self):
        assert self._eval("-5") == -5

    def test_nested_parentheses(self):
        assert self._eval("((2 + 3) * (4 - 1))") == 15

    def test_integer_result(self):
        result = self._eval("6")
        assert isinstance(result, int)

    def test_float_result(self):
        result = self._eval("1.5")
        assert isinstance(result, float)

    def test_extra_text_raises(self):
        with pytest.raises(NumericParserError):
            NumericParser("1 + 2 extra").parse()

    def test_invalid_expr_raises(self):
        with pytest.raises(NumericParserError):
            NumericParser("abc").parse()

    def test_unclosed_paren_raises(self):
        with pytest.raises(NumericParserError):
            NumericParser("(1 + 2").parse()

    def test_division_float(self):
        result = self._eval("7 / 2")
        assert result == 3.5

    def test_zero_subtraction(self):
        assert self._eval("5 - 5") == 0


# ---------------------------------------------------------------------------
# NumericAstNode
# ---------------------------------------------------------------------------


class TestNumericAstNode:
    def test_number_node(self):
        node = NumericAstNode(NumTokens.NUMBER, 7, None)
        assert node.eval() == 7

    def test_add_node(self):
        lhs = NumericAstNode(NumTokens.NUMBER, 3, None)
        r = NumericAstNode(NumTokens.NUMBER, 4, None)
        node = NumericAstNode(NumTokens.ADD, lhs, r)
        assert node.eval() == 7

    def test_mul_node(self):
        lhs = NumericAstNode(NumTokens.NUMBER, 3, None)
        r = NumericAstNode(NumTokens.NUMBER, 4, None)
        node = NumericAstNode(NumTokens.MUL, lhs, r)
        assert node.eval() == 12

    def test_div_node(self):
        lhs = NumericAstNode(NumTokens.NUMBER, 9, None)
        r = NumericAstNode(NumTokens.NUMBER, 3, None)
        node = NumericAstNode(NumTokens.DIV, lhs, r)
        assert node.eval() == 3.0

    def test_sub_node(self):
        lhs = NumericAstNode(NumTokens.NUMBER, 10, None)
        r = NumericAstNode(NumTokens.NUMBER, 4, None)
        node = NumericAstNode(NumTokens.SUB, lhs, r)
        assert node.eval() == 6


# ---------------------------------------------------------------------------
# CondAstNode (structure only — no dispatch table needed)
# ---------------------------------------------------------------------------


class TestCondAstNode:
    def _bool_leaf(self, val: bool) -> CondAstNode:
        """Build a CONDITIONAL leaf that returns a fixed bool without _state."""

        class FakeCmd:
            def __init__(self, v):
                self._v = v

            @property
            def exec_fn(self):
                v = self._v
                return lambda **kw: v

        node = CondAstNode(CondTokens.CONDITIONAL, (FakeCmd(val), {}), None)
        return node

    def test_not_node_inverts(self):
        leaf = self._bool_leaf(True)
        not_node = CondAstNode(CondTokens.NOT, leaf, None)
        assert not_node.eval() is False

    def test_and_node_both_true(self):
        lhs = self._bool_leaf(True)
        r = self._bool_leaf(True)
        node = CondAstNode(CondTokens.AND, lhs, r)
        assert node.eval() is True

    def test_and_node_short_circuit_false(self):
        lhs = self._bool_leaf(False)
        r = self._bool_leaf(True)
        node = CondAstNode(CondTokens.AND, lhs, r)
        assert node.eval() is False

    def test_or_node_one_true(self):
        lhs = self._bool_leaf(False)
        r = self._bool_leaf(True)
        node = CondAstNode(CondTokens.OR, lhs, r)
        assert node.eval() is True

    def test_or_node_short_circuit_true(self):
        lhs = self._bool_leaf(True)
        r = self._bool_leaf(False)
        node = CondAstNode(CondTokens.OR, lhs, r)
        assert node.eval() is True

    def test_conditional_leaf(self):
        leaf = self._bool_leaf(True)
        assert leaf.eval() is True


# ---------------------------------------------------------------------------
# CondParser — operator matching (no conditionallist required)
# ---------------------------------------------------------------------------


class TestCondParserOperatorMatching:
    """Test the simple operator-matching helpers on CondParser directly.

    These helpers only do string matching against the internal SourceString and
    do not need the conditionallist metacommand table to be populated.
    """

    def test_match_not_returns_none_when_absent(self):
        cp = CondParser("something else")
        assert cp.match_not() is None

    def test_match_andop_returns_none_when_absent(self):
        """match_andop returns None when AND is not present (line 199)."""
        cp = CondParser("something else")
        assert cp.match_andop() is None

    def test_match_orop_returns_none_when_absent(self):
        """match_orop returns None when OR is not present (line 206)."""
        cp = CondParser("something else")
        assert cp.match_orop() is None

    def test_match_not_returns_not_token(self):
        cp = CondParser("NOT something")
        result = cp.match_not()
        assert result == CondTokens.NOT

    def test_match_andop_returns_and_token(self):
        cp = CondParser("AND something")
        result = cp.match_andop()
        assert result == CondTokens.AND

    def test_match_orop_returns_or_token(self):
        cp = CondParser("OR something")
        result = cp.match_orop()
        assert result == CondTokens.OR
