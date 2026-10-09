"""Rename a user variable everywhere the index sees it: the script and the files it includes.

Scripts that ``INCLUDE`` this one are not known to the server, so their
uses of the variable are not renamed.
"""

from __future__ import annotations

import re

from lsprotocol import types

from execsql.lsp.document import Location, ScriptIndex, uri_for, variable_at

__all__ = ["RenameError", "prepare_rename", "rename"]

_RX_NAME = re.compile(r"^\w+$")


class RenameError(ValueError):
    """Why a rename cannot be done; the server shows the message."""


def _target(index: ScriptIndex, line: int, character: int) -> tuple[str, Location] | None:
    """The user variable under the cursor: its key and where its bare name is written."""
    ref = variable_at(index, line, character)
    if ref is not None:
        bare = ref.name.lstrip("~+")
        if not _RX_NAME.match(bare):  # $system, &environment, @column or #parameter
            return None
        loc = ref.location
        return ref.key, Location(loc.path, loc.line, loc.end - len(bare), loc.end)
    for key, locations in index.definitions.items():
        for loc in locations:
            if loc.path == index.path and loc.line == line and loc.start <= character <= loc.end:
                return key, loc
    return None


def _range(loc: Location) -> types.Range:
    return types.Range(
        start=types.Position(line=loc.line, character=loc.start),
        end=types.Position(line=loc.line, character=loc.end),
    )


def prepare_rename(index: ScriptIndex, line: int, character: int) -> types.Range | None:
    """The name to rename at the cursor, or ``None`` if there is nothing renameable there."""
    target = _target(index, line, character)
    return _range(target[1]) if target else None


def rename(index: ScriptIndex, uri: str, line: int, character: int, new_name: str) -> types.WorkspaceEdit | None:
    """Edits renaming the variable under the cursor to *new_name*.

    Raises :class:`RenameError` when the rename would not be correct: an
    invalid name, one already defined, a name used both as a local
    (``~name``) and a global variable (execsql keeps those apart; the index
    does not), or a definition whose name cannot be located on its line.
    """
    target = _target(index, line, character)
    if target is None:
        return None
    key = target[0]
    if not _RX_NAME.match(new_name):
        raise RenameError(f"{new_name!r} is not a variable name: use letters, digits and underscores.")
    if new_name.upper() != key and new_name.upper() in index.definitions:
        raise RenameError(f"{new_name} is already defined.")

    uses = [r for r in index.references if r.key == key]
    prefixes = {r.name[: len(r.name) - len(r.name.lstrip("~+"))] for r in uses}
    if "~" in prefixes and len(prefixes) > 1:
        raise RenameError(f"{key.lower()} is used both as a local (~) and a global variable; rename it by hand.")

    spans: set[Location] = set()
    for ref in uses:
        bare = ref.name.lstrip("~+")
        loc = ref.location
        spans.add(Location(loc.path, loc.line, loc.end - len(bare), loc.end))
    for loc in index.definitions.get(key, []):
        if loc.end - loc.start != len(key):
            where = f"{loc.path or 'this file'}, line {loc.line + 1}"
            raise RenameError(f"Cannot find the name {key.lower()} in its definition ({where}); rename it by hand.")
        spans.add(loc)

    changes: dict[str, list[types.TextEdit]] = {}
    for loc in sorted(spans, key=lambda s: (s.path or "", s.line, s.start)):
        changes.setdefault(uri_for(loc.path, index, uri), []).append(
            types.TextEdit(range=_range(loc), new_text=new_name),
        )
    return types.WorkspaceEdit(changes=changes)
