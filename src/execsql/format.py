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


def _sqlglot_format(sql_lines: list[str]) -> list[str]:
    """Format a list of SQL-only lines (no comment-only lines) via sqlglot."""
    text = "\n".join(sql_lines)
    protected, replacements = _protect_variables(text)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            ast = sqlglot.parse(protected, read="postgres", error_level=sqlglot.errors.ErrorLevel.IGNORE)
            statements = [
                node.sql(dialect="postgres", pretty=True)
                for node in ast
                if node is not None and type(node).__name__ != "Command"
            ]
        stmts = [s for s in statements if s]
        if not stmts:
            return sql_lines
        joined = ";\n".join(stmts) + ";"
        joined = re.sub(r"\bINTO TEMPORARY\b(?!\s+TABLE)", "INTO TEMPORARY TABLE", joined)
        return _restore_variables(joined, replacements).split("\n")
    except Exception:
        return sql_lines


# ---------------------------------------------------------------------------
# Public formatting functions
# ---------------------------------------------------------------------------


def format_sql_block(lines: list[str], depth: int, indent: int, use_sql: bool) -> list[str]:
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
            result.extend(_sqlglot_format(seg))
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


def format_file(source: str, indent: int = 4, use_sql: bool = True) -> str:
    """Format the source text of an execsql script and return the result."""
    depth = 0
    sql_acc: list[str] = []
    output: list[str] = []

    in_dollar_quote = False

    def flush_sql() -> None:
        nonlocal in_dollar_quote
        if sql_acc:
            # If any line in the accumulated block is inside a $$-delimited
            # region, skip sqlglot formatting entirely.  PL/pgSQL function
            # bodies contain IF/END IF, LOOP, RETURN, etc. that sqlglot does
            # not understand and will corrupt (e.g., rewriting to COMMIT).
            safe_for_sqlglot = use_sql and not in_dollar_quote
            output.extend(format_sql_block(sql_acc, depth, indent, safe_for_sqlglot))
            sql_acc.clear()

    for raw_line in source.expandtabs(4).splitlines():
        m = METACOMMAND_RE.match(raw_line)

        if not raw_line.strip():
            if not in_dollar_quote:
                flush_sql()
            else:
                sql_acc.append(raw_line)
            output.append("")

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

            formatted = format_file(source, indent=indent, use_sql=use_sql)

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
