"""AST-producing parser for execsql scripts.

Converts raw ``.sql`` script text into a :class:`~execsql.script.ast.Script`
tree.  This is intended to eventually replace ``_parse_script_lines()`` in
:mod:`execsql.script.engine` — during the transition both paths coexist and
can be compared for correctness.

The parser is a single-pass, line-oriented state machine that tracks:

- **Block comment state** — inside ``/* ... */``
- **SQL accumulation** — multi-line SQL statements terminated by ``;``
- **BEGIN SQL** mode — all lines become SQL regardless of ``;``
- **Block nesting** — IF/LOOP/BATCH/SCRIPT blocks are pushed onto a stack
  and popped when the closing metacommand is encountered.

Usage::

    from execsql.script.parser import parse_script, parse_string

    # From a file
    script = parse_script("pipeline.sql", encoding="utf-8")

    # From an inline string
    script = parse_string("SELECT 1;", source_name="<inline>")
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from execsql.exceptions import ErrInfo
from execsql.utils.errors import write_warning
from execsql.script.ast import (
    BatchBlock,
    Comment,
    ConditionModifier,
    ElseIfClause,
    IfBlock,
    IncludeDirective,
    LoopBlock,
    MetaCommandStatement,
    Node,
    ParamDef,
    Script,
    ScriptBlock,
    SourceSpan,
    SqlBlock,
    SqlStatement,
)

__all__ = [
    "parse_script",
    "parse_string",
]


# ---------------------------------------------------------------------------
# Compiled regexes (module-level for reuse)
# ---------------------------------------------------------------------------

_BEGIN_SCRIPT_RX = re.compile(
    r"^\s*(?:BEGIN|CREATE)\s+SCRIPT\s+(?P<name>\w+)(?P<paramexpr>\s*.+)?$",
    re.I,
)
_END_SCRIPT_RX = re.compile(
    r"^\s*END\s+SCRIPT(?:\s+(?P<name>\w+))?\s*$",
    re.I,
)
_BEGIN_SQL_RX = re.compile(r"^\s*BEGIN\s+SQL\s*$", re.I)
_END_SQL_RX = re.compile(r"^\s*END\s+SQL\s*$", re.I)
_BEGIN_BATCH_RX = re.compile(r"^\s*BEGIN\s+BATCH\s*$", re.I)
_END_BATCH_RX = re.compile(r"^\s*END\s+BATCH\s*$", re.I)

_IF_BLOCK_RX = re.compile(r"^\s*IF\s*\(\s*(?P<cond>.+)\s*\)\s*$", re.I)
_IF_INLINE_RX = re.compile(
    r"^\s*IF\s*\(\s*(?P<cond>.+)\s*\)\s*{\s*(?P<cmd>.+)\s*}\s*$",
    re.I,
)
_ELSEIF_RX = re.compile(r"^\s*ELSEIF\s*\(\s*(?P<cond>.+)\s*\)\s*$", re.I)
_ORIF_RX = re.compile(r"^\s*ORIF\s*\(\s*(?P<cond>.+)\s*\)\s*$", re.I)
_ANDIF_RX = re.compile(r"^\s*ANDIF\s*\(\s*(?P<cond>.+)\s*\)\s*$", re.I)
_ELSE_RX = re.compile(r"^\s*ELSE\s*$", re.I)
_ENDIF_RX = re.compile(r"^\s*ENDIF\s*$", re.I)

_LOOP_RX = re.compile(
    r"^\s*LOOP\s+(?P<looptype>WHILE|UNTIL)\s*\(\s*(?P<loopcond>.+)\s*\)\s*$",
    re.I,
)
_ENDLOOP_RX = re.compile(r"^\s*END\s*LOOP\s*$", re.I)

# EXIST (without trailing S) is an accepted legacy alias for EXISTS
_INCLUDE_RX = re.compile(
    r"^\s*INCLUDE(?P<exists>\s+IF\s+EXISTS?)?\s+(?P<target>.+)\s*$",
    re.I,
)


def _strip_quotes(s: str) -> str:
    """Strip a matching pair of surrounding quotes from *s*."""
    if len(s) >= 2 and s[0] in ('"', "'") and s[-1] == s[0]:
        return s[1:-1]
    return s


_EXEC_SCRIPT_RX = re.compile(
    r"^\s*(?:EXEC(?:UTE)?|RUN)\s+SCRIPT"
    r"(?P<exists>\s+IF\s+EXISTS)?"
    r"\s+(?P<script_id>(?:\w+|!(?:['\"]?)![^!]+!(?:['\"]?)!))"
    r"(?:(?:\s+WITH)?(?:\s+ARG(?:UMENT)?S?)?\s*\(\s*(?P<argexp>.+?)\s*\))?"
    r"(?:\s+(?P<looptype>WHILE|UNTIL)\s*\(\s*(?P<loopcond>.+)\s*\))?"
    r"\s*$",
    re.I,
)

_WITH_PARAMS_RX = re.compile(
    r"(?:\s+WITH)?(?:\s+PARAM(?:ETER)?S)?\s*\(\s*(?P<params>"
    r"\w+(?:\s*=\s*\S+)?(?:\s*,\s*\w+(?:\s*=\s*\S+)?)*"
    r")\s*\)\s*$",
    re.I,
)

_PARAM_TOKEN_RX = re.compile(r"(\w+)(?:\s*=\s*(\S+))?")


def _parse_param_defs(
    params_str: str,
    lineno: int,
    source: str,
) -> list[ParamDef]:
    """Parse ``'a, b, c=100, d=false'`` into a list of :class:`ParamDef`.

    Required parameters (no default) must precede optional parameters
    (with default).  Raises :class:`ErrInfo` if ordering is violated.
    """
    tokens = [t.strip() for t in params_str.split(",")]
    defs: list[ParamDef] = []
    seen_optional: str | None = None  # name of first optional param
    for token in tokens:
        m = _PARAM_TOKEN_RX.match(token.strip())
        if not m:
            raise ErrInfo(
                type="cmd",
                other_msg=(f"Invalid parameter token '{token}' on line {lineno} of {source}."),
            )
        name, default = m.group(1), m.group(2)
        if default is not None:
            if seen_optional is None:
                seen_optional = name
        elif seen_optional is not None:
            raise ErrInfo(
                type="cmd",
                other_msg=(
                    f"Required parameter '{name}' after optional parameter "
                    f"'{seen_optional}' on line {lineno} of {source}. "
                    f"Required parameters must precede optional parameters."
                ),
            )
        defs.append(ParamDef(name=name, default=default))
    return defs


# Line classification
_EXEC_LINE_RX = re.compile(r"^\s*--\s*!x!\s*(?P<cmd>.+)$", re.I)
_COMMENT_LINE_RX = re.compile(r"^\s*--")


# ---------------------------------------------------------------------------
# Block stack frame
# ---------------------------------------------------------------------------


class _BlockFrame:
    """Tracks an open block during parsing.

    Each frame holds the partially-constructed AST node and metadata needed
    to close the block correctly.
    """

    __slots__ = (
        "node",
        "kind",
        "start_line",
        "source",
        "_in_else",
        "_in_elseif",
        "collecting_doc",
        "doc_lines",
    )

    def __init__(self, node: Node, kind: str, start_line: int, source: str) -> None:
        self.node = node
        self.kind = kind  # "if", "loop", "batch", "script", "sqlblock"
        self.start_line = start_line
        self.source = source
        self._in_else = False
        self._in_elseif = False
        self.collecting_doc: bool = kind == "script"  # auto-collect doc after BEGIN SCRIPT
        self.doc_lines: list[str] = []


# ---------------------------------------------------------------------------
# Parser implementation
# ---------------------------------------------------------------------------


def _parse_lines(lines: Iterable[str], source_name: str) -> Script:
    """Core parsing logic: convert an iterable of lines into a Script AST."""
    body: list[Node] = []
    block_stack: list[_BlockFrame] = []
    in_block_comment = False
    block_comment_start = 0  # line where /* was found
    block_comment_lines: list[str] = []  # accumulated block-comment text
    line_comment_start = 0  # line where a consecutive -- run began
    line_comment_lines: list[str] = []  # accumulated consecutive -- lines
    in_sql_block = False  # inside BEGIN SQL ... END SQL
    sql_accum = ""  # multi-line SQL accumulator
    sql_start_line = 0
    sql_accum_at_block_comment = False  # was sql_accum non-empty when /* started?

    def _current_body() -> list[Node]:
        """Return the body list that new nodes should be appended to."""
        if not block_stack:
            return body
        frame = block_stack[-1]
        node = frame.node
        if isinstance(node, IfBlock):
            # Determine which branch we're currently appending to
            if frame._in_else:
                return node.else_body
            if node.elseif_clauses and frame._in_elseif:
                return node.elseif_clauses[-1].body
            return node.body
        if isinstance(node, (LoopBlock, BatchBlock, ScriptBlock, SqlBlock)):
            return node.body
        return body  # pragma: no cover — defensive fallback

    def _flush_sql(line_no: int) -> None:
        """If there's accumulated SQL text, emit a SqlStatement node."""
        nonlocal sql_accum, sql_start_line
        if sql_accum:
            stmt = SqlStatement(
                span=SourceSpan(source_name, sql_start_line, line_no),
                text=sql_accum.strip(),
            )
            _current_body().append(stmt)
            sql_accum = ""

    def _flush_line_comments() -> None:
        """If there are accumulated consecutive ``--`` comment lines, emit a single Comment node."""
        nonlocal line_comment_lines, line_comment_start
        if line_comment_lines:
            end = line_comment_start + len(line_comment_lines) - 1
            _current_body().append(
                Comment(
                    span=SourceSpan(source_name, line_comment_start, end),
                    text="\n".join(line_comment_lines),
                ),
            )
            line_comment_lines = []

    def _stop_doc_collection() -> None:
        """Stop collecting docstring lines and finalize the doc on the script node."""
        if block_stack and block_stack[-1].collecting_doc:
            frame = block_stack[-1]
            frame.collecting_doc = False
            if frame.doc_lines:
                doc_text = "\n".join(frame.doc_lines).strip()
                if doc_text and isinstance(frame.node, ScriptBlock):
                    frame.node.doc = doc_text

    for file_lineno, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip()

        # --- Docstring collection for SCRIPT blocks ---
        # Comments immediately following BEGIN SCRIPT are captured as the
        # docstring.  A blank line terminates the doc.
        if block_stack and block_stack[-1].collecting_doc and not in_block_comment:
            frame = block_stack[-1]
            if not line:
                # Blank line terminates doc collection
                _stop_doc_collection()
                _flush_line_comments()
                continue
            # Check for block comment opening
            stripped = line.lstrip()
            if stripped.startswith("/*"):
                # Collect block comment as doc lines
                comment_body = stripped[2:]
                if comment_body.rstrip().endswith("*/"):
                    # Single-line block comment: /* text */
                    comment_body = comment_body.rstrip()[:-2].strip()
                    if comment_body:
                        frame.doc_lines.append(comment_body)
                    continue
                # Multi-line block comment — collect until */
                if comment_body.strip():
                    frame.doc_lines.append(comment_body.rstrip())
                # Let the block comment tracker handle the rest, but mark
                # that we're collecting doc inside a block comment.
                in_block_comment = True
                block_comment_lines = [line]
                block_comment_start = file_lineno
                sql_accum_at_block_comment = False
                # We'll handle the doc finalization when */ is found below.
                # For now, mark doc as still collecting.
                continue
            # Check for single-line comment (not metacommand)
            metacommand_match_doc = _EXEC_LINE_RX.match(line)
            if not metacommand_match_doc and _COMMENT_LINE_RX.match(line):
                # Strip -- prefix and optional leading space
                text = stripped
                if text.startswith("--"):
                    text = text[2:]
                    if text.startswith(" "):
                        text = text[1:]
                frame.doc_lines.append(text.rstrip())
                continue
            # Non-comment line (metacommand or SQL) — stop doc collection
            _stop_doc_collection()
            # Fall through to normal processing

        # --- Block comment tracking ---
        if not line:
            _flush_line_comments()
            continue

        if in_block_comment:
            block_comment_lines.append(line)
            if len(line) > 1 and line.rstrip().endswith("*/"):
                in_block_comment = False
                comment_text = "\n".join(block_comment_lines)
                # If we were collecting doc lines when the block comment opened,
                # feed the content into the docstring instead of creating a node.
                if block_stack and block_stack[-1].collecting_doc:
                    frame = block_stack[-1]
                    # Extract text between /* and */, stripping delimiters
                    for bc_line in block_comment_lines:
                        stripped_bc = bc_line.strip()
                        if stripped_bc.startswith("/*"):
                            stripped_bc = stripped_bc[2:]
                        if stripped_bc.endswith("*/"):
                            stripped_bc = stripped_bc[:-2]
                        stripped_bc = stripped_bc.strip()
                        if stripped_bc:
                            frame.doc_lines.append(stripped_bc)
                    block_comment_lines = []
                    sql_accum_at_block_comment = False
                    continue
                if sql_accum_at_block_comment:
                    # Block comment started inside a SQL statement — fold it
                    # back into sql_accum so the statement isn't split.
                    sql_accum += "\n" + comment_text
                else:
                    _flush_sql(file_lineno)
                    _current_body().append(
                        Comment(
                            span=SourceSpan(source_name, block_comment_start, file_lineno),
                            text=comment_text,
                        ),
                    )
                block_comment_lines = []
                sql_accum_at_block_comment = False
            continue

        # --- Single-line comment classification ---
        metacommand_match = _EXEC_LINE_RX.match(line)
        comment_match = _COMMENT_LINE_RX.match(line)

        if comment_match and not metacommand_match and not in_sql_block:
            if sql_accum:
                # Inside a multi-line SQL statement — keep the comment as part
                # of the SQL text so that commented-out columns, WHERE clauses,
                # etc. don't split the statement.
                sql_accum += "\n" + line.rstrip()
            else:
                # Standalone comment (not inside a SQL statement) — accumulate
                # consecutive -- lines into a single Comment node.
                if not line_comment_lines:
                    line_comment_start = file_lineno
                line_comment_lines.append(line.rstrip())
            continue

        # Non-comment line — flush any accumulated -- comment group before proceeding.
        _flush_line_comments()

        # --- Block comment opening (/* ... */) ---
        stripped = line.strip()
        if len(stripped) > 1 and stripped.startswith("/*"):
            block_comment_start = file_lineno
            block_comment_lines = [line]
            # Remember whether we were inside a SQL statement when the block
            # comment started, so we can fold it back on close.
            sql_accum_at_block_comment = bool(sql_accum)
            in_block_comment = True
            if stripped.endswith("*/"):
                in_block_comment = False
                if sql_accum_at_block_comment:
                    sql_accum += "\n" + line.rstrip()
                else:
                    _flush_sql(file_lineno)
                    _current_body().append(
                        Comment(
                            span=SourceSpan(source_name, file_lineno),
                            text=line,
                        ),
                    )
                block_comment_lines = []
                sql_accum_at_block_comment = False
            continue

        # --- Metacommand handling ---
        if metacommand_match:
            cmd_text = metacommand_match.group("cmd").strip()

            # -- BEGIN SQL --
            if _BEGIN_SQL_RX.match(cmd_text):
                _flush_sql(file_lineno)
                in_sql_block = True
                block_stack.append(
                    _BlockFrame(
                        SqlBlock(span=SourceSpan(source_name, file_lineno)),
                        kind="sqlblock",
                        start_line=file_lineno,
                        source=source_name,
                    ),
                )
                continue

            # -- END SQL --
            if _END_SQL_RX.match(cmd_text):
                _flush_sql(file_lineno)
                in_sql_block = False
                if not block_stack or block_stack[-1].kind != "sqlblock":
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"Unmatched END SQL on line {file_lineno} of {source_name}.",
                    )
                frame = block_stack.pop()
                frame.node.span = SourceSpan(source_name, frame.start_line, file_lineno)
                _current_body().append(frame.node)
                continue

            # Inside a SQL block, non-END SQL metacommands are silently
            # ignored (matching the original parser behavior).
            if in_sql_block:
                continue

            # Flush any pending SQL before processing a metacommand
            if sql_accum:
                write_warning(
                    f"Incomplete SQL statement starting on line {sql_start_line} "
                    f"at metacommand on line {file_lineno} of {source_name}.",
                )
                sql_accum = ""

            # -- BEGIN SCRIPT --
            m = _BEGIN_SCRIPT_RX.match(cmd_text)
            if m:
                name = m.group("name").lower()
                paramexpr = m.group("paramexpr")
                param_defs = None
                if paramexpr:
                    wp = _WITH_PARAMS_RX.match(paramexpr)
                    if not wp:
                        raise ErrInfo(
                            type="cmd",
                            command_text=line,
                            other_msg=f"Invalid BEGIN SCRIPT metacommand on line {file_lineno} of file {source_name}.",
                        )
                    param_defs = _parse_param_defs(wp.group("params"), file_lineno, source_name)
                block_stack.append(
                    _BlockFrame(
                        ScriptBlock(
                            span=SourceSpan(source_name, file_lineno),
                            name=name,
                            param_defs=param_defs,
                        ),
                        kind="script",
                        start_line=file_lineno,
                        source=source_name,
                    ),
                )
                continue

            # -- END SCRIPT --
            m = _END_SCRIPT_RX.match(cmd_text)
            if m:
                end_name = m.group("name")
                if end_name is not None:
                    end_name = end_name.lower()
                if not block_stack or block_stack[-1].kind != "script":
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"Unmatched END SCRIPT metacommand on line {file_lineno} of file {source_name}.",
                    )
                frame = block_stack[-1]
                script_node = frame.node
                if end_name is not None and end_name != script_node.name:  # type: ignore[union-attr]
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"Mismatched script name in the END SCRIPT metacommand on line {file_lineno} of file {source_name}.",
                    )
                if sql_accum:
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=(
                            f"Incomplete SQL statement\n  ({sql_accum})\n"
                            f"at END SCRIPT metacommand on line {file_lineno} of file {source_name}."
                        ),
                    )
                frame = block_stack.pop()
                frame.node.span = SourceSpan(source_name, frame.start_line, file_lineno)
                _current_body().append(frame.node)
                continue

            # -- IF (block form) --
            m = _IF_BLOCK_RX.match(cmd_text)
            if m:
                block_stack.append(
                    _BlockFrame(
                        IfBlock(
                            span=SourceSpan(source_name, file_lineno),
                            condition=m.group("cond").strip(),
                        ),
                        kind="if",
                        start_line=file_lineno,
                        source=source_name,
                    ),
                )
                continue

            # -- IF (inline form): IF (cond) { cmd } --
            m = _IF_INLINE_RX.match(cmd_text)
            if m:
                inner = MetaCommandStatement(
                    span=SourceSpan(source_name, file_lineno),
                    command=m.group("cmd").strip(),
                )
                if_node = IfBlock(
                    span=SourceSpan(source_name, file_lineno),
                    condition=m.group("cond").strip(),
                    body=[inner],
                )
                _current_body().append(if_node)
                continue

            # -- ELSEIF --
            m = _ELSEIF_RX.match(cmd_text)
            if m:
                if not block_stack or block_stack[-1].kind != "if":
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"ELSEIF without matching IF on line {file_lineno} of {source_name}.",
                    )
                frame = block_stack[-1]
                frame._in_else = False
                frame._in_elseif = True
                if_node = frame.node
                if_node.elseif_clauses.append(  # type: ignore[union-attr]
                    ElseIfClause(
                        condition=m.group("cond").strip(),
                        span=SourceSpan(source_name, file_lineno),
                    ),
                )
                continue

            # -- ANDIF --
            m = _ANDIF_RX.match(cmd_text)
            if m:
                if not block_stack or block_stack[-1].kind != "if":
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"ANDIF without matching IF on line {file_lineno} of {source_name}.",
                    )
                if_node = block_stack[-1].node
                if_node.condition_modifiers.append(  # type: ignore[union-attr]
                    ConditionModifier(
                        kind="AND",
                        condition=m.group("cond").strip(),
                        span=SourceSpan(source_name, file_lineno),
                    ),
                )
                continue

            # -- ORIF --
            m = _ORIF_RX.match(cmd_text)
            if m:
                if not block_stack or block_stack[-1].kind != "if":
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"ORIF without matching IF on line {file_lineno} of {source_name}.",
                    )
                if_node = block_stack[-1].node
                if_node.condition_modifiers.append(  # type: ignore[union-attr]
                    ConditionModifier(
                        kind="OR",
                        condition=m.group("cond").strip(),
                        span=SourceSpan(source_name, file_lineno),
                    ),
                )
                continue

            # -- ELSE --
            m = _ELSE_RX.match(cmd_text)
            if m:
                if not block_stack or block_stack[-1].kind != "if":
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"ELSE without matching IF on line {file_lineno} of {source_name}.",
                    )
                frame = block_stack[-1]
                frame._in_else = True
                frame._in_elseif = False
                frame.node.else_span = SourceSpan(source_name, file_lineno)  # type: ignore[union-attr]
                continue

            # -- ENDIF --
            m = _ENDIF_RX.match(cmd_text)
            if m:
                if not block_stack or block_stack[-1].kind != "if":
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"ENDIF without matching IF on line {file_lineno} of {source_name}.",
                    )
                frame = block_stack.pop()
                frame.node.span = SourceSpan(source_name, frame.start_line, file_lineno)
                _current_body().append(frame.node)
                continue

            # -- LOOP --
            m = _LOOP_RX.match(cmd_text)
            if m:
                block_stack.append(
                    _BlockFrame(
                        LoopBlock(
                            span=SourceSpan(source_name, file_lineno),
                            loop_type=m.group("looptype").upper(),
                            condition=m.group("loopcond").strip(),
                        ),
                        kind="loop",
                        start_line=file_lineno,
                        source=source_name,
                    ),
                )
                continue

            # -- ENDLOOP --
            m = _ENDLOOP_RX.match(cmd_text)
            if m:
                if not block_stack or block_stack[-1].kind != "loop":
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"ENDLOOP without matching LOOP on line {file_lineno} of {source_name}.",
                    )
                frame = block_stack.pop()
                frame.node.span = SourceSpan(source_name, frame.start_line, file_lineno)
                _current_body().append(frame.node)
                continue

            # -- BEGIN BATCH --
            m = _BEGIN_BATCH_RX.match(cmd_text)
            if m:
                block_stack.append(
                    _BlockFrame(
                        BatchBlock(span=SourceSpan(source_name, file_lineno)),
                        kind="batch",
                        start_line=file_lineno,
                        source=source_name,
                    ),
                )
                continue

            # -- END BATCH --
            m = _END_BATCH_RX.match(cmd_text)
            if m:
                if not block_stack or block_stack[-1].kind != "batch":
                    raise ErrInfo(
                        type="cmd",
                        command_text=line,
                        other_msg=f"END BATCH without matching BEGIN BATCH on line {file_lineno} of {source_name}.",
                    )
                frame = block_stack.pop()
                frame.node.span = SourceSpan(source_name, frame.start_line, file_lineno)
                _current_body().append(frame.node)
                continue

            # -- INCLUDE --
            m = _INCLUDE_RX.match(cmd_text)
            if m:
                _current_body().append(
                    IncludeDirective(
                        span=SourceSpan(source_name, file_lineno),
                        target=_strip_quotes(m.group("target").strip()),
                        if_exists=m.group("exists") is not None,
                    ),
                )
                continue

            # -- EXECUTE SCRIPT / RUN SCRIPT --
            m = _EXEC_SCRIPT_RX.match(cmd_text)
            if m:
                _current_body().append(
                    IncludeDirective(
                        span=SourceSpan(source_name, file_lineno),
                        target=m.group("script_id"),
                        is_execute_script=True,
                        if_exists=m.group("exists") is not None,
                        arguments=m.group("argexp"),
                        loop_type=m.group("looptype").upper() if m.group("looptype") else None,
                        loop_condition=m.group("loopcond"),
                    ),
                )
                continue

            # -- All other metacommands (flat) --
            _current_body().append(
                MetaCommandStatement(
                    span=SourceSpan(source_name, file_lineno),
                    command=cmd_text,
                ),
            )
            continue

        # --- SQL line ---
        # Not a comment, not a metacommand — part of a SQL statement.
        if in_sql_block:
            if sql_accum == "":
                sql_start_line = file_lineno
                sql_accum = line
            else:
                sql_accum = f"{sql_accum} \n{line}"
            continue

        # Line continuation with backslash
        actual_line = line
        if actual_line.endswith("\\"):
            actual_line = actual_line[:-1].strip()

        cmd_end = line.rstrip().endswith(";")

        if sql_accum == "":
            sql_start_line = file_lineno
            sql_accum = actual_line
        else:
            sql_accum = f"{sql_accum} \n{actual_line}"

        if cmd_end:
            _flush_sql(file_lineno)

    # --- End of file checks ---

    # Flush any trailing consecutive -- comments
    _flush_line_comments()

    # Unclosed blocks
    if block_stack:
        frame = block_stack[-1]
        raise ErrInfo(
            type="error",
            other_msg=f"Unmatched {frame.kind.upper()} block starting on line {frame.start_line} at end of file {source_name}.",
        )

    # Trailing SQL without semicolon
    if sql_accum:
        raise ErrInfo(
            type="error",
            other_msg=(
                f"Incomplete SQL statement starting on line {sql_start_line} at end of file {source_name}."
                + (" Metacommands must be prefixed with '-- !x!'." if source_name == "<inline>" else "")
            ),
        )

    return Script(source=source_name, body=body)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_script(filename: str, encoding: str = "utf-8") -> Script:
    """Parse a ``.sql`` file and return a :class:`Script` AST.

    Reads the file directly (no dependency on runtime state) so it can be
    used in early-exit CLI modes like ``--parse-tree``.

    Args:
        filename: Path to the SQL script file.
        encoding: File encoding (default ``utf-8``).

    Returns:
        A :class:`Script` tree representing the parsed file.
    """
    text = Path(filename).read_text(encoding=encoding)
    return _parse_lines(text.splitlines(), filename)


def parse_string(content: str, source_name: str = "<inline>") -> Script:
    """Parse an inline script string and return a :class:`Script` AST.

    Args:
        content: The script content as a string.
        source_name: Name to use in source spans (default ``"<inline>"``).

    Returns:
        A :class:`Script` tree representing the parsed content.
    """
    return _parse_lines(content.splitlines(), source_name)
