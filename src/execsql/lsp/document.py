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
from execsql.lsp._util import RX_METACOMMAND
from execsql.utils.paths import is_network_path
from execsql.script.ast import IncludeDirective, MetaCommandStatement, ScriptBlock
from execsql.script.parser import parse_string

__all__ = [
    "FileFacts",
    "Location",
    "Reference",
    "ScriptIndex",
    "file_facts",
    "file_uri",
    "index_script",
    "read_included",
    "same_file_key",
    "uri_for",
    "variable_at",
    "is_file",
]

# A substitution variable as written: !!name!!, !'!name!'!, !"!name!"! or the deferred !{name}!.
# The lookahead also finds one written inside another's name: in !!N_!!GROUP!!_CHECKS!!,
# execsql substitutes !!GROUP!! first, so GROUP is a use (N_ and _CHECKS are found too).
_RX_VARIABLE = re.compile(r"""(?=!(['"]?)!(?P<name>[$&@~#+]?\w+)!\1!)|!\{(?P<deferred>[$&@~#+]?\w+)\}!""")


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
# The files an INCLUDE names, all together; past it indexing follows no more of them.
MAX_INCLUDED_TOTAL_BYTES = 20 * 1024 * 1024


def read_included(path: Path) -> str | None:
    """The text of an ``INCLUDE``d file, or ``None`` if it is not one to index.

    Only a regular file (not a FIFO or a device, whose read could block or
    never end) of at most :data:`MAX_INCLUDED_BYTES` that decodes as UTF-8.
    """
    try:
        if not path.is_file() or path.stat().st_size > MAX_INCLUDED_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeDecodeError):  # ValueError: a NUL in the name
        return None


def _span_of(word: str, line: str, start: int = 0) -> tuple[int, int]:
    """Columns of *word* in *line* at or after *start* (any case); the whole line if absent."""
    m = re.search(rf"(?<![\w$#@&]){re.escape(word)}(?!\w)", line[start:], re.I)  # after ~ or +: SUB ~name
    if m is None:
        return 0, len(line)
    return start + m.start(), start + m.end()


@dataclass(frozen=True)
class _Define:
    name: str  # as the script spells it
    location: Location


@dataclass(frozen=True)
class _ScriptDef:
    name: str  # lower case
    location: Location
    params: tuple[str, ...]


@dataclass(frozen=True)
class _ScriptCall:
    location: Location
    name: str  # lower case


@dataclass(frozen=True)
class _Include:
    location: Location
    target: str  # as written, quotes removed
    resolved: str  # relative to the including file


@dataclass(frozen=True)
class FileFacts:
    """What one file adds to an index, in the order indexing meets it.

    It depends on the file's text and path alone, not on the files it
    includes, so a caller may keep it while the text is unchanged, unless
    :attr:`reads_ini`: a ``SUB_INI`` reads an INI file that can change on its own.
    """

    steps: tuple[_Define | _ScriptDef | _ScriptCall | _Include, ...]
    references: tuple[Reference, ...]
    reads_ini: bool = False

    @property
    def includes(self) -> tuple[str, ...]:
        """The path of each file an ``INCLUDE`` in this file names, relative to it."""
        return tuple(step.resolved for step in self.steps if isinstance(step, _Include))


_RX_SUB_INI = re.compile(r"\s*SUB_INI\b", re.I)


