"""What a script defines and refers to, with positions: the index the editor features read.

Built from the recovering parser (a script with an unclosed block still
indexes) and from the script's text for exact columns.  ``INCLUDE``d files
are read from disk and indexed too, so a variable set in a shared setup
script completes and resolves in the scripts that include it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from execsql.cli.lint import variables_defined_by
from execsql.script.ast import IncludeDirective, MetaCommandStatement, ScriptBlock
from execsql.script.parser import parse_string

__all__ = [
    "Location",
    "Reference",
    "ScriptIndex",
    "index_script",
    "variable_at",
]

# A substitution variable as written: !!name!!, !'!name!'!, !"!name!"! or the deferred !{name}!.
_RX_VARIABLE = re.compile(r"""!(['"]?)!(?P<name>[$&@~#+]?\w+)!\1!|!\{(?P<deferred>[$&@~#+]?\w+)\}!""")
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
    references: list[Reference] = field(default_factory=list)  # in this file only

    def define(self, name: str, location: Location) -> None:
        key = name.lstrip("~+").upper()
        self.definitions.setdefault(key, []).append(location)
        self.spellings.setdefault(key, name.lstrip("~+"))


def _span_of(word: str, line: str, start: int = 0) -> tuple[int, int]:
    """Columns of *word* in *line* at or after *start* (any case); the whole line if absent."""
    m = re.search(rf"(?<![\w$#@&~+]){re.escape(word)}(?!\w)", line[start:], re.I)
    if m is None:
        return 0, len(line)
    return start + m.start(), start + m.end()


def index_script(source: str, path: str | None, _seen: set[str] | None = None) -> ScriptIndex:
    """Index *source*, the text of the file at *path* (``None`` for an unsaved buffer)."""
    index = ScriptIndex(path=path)
    _index_into(index, source, path, _seen if _seen is not None else set(), top=True)
    return index


def _index_into(index: ScriptIndex, source: str, path: str | None, seen: set[str], *, top: bool) -> None:
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
        elif isinstance(node, IncludeDirective) and not node.is_execute_script:
            target = node.target.strip().strip("\"'")
            start, end = _span_of(target, text) if target else (0, len(text))
            resolved = Path(target) if Path(target).is_absolute() or script_dir is None else script_dir / target
            if top:
                index.includes.append((Location(path, row, start, end), str(resolved)))
            if "!" not in target and resolved.is_file() and str(resolved.resolve()) not in seen:
                try:
                    included = resolved.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                _index_into(index, included, str(resolved), seen, top=False)

    if top:
        for row, text in enumerate(lines):
            for m in _RX_VARIABLE.finditer(text):
                group = "deferred" if m.group("deferred") else "name"
                index.references.append(Reference(m.group(group), Location(path, row, m.start(group), m.end(group))))


def variable_at(index: ScriptIndex, line: int, character: int) -> Reference | None:
    """The variable reference under the cursor, if any."""
    for ref in index.references:
        loc = ref.location
        if loc.line == line and loc.start <= character <= loc.end:
            return ref
    return None
