"""Navigation: go to definition, find references, the document outline and INCLUDE links."""

from __future__ import annotations

from pathlib import Path

from lsprotocol import types

from execsql.lsp.document import Location, ScriptIndex, file_uri, uri_for, variable_at
from execsql.script.ast import (
    BatchBlock,
    IfBlock,
    IncludeDirective,
    LoopBlock,
    MetaCommandStatement,
    Node,
    ScriptBlock,
    SqlBlock,
)
from execsql.script.parser import parse_string

__all__ = ["definition", "document_links", "document_symbols", "references"]


def _range(line: int, start: int, end: int) -> types.Range:
    return types.Range(start=types.Position(line=line, character=start), end=types.Position(line=line, character=end))


def _lsp_location(loc: Location, index: ScriptIndex, uri: str) -> types.Location:
    return types.Location(uri=uri_for(loc.path, index, uri), range=_range(loc.line, loc.start, loc.end))


def _at(entries: list[tuple[Location, str]], line: int, character: int) -> str | None:
    for loc, value in entries:
        if loc.line == line and loc.start <= character <= loc.end:
            return value
    return None


def definition(index: ScriptIndex, uri: str, line: int, character: int) -> list[types.Location]:
    """Where the variable, SCRIPT or included file under the cursor is defined."""
    ref = variable_at(index, line, character)
    if ref is not None:
        if ref.name.startswith("#"):
            name = ref.name[1:].lower()
            return [
                _lsp_location(index.scripts[script], index, uri)
                for script, params in index.script_params.items()
                if name in (p.lower() for p in params) and script in index.scripts
            ]
        return [_lsp_location(loc, index, uri) for loc in index.definitions.get(ref.key, [])]

    script = _at(index.script_calls, line, character)
    if script is not None and script in index.scripts:
        return [_lsp_location(index.scripts[script], index, uri)]

    target = _at(index.includes, line, character)
    if target is not None and Path(target).is_file():
        uri_of_file = file_uri(target, index)
        if uri_of_file:
            return [types.Location(uri=uri_of_file, range=_range(0, 0, 0))]
    return []


def references(
    index: ScriptIndex,
    uri: str,
    line: int,
    character: int,
    include_declaration: bool = True,
) -> list[types.Location]:
    """Every use of the variable under the cursor in this file and the files it includes (and its definitions)."""
    ref = variable_at(index, line, character)
    if ref is None:
        return []
    found = [_lsp_location(r.location, index, uri) for r in index.references if r.key == ref.key]
    if include_declaration and not ref.name.startswith(("$", "&", "@", "#")):
        found += [_lsp_location(loc, index, uri) for loc in index.definitions.get(ref.key, [])]
    return found


def document_links(index: ScriptIndex) -> list[types.DocumentLink]:
    """Each INCLUDE target that exists, as a link to the file."""
    links = []
    for loc, target in index.includes:
        path = Path(target)
        if path.is_file():
            uri = file_uri(target, index)
            if uri:
                links.append(types.DocumentLink(range=_range(loc.line, loc.start, loc.end), target=uri))
    return links


def _node_range(node: Node, lines: list[str]) -> types.Range:
    start = node.span.start_line - 1
    end = node.span.effective_end_line - 1
    end_text = lines[end] if 0 <= end < len(lines) else ""
    return types.Range(
        start=types.Position(line=start, character=0),
        end=types.Position(line=end, character=len(end_text)),
    )


def _symbol(
    name: str,
    kind: types.SymbolKind,
    node: Node,
    lines: list[str],
    children: list[types.DocumentSymbol],
) -> types.DocumentSymbol:
    rng = _node_range(node, lines)
    head = types.Range(
        start=rng.start,
        end=types.Position(
            line=rng.start.line,
            character=len(lines[rng.start.line]) if rng.start.line < len(lines) else 0,
        ),
    )
    return types.DocumentSymbol(name=name, kind=kind, range=rng, selection_range=head, children=children or None)


def _symbols(nodes: list[Node], lines: list[str], index: ScriptIndex) -> list[types.DocumentSymbol]:
    out: list[types.DocumentSymbol] = []
    for node in nodes:
        children = _symbols(list(node.children()), lines, index)
        if isinstance(node, ScriptBlock):
            params = ", ".join(p.name for p in node.param_defs or [])
            out.append(
                _symbol(
                    f"SCRIPT {node.name}({params})" if params else f"SCRIPT {node.name}",
                    types.SymbolKind.Function,
                    node,
                    lines,
                    children,
                ),
            )
        elif isinstance(node, IfBlock):
            out.append(_symbol(f"IF ({node.condition.strip()})", types.SymbolKind.Namespace, node, lines, children))
        elif isinstance(node, LoopBlock):
            out.append(
                _symbol(
                    f"LOOP {node.loop_type} ({node.condition.strip()})",
                    types.SymbolKind.Namespace,
                    node,
                    lines,
                    children,
                ),
            )
        elif isinstance(node, BatchBlock):
            out.append(_symbol("BATCH", types.SymbolKind.Namespace, node, lines, children))
        elif isinstance(node, SqlBlock):
            out.append(_symbol("SQL block", types.SymbolKind.Namespace, node, lines, children))
        elif isinstance(node, IncludeDirective) and not node.is_execute_script:
            out.append(_symbol(f"INCLUDE {node.target.strip()}", types.SymbolKind.File, node, lines, []))
        elif isinstance(node, MetaCommandStatement):
            row = node.span.start_line - 1
            for key, locations in index.definitions.items():
                for loc in locations:
                    if loc.path == index.path and loc.line == row:
                        out.append(_symbol(index.spellings[key], types.SymbolKind.Variable, node, lines, []))
        else:
            out.extend(children)
    return out


def document_symbols(index: ScriptIndex, source: str) -> list[types.DocumentSymbol]:
    """The outline: SCRIPT blocks, IF / LOOP / BATCH blocks, INCLUDE directives and variable definitions, nested."""
    tree = parse_string(source, index.path or "<untitled>", errors=[])
    return _symbols(tree.body, source.splitlines(), index)
