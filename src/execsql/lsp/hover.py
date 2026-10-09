"""Hover: what the metacommand, conditional test or variable under the cursor is.

Metacommands and conditional tests are explained from
:mod:`execsql.metacommands.reference`; a variable by where the script defines
it, or by its reference entry for system variables.
"""

from __future__ import annotations

import re

from lsprotocol import types

from execsql.lsp.document import Reference, ScriptIndex, variable_at
from execsql.metacommands import reference

__all__ = ["hover", "metacommand_for"]

_RX_METACOMMAND = re.compile(r"^(?P<lead>\s*--\s*!x!\s*)(?P<command>.*?)\s*$", re.I)
_RX_WORD = re.compile(r"[A-Za-z_]+")


def metacommand_for(command: str) -> reference.Metacommand | None:
    """The reference entry for a metacommand's text (what follows ``-- !x!``).

    The dispatch entry that would run it names its keyword when it has one
    (``PROMPT MESSAGE "..." MAP ...`` is PROMPT MAP); otherwise the longest
    keyword the text starts with (``AUTOCOMMIT ON`` is AUTOCOMMIT,
    ``CONFIG BOOLEAN_INT YES`` is CONFIG).
    """
    from execsql.cli.lint import _dispatch_table

    match = _dispatch_table().get_match(command)
    if match is not None and match[0].description:
        entry = reference.metacommand(match[0].description)
        if entry is not None:
            return entry
    best = None
    for entry in reference.metacommands():
        if re.match(rf"{re.escape(entry.keyword)}S?\b", command.strip(), re.I) and (
            best is None or len(entry.keyword) > len(best.keyword)
        ):
            best = entry
    return best


def _markdown(text: str) -> types.MarkupContent:
    return types.MarkupContent(kind=types.MarkupKind.Markdown, value=text)


def _range(line: int, start: int, end: int) -> types.Range:
    return types.Range(start=types.Position(line=line, character=start), end=types.Position(line=line, character=end))


def _syntax_block(forms: tuple[str, ...]) -> str:
    return "```\n" + "\n".join(forms) + "\n```"


def _variable_hover(index: ScriptIndex, ref: Reference, lines: list[str]) -> str | None:
    name = ref.name
    if name.startswith("$"):
        var = reference.system_variable(name)
        if var is None:
            return f"**{name}**: not a system variable execsql defines."
        return f"**{name}** — system variable\n\n{var.summary}\n\n[Reference]({var.url})"
    if name.startswith("&"):
        return f"**{name}** — the environment variable `{name[1:]}`."
    if name.startswith("@"):
        return f"**{name}** — a column value assigned by SELECT_SUB or PROMPT SELECT_SUB."
    if name.startswith("#"):
        owners = [s for s, params in index.script_params.items() if name[1:].lower() in (p.lower() for p in params)]
        if owners:
            return f"**{name}** — parameter of SCRIPT {', '.join(owners)}."
        return f"**{name}** — a SCRIPT parameter, but no SCRIPT here declares `{name[1:]}`."
    locations = index.definitions.get(ref.key)
    if not locations:
        return f"**{name}** is not defined in this script or the files it includes (lint rule V001)."
    parts = [f"**{name}** — substitution variable"]
    for loc in locations[:5]:
        where = f"line {loc.line + 1}" if loc.path == index.path else f"{loc.path}, line {loc.line + 1}"
        text = lines[loc.line].strip() if loc.path == index.path and loc.line < len(lines) else ""
        parts.append(f"Defined at {where}" + (f":\n```\n{text}\n```" if text else "."))
    if len(locations) > 5:
        parts.append(f"… and {len(locations) - 5} more.")
    return "\n\n".join(parts)


def hover(index: ScriptIndex, source: str, line: int, character: int) -> types.Hover | None:
    """What to show for the cursor at (*line*, *character*), zero-based."""
    lines = source.splitlines()
    text = lines[line] if 0 <= line < len(lines) else ""

    ref = variable_at(index, line, character)
    if ref is not None:
        content = _variable_hover(index, ref, lines)
        loc = ref.location
        return types.Hover(contents=_markdown(content), range=_range(line, loc.start, loc.end)) if content else None

    m = _RX_METACOMMAND.match(text)
    if not m or character < m.end("lead"):
        return None

    # A conditional test under the cursor: a word followed by "(".
    for word in _RX_WORD.finditer(text):
        if word.start() <= character <= word.end() and text[word.end() :].lstrip().startswith("("):
            cond = reference.condition(word.group())
            if cond is not None and cond.name not in ("NOT", "OR"):
                body = f"**{cond.name}** — conditional test\n\n{cond.summary}\n\n{_syntax_block(cond.forms)}\n\n[Reference]({cond.url})"
                return types.Hover(contents=_markdown(body), range=_range(line, word.start(), word.end()))

    entry = metacommand_for(m.group("command"))
    if entry is None:
        return None
    start = m.end("lead")
    written = re.match(r"\s*".join(map(re.escape, entry.keyword.split())), text[start:], re.I)
    first_word = re.match(r"[A-Za-z_]+", text[start:])
    keyword_end = start + (written.end() if written else first_word.end() if first_word else 0)
    body = f"**{entry.keyword}** — {entry.category} metacommand\n\n{entry.summary}\n\n{_syntax_block(entry.forms)}\n\n[Reference]({entry.url})"
    return types.Hover(contents=_markdown(body), range=_range(line, start, keyword_end))
