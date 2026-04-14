from __future__ import annotations

"""
Expression parsers for execsql conditional and arithmetic metacommands.

Provides a small recursive-descent parser toolkit used to evaluate the
boolean and numeric expressions that appear in execsql ``IF``/``ELSEIF``
and ``SET`` metacommands.

Classes:

- :class:`SourceString` — cursor-based scanner over a raw string; supports
  case-insensitive keyword matching, regex matching, and metacommand matching.
- :class:`CondTokens` / :class:`NumTokens` — integer token-type constants.
- :class:`CondAstNode` — AST node for boolean expressions (AND, OR, NOT,
  CONDITIONAL leaf).  ``eval()`` returns a ``bool``.
- :class:`NumericAstNode` — AST node for arithmetic expressions (MUL, DIV,
  ADD, SUB, NUMBER leaf).  ``eval()`` returns a number.
- :class:`CondParser` — parses a conditional expression string into a
  :class:`CondAstNode` tree.
- :class:`NumericParser` — parses an arithmetic expression string into a
  :class:`NumericAstNode` tree.
"""

import re
from typing import Any

from execsql.exceptions import CondParserError, NumericParserError

__all__ = [
    "SourceString",
    "CondTokens",
    "NumTokens",
    "CondAstNode",
    "NumericAstNode",
    "CondParser",
    "NumericParser",
]


class SourceString:
    """Cursor-based scanner over a raw string for token matching."""

    def __init__(self, source_string: str) -> None:
        """Initialise the scanner at position zero of the given string."""
        self.str = source_string
        self.currpos = 0

    def eoi(self) -> bool:
        """Return True if the entire source string has been consumed."""
        # Returns True or False indicating whether or not there is any of
        # the source string left to be consumed.
        return self.currpos >= len(self.str)

    def eat_whitespace(self) -> None:
        """Advance the cursor past any whitespace at the current position."""
        while not self.eoi() and self.str[self.currpos] in [" ", "\t", "\n"]:
            self.currpos += 1

    def match_str(self, str: str) -> str | None:
        """Match a string case-insensitively at the current position and advance."""
        # Tries to match the 'str' argument at the current position in the
        # source string.  Matching is case-insensitive.  If matching succeeds,
        # the matched string is returned and the internal pointer is incremented.
        # If matching fails, None is returned and the internal pointer is unchanged.
        self.eat_whitespace()
        if self.eoi():
            return None
        else:
            found = self.str.lower().startswith(str.lower(), self.currpos)
            if found:
                matched = self.str[self.currpos : self.currpos + len(str)]
                self.currpos += len(str)
                return matched
            else:
                return None

    def match_regex(self, regex: Any) -> dict | None:
        """Match a compiled regex at the current position and return named groups."""
        # Tries to match the 'regex' argument at the current position in the
        # source string.  If it succeeds, a dictionary of all of the named
        # groups is returned, and the internal pointer is incremented.
        self.eat_whitespace()
        if self.eoi():
            return None
        else:
            m = regex.match(self.str[self.currpos :])
            if m:
                self.currpos += m.end(0)
                return m.groupdict() or {}
            else:
                return None

    def match_metacommand(self, commandlist: Any) -> tuple | None:
        """Match a metacommand from the command list at the current position."""
        # Tries to match text at the current position to any metacommand
        # in the specified commandlist.
        # If it succeeds, the return value is a tuple of the MetaCommand object
        # and a dictionary of all of the named groups.  The internal pointer is
        # incremented past the match.
        self.eat_whitespace()
        if self.eoi():
            return None
        else:
            m = commandlist.get_match(self.str[self.currpos :])
            if m is not None:
                self.currpos += m[1].end(0)
                return (m[0], m[1].groupdict() or {})
            else:
                return None

    def remainder(self) -> str:
        """Return the unconsumed portion of the source string."""
        return self.str[self.currpos :]


# Classes for AST operator types.


class CondTokens:
    """Integer constants for conditional-expression AST node types."""

    AND, OR, NOT, CONDITIONAL = range(4)


class NumTokens:
    """Integer constants for numeric-expression AST node types."""

    MUL, DIV, ADD, SUB, NUMBER = range(5)


# AST for conditional expressions


