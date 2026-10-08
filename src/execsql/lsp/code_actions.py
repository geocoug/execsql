"""Quick fixes for lint findings.

Each fix is checked before it is offered: a spelling fix must make the
metacommand match a dispatch-table form (P003) or make lint's finding go away
(P004, P002).  A fix that would not clear the finding is never shown.

- P003 unknown metacommand: a misspelled keyword, e.g. ``EXPROT`` -> ``EXPORT``.
- P004 unknown condition: a misspelled conditional test, e.g. ``HASROWZ`` -> ``HASROWS``.
- V001 undefined variable: a near-miss of a variable the script defines (or of a system variable).
- P002 split dollar quote: put the statement between ``BEGIN SQL`` and ``END SQL``.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterator, Sequence

from lsprotocol import types

from execsql.cli.lint import _dispatch_table, _with_placeholders, lint_source
from execsql.format import open_dollar_quote
from execsql.lsp.document import ScriptIndex
from execsql.metacommands import reference

__all__ = ["code_actions"]

_RX_METACOMMAND = re.compile(r"^(?P<lead>\s*--\s*!x!\s*)(?P<command>.*?)\s*$", re.I)
_RX_WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_RX_UNDEFINED = re.compile(r"!!(?P<name>[^!]+)!!")
_SUGGESTIONS = 3  # per misspelled word
_CUTOFF = 0.7


def _vocabulary() -> set[str]:
    """Every literal word of a metacommand's syntax: keywords and words such as TO, AS, WITH."""
    words: set[str] = set()
    for entry in reference.metacommands():
        for form in entry.forms:
            words.update(re.findall(r"\b[A-Z][A-Z_]+\b", re.sub(r"<[^>]*>", " ", form)))
    return words


def _cased_like(word: str, written: str) -> str:
    return word.lower() if written.islower() else word


def _close(word: str, choices: set[str] | list[str]) -> list[str]:
    return difflib.get_close_matches(word.upper(), list(choices), n=_SUGGESTIONS, cutoff=_CUTOFF)


def _replace(text: str, start: int, end: int, new: str) -> str:
    return text[:start] + new + text[end:]


def _range(line: int, start: int, end: int) -> types.Range:
    return types.Range(start=types.Position(line=line, character=start), end=types.Position(line=line, character=end))


def _fix(title: str, uri: str, diagnostic: types.Diagnostic, edits: list[types.TextEdit]) -> types.CodeAction:
    return types.CodeAction(
        title=title,
        kind=types.CodeActionKind.QuickFix,
        diagnostics=[diagnostic],
        edit=types.WorkspaceEdit(changes={uri: edits}),
    )


def _count(source: str, path: str | None, code: str) -> int:
    return sum(1 for issue in lint_source(source, path or "<untitled>", script_path=path) if issue.code == code)


def _clears(lines: list[str], path: str | None, code: str, before: tuple[int, int], row: int, new_line: str) -> bool:
    """Whether replacing line *row* with *new_line* removes a *code* finding without adding a parse error.

    *before* is the (*code*, P001) count of the unchanged script.
    """
    fixed = "\n".join(lines[:row] + [new_line] + lines[row + 1 :]) + "\n"
    return _count(fixed, path, code) < before[0] and _count(fixed, path, "P001") <= before[1]


def _metacommand_fixes(text: str, row: int) -> Iterator[tuple[str, int, int, str]]:
    """(suggestion, start, end, written) for each word whose replacement makes the metacommand match."""
    m = _RX_METACOMMAND.match(text)
    if not m:
        return
    vocabulary = _vocabulary()
    offset = m.start("command")
    command = m.group("command")
    table = _dispatch_table()
    for word in _RX_WORD.finditer(command):
        if word.group().upper() in vocabulary:
            continue
        for candidate in _close(word.group(), vocabulary):
            fixed = _replace(command, word.start(), word.end(), candidate)
            if table.get_match(fixed) is not None or table.get_match(_with_placeholders(fixed)) is not None:
                yield candidate, offset + word.start(), offset + word.end(), word.group()


def _p003(uri: str, lines: list[str], diagnostic: types.Diagnostic) -> list[types.CodeAction]:
    row = diagnostic.range.start.line
    return [
        _fix(
            f"Change {written} to {_cased_like(candidate, written)}",
            uri,
            diagnostic,
            [types.TextEdit(range=_range(row, start, end), new_text=_cased_like(candidate, written))],
        )
        for candidate, start, end, written in _metacommand_fixes(lines[row], row)
    ]


