"""execsql formatter — normalize metacommand indentation and uppercase keywords.

Public API
----------
format_file(source, indent=4, use_sql=True) -> str
    Format the source text of an execsql script and return the result.

collect_paths(inputs) -> list[Path]
    Expand directories to a recursive list of *.sql files; pass files through.
"""

from __future__ import annotations

import contextlib
import io
import re
from pathlib import Path

import sqlglot
import sqlglot.errors

__all__ = ["collect_paths", "format_file", "main", "parse_keyword"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METACOMMAND_RE = re.compile(r"^\s*--\s*!x!\s*(.*)", re.IGNORECASE)

# Multi-word keywords — checked longest-first before single-word fallback.
# Order matters: more-specific variants must precede their prefixes.
MULTIWORD_KEYWORDS = [
    "METACOMMAND_ERROR_HALT",
    "ON ERROR_HALT",
    "ON CANCEL_HALT",
    "ROLLBACK BATCH",
    "BEGIN SCRIPT",
    "END SCRIPT",
    "BEGIN BATCH",
    "END BATCH",
    "BEGIN SQL",
    "END SQL",
    "END LOOP",
    "EXECUTE SCRIPT",
    "EXTEND SCRIPT",
    "CREATE SCRIPT",
    "EXPORT_METADATA",
    "COPY QUERY",
    "SUB_TEMPFILE",
    "SUB_APPEND",
    "SELECT_SUB",
    "SUB_EMPTY",
    "SYSTEM_CMD",
    "ERROR_HALT",
    "CANCEL_HALT",
    "WAIT_UNTIL",
    "SUB_ADD",
    "RM_FILE",
    "SUBDATA",
    "RM_SUB",
    "SUB_INI",
    "PROMPT ENTRY_FORM",
    "PROMPT SELECT_SUB",
    "PROMPT ENTER_SUB",
    "PROMPT DIRECTORY",
    "PROMPT CONNECT",
    "PROMPT COMPARE",
    "PROMPT MESSAGE",
    "PROMPT DISPLAY",
    "PROMPT ACTION",
    "PROMPT PAUSE",
    "PROMPT FILE",
    "PROMPT ASK",
    "WITH TEMPLATE",
    "IN ZIPFILE",
    "SHOW SCRIPTS",
    "SHOW SCRIPT",
]

# Depth-tracking sets
BLOCK_OPEN = frozenset({"IF", "LOOP", "BEGIN SCRIPT", "BEGIN BATCH", "BEGIN SQL", "CREATE SCRIPT"})
BLOCK_CLOSE = frozenset({"ENDIF", "END LOOP", "ENDLOOP", "END SCRIPT", "END BATCH", "END SQL"})
PIVOT = frozenset({"ELSE", "ELSEIF"})  # decrease depth before emit, increase after
CONTINUATION = frozenset({"ANDIF", "ORIF"})  # emit at depth-1, no depth change


# ---------------------------------------------------------------------------
# Keyword parsing
# ---------------------------------------------------------------------------


def parse_keyword(payload: str) -> str:
    """Return the canonical UPPERCASE keyword at the start of a metacommand payload.

    Tries multi-word keywords longest-first, then falls back to the first word
    (split on whitespace or '(').
    """
    upper = payload.upper().strip()
    for kw in MULTIWORD_KEYWORDS:
        if upper == kw or upper.startswith(kw + " ") or upper.startswith(kw + "(") or upper.startswith(kw + "\t"):
            return kw
    return re.split(r"[\s(]", upper.strip(), maxsplit=1)[0]


# ---------------------------------------------------------------------------
# SQL block formatting helpers
# ---------------------------------------------------------------------------

# Matches execsql variable substitutions: !!varname!!, !!#param!!, !!@col!!, etc.
# and deferred substitutions !{varname}!
_EXECSQL_VAR_RE = re.compile(r"!!([^!\s][^!]*)!!|!\{[^}]+\}!")


def _protect_variables(sql: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace execsql substitutions with valid SQL identifiers, return (protected, replacements)."""
    replacements: list[tuple[str, str]] = []

    def replace(m: re.Match) -> str:
        placeholder = f"execsqlvar{len(replacements)}"
        replacements.append((placeholder, m.group(0)))
        return placeholder

    return _EXECSQL_VAR_RE.sub(replace, sql), replacements


def _restore_variables(sql: str, replacements: list[tuple[str, str]]) -> str:
    if not replacements:
        return sql
    mapping = {p.lower(): orig for p, orig in replacements}
    pattern = re.compile(
        "|".join(re.escape(p) for p in sorted(mapping, key=len, reverse=True)),
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: mapping[m.group(0).lower()], sql)


def _is_comment_line(line: str, in_block: bool) -> tuple[bool, bool]:
    """Return (is_comment, new_in_block) for a single stripped line."""
    if in_block:
        return True, ("*/" not in line)
    s = line.strip()
    if not s:
        return False, False
    if s.startswith("--"):
        return True, False
    if s.startswith("/*"):
        return True, ("*/" not in s[2:])
    return False, False


def _sqlglot_format(
    sql_lines: list[str],
    sql_indent: int = 4,
    leading_comma: bool = False,
) -> list[str]:
    """Format a list of SQL-only lines (no comment-only lines) via sqlglot."""
    text = "\n".join(sql_lines)
    protected, replacements = _protect_variables(text)

    # Count semicolons in input as a rough statement count.
    input_semis = protected.count(";")

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            ast = sqlglot.parse(protected, read="postgres", error_level=sqlglot.errors.ErrorLevel.IGNORE)
            statements: list[str] = []
            for node in ast:
                if node is None:
                    continue
                # For Command nodes (psql backslash commands, ERROR:, etc.)
                # use unpretty output to avoid mangling.
                if type(node).__name__ == "Command":
                    statements.append(node.sql(dialect="postgres"))
                else:
                    statements.append(
                        node.sql(
                            dialect="postgres",
                            pretty=True,
                            pad=sql_indent,
                            indent=sql_indent,
                            max_text_width=120,
                            leading_comma=leading_comma,
                        ),
                    )
        stmts = [s for s in statements if s]
        if not stmts:
            return sql_lines

        # Safety: if sqlglot produced more statements than the input had
        # semicolons, it likely split a fragment (e.g. a SELECT column list)
        # into multiple pseudo-statements.  Fall back to the original text.
        if len(stmts) > max(input_semis, 1):
            return sql_lines

        joined = ";\n".join(stmts) + ";"

        # Content-loss check: sqlglot with IGNORE error level can silently
        # drop tokens it doesn't understand (e.g. ``ERROR: ...``).  If the
        # formatted output lost a significant fraction of the alphanumeric
        # content, the formatting is unreliable — fall back.
        # Exclude comment markers from the comparison — they are injected by
        # _format_preserving_comments and are expected to be dropped by sqlglot
        # for certain AST positions (e.g. inside CASE WHEN).
        _alnum = re.compile(r"[^a-zA-Z0-9]")
        _marker_alnum = re.compile(rf"{re.escape(_CMT_MARKER)}\d+")
        input_for_check = _marker_alnum.sub("", protected)
        input_alnum_len = len(_alnum.sub("", input_for_check))
        output_alnum_len = len(_alnum.sub("", joined))
        if input_alnum_len and output_alnum_len < input_alnum_len * 0.7:
            return sql_lines
        joined = re.sub(r"\bINTO TEMPORARY\b(?!\s+TABLE)", "INTO TEMPORARY TABLE", joined)
        return _restore_variables(joined, replacements).split("\n")
    except Exception:
        return sql_lines


# ---------------------------------------------------------------------------
# Public formatting functions
# ---------------------------------------------------------------------------


def _has_mid_statement_comments(lines: list[str]) -> bool:
    """Return True if any comment-only line appears inside a SQL statement.

    A comment is "mid-statement" if it occurs after a SQL line that does not
    end with ``;`` (i.e. the statement is still open).  This is a lightweight
    heuristic — it can be fooled by ``;`` inside string literals, but in that
    case the block simply gets the benefit of sqlglot formatting rather than
    being skipped (which is harmless because the SQL isn't fragmented).
    """
    in_block = False
    in_statement = False
    for line in lines:
        is_comment, in_block = _is_comment_line(line, in_block)
        stripped = line.strip()
        if not stripped:
            continue
        if is_comment:
            if in_statement:
                return True
        else:
            in_statement = True
            if stripped.endswith(";"):
                in_statement = False
    return False


_CMT_MARKER = "EXECSQL_CMTMARKER_"
_CMT_MARKER_RE = re.compile(rf"/\*\s*({re.escape(_CMT_MARKER)}\d+)\s*\*/")


def _format_preserving_comments(
    lines: list[str],
    sql_indent: int = 4,
    leading_comma: bool = False,
) -> list[str]:
    """Format SQL with interleaved comments via marker-based round-tripping.

    Strategy
    --------
    1. Replace each comment-only line with a unique inline ``/* marker */``
       prepended to the *next* SQL line.  This lets sqlglot see the full
       statement without fragmentation while preserving comment anchors.
    2. Format the marker-annotated SQL through ``_sqlglot_format``.
    3. Walk the formatted output: wherever a marker appears, emit the
       original comment on its own line **before** that SQL line, then
       strip the marker from the SQL.
    4. Any marker that sqlglot dropped (e.g. inside a CASE expression)
       is re-inserted by matching key tokens from its anchor SQL line
       against the formatted output.
    """
    # ---- Step 1: extract comments, replace with inline markers ----------
    comment_store: dict[str, str] = {}  # marker → original comment line
    # Track the SQL line that originally followed each comment, for fallback
    anchor_sql: dict[str, str] = {}  # marker → next SQL line (stripped)
    pending_markers: list[str] = []
    processed: list[str] = []
    in_block = False

    for line in lines:
        is_comment, in_block = _is_comment_line(line, in_block)
        stripped = line.strip()
        if not stripped:
            # Blank lines: if we have pending markers, attach blanks as
            # comment entries so they reappear in the right place.
            if pending_markers:
                mid = f"{_CMT_MARKER}{len(comment_store)}"
                comment_store[mid] = line
                pending_markers.append(mid)
            else:
                processed.append(line)
        elif is_comment:
            mid = f"{_CMT_MARKER}{len(comment_store)}"
            comment_store[mid] = line
            pending_markers.append(mid)
        else:
            # SQL line — prepend any pending markers as inline comments
            prefix = " ".join(f"/* {m} */" for m in pending_markers)
            processed.append(f"{prefix} {line}" if prefix else line)
            for m in pending_markers:
                anchor_sql[m] = stripped
            pending_markers.clear()

    # Trailing comments with no following SQL — preserve as-is
    trailing: list[str] = [comment_store[m] for m in pending_markers]

    # ---- Step 2: format through sqlglot ---------------------------------
    formatted = _sqlglot_format(processed, sql_indent=sql_indent, leading_comma=leading_comma)

    # ---- Step 3: restore surviving markers to comment lines -------------
    found_markers: set[str] = set()
    result: list[str] = []
    for fline in formatted:
        markers_here = _CMT_MARKER_RE.findall(fline)
        if markers_here:
            # Strip markers to get the underlying SQL line and its indent
            cleaned = _CMT_MARKER_RE.sub("", fline).strip()
            # Determine indent: use the SQL line's indent from sqlglot
            sql_indent = ""
            if cleaned:
                raw_cleaned = _CMT_MARKER_RE.sub("", fline)
                sql_indent = raw_cleaned[: len(raw_cleaned) - len(raw_cleaned.lstrip())]
            for m in markers_here:
                if m in comment_store:
                    orig = comment_store[m]
                    # Re-indent the comment to match the SQL line it precedes
                    orig_stripped = orig.strip()
                    if orig_stripped:
                        result.append(sql_indent + orig_stripped)
                    else:
                        result.append("")
                    found_markers.add(m)
            if cleaned:
                result.append(sql_indent + cleaned)
        else:
            result.append(fline)

    # ---- Step 4: reinsert lost markers ----------------------------------
    lost = [m for m in comment_store if m not in found_markers and m not in set(pending_markers)]
    if lost:
        _reinsert_lost_comments(result, lost, comment_store, anchor_sql)

    result.extend(trailing)
    return result


def _reinsert_lost_comments(
    result: list[str],
    lost_markers: list[str],
    comment_store: dict[str, str],
    anchor_sql: dict[str, str],
) -> None:
    """Best-effort reinsertion of comments that sqlglot dropped.

    For each lost comment, extract key tokens from its anchor SQL line and
    find the output line that best matches, then insert the comment before
    that line (indented to match).  Operates on *result* in place.
    """
    _word_re = re.compile(r"[a-zA-Z_]\w*")

    # Process in reverse order so earlier inserts don't shift later indices.
    insertions: list[tuple[int, str]] = []
    for marker in lost_markers:
        anchor = anchor_sql.get(marker, "")
        orig = comment_store[marker]
        orig_stripped = orig.strip()
        if not anchor or not orig_stripped:
            insertions.append((len(result), orig))
            continue

        anchor_words = [w.lower() for w in _word_re.findall(anchor)]
        if not anchor_words:
            insertions.append((len(result), orig))
            continue

        # Find the output line with the best token overlap
        best_idx = len(result)
        best_score = 0
        for i, rline in enumerate(result):
            rwords = {w.lower() for w in _word_re.findall(rline)}
            score = sum(1 for w in anchor_words if w in rwords)
            if score > best_score:
                best_score = score
                best_idx = i

        # Re-indent comment to match the target line
        if best_idx < len(result):
            target = result[best_idx]
            indent_str = target[: len(target) - len(target.lstrip())]
        else:
            indent_str = ""
        insertions.append((best_idx, indent_str + orig_stripped))

    # Sort descending by index; within the same index, reverse the
    # original order so sequential result.insert() calls produce the
    # correct final ordering (last inserted at a given index ends up first).
    indexed = list(enumerate(insertions))
    indexed.sort(key=lambda x: (x[1][0], x[0]), reverse=True)
    for _, (idx, text) in indexed:
        result.insert(idx, text)


def format_sql_block(
    lines: list[str],
    depth: int,
    indent: int,
    use_sql: bool,
    leading_comma: bool = False,
) -> list[str]:
    """Re-indent a SQL block to the current depth, optionally formatting via sqlglot."""
    if not lines:
        return lines

    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return [""] * len(lines)

    base = min(len(line) - len(line.lstrip()) for line in non_empty)
    target_prefix = " " * (depth * indent)
    rebased = [line[base:] if line.strip() else "" for line in lines]

    if not use_sql:
        return [target_prefix + line if line.strip() else "" for line in rebased]

    # When comments appear mid-statement, use the marker-based approach
    # which preserves both comments AND sqlglot formatting.  When all
    # comments are between statements, the simpler segmentation works.
    if _has_mid_statement_comments(rebased):
        result = _format_preserving_comments(rebased, sql_indent=indent, leading_comma=leading_comma)
        return [target_prefix + line if line.strip() else "" for line in result]

    result: list[str] = []
    seg: list[str] = []
    seg_is_comment: bool | None = None
    in_block = False

    def flush() -> None:
        if not seg:
            return
        if seg_is_comment:
            result.extend(seg)
        else:
            result.extend(_sqlglot_format(seg, sql_indent=indent, leading_comma=leading_comma))
        seg.clear()

    for line in rebased:
        is_comment, in_block = _is_comment_line(line, in_block)
        if not line.strip():
            seg.append(line)
        elif is_comment:
            if seg_is_comment is False:
                flush()
            seg_is_comment = True
            seg.append(line)
        else:
            if seg_is_comment is True:
                flush()
            seg_is_comment = False
            seg.append(line)

    flush()
    return [target_prefix + line if line.strip() else "" for line in result]


def format_metacommand(payload: str, depth: int, indent: int) -> str:
    """Format a single metacommand payload: uppercase keyword, apply indentation.

    The arguments after the keyword are preserved as-is (original case/spacing).
    """
    payload_stripped = payload.strip()
    keyword = parse_keyword(payload_stripped)
    rest = payload_stripped[len(keyword) :].lstrip()
    prefix = " " * (depth * indent)
    if rest:
        return f"{prefix}-- !x! {keyword} {rest}"
    return f"{prefix}-- !x! {keyword}"


def format_file(source: str, indent: int = 4, use_sql: bool = True, leading_comma: bool = False) -> str:
    """Format the source text of an execsql script and return the result."""
    depth = 0
    sql_acc: list[str] = []
    output: list[str] = []

    in_dollar_quote = False
    in_block_comment = False
    # Track whether we are inside an open SQL statement (last SQL line
    # did not end with ';').  Blank lines mid-statement should NOT flush
    # the accumulator — doing so would split a single statement into
    # fragments that sqlglot cannot parse.
    in_sql_statement = False

    def flush_sql() -> None:
        nonlocal in_dollar_quote, in_sql_statement
        if sql_acc:
            # If any line in the accumulated block is inside a $$-delimited
            # region, skip sqlglot formatting entirely.  PL/pgSQL function
            # bodies contain IF/END IF, LOOP, RETURN, etc. that sqlglot does
            # not understand and will corrupt (e.g., rewriting to COMMIT).
            safe_for_sqlglot = use_sql and not in_dollar_quote
            output.extend(format_sql_block(sql_acc, depth, indent, safe_for_sqlglot, leading_comma=leading_comma))
            sql_acc.clear()
        in_sql_statement = False

    for raw_line in source.expandtabs(4).splitlines():
        stripped_line = raw_line.strip()

        # Track /* */ block comment boundaries (but not inside $$ regions).
        # Lines inside block comments must not be processed as metacommands.
        if not in_dollar_quote:
            if in_block_comment:
                sql_acc.append(raw_line)
                if "*/" in raw_line:
                    in_block_comment = False
                continue
            if stripped_line.startswith("/*") and "*/" not in stripped_line[2:]:
                in_block_comment = True
                sql_acc.append(raw_line)
                continue

        m = METACOMMAND_RE.match(raw_line)

        if not stripped_line:
            if not in_dollar_quote and not in_sql_statement:
                flush_sql()
                output.append("")
            else:
                # Mid-statement blank line stays in the accumulator and
                # will appear in the output when the block is formatted.
                sql_acc.append(raw_line)

        elif m:
            flush_sql()
            payload = m.group(1).strip()
            keyword = parse_keyword(payload)

            if keyword in BLOCK_CLOSE:
                depth = max(0, depth - 1)
                output.append(format_metacommand(payload, depth, indent))

            elif keyword in PIVOT:
                depth = max(0, depth - 1)
                output.append(format_metacommand(payload, depth, indent))
                depth += 1

            elif keyword in CONTINUATION:
                output.append(format_metacommand(payload, max(0, depth - 1), indent))

            elif keyword in BLOCK_OPEN:
                output.append(format_metacommand(payload, depth, indent))
                depth += 1

            else:
                output.append(format_metacommand(payload, depth, indent))

        else:
            # Track $$ boundaries to prevent sqlglot from mangling PL/pgSQL
            if "$$" in raw_line and raw_line.count("$$") % 2 == 1:
                in_dollar_quote = not in_dollar_quote
            sql_acc.append(raw_line)
            # Update statement tracking: if this SQL line ends with ';'
            # (and isn't a comment), the statement is complete.
            if stripped_line.endswith(";") and not stripped_line.startswith("--"):
                in_sql_statement = False
            elif not stripped_line.startswith("--"):
                in_sql_statement = True

    flush_sql()

    result = "\n".join(output)
    if not result.endswith("\n"):
        result += "\n"
    return result


def collect_paths(inputs: list[Path]) -> list[Path]:
    """Expand directories to a recursive list of *.sql files; pass files through as-is."""
    paths: list[Path] = []
    for p in inputs:
        if p.is_dir():
            paths.extend(sorted(p.rglob("*.sql")))
        else:
            paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Entry point (execsql-format)
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for the execsql-format console script."""
    import sys

    import typer
    from rich.console import Console

    _console = Console()
    _err_console = Console(stderr=True)

    app = typer.Typer(
        name="execsql-format",
        help="Format execsql scripts: normalize metacommand indentation and uppercase keywords.",
        rich_markup_mode="rich",
        no_args_is_help=True,
        add_completion=False,
    )

    @app.command(context_settings={"allow_extra_args": False})
    def _cmd(
        targets: list[Path] = typer.Argument(
            ...,
            metavar="FILE_OR_DIR",
            help="Files or directories to format. Directories are searched recursively for *.sql files.",
        ),
        check: bool = typer.Option(False, "--check", help="Exit 1 if any file needs changes (don't write)."),
        in_place: bool = typer.Option(False, "-i", "--in-place", help="Modify files in place."),
        no_sql: bool = typer.Option(False, "--no-sql", help="Skip SQL formatting via sqlglot."),
        indent: int = typer.Option(4, "--indent", metavar="N", help="Spaces per indent level."),
        leading_comma: bool = typer.Option(
            False,
            "--leading-comma",
            help="Place commas at the start of lines instead of the end.",
        ),
    ) -> None:
        use_sql = not no_sql
        paths = collect_paths(targets)
        if not paths:
            _err_console.print("[bold red]Error:[/bold red] No .sql files found.")
            raise typer.Exit(code=1)

        any_changed = False
        for path in paths:
            try:
                source = path.read_text(encoding="utf-8")
            except OSError as exc:
                _err_console.print(f"[bold red]Error:[/bold red] reading {path}: {exc}")
                raise typer.Exit(code=1) from None

            formatted = format_file(source, indent=indent, use_sql=use_sql, leading_comma=leading_comma)

            if check:
                if formatted != source:
                    _console.print(f"would reformat {path}")
                    any_changed = True
            elif in_place:
                if formatted != source:
                    path.write_text(formatted, encoding="utf-8")
                    _console.print(f"reformatted {path}")
            else:
                sys.stdout.write(formatted)

        if check and any_changed:
            raise typer.Exit(code=1)

    app()
