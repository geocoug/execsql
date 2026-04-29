"""execsql Language Server using pygls.

Provides diagnostics, hover, go-to-definition, completions, and document
symbols for ``.sql`` files containing execsql metacommands.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from execsql.lsp.analysis import AnalysisResult, analyze_document
from execsql.lsp.completions import get_completions
from execsql.lsp.hover import get_hover

__all__ = ["create_server"]

_log = logging.getLogger(__name__)

_EXEC_LINE_RX = re.compile(r"^\s*--\s*!x!\s*", re.I)

# Mapping from our severity strings to LSP severity
_SEVERITY_MAP = {
    "error": lsp.DiagnosticSeverity.Error,
    "warning": lsp.DiagnosticSeverity.Warning,
}


def create_server() -> LanguageServer:
    """Create and configure the execsql language server."""
    server = LanguageServer("execsql-lsp", "v1")

    # Document analysis cache
    _analysis_cache: dict[str, AnalysisResult] = {}

    # ------------------------------------------------------------------
    # Diagnostics (on open, change, save)
    # ------------------------------------------------------------------

    def _publish_diagnostics(uri: str, source: str) -> None:
        """Parse, lint, and publish diagnostics for a document."""
        result = analyze_document(uri, source)
        _analysis_cache[uri] = result

        diagnostics = []
        for severity, start_line, end_line, message in result.diagnostics:
            diagnostics.append(
                lsp.Diagnostic(
                    range=lsp.Range(
                        start=lsp.Position(line=max(0, start_line - 1), character=0),
                        end=lsp.Position(line=max(0, end_line - 1), character=999),
                    ),
                    message=message,
                    severity=_SEVERITY_MAP.get(severity, lsp.DiagnosticSeverity.Information),
                    source="execsql",
                ),
            )
        server.text_document_publish_diagnostics(
            lsp.PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics),
        )

    @server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
    def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
        doc = params.text_document
        _publish_diagnostics(doc.uri, doc.text)

    @server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
        uri = params.text_document.uri
        # Get the full document text (we use full sync)
        doc = server.workspace.get_text_document(uri)
        _publish_diagnostics(uri, doc.source)

    @server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
    def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
        uri = params.text_document.uri
        doc = server.workspace.get_text_document(uri)
        _publish_diagnostics(uri, doc.source)

    @server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
    def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
        uri = params.text_document.uri
        _analysis_cache.pop(uri, None)
        server.text_document_publish_diagnostics(
            lsp.PublishDiagnosticsParams(uri=uri, diagnostics=[]),
        )

    # ------------------------------------------------------------------
    # Hover
    # ------------------------------------------------------------------

    @server.feature(lsp.TEXT_DOCUMENT_HOVER)
    def hover(params: lsp.HoverParams) -> lsp.Hover | None:
        uri = params.text_document.uri
        doc = server.workspace.get_text_document(uri)
        pos = params.position

        lines = doc.source.splitlines()
        if pos.line >= len(lines):
            return None

        line_text = lines[pos.line]
        analysis = _analysis_cache.get(uri)

        content = get_hover(line_text, pos.character, analysis)
        if content:
            return lsp.Hover(
                contents=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=content,
                ),
            )
        return None

    # ------------------------------------------------------------------
    # Go-to-definition
    # ------------------------------------------------------------------

    @server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
    def definition(params: lsp.DefinitionParams) -> lsp.Location | list[lsp.Location] | None:
        uri = params.text_document.uri
        doc = server.workspace.get_text_document(uri)
        pos = params.position
        analysis = _analysis_cache.get(uri)

        lines = doc.source.splitlines()
        if pos.line >= len(lines):
            return None

        line_text = lines[pos.line]
        m = _EXEC_LINE_RX.match(line_text)
        if not m:
            return None

        cmd_text = line_text[m.end() :].strip()
        upper = cmd_text.upper()

        # EXECUTE SCRIPT / EXEC SCRIPT / RUN SCRIPT → jump to SCRIPT block
        exec_m = re.match(
            r"(?:EXEC(?:UTE)?|RUN)\s+SCRIPT(?:\s+IF\s+EXISTS)?\s+(\w+)",
            upper,
        )
        if exec_m and analysis:
            target = exec_m.group(1).lower()
            if target in analysis.script_blocks:
                span = analysis.script_blocks[target]
                return lsp.Location(
                    uri=uri,
                    range=lsp.Range(
                        start=lsp.Position(line=span.start_line - 1, character=0),
                        end=lsp.Position(line=span.effective_end_line - 1, character=999),
                    ),
                )

        # INCLUDE → jump to file
        inc_m = re.match(r"INCLUDE(?:\s+IF\s+EXISTS?)?\s+(.+)", upper)
        if inc_m:
            raw_path = cmd_text[inc_m.start(1) - len(upper) + len(cmd_text) :].strip().strip("\"'")
            # Resolve relative to the script directory
            if uri.startswith("file://"):
                from urllib.parse import unquote, urlparse

                script_dir = Path(unquote(urlparse(uri).path)).parent
                target_path = script_dir / raw_path
                if target_path.exists():
                    target_uri = target_path.as_uri()
                    return lsp.Location(
                        uri=target_uri,
                        range=lsp.Range(
                            start=lsp.Position(line=0, character=0),
                            end=lsp.Position(line=0, character=0),
                        ),
                    )

        return None

    # ------------------------------------------------------------------
    # Completions
    # ------------------------------------------------------------------

    @server.feature(
        lsp.TEXT_DOCUMENT_COMPLETION,
        lsp.CompletionOptions(trigger_characters=["!", " ", "("]),
    )
    def completions(params: lsp.CompletionParams) -> lsp.CompletionList | None:
        uri = params.text_document.uri
        doc = server.workspace.get_text_document(uri)
        pos = params.position

        lines = doc.source.splitlines()
        if pos.line >= len(lines):
            return None

        line_text = lines[pos.line]
        analysis = _analysis_cache.get(uri)

        items_data = get_completions(line_text, pos.character, analysis)
        if not items_data:
            return None

        _KIND_MAP = {
            "keyword": lsp.CompletionItemKind.Keyword,
            "function": lsp.CompletionItemKind.Function,
            "variable": lsp.CompletionItemKind.Variable,
        }

        items = []
        for item in items_data:
            doc = None
            if "documentation" in item:
                doc = lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=item["documentation"],
                )
            items.append(
                lsp.CompletionItem(
                    label=item["label"],
                    kind=_KIND_MAP.get(item.get("kind", ""), lsp.CompletionItemKind.Text),
                    detail=item.get("detail", ""),
                    insert_text=item.get("insert_text"),
                    documentation=doc,
                ),
            )

        return lsp.CompletionList(is_incomplete=False, items=items)

    # ------------------------------------------------------------------
    # Document symbols
    # ------------------------------------------------------------------

    @server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def document_symbols(params: lsp.DocumentSymbolParams) -> list[lsp.DocumentSymbol] | None:
        uri = params.text_document.uri
        analysis = _analysis_cache.get(uri)
        if not analysis or not analysis.symbols:
            return None

        _SYMBOL_KIND_MAP = {
            "script": lsp.SymbolKind.Function,
            "if": lsp.SymbolKind.Struct,
            "loop": lsp.SymbolKind.Struct,
            "batch": lsp.SymbolKind.Struct,
        }

        def _convert(sym) -> lsp.DocumentSymbol:
            kind = _SYMBOL_KIND_MAP.get(sym.kind, lsp.SymbolKind.Object)
            range_ = lsp.Range(
                start=lsp.Position(line=sym.span.start_line - 1, character=0),
                end=lsp.Position(line=sym.span.effective_end_line - 1, character=999),
            )
            children = [_convert(c) for c in sym.children] if sym.children else []
            return lsp.DocumentSymbol(
                name=sym.name,
                kind=kind,
                range=range_,
                selection_range=lsp.Range(
                    start=lsp.Position(line=sym.span.start_line - 1, character=0),
                    end=lsp.Position(line=sym.span.start_line - 1, character=len(sym.name)),
                ),
                children=children,
            )

        return [_convert(s) for s in analysis.symbols]

    return server