def _p004(uri: str, path: str | None, lines: list[str], diagnostic: types.Diagnostic) -> list[types.CodeAction]:
    row = diagnostic.range.start.line
    text = lines[row]
    m = _RX_METACOMMAND.match(text)
    if not m:
        return []
    names = {c.name for c in reference.conditions() if c.name not in ("NOT", "OR")}
    source = "\n".join(lines) + "\n"
    before = (_count(source, path, "P004"), _count(source, path, "P001"))
    actions = []
    for word in _RX_WORD.finditer(text, m.start("command")):
        if word.group().upper() in names or not text[word.end() :].lstrip().startswith("("):
            continue
        for candidate in _close(word.group(), names):
            new = _cased_like(candidate, word.group())
            if _clears(lines, path, "P004", before, row, _replace(text, word.start(), word.end(), new)):
                edit = types.TextEdit(range=_range(row, word.start(), word.end()), new_text=new)
                actions.append(_fix(f"Change {word.group()} to {new}", uri, diagnostic, [edit]))
    return actions


def _v001(index: ScriptIndex, uri: str, diagnostic: types.Diagnostic) -> list[types.CodeAction]:
    m = _RX_UNDEFINED.search(diagnostic.message)
    if not m:
        return []
    row = diagnostic.range.start.line
    written = m.group("name")
    actions = []
    for ref in index.references:
        loc = ref.location
        if loc.path != index.path or loc.line != row or ref.name.lower() != written.lower():
            continue
        prefix = ref.name[: len(ref.name) - len(ref.name.lstrip("~+"))]
        bare = ref.name[len(prefix) :]
        if bare.startswith("$"):
            choices = {v.name for v in reference.system_variables() if not v.name.endswith("_x")}
            spelled = {name: name for name in choices}
        else:
            spelled = {key: index.spellings[key] for key in index.definitions}
        for candidate in _close(bare, set(spelled)):
            new = prefix + spelled[candidate]
            edit = types.TextEdit(range=_range(row, loc.start, loc.end), new_text=new)
            actions.append(_fix(f"Change !!{ref.name}!! to !!{new}!!", uri, diagnostic, [edit]))
        break
    return actions


def _statement_end(lines: list[str], row: int) -> int | None:
    """The line that ends the statement whose dollar-quoted body opens on *row*."""
    open_tag: str | None = None
    for end in range(row, len(lines)):
        open_tag = open_dollar_quote(lines[end] + "\n", open_tag)
        if open_tag is None and end > row and lines[end].rstrip().endswith(";"):
            return end
    return None


def _p002(uri: str, path: str | None, lines: list[str], diagnostic: types.Diagnostic) -> list[types.CodeAction]:
    row = diagnostic.range.start.line
    end = _statement_end(lines, row)
    if end is None:
        return []
    indent = lines[row][: len(lines[row]) - len(lines[row].lstrip())]
    fixed = (
        lines[:row]
        + [f"{indent}-- !x! BEGIN SQL"]
        + lines[row : end + 1]
        + [f"{indent}-- !x! END SQL"]
        + lines[end + 1 :]
    )
    if _count("\n".join(fixed) + "\n", path, "P002") >= _count("\n".join(lines) + "\n", path, "P002"):
        return []
    edits = [
        types.TextEdit(range=_range(row, 0, 0), new_text=f"{indent}-- !x! BEGIN SQL\n"),
        types.TextEdit(range=_range(end, len(lines[end]), len(lines[end])), new_text=f"\n{indent}-- !x! END SQL"),
    ]
    return [_fix("Put the statement between BEGIN SQL and END SQL", uri, diagnostic, edits)]


def code_actions(
    index: ScriptIndex,
    uri: str,
    source: str,
    diagnostics: Sequence[types.Diagnostic],
) -> list[types.CodeAction]:
    """The quick fixes for the execsql *diagnostics* the editor asks about."""
    lines = source.splitlines()
    actions: list[types.CodeAction] = []
    for diagnostic in diagnostics:
        if diagnostic.source != "execsql" or diagnostic.range.start.line >= len(lines):
            continue
        if diagnostic.code == "P003":
            found = _p003(uri, lines, diagnostic)
        elif diagnostic.code == "P004":
            found = _p004(uri, index.path, lines, diagnostic)
        elif diagnostic.code == "V001":
            found = _v001(index, uri, diagnostic)
        elif diagnostic.code == "P002":
            found = _p002(uri, index.path, lines, diagnostic)
        else:
            continue
        if len(found) == 1:
            found[0].is_preferred = True
        actions.extend(found)
    return actions
