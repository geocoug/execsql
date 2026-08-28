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
from collections.abc import Iterator
from pathlib import Path

__all__ = ["collect_paths", "format_file", "main", "parse_keyword"]


_SQLGLOT_MISSING_MSG = (
    "execsql-format requires sqlglot for SQL reformatting.\n"
    "  Install with:  pip install execsql2[formatter]\n"
    "  Or skip SQL reformatting with the --no-sql flag."
)


def _require_sqlglot():
    """Lazy import of sqlglot, raising ImportError with an install hint if missing."""
    try:
        import sqlglot
        import sqlglot.errors  # noqa: F401

        return sqlglot
    except ImportError as e:
        raise ImportError(_SQLGLOT_MISSING_MSG) from e


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METACOMMAND_RE = re.compile(r"^\s*--\s*!x!\s*(.*)", re.IGNORECASE)

# Multi-word keywords — checked longest-first before single-word fallback.
# Order matters: more-specific variants must precede their prefixes.
# Only entries that appear at the *start* of a `-- !x!` payload belong
# here — `parse_keyword()` matches against the beginning of the payload,
# not embedded sub-clauses. `IN ZIPFILE` / `WITH TEMPLATE` are EXPORT
# sub-clauses and never appear at the start, so they don't go here.
# When adding a new dispatch keyword, mirror it here (or fix the missing
# entry via the `tests/test_format.py` drift check that pulls names from
# the dispatch table).
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
    "PROMPT SELECT_ROWS",
    "PROMPT ENTER_SUB",
    "PROMPT DIRECTORY",
    "PROMPT CREDENTIALS",
    "PROMPT CONNECT",
    "PROMPT COMPARE",
    "PROMPT MESSAGE",
    "PROMPT DISPLAY",
    "PROMPT ACTION",
    "PROMPT OPENFILE",
    "PROMPT SAVEFILE",
    "PROMPT PAUSE",
    # PROMPT ASK COMPARE must precede PROMPT ASK so longest-match wins;
    # parse_keyword iterates in list order, not by length.
    "PROMPT ASK COMPARE",
    "PROMPT ASK",
    "PROMPT MAP",
    "APPEND SCRIPT",
    "PG_UPSERT CHECK",
    "PG_UPSERT QA",
    "RESET COUNTER",
    "RESET DIALOG_CANCELED",
    "SET COUNTER",
    "WRITE CREATE_TABLE",
    "WRITE SCRIPT",
    "SHOW SCRIPTS",
]

# Depth-tracking sets
BLOCK_OPEN = frozenset({"IF", "LOOP", "BEGIN SCRIPT", "BEGIN BATCH", "BEGIN SQL", "CREATE SCRIPT"})
BLOCK_CLOSE = frozenset({"ENDIF", "END LOOP", "ENDLOOP", "END SCRIPT", "END BATCH", "END SQL"})
PIVOT = frozenset({"ELSE", "ELSEIF"})  # decrease depth before emit, increase after
CONTINUATION = frozenset({"ANDIF", "ORIF"})  # emit at depth-1, no depth change

# Inline IF: "IF (cond) { command }" — self-contained, no ENDIF, no depth
# change. Pattern must accept the same payloads as
# src/execsql/script/parser.py:_IF_INLINE_RX. Kept as a separate compiled
# pattern (not an import) so execsql-format doesn't pull in the AST parser
# module graph at startup; tests/test_format.py has a drift check that
# asserts both regexes recognise the same inputs.
_IF_INLINE_RE = re.compile(r"^\s*IF\s*\(\s*.+\s*\)\s*\{.+\}\s*$", re.I)

# Matches both untagged `$$` and tagged `$tag$` dollar-quote markers
# (PostgreSQL PL/pgSQL / DO-block syntax). Tags are letter-or-underscore
# followed by word characters; the empty tag (just `$$`) is also valid.
_DOLLAR_QUOTE_RE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")
# BLOCK_OPEN keywords whose bodies are guaranteed-SQL (not metacommand-driven).
# Blank lines inside these belong to the SQL accumulator, not the output stream.
_SQL_BODY_BLOCKS = frozenset({"BEGIN SQL", "BEGIN BATCH"})
_SQL_BODY_BLOCK_CLOSES = frozenset({"END SQL", "END BATCH"})


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