def file_facts(source: str, path: str | None, base_dir: str | None = None) -> FileFacts:
    """The definitions, script blocks, ``INCLUDE`` targets and variable uses written in *source*.

    Relative paths in it resolve against *path*'s directory, or for an
    unsaved buffer (no *path*) against *base_dir*, else the working directory.
    """
    steps: list[_Define | _ScriptDef | _ScriptCall | _Include] = []
    reads_ini = False
    lines = source.splitlines()
    script_dir = Path(path).parent if path else (Path(base_dir) if base_dir else None)
    tree = parse_string(source, path or "<untitled>", errors=[])

    for node in tree.walk():
        row = node.span.start_line - 1
        text = lines[row] if 0 <= row < len(lines) else ""
        if isinstance(node, MetaCommandStatement):
            reads_ini = reads_ini or _RX_SUB_INI.match(node.command) is not None
            prefix = RX_METACOMMAND.match(text)
            after = prefix.end("lead") if prefix else 0
            for name in sorted(variables_defined_by(node.command, script_dir)):
                start, end = _span_of(name, text, after)
                found = text[start:end] if text[start:end].upper() == name else name  # keep the script's spelling
                steps.append(_Define(found, Location(path, row, start, end)))
        elif isinstance(node, ScriptBlock):
            start, end = _span_of(node.name, text)
            params = tuple(p.name for p in node.param_defs or [])
            steps.append(_ScriptDef(node.name.lower(), Location(path, row, start, end), params))
        elif isinstance(node, IncludeDirective) and node.is_execute_script:
            start, end = _span_of(node.target, text)
            steps.append(_ScriptCall(Location(path, row, start, end), node.target.lower()))
        elif isinstance(node, IncludeDirective):
            target = node.target.strip().strip("\"'")
            if is_network_path(target):
                continue  # never followed: checking it would contact the named host
            start, end = _span_of(target, text) if target else (0, len(text))
            resolved = Path(target) if Path(target).is_absolute() or script_dir is None else script_dir / target
            steps.append(_Include(Location(path, row, start, end), target, str(resolved)))

    references: list[Reference] = []
    for row, text in enumerate(lines):
        for m in _RX_VARIABLE.finditer(text):
            group = "deferred" if m.group("deferred") else "name"
            references.append(Reference(m.group(group), Location(path, row, m.start(group), m.end(group))))
    return FileFacts(tuple(steps), tuple(references), reads_ini)


def index_script(
    source: str,
    path: str | None,
    read: Callable[[Path], str | None] = read_included,
    facts: Callable[[str, str | None, str | None], FileFacts] = file_facts,
    base_dir: str | None = None,
) -> ScriptIndex:
    """Index *source*, the text of the file at *path* (``None`` for an unsaved buffer).

    *read* supplies an ``INCLUDE``d file's text; the server passes one that
    prefers the editor's unsaved copy of a file that is open.  *facts*
    reads one file's text; the server passes one that remembers the answer.
    An unsaved buffer's relative ``INCLUDE`` resolves against *base_dir*.
    """
    index = ScriptIndex(path=path)
    found = facts(source, path, None if path else base_dir)
    _index_into(index, found, path, set(), read, facts, top=True, budget=[MAX_INCLUDED_TOTAL_BYTES])
    return index


def _index_into(
    index: ScriptIndex,
    found: FileFacts,
    path: str | None,
    seen: set[str],
    read: Callable[[Path], str | None],
    facts: Callable[[str, str | None, str | None], FileFacts],
    *,
    top: bool,
    budget: list[int],
) -> None:
    if path is not None:
        seen.add(_resolved(path))
    for step in found.steps:
        if isinstance(step, _Define):
            index.define(step.name, step.location)
        elif isinstance(step, _ScriptDef):
            index.scripts.setdefault(step.name, step.location)
            index.script_params[step.name] = list(step.params)
        elif isinstance(step, _ScriptCall):
            if top:
                index.script_calls.append((step.location, step.name))
        else:
            if top:
                index.includes.append((step.location, step.resolved))
            if "!" not in step.target and _resolved(step.resolved) not in seen and len(seen) < MAX_INCLUDED_FILES:
                included = read(Path(step.resolved))
                if included is not None and len(included) <= budget[0]:
                    budget[0] -= len(included)
                    included_facts = facts(included, step.resolved, None)
                    _index_into(index, included_facts, step.resolved, seen, read, facts, top=False, budget=budget)
    index.references.extend(found.references)


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


def _resolved(path: str) -> str:
    """*path* made absolute with links resolved, or just made absolute when the OS rejects it (too long, a NUL)."""
    try:
        return str(Path(path).resolve())
    except (OSError, ValueError):
        return os.path.abspath(path)


def is_file(path: str | Path) -> bool:
    """Whether *path* names a regular file; ``False`` for a name the OS rejects (too long, a NUL)."""
    try:
        return Path(path).is_file()
    except (OSError, ValueError):
        return False


def same_file_key(path: str) -> str:
    """*path* resolved and case-folded where the file system ignores case, for comparing files."""
    return os.path.normcase(_resolved(path))


def variable_at(index: ScriptIndex, line: int, character: int) -> Reference | None:
    """The variable reference under the cursor in the indexed file, if any."""
    for ref in index.references:
        loc = ref.location
        if loc.path == index.path and loc.line == line and loc.start <= character <= loc.end:
            return ref
    return None
