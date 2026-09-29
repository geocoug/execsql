"""Static inspection of a script: what it needs and what it touches.

Backs ``execsql inspect``. Nothing is executed and no database is opened.
Metacommands are matched against the dispatch table — the same regexes a run
uses — so a file path is read out of a metacommand exactly as a run would read
it. Variable definitions and references come from :mod:`execsql.cli.lint`, so
what ``inspect`` lists as needed from outside is what ``lint`` warns about as
undefined (V001).

The module is not named ``inspect`` so it never shadows the standard library.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from execsql.metacommands.effects import effects
from execsql.script.ast import IncludeDirective, MetaCommandStatement, Script

__all__ = ["Inspection", "Touch", "inspect_script"]


@dataclass(frozen=True)
class Touch:
    """One place a script reads, writes or deletes a file, includes a script, or connects."""

    line: int
    by: str
    target: str
    detail: str = ""


@dataclass
class Inspection:
    """Everything :func:`inspect_script` found in one script."""

    script: str
    arguments: list[str] = field(default_factory=list)
    environment: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)
    defined: list[str] = field(default_factory=list)
    script_blocks: list[str] = field(default_factory=list)
    includes: list[Touch] = field(default_factory=list)
    reads: list[Touch] = field(default_factory=list)
    writes: list[Touch] = field(default_factory=list)
    deletes: list[Touch] = field(default_factory=list)
    connections: list[Touch] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "script": self.script,
            "needs": {"arguments": self.arguments, "environment": self.environment, "variables": self.external},
            "defines": {"variables": self.defined, "scripts": self.script_blocks},
            "includes": [asdict(t) for t in self.includes],
            "reads": [asdict(t) for t in self.reads],
            "writes": [asdict(t) for t in self.writes],
            "deletes": [asdict(t) for t in self.deletes],
            "connections": [asdict(t) for t in self.connections],
        }


_RX_KEYWORD = re.compile(r"^\s*(\w+)")
_RX_ANY_VAR = re.compile(r"!!([$@&~#+]?\w+)!!|![{]\w+[}]!|!'!\w+!'!|!\"!\w+!\"!")


def _match(command: str):
    """``(MetaCommand, groups)`` for *command*, as a run would match it after substitution.

    A run substitutes variables before the dispatch regexes see the command,
    and a raw ``!!outdir!!`` fits few of them. Each reference is swapped for a
    plain word, the command matched, and the original text put back into the
    captured groups, so a path is reported as ``!!outdir!!/summary.xlsx``.
    """
    from execsql.metacommands import DISPATCH_TABLE

    originals: dict[str, str] = {}

    def placeholder(m: re.Match) -> str:
        key = f"execsqlvar{len(originals)}x"
        originals[key] = m.group(0)
        return key

    hit = DISPATCH_TABLE.get_match(_RX_ANY_VAR.sub(placeholder, command))
    if hit is None:
        return None
    mc, m = hit
    groups = {}
    for name, value in m.groupdict().items():
        if value:
            for key, original in originals.items():
                value = value.replace(key, original)
        groups[name] = value
    return mc, groups


def _keyword(command: str, description: str | None) -> str:
    """The metacommand's name for display: its registered description, else its first word."""
    if description:
        return description
    m = _RX_KEYWORD.match(command)
    return m.group(1).upper() if m else "?"


def inspect_script(script: Script, script_path: str | None) -> Inspection:
    """Everything *script* needs from outside and everything it touches, in line order."""
    from execsql.cli.lint import (
        _RX_VAR_REF,
        _collect_defined_vars_from_nodes,
        _collect_script_blocks,
        _get_builtin_vars,
        _referencing_text,
    )

    result = Inspection(script_path or script.source)
    script_dir = Path(script_path).resolve().parent if script_path else None
    blocks = _collect_script_blocks(script)
    result.script_blocks = sorted(blocks)

    defined: set[str] = set()
    _collect_defined_vars_from_nodes(script.body, blocks, script_dir, defined)
    result.defined = sorted(defined)

    # Needs from outside: the references lint's V001 would not call defined.
    builtins = _get_builtin_vars()
    arguments: set[str] = set()
    environment: set[str] = set()
    external: set[str] = set()
    for node in script.walk():
        for text in _referencing_text(node):
            for ref in _RX_VAR_REF.finditer(text):
                raw = ref.group(1)
                sigil = raw[0] if raw[0] in "$@&~#+" else ""
                name = raw[len(sigil) :]
                if sigil == "&":
                    environment.add(raw)
                elif sigil == "$" and re.fullmatch(r"ARG_\d+", name, re.I):
                    arguments.add(raw.upper())
                elif (
                    sigil in ("", "$")
                    and not re.fullmatch(r"COUNTER_\d+", name, re.I)
                    and name.upper() not in builtins
                    and name.upper() not in defined
                ):
                    external.add(raw)
    result.arguments = sorted(arguments, key=lambda a: int(a.split("_")[1]))
    result.environment = sorted(environment, key=str.upper)
    result.external = sorted(external, key=str.upper)

    for node in script.walk():
        line = node.span.start_line
        if isinstance(node, IncludeDirective):
            if node.is_execute_script:
                found = node.target.lower() in blocks
                detail = "defined in this file" if found else "not defined in this file"
                result.includes.append(Touch(line, "EXECUTE SCRIPT", node.target, detail))
            else:
                target = Path(node.target)
                if not target.is_absolute() and script_dir is not None:
                    target = script_dir / target
                detail = "" if target.exists() else "does not exist"
                if node.if_exists:
                    detail = "optional (IF EXISTS)" if not detail else "optional (IF EXISTS); does not exist"
                result.includes.append(Touch(line, "INCLUDE", node.target, detail))
            continue
        if not isinstance(node, MetaCommandStatement):
            continue
        hit = _match(node.command)
        if hit is None:
            continue
        mc, groups = hit
        by = _keyword(node.command, mc.description)
        for effect in effects(mc.exec_fn.__name__, groups):
            if effect.role in ("connect", "use"):
                result.connections.append(Touch(line, effect.role.upper(), effect.target, effect.detail))
            else:
                touch = Touch(line, by, effect.target)
                {"read": result.reads, "write": result.writes, "delete": result.deletes}[effect.role].append(touch)
    return result
