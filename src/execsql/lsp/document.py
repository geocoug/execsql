"""What a script defines and refers to, with positions: the index the editor features read.

Built from the recovering parser (a script with an unclosed block still
indexes) and from the script's text for exact columns.  ``INCLUDE``d files
are read from disk and indexed too, so a variable set in a shared setup
script completes and resolves in the scripts that include it.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pygls.uris import from_fs_path

from execsql.cli.lint import variables_defined_by
from execsql.script.ast import IncludeDirective, MetaCommandStatement, ScriptBlock
from execsql.script.parser import parse_string

__all__ = [
    "Location",
    "Reference",
    "ScriptIndex",
    "file_uri",
    "index_script",
    "read_included",
    "same_file_key",
    "uri_for",
    "variable_at",
]

# A substitution variable as written: !!name!!, !'!name!'!, !"!name!"! or the deferred !{name}!.
# The lookahead also finds one written inside another's name: in !!N_!!GROUP!!_CHECKS!!,
# execsql substitutes !!GROUP!! first, so GROUP is a use (N_ and _CHECKS are found too).
_RX_VARIABLE = re.compile(r"""(?=!(['"]?)!(?P<name>[$&@~#+]?\w+)!\1!)|!\{(?P<deferred>[$&@~#+]?\w+)\}!""")
_RX_METACOMMAND = re.compile(r"^\s*--\s*!x!\s*", re.I)


@dataclass(frozen=True)
class Location:
    """A span on one line of a file: zero-based line, character offsets."""

    path: str | None
    line: int
    start: int
    end: int


@dataclass(frozen=True)
class Reference:
    """A variable written in the script, e.g. ``!!report_dir!!``."""

    name: str  # as written, with its prefix: "report_dir", "$CURRENT_DATE", "#param"
    location: Location  # the name itself, inside the delimiters

    @property
    def key(self) -> str:
        """The name a definition is filed under: user variables without ``~``/``+``, upper case."""
        return self.name.lstrip("~+").upper()


@dataclass
class ScriptIndex:
    """Definitions and uses in one script and the files it includes."""

    path: str | None
    definitions: dict[str, list[Location]] = field(default_factory=dict)  # by Reference.key
    spellings: dict[str, str] = field(default_factory=dict)  # key -> name as first written
    scripts: dict[str, Location] = field(default_factory=dict)  # BEGIN SCRIPT name (lower case) -> where
    script_params: dict[str, list[str]] = field(default_factory=dict)  # script name -> its #parameters
    includes: list[tuple[Location, str]] = field(default_factory=list)  # (where the target is written, resolved path)
    script_calls: list[tuple[Location, str]] = field(default_factory=list)  # EXECUTE SCRIPT name, in this file
    references: list[Reference] = field(default_factory=list)  # in this file and the files it includes
    open_uris: dict[str, str] = field(default_factory=dict)  # same_file_key(path) -> URI of the editor's open copy

    def define(self, name: str, location: Location) -> None:
        key = name.lstrip("~+").upper()
        self.definitions.setdefault(key, []).append(location)
        self.spellings.setdefault(key, name.lstrip("~+"))


# Limits on what INCLUDE indexing reads, so a script in an untrusted workspace
# cannot make every request read a huge file or walk an endless include chain.
MAX_INCLUDED_BYTES = 10 * 1024 * 1024
MAX_INCLUDED_FILES = 200


def read_included(path: Path) -> str | None:
    """The text of an ``INCLUDE``d file, or ``None`` if it is not one to index.

    Only a regular file (not a FIFO or a device, whose read could block or
    never end) of at most :data:`MAX_INCLUDED_BYTES` that decodes as UTF-8.
    """
    try:
        if not path.is_file() or path.stat().st_size > MAX_INCLUDED_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _span_of(word: str, line: str, start: int = 0) -> tuple[int, int]:
    """Columns of *word* in *line* at or after *start* (any case); the whole line if absent."""
    m = re.search(rf"(?<![\w$#@&]){re.escape(word)}(?!\w)", line[start:], re.I)  # after ~ or +: SUB ~name
    if m is None:
        return 0, len(line)
    return start + m.start(), start + m.end()


def index_script(
    source: str,
    path: str | None,
    read: Callable[[Path], str | None] = read_included,
) -> ScriptIndex:
    """Index *source*, the text of the file at *path* (``None`` for an unsaved buffer).

    *read* supplies an ``INCLUDE``d file's text; the server passes one that
    prefers the editor's unsaved copy of a file that is open.
    """
    index = ScriptIndex(path=path)
    _index_into(index, source, path, set(), read, top=True)
    return index


def _index_into(
    index: ScriptIndex,
    source: str,
    path: str | None,
    seen: set[str],
    read: Callable[[Path], str | None],
    *,
    top: bool,
) -> None:
    if path is not None:
        seen.add(str(Path(path).resolve()))
    lines = source.splitlines()
    script_dir = Path(path).parent if path else None
    tree = parse_string(source, path or "<untitled>", errors=[])

    for node in tree.walk():
        row = node.span.start_line - 1
        text = lines[row] if 0 <= row < len(lines) else ""
        if isinstance(node, MetaCommandStatement):
            prefix = _RX_METACOMMAND.match(text)
            after = prefix.end() if prefix else 0
            for name in sorted(variables_defined_by(node.command, script_dir)):
                start, end = _span_of(name, text, after)
                found = text[start:end] if text[start:end].upper() == name else name  # keep the script's spelling
                index.define(found, Location(path, row, start, end))
        elif isinstance(node, ScriptBlock):
            start, end = _span_of(node.name, text)
            index.scripts.setdefault(node.name.lower(), Location(path, row, start, end))
            index.script_params[node.name.lower()] = [p.name for p in node.param_defs or []]
        elif isinstance(node, IncludeDirective) and node.is_execute_script:
            if top:
                start, end = _span_of(node.target, text)
                index.script_calls.append((Location(path, row, start, end), node.target.lower()))
        elif isinstance(node, IncludeDirective):
            target = node.target.strip().strip("\"'")
            start, end = _span_of(target, text) if target else (0, len(text))
            resolved = Path(target) if Path(target).is_absolute() or script_dir is None else script_dir / target
            if top:
                index.includes.append((Location(path, row, start, end), str(resolved)))
            if "!" not in target and str(resolved.resolve()) not in seen and len(seen) < MAX_INCLUDED_FILES:
                included = read(resolved)
                if included is not None:
                    _index_into(index, included, str(resolved), seen, read, top=False)

    for row, text in enumerate(lines):
        for m in _RX_VARIABLE.finditer(text):
            group = "deferred" if m.group("deferred") else "name"
            index.references.append(Reference(m.group(group), Location(path, row, m.start(group), m.end(group))))


def uri_for(path: str | None, index: ScriptIndex, uri: str) -> str:
    """The URI to report for a location in *path*.

    For the indexed file it is the request's *uri*, as the client spelled it:
    one rebuilt from the path can differ (``file:///c:/`` and ``file:///C:/``
    on Windows), and a client may not match the two.
    """
    if path is None or path == index.path:
        return uri
    return file_uri(path, index) or uri


def file_uri(path: str, index: ScriptIndex) -> str | None:
    """The URI for another file at *path*: as the client spelled it if the file is open, else one built from the path."""
    return index.open_uris.get(same_file_key(path)) or from_fs_path(path)


def same_file_key(path: str) -> str:
    """*path* resolved and case-folded where the file system ignores case, for comparing files."""
    return os.path.normcase(str(Path(path).resolve()))


def variable_at(index: ScriptIndex, line: int, character: int) -> Reference | None:
    """The variable reference under the cursor in the indexed file, if any."""
    for ref in index.references:
        loc = ref.location
        if loc.path == index.path and loc.line == line and loc.start <= character <= loc.end:
            return ref
    return None
