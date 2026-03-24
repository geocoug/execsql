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


class SourceString:
    def __init__(self, source_string: str) -> None:
        self.str = source_string
        self.currpos = 0

    def eoi(self) -> bool:
        # Returns True or False indicating whether or not there is any of
        # the source string left to be consumed.
        return self.currpos >= len(self.str)

    def eat_whitespace(self) -> None:
        while not self.eoi() and self.str[self.currpos] in [" ", "\t", "\n"]:
            self.currpos += 1

    def match_str(self, str: str) -> str | None:
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
        return self.str[self.currpos :]


# Classes for AST operator types.


class CondTokens:
    AND, OR, NOT, CONDITIONAL = range(4)


class NumTokens:
    MUL, DIV, ADD, SUB, NUMBER = range(5)


# AST for conditional expressions


class CondAstNode(CondTokens):
    def __init__(self, type: int, cond1: Any, cond2: Any) -> None:
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
        # Evaluates the subtrees and/or conditional value for this node,
        # returning True or False.
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


# AST for numeric expressions


class NumericAstNode(NumTokens):
    def __init__(self, type: int, value1: Any, value2: Any) -> None:
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
                return lnum / rnum
            elif self.type == self.ADD:
                return lnum + rnum
            else:
                return lnum - rnum


# Conditional Parser


class CondParser(CondTokens):
    # Takes a conditional expression string.
    def __init__(self, condexpr: str) -> None:
        self.condexpr = condexpr
        self.cond_expr = SourceString(condexpr)

    def match_not(self) -> int | None:
        # Try to match 'NOT' operator. If not found, return None
        m1 = self.cond_expr.match_str("NOT")
        if m1 is not None:
            return self.NOT
        return None

    def match_andop(self) -> int | None:
        # Try to match 'AND' operator. If not found, return None
        m1 = self.cond_expr.match_str("AND")
        if m1 is not None:
            return self.AND
        return None

    def match_orop(self) -> int | None:
        # Try to match 'OR' operator. If not found, return None
        m1 = self.cond_expr.match_str("OR")
        if m1 is not None:
            return self.OR
        return None

    def factor(self) -> Any:
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
        m1 = self.factor()
        andop = self.match_andop()
        if andop is not None:
            m2 = self.term()
            return CondAstNode(andop, m1, m2)
        else:
            return m1

    def expression(self) -> Any:
        e1 = self.term()
        orop = self.match_orop()
        if orop is not None:
            e2 = self.expression()
            return CondAstNode(orop, e1, e2)
        else:
            return e1

    def parse(self) -> Any:
        exp = self.expression()
        if not self.cond_expr.eoi():
            raise CondParserError(
                f"Conditional expression parser did not consume entire string; remainder = {self.cond_expr.remainder()}.",
            )
        return exp


# Numeric Parser


class NumericParser(NumTokens):
    # Takes a numeric expression string
    def __init__(self, numexpr: str) -> None:
        self.num_expr = SourceString(numexpr)
        self.rxint = re.compile(r"(?P<int_num>[+-]?[0-9]+)")
        self.rxfloat = re.compile(r"(?P<float_num>[+-]?(?:(?:[0-9]*\.[0-9]+)|(?:[0-9]+\.[0-9]*)))")

    def match_number(self) -> Any | None:
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
        # Parses a term out of the source string and returns the
        # AST node that is created.
        m1 = self.factor()
        mulop = self.match_mulop()
        if mulop is not None:
            m2 = self.term()
            return NumericAstNode(mulop, m1, m2)
        else:
            return m1

    def expression(self) -> Any:
        # Parses an expression out of the source string and returns the
        # AST node that is created.
        e1 = self.term()
        if e1 is None:
            return
        addop = self.match_addop()
        if addop is not None:
            e2 = self.expression()
            return NumericAstNode(addop, e1, e2)
        else:
            return e1

    def parse(self) -> Any:
        exp = self.expression()
        if not self.num_expr.eoi():
            raise NumericParserError(
                f"Numeric expression parser did not consume entire string; remainder = {self.num_expr.remainder()}.",
            )
        return exp