class CondAstNode(CondTokens):
    """AST node for boolean expressions supporting AND, OR, NOT, and leaf conditionals."""

    def __init__(self, type: int, cond1: Any, cond2: Any) -> None:
        """Create a conditional AST node with the given operator type and children."""
        # 'type' should be one of the constants AND, OR, NOT, CONDITIONAL.
        # For AND and OR types, 'cond1' and 'cond2' should be a subtree (a CondAstNode)
        # For NOT type, 'cond1' should be a CondAstNode and 'cond2' should be None
        # For CONDITIONAL type, cond1' should be a tuple consisting of metacommand object and
        # its dictionary of named groups (mcmd, groupdict) and 'cond2' should be None.
        self.type = type
        self.left = cond1
        if type not in (self.CONDITIONAL, self.NOT):
            self.right = cond2
        else:
            self.right = None

    def eval(self) -> bool:
        """Evaluate this subtree and return a boolean result."""
        if self.type == self.CONDITIONAL:
            exec_fn = self.left[0].exec_fn
            cmdargs = self.left[1]
            return exec_fn(**cmdargs)
        if self.type == self.NOT:
            return not self.left.eval()
        lcond = self.left.eval()
        if self.type == self.AND:
            if not lcond:
                return False
            return self.right.eval()
        if self.type == self.OR:
            if lcond:
                return True
            return self.right.eval()
        raise CondParserError(f"Unknown conditional node type: {self.type}")


# AST for numeric expressions


class NumericAstNode(NumTokens):
    """AST node for arithmetic expressions supporting MUL, DIV, ADD, SUB, and NUMBER."""

    def __init__(self, type: int, value1: Any, value2: Any) -> None:
        """Create a numeric AST node with the given operator type and operands."""
        # 'type' should be one of the constants MUL, DIV, ADD, SUB, OR NUMBER.
        # 'value1' and 'value2' should each be either a subtree (a
        # NumericAstNode) or (only 'value1' should be) a number.
        self.type = type
        self.left = value1
        if type != self.NUMBER:
            self.right = value2
        else:
            self.right = None

    def eval(self) -> Any:
        """Evaluate this subtree and return a numeric result."""
        # Evaluates the subtrees and/or numeric value for this node,
        # returning a numeric value.
        if self.type == self.NUMBER:
            return self.left
        else:
            lnum = self.left.eval()
            rnum = self.right.eval()
            if self.type == self.MUL:
                return lnum * rnum
            elif self.type == self.DIV:
                if rnum == 0:
                    raise NumericParserError("Division by zero.")
                return lnum / rnum
            elif self.type == self.ADD:
                return lnum + rnum
            else:
                return lnum - rnum


# Conditional Parser


class CondParser(CondTokens):
    """Recursive-descent parser for boolean conditional expressions."""

    # Takes a conditional expression string.
    def __init__(self, condexpr: str) -> None:
        """Initialise the parser with the conditional expression string."""
        self.condexpr = condexpr
        self.cond_expr = SourceString(condexpr)

    def match_not(self) -> int | None:
        """Match a NOT operator and return its token type, or None."""
        # Try to match 'NOT' operator. If not found, return None
        m1 = self.cond_expr.match_str("NOT")
        if m1 is not None:
            return self.NOT
        return None

    def match_andop(self) -> int | None:
        """Match an AND operator and return its token type, or None."""
        # Try to match 'AND' operator. If not found, return None
        m1 = self.cond_expr.match_str("AND")
        if m1 is not None:
            return self.AND
        return None

    def match_orop(self) -> int | None:
        """Match an OR operator and return its token type, or None."""
        # Try to match 'OR' operator. If not found, return None
        m1 = self.cond_expr.match_str("OR")
        if m1 is not None:
            return self.OR
        return None

    def factor(self) -> Any:
        """Parse a factor: NOT, a parenthesised expression, or a metacommand leaf."""
        m1 = self.match_not()
        if m1 is not None:
            m1 = self.factor()
            return CondAstNode(self.NOT, m1, None)
        # Find the matching metacommand -- get a tuple consisting of (metacommand, groupdict)
        # conditionallist is a module-level global in the main execsql module
        import execsql.state as _state

        m1 = self.cond_expr.match_metacommand(_state.conditionallist)
        if m1 is not None:
            m1[1]["metacommandline"] = self.condexpr
            return CondAstNode(self.CONDITIONAL, m1, None)
        else:
            if self.cond_expr.match_str("(") is not None:
                m1 = self.expression()
                rp = self.cond_expr.match_str(")")
                if rp is None:
                    raise CondParserError(
                        f"Expected closing parenthesis at position {self.cond_expr.currpos} of {self.cond_expr.str}.",
                    )
                return m1
            else:
                raise CondParserError(
                    f"Can't parse a factor at position {self.cond_expr.currpos} of {self.cond_expr.str}.",
                )

    def term(self) -> Any:
        """Parse a term: a factor optionally followed by AND and another term."""
        m1 = self.factor()
        andop = self.match_andop()
        if andop is not None:
            m2 = self.term()
            return CondAstNode(andop, m1, m2)
        else:
            return m1

    def expression(self) -> Any:
        """Parse an expression: a term optionally followed by OR and another expression."""
        e1 = self.term()
        orop = self.match_orop()
        if orop is not None:
            e2 = self.expression()
            return CondAstNode(orop, e1, e2)
        else:
            return e1

    def parse(self) -> Any:
        """Parse the entire conditional expression and return the AST root."""
        exp = self.expression()
        if not self.cond_expr.eoi():
            raise CondParserError(
                f"Conditional expression parser did not consume entire string; remainder = {self.cond_expr.remainder()}.",
            )
        return exp