# Matches execsql variable substitutions:
#   !!varname!!     verbatim
#   !'!varname!'!   single-quoted (apostrophes doubled at expansion)
#   !"!varname!"!   double-quoted (quotes doubled at expansion)
#   !{varname}!     deferred
# The bare/quoted forms mirror src/execsql/script/variables.py:_TOKEN_RX so
# every token the executor recognises is hidden from sqlglot — otherwise the
# `!` in a quoted form is parsed as a NOT operator (e.g. `!'!v!'!` -> `NOT NOT '!v!'`).
_EXECSQL_VAR_RE = re.compile(r"""!(['"]?)!([^!\s][^!]*)!\1!|!\{[^}]+\}!""")


# Characters that may appear in an identifier, used to tell an ``E'...'``
# escape-string prefix from a trailing ``e`` on an identifier (``abce'x'`` is
# the identifier ``abce`` followed by a separate literal).
_IDENT_CHAR_RE = re.compile(r"[A-Za-z0-9_$]")


def _iter_sql_literals(sql: str) -> Iterator[tuple[int, int, str]]:
    """Yield ``(start, end, kind)`` spans for every string literal in *sql*.

    This is a lexical walk rather than a regex sweep, because an apostrophe
    only starts a literal in some contexts.  Line comments, block comments
    (which nest in PostgreSQL), and quoted identifiers are skipped entirely,
    so quotes inside them never open a literal.

    *kind* is one of:

    ``"estring"``
        A PostgreSQL escape string, ``E'...'``.  Backslash escapes are
        significant inside it, which is what makes it unsafe to hand to
        sqlglot — see :func:`_protect_estrings`.
    ``"plain"``
        An ordinary ``'...'`` literal, where only a doubled ``''`` escapes.
    ``"dollar"``
        A dollar-quoted body, ``$$...$$`` or ``$tag$...$tag$``, in which no
        character is special.
    """
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]

        if c == "-" and sql.startswith("--", i):
            nl = sql.find("\n", i)
            i = n if nl < 0 else nl + 1
            continue

        if c == "/" and sql.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if sql.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif sql.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            continue

        if c == '"':
            i += 1
            while i < n:
                if sql[i] == '"':
                    if sql.startswith('""', i):
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue

        if c == "$":
            m = _DOLLAR_QUOTE_RE.match(sql, i)
            if m:
                tag = m.group(0)
                close = sql.find(tag, m.end())
                stop = n if close < 0 else close + len(tag)
                yield i, stop, "dollar"
                i = stop
                continue

        # E'...' — only when the `e` is not the tail of an identifier.
        if c in "eE" and sql.startswith("'", i + 1) and not (i and _IDENT_CHAR_RE.match(sql[i - 1])):
            j = i + 2
            while j < n:
                if sql[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if sql[j] == "'":
                    if sql.startswith("''", j):
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            yield i, j, "estring"
            i = j
            continue

        if c == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if sql.startswith("''", j):
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            yield i, j, "plain"
            i = j
            continue

        i += 1


def _sql_literal_texts(sql: str) -> list[str]:
    """Return the source text of every string literal in *sql*, in order."""
    return [sql[start:end] for start, end, _ in _iter_sql_literals(sql)]


def _literal_line_starts(lines: list[str]) -> list[int]:
    """Return the character offset at which each of *lines* starts once joined."""
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1  # +1 for the newline joined between lines
    return starts


def _literal_interior_lines(lines: list[str]) -> set[int]:
    """Return indices of *lines* that begin inside a multi-line string literal.

    The line that *opens* a literal is ordinary SQL up to the delimiter, so it
    is indented with the statement as usual.  Every later line of that literal
    — through and including the one holding the closing delimiter — begins
    inside the string, which makes its leading whitespace part of the stored
    value rather than layout.  Re-indenting those lines changes what the
    database receives, so callers must emit them verbatim.

    This covers every literal kind the scanner reports, not just dollar-quoted
    bodies: an ordinary ``'…'`` string spanning lines carries its newlines and
    indentation exactly the same way.
    """
    if len(lines) < 2:
        return set()
    text = "\n".join(lines)
    starts = _literal_line_starts(lines)

    interior: set[int] = set()
    for start, end, _kind in _iter_sql_literals(text):
        interior.update(i for i, line_start in enumerate(starts) if start < line_start < end)
    return interior


def _literal_spanning_lines(lines: list[str]) -> set[int]:
    """Return indices of every line that any multi-line literal touches.

    Unlike :func:`_literal_interior_lines` this also includes the line that
    *opens* the literal.  Passes that move text between lines — rather than
    only adjusting leading whitespace — must leave the whole span alone, since
    the opening line holds literal content after its delimiter.
    """
    if len(lines) < 2:
        return set()
    text = "\n".join(lines)
    starts = _literal_line_starts(lines)

    spanning: set[int] = set()
    for start, end, _kind in _iter_sql_literals(text):
        touched = [i for i, line_start in enumerate(starts) if start < line_start < end]
        if not touched:
            continue  # single-line literal — nothing spans
        spanning.update(touched)
        spanning.add(min(touched) - 1)  # the line that opens the literal
    return spanning


# Placeholder standing in for a masked E'...' literal.  It is a plain literal
# so that sqlglot sees a string where a string was, and lays the statement out
# the same way it would have for the real one.
_ESTR_PLACEHOLDER = "execsqlestr"
_ESTR_RESTORE_RE = re.compile(rf"'{_ESTR_PLACEHOLDER}(\d+)'")


def _protect_estrings(sql: str) -> tuple[str, list[str]]:
    """Replace ``E'...'`` literals with placeholders, return (protected, originals).

    sqlglot's Postgres tokenizer consumes backslash escapes inside an escape
    string but its generator never re-emits them, so ``E'\\\\s+'`` round-trips
    to ``e'\\s+'`` — a different string (tobymao/sqlglot#8191).  Masking these
    literals keeps them out of the round trip entirely and restores them
    byte-for-byte, independently of the installed sqlglot version.
    """
    originals: list[str] = []
    out: list[str] = []
    last = 0
    for start, end, kind in _iter_sql_literals(sql):
        if kind != "estring":
            continue
        out.append(sql[last:start])
        out.append(f"'{_ESTR_PLACEHOLDER}{len(originals)}'")
        originals.append(sql[start:end])
        last = end
    if not originals:
        return sql, []
    out.append(sql[last:])
    return "".join(out), originals


def _restore_estrings(sql: str, originals: list[str]) -> str | None:
    """Put masked ``E'...'`` literals back; return None if any went missing.

    A missing placeholder means sqlglot dropped or mangled the literal, so the
    caller must fall back to the unformatted text rather than emit SQL with a
    placeholder left in it.
    """
    if not originals:
        return sql
    seen: set[int] = set()

    def replace(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        if idx >= len(originals):
            return m.group(0)
        seen.add(idx)
        return originals[idx]

    restored = _ESTR_RESTORE_RE.sub(replace, sql)
    if len(seen) != len(originals) or _ESTR_PLACEHOLDER in restored:
        return None
    return restored


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
    leading_comma: bool = False,  # noqa: ARG001 — leading-comma layout is applied as a textual post-pass on the assembled output; sqlglot's own `leading_comma=True` is non-idempotent under inline comments.
) -> list[str]:
    """Format a list of SQL-only lines (no comment-only lines) via sqlglot.

    Always emits trailing-comma style; if the caller wants leading commas
    they are produced by ``_apply_leading_comma`` at the end of
    ``format_file``. sqlglot's own ``leading_comma=True`` reshuffles inline
    comments and is therefore non-idempotent on SQL with mid-statement
    comments, which is the dominant real-world case.
    """
    sqlglot = _require_sqlglot()
    import sqlglot.errors as sqlglot_errors

    text = "\n".join(sql_lines)
    protected, replacements = _protect_variables(text)
    # Keep E'...' literals out of the round trip; sqlglot loses their
    # backslash escapes (see _protect_estrings).
    protected, estrings = _protect_estrings(protected)

    # Count semicolons in input as a rough statement count.
    input_semis = protected.count(";")

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            ast = sqlglot.parse(protected, read="postgres", error_level=sqlglot_errors.ErrorLevel.IGNORE)
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

        # Literal round-trip check.  The alphanumeric check above is a
        # gross-token-loss detector: it deletes every non-alphanumeric
        # character before counting, so a transformation that changes only
        # punctuation — a dropped backslash, a swapped quote — is invisible to
        # it at any threshold.  Requiring every literal to survive verbatim
        # closes that blind spot for the whole class, not just for the E'...'
        # case masked above.
        #
        # Containment, not equality: sqlglot rewrites dialect-specific
        # constructs into Postgres equivalents that can legitimately repeat a
        # literal (``SUBSTRING_INDEX(d, ',', 1)`` expands into a form using
        # ``','`` more than once), so the output may hold more literals than
        # the input.  What must never happen is an input literal coming back
        # altered or not at all — that is content loss, and it falls back.
        if set(_sql_literal_texts(protected)) - set(_sql_literal_texts(joined)):
            return sql_lines

        joined = re.sub(r"\bINTO TEMPORARY\b(?!\s+TABLE)", "INTO TEMPORARY TABLE", joined)
        restored = _restore_estrings(joined, estrings)
        if restored is None:
            return sql_lines
        return _restore_variables(restored, replacements).split("\n")
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
            line_indent = ""
            if cleaned:
                raw_cleaned = _CMT_MARKER_RE.sub("", fline)
                line_indent = raw_cleaned[: len(raw_cleaned) - len(raw_cleaned.lstrip())]
            for m in markers_here:
                if m in comment_store:
                    orig = comment_store[m]
                    # Re-indent the comment to match the SQL line it precedes
                    orig_stripped = orig.strip()
                    if orig_stripped:
                        result.append(line_indent + orig_stripped)
                    else:
                        result.append("")
                    found_markers.add(m)
            if cleaned:
                result.append(line_indent + cleaned)
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

    # Lines that begin inside a multi-line literal carry content, not layout —
    # dedenting or indenting them changes the value the database stores.
    # Exclude them from the indent arithmetic and emit them verbatim.
    interior = _literal_interior_lines(lines)
    if interior:
        # format_file already withholds dollar-quoted blocks from sqlglot; keep
        # that true here so the line indices below stay aligned with the output.
        use_sql = False

    layout_lines = [line for i, line in enumerate(lines) if line.strip() and i not in interior]
    base = min((len(line) - len(line.lstrip()) for line in layout_lines), default=0)
    target_prefix = " " * (depth * indent)
    rebased = [line if i in interior else (line[base:] if line.strip() else "") for i, line in enumerate(lines)]

    if not use_sql:
        return [
            line if i in interior else (target_prefix + line if line.strip() else "") for i, line in enumerate(rebased)
        ]

    # When comments appear mid-statement, use the marker-based approach
    # which preserves both comments AND sqlglot formatting.  When all
    # comments are between statements, the simpler segmentation works.
    if _has_mid_statement_comments(rebased):
        formatted_lines = _format_preserving_comments(rebased, sql_indent=indent, leading_comma=leading_comma)
        return [target_prefix + line if line.strip() else "" for line in formatted_lines]

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


def _is_comment_only(s: str) -> bool:
    """Strict comment classifier for the leading-comma post/pre passes."""
    st = s.strip()
    return st.startswith("--") or st.startswith("/*") or st.startswith("*/")


def _normalize_to_trailing_comma(text: str) -> str:
    """Rewrite leading-comma SQL (`, foo`) back to trailing-comma style.

    Symmetric inverse of ``_apply_leading_comma``. Used as a pre-pass so
    that sqlglot — which migrates inline ``/* marker */`` comments under
    leading-comma input — sees a consistent trailing-comma shape on
    every invocation. Comments between the two SQL lines stay in place.
    """
    lines = text.split("\n")
    # Symmetric with _apply_leading_comma: a leading comma inside a multi-line
    # literal is data, not layout, so the whole span is left alone.
    protected = _literal_spanning_lines(lines)

    def find_prev_sql_line(idx: int) -> int:
        k = idx - 1
        while k >= 0 and (not lines[k].strip() or _is_comment_only(lines[k])):
            k -= 1
        return k

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith(",") or _is_comment_only(line) or i in protected:
            continue
        # Don't try to rewrite leading-comma inside a comment-only line.
        # Move the comma onto the previous SQL line as a trailing `,`.
        prev = find_prev_sql_line(i)
        if prev < 0:
            continue
        # Drop the `, ` (or `,`) at the start of this line.
        indent_len = len(line) - len(stripped)
        rest = stripped[1:].lstrip()
        lines[i] = line[:indent_len] + rest
        # Append `,` to the prev SQL line (preserving any existing right-side
        # trailing whitespace — there shouldn't be any after format_file).
        prev_rstripped = lines[prev].rstrip()
        if not prev_rstripped.endswith(","):
            lines[prev] = prev_rstripped + ","
    return "\n".join(lines)


def _apply_leading_comma(text: str) -> str:
    """Rewrite trailing-comma SQL to leading-comma style as a textual pass.

    Walks the assembled output line-by-line. For every line that ends with
    ``,`` (and is not a comment), strip the comma and prepend ``, `` to the
    next non-blank, non-comment line — preserving that target line's
    indent. Comments between the two SQL lines stay in place. The
    transformation is idempotent: rerunning it on its own output is a
    no-op (the source line no longer ends with ``,``).

    This decouples our user-facing ``--leading-comma`` flag from
    sqlglot's own ``leading_comma=True`` mode, which is non-idempotent
    when inline ``/* marker */`` comments are present — sqlglot moves
    the markers around between passes (verified in tests/test_format.py
    TestIdempotency).
    """
    lines = text.split("\n")
    # A comma inside a multi-line string literal is data. Moving it to the next
    # line would rewrite the stored value, so leave every line such a literal
    # touches — including the one that opens it — exactly as it is.
    protected = _literal_spanning_lines(lines)
    i = 0
    n = len(lines)
    while i < n:
        rstripped = lines[i].rstrip()
        if rstripped.endswith(",") and not _is_comment_only(lines[i]) and i not in protected:
            j = i + 1
            while j < n and (not lines[j].strip() or _is_comment_only(lines[j])):
                j += 1
            if j < n and j not in protected:
                stripped = lines[i].rstrip()
                comma_idx = stripped.rfind(",")
                lines[i] = stripped[:comma_idx] + stripped[comma_idx + 1 :]
                target = lines[j]
                indent_len = len(target) - len(target.lstrip())
                lines[j] = target[:indent_len] + ", " + target[indent_len:]
        i += 1
    return "\n".join(lines)


def format_file(source: str, indent: int = 4, use_sql: bool = True, leading_comma: bool = False) -> str:
    """Format the source text of an execsql script and return the result."""
    # Normalize any leading-comma SQL in the source to trailing commas so
    # that sqlglot always sees the same comma shape regardless of how
    # the user saved the file. The post-pass at the bottom of this
    # function re-applies leading commas when the caller asked for them.
    # This is what makes leading_comma=True idempotent under inline
    # comments — sqlglot itself migrates `/* marker */` comments when
    # parsing leading-comma input.
    source = _normalize_to_trailing_comma(source)

    depth = 0
    sql_acc: list[str] = []
    output: list[str] = []

    in_dollar_quote = False
    # When in_dollar_quote, the tag string we are inside ("" for `$$`,
    # "body" for `$body$`, etc.). Nested markers with a different tag
    # are ignored — only a matching close marker re-opens us.
    current_dq_tag: str | None = None
    # Sticky flag: True once the current accumulator has seen ANY dollar-quote
    # marker. `in_dollar_quote` alone is False by the time a complete
    # `CREATE FUNCTION ... $$ ... $$;` is flushed (the closing `$$` reset it),
    # which would wrongly hand the PL/pgSQL body to sqlglot. This flag keeps the
    # whole containing statement opaque to sqlglot. Reset in flush_sql().
    sql_acc_contains_dollar_quote = False
    in_block_comment = False
    # Track whether we are inside an open SQL statement (last SQL line
    # did not end with ';').  Blank lines mid-statement should NOT flush
    # the accumulator — doing so would split a single statement into
    # fragments that sqlglot cannot parse.
    in_sql_statement = False
    # True between BEGIN SQL/BATCH and END SQL/BATCH.  Blank lines inside
    # these blocks belong to the SQL accumulator so they re-emit at the
    # block's indent depth, not flush-left in the output stream.
    in_explicit_sql_block = False

    def flush_sql() -> None:
        nonlocal in_dollar_quote, current_dq_tag, in_sql_statement
        nonlocal sql_acc_contains_dollar_quote
        if sql_acc:
            # If any line in the accumulated block is inside a $$-delimited
            # region, skip sqlglot formatting entirely.  PL/pgSQL function
            # bodies contain IF/END IF, LOOP, RETURN, etc. that sqlglot does
            # not understand and will corrupt (e.g., rewriting to COMMIT).
            # `sql_acc_contains_dollar_quote` catches the case where the region
            # already closed (`... $$;`) so `in_dollar_quote` is False at flush.
            safe_for_sqlglot = use_sql and not in_dollar_quote and not sql_acc_contains_dollar_quote
            output.extend(format_sql_block(sql_acc, depth, indent, safe_for_sqlglot, leading_comma=leading_comma))
            sql_acc.clear()
        in_sql_statement = False
        sql_acc_contains_dollar_quote = False

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
            if not in_dollar_quote and not in_sql_statement and not in_explicit_sql_block:
                flush_sql()
                output.append("")
            else:
                # Mid-statement OR mid-explicit-SQL-block blank line stays in
                # the accumulator and will appear in the output at the block's
                # indent depth when the SQL is formatted.
                sql_acc.append(raw_line)

        elif m:
            flush_sql()
            payload = m.group(1).strip()
            keyword = parse_keyword(payload)

            if keyword in BLOCK_CLOSE:
                depth = max(0, depth - 1)
                output.append(format_metacommand(payload, depth, indent))
                if keyword in _SQL_BODY_BLOCK_CLOSES:
                    in_explicit_sql_block = False

            elif keyword in PIVOT:
                depth = max(0, depth - 1)
                output.append(format_metacommand(payload, depth, indent))
                depth += 1

            elif keyword in CONTINUATION:
                output.append(format_metacommand(payload, max(0, depth - 1), indent))

            elif keyword in BLOCK_OPEN:
                output.append(format_metacommand(payload, depth, indent))
                if not (keyword == "IF" and _IF_INLINE_RE.match(payload)):
                    depth += 1
                if keyword in _SQL_BODY_BLOCKS:
                    in_explicit_sql_block = True

            else:
                output.append(format_metacommand(payload, depth, indent))

        else:
            # Track $$ and $tag$ boundaries to prevent sqlglot from mangling
            # PL/pgSQL. Walk every dollar-quote marker on the line; toggle
            # state only when we hit the matching open or close.
            for m in _DOLLAR_QUOTE_RE.finditer(raw_line):
                sql_acc_contains_dollar_quote = True
                tag = m.group(1) or ""
                if not in_dollar_quote:
                    in_dollar_quote = True
                    current_dq_tag = tag
                elif tag == current_dq_tag:
                    in_dollar_quote = False
                    current_dq_tag = None
                # else: tag mismatch — a foreign-tagged marker inside our
                # quoted region; ignore (PG would treat it as literal text).
            sql_acc.append(raw_line)
            # Update statement tracking: if this SQL line ends with ';'
            # (and isn't a comment), the statement is complete.
            if stripped_line.endswith(";") and not stripped_line.startswith("--"):
                in_sql_statement = False
            elif not stripped_line.startswith("--"):
                in_sql_statement = True

    flush_sql()

    result = "\n".join(output)
    if leading_comma:
        result = _apply_leading_comma(result)
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
        encoding: str = typer.Option(
            "utf-8",
            "--encoding",
            metavar="NAME",
            help="Text encoding used to read and write SQL files (default utf-8).",
        ),
    ) -> None:
        use_sql = not no_sql
        paths = collect_paths(targets)
        if not paths:
            _err_console.print("[bold red]Error:[/bold red] No .sql files found.")
            raise typer.Exit(code=1)

        any_changed = False
        any_errors = False
        for path in paths:
            try:
                source = path.read_text(encoding=encoding)
            except OSError as exc:
                _err_console.print(f"[bold red]Error:[/bold red] reading {path}: {exc}")
                any_errors = True
                # Collect read errors instead of short-circuiting so a single
                # unreadable file doesn't hide the rest of the report.
                continue
            except UnicodeDecodeError as exc:
                _err_console.print(
                    f"[bold red]Error:[/bold red] decoding {path} as {encoding}: {exc}. "
                    f"Try [bold]--encoding cp1252[/bold] or another text encoding.",
                )
                any_errors = True
                continue

            formatted = format_file(source, indent=indent, use_sql=use_sql, leading_comma=leading_comma)

            if check:
                if formatted != source:
                    _console.print(f"would reformat {path}")
                    any_changed = True
            elif in_place:
                if formatted != source:
                    path.write_text(formatted, encoding=encoding)
                    _console.print(f"reformatted {path}")
            else:
                sys.stdout.write(formatted)

        if any_errors or (check and any_changed):
            raise typer.Exit(code=1)

    app()
