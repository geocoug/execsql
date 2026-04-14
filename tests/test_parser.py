"""
Tests for the expression parsers in execsql.parser.

NumericParser is fully self-contained and is tested here comprehensively.
CondParser requires the metacommand dispatch table (conditionallist) for leaf
evaluation, so only structural / error-path tests are included here;
end-to-end conditional tests belong in integration tests.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from execsql.exceptions import CondParserError, NumericParserError
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


# ---------------------------------------------------------------------------
# NumericParser — edge cases and error paths
# ---------------------------------------------------------------------------


class TestNumericParserEdgeCases:
    """Error-path and boundary tests for NumericParser."""

    def _eval(self, expr: str):
        return NumericParser(expr).parse().eval()

    def test_division_by_zero(self):
        with pytest.raises(NumericParserError, match="Division by zero"):
            self._eval("1 / 0")

    def test_unmatched_open_paren(self):
        with pytest.raises(NumericParserError):
            NumericParser("(((1 + 2)").parse()

    def test_empty_parens(self):
        with pytest.raises(NumericParserError):
            NumericParser("()").parse()

    def test_empty_string(self):
        with pytest.raises(NumericParserError):
            NumericParser("").parse()

    def test_only_whitespace(self):
        with pytest.raises(NumericParserError):
            NumericParser("   ").parse()

    def test_only_operator(self):
        with pytest.raises(NumericParserError):
            NumericParser("*").parse()

    def test_trailing_operator(self):
        with pytest.raises(NumericParserError):
            NumericParser("1 +").parse()

    def test_double_operator(self):
        with pytest.raises(NumericParserError):
            NumericParser("1 + + 2").parse()

    def test_deeply_nested_parens(self):
        assert self._eval("((((((1 + 2))))))") == 3

    def test_many_chained_additions(self):
        expr = " + ".join(["1"] * 50)
        assert self._eval(expr) == 50

    def test_float_division_by_zero(self):
        with pytest.raises(NumericParserError, match="Division by zero"):
            self._eval("1.0 / 0.0")

    def test_unmatched_close_paren(self):
        with pytest.raises(NumericParserError):
            NumericParser("1 + 2)").parse()

    def test_non_numeric_input(self):
        with pytest.raises(NumericParserError):
            NumericParser("hello world").parse()


# ---------------------------------------------------------------------------
# CondParser — edge cases and error paths
# ---------------------------------------------------------------------------


class TestCondParserEdgeCases:
    """Error-path tests for CondParser structural parsing."""

    def test_empty_string_raises(self):
        with pytest.raises(CondParserError):
            CondParser("").parse()

    def test_only_whitespace_raises(self):
        with pytest.raises(CondParserError):
            CondParser("   ").parse()


# ---------------------------------------------------------------------------
# NumericParser — additional edge cases (left-associativity, chaining, etc.)
# ---------------------------------------------------------------------------


class TestNumericParserAssociativity:
    """Verify left-to-right evaluation for subtraction and division."""

    def _eval(self, expr: str):
        return NumericParser(expr).parse().eval()

    def test_subtraction_left_assoc(self):
        # 10 - 3 - 2 should be (10 - 3) - 2 = 5, not 10 - (3 - 2) = 9
        assert self._eval("10 - 3 - 2") == 5

    def test_division_left_assoc(self):
        # 12 / 3 / 2 should be (12 / 3) / 2 = 2, not 12 / (3 / 2) = 8
        assert self._eval("12 / 3 / 2") == 2.0

    def test_chained_subtraction_three(self):
        assert self._eval("100 - 20 - 30 - 10") == 40

    def test_chained_division_three(self):
        assert abs(self._eval("120 / 2 / 3 / 4") - 5.0) < 1e-9

    def test_mixed_add_sub_chain(self):
        assert self._eval("10 + 5 - 3 + 2 - 1") == 13

    def test_mixed_mul_div_chain(self):
        assert abs(self._eval("2 * 3 / 2 * 4") - 12.0) < 1e-9

    def test_precedence_mul_over_add_left_assoc(self):
        # 2 + 3 * 4 - 1 should be 2 + 12 - 1 = 13
        assert self._eval("2 + 3 * 4 - 1") == 13

    def test_precedence_div_over_sub(self):
        # 10 - 6 / 2 should be 10 - 3 = 7
        assert self._eval("10 - 6 / 2") == 7.0

    def test_negative_result(self):
        assert self._eval("3 - 5") == -2

    def test_parentheses_override_precedence(self):
        assert self._eval("(2 + 3) * (4 - 1)") == 15

    def test_deeply_nested_arithmetic(self):
        assert self._eval("((10 - 3) * 2 + (4 / 2))") == 16.0

    def test_single_zero(self):
        assert self._eval("0") == 0

    def test_add_negative_numbers(self):
        assert self._eval("-3 + -2") == -5

    def test_multiply_negative(self):
        assert self._eval("-3 * 4") == -12

    def test_float_precision(self):
        result = self._eval("0.1 + 0.2")
        assert abs(result - 0.3) < 1e-9


# ---------------------------------------------------------------------------
# CondAstNode — unknown type raises
# ---------------------------------------------------------------------------


class TestCondAstNodeUnknownType:
    def test_unknown_type_raises(self):
        # type=999 is unknown; left must be non-None so the node reaches the
        # fallthrough guard after the AND/OR branches (which call left.eval()).
        dummy_leaf = CondAstNode(CondAstNode.CONDITIONAL, (SimpleNamespace(exec_fn=lambda **kw: True), {}), None)
        node = CondAstNode(999, dummy_leaf, dummy_leaf)
        with pytest.raises(CondParserError, match="Unknown conditional node type"):
            node.eval()