# Numeric Parser


class NumericParser(NumTokens):
    """Recursive-descent parser for arithmetic numeric expressions."""

    # Takes a numeric expression string
    def __init__(self, numexpr: str) -> None:
        """Initialise the parser with the numeric expression string."""
        self.num_expr = SourceString(numexpr)
        self.rxint = re.compile(r"(?P<int_num>[+-]?[0-9]+)")
        self.rxfloat = re.compile(r"(?P<float_num>[+-]?(?:(?:[0-9]*\.[0-9]+)|(?:[0-9]+\.[0-9]*)))")

    def match_number(self) -> Any | None:
        """Match a float or integer literal and return its numeric value, or None."""
        # Try to match a number in the source string.
        # Return it if matched, return None if unmatched.
        m1 = self.num_expr.match_regex(self.rxfloat)
        if m1 is not None:
            return float(m1["float_num"])
        else:
            m2 = self.num_expr.match_regex(self.rxint)
            if m2 is not None:
                return int(m2["int_num"])
        return None

    def match_mulop(self) -> int | None:
        """Match a multiplication or division operator and return its token type, or None."""
        # Try to match a multiplication or division operator in the source string.
        # if found, return the matching operator type.  If not found, return None.
        m1 = self.num_expr.match_str("*")
        if m1 is not None:
            return self.MUL
        else:
            m2 = self.num_expr.match_str("/")
            if m2 is not None:
                return self.DIV
        return None

    def match_addop(self) -> int | None:
        """Match an addition or subtraction operator and return its token type, or None."""
        # Try to match an addition or subtraction operator in the source string.
        # if found, return the matching operator type.  If not found, return None.
        m1 = self.num_expr.match_str("+")
        if m1 is not None:
            return self.ADD
        else:
            m2 = self.num_expr.match_str("-")
            if m2 is not None:
                return self.SUB
        return None

    def factor(self) -> Any:
        """Parse a numeric factor: a number literal or a parenthesised expression."""
        # Parses a factor out of the source string and returns the
        # AST node that is created.
        m1 = self.match_number()
        if m1 is not None:
            return NumericAstNode(self.NUMBER, m1, None)
        else:
            if self.num_expr.match_str("(") is not None:
                m1 = self.expression()
                rp = self.num_expr.match_str(")")
                if rp is None:
                    raise NumericParserError(
                        f"Expected closing parenthesis at position {self.num_expr.currpos} of {self.num_expr.str}.",
                    )
                else:
                    return m1
            else:
                raise NumericParserError(
                    f"Can't parse a factor at position {self.num_expr.currpos} of {self.num_expr.str}.",
                )

    def term(self) -> Any:
        """Parse a term: a factor followed by zero or more MUL/DIV operators (left-associative)."""
        node = self.factor()
        while True:
            mulop = self.match_mulop()
            if mulop is None:
                break
            right = self.factor()
            node = NumericAstNode(mulop, node, right)
        return node

    def expression(self) -> Any:
        """Parse an expression: a term followed by zero or more ADD/SUB operators (left-associative)."""
        node = self.term()
        if node is None:
            return
        while True:
            addop = self.match_addop()
            if addop is None:
                break
            right = self.term()
            node = NumericAstNode(addop, node, right)
        return node

    def parse(self) -> Any:
        """Parse the entire numeric expression and return the AST root."""
        exp = self.expression()
        if not self.num_expr.eoi():
            raise NumericParserError(
                f"Numeric expression parser did not consume entire string; remainder = {self.num_expr.remainder()}.",
            )
        return exp
