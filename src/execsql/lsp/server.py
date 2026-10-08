"""The pygls server behind ``execsql lsp``."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path

from execsql import __version__
from execsql.lsp.completion import completions
from execsql.lsp.diagnostics import diagnostics
from execsql.lsp.document import ScriptIndex, index_script
from execsql.lsp.hover import hover
from execsql.lsp.navigation import definition, document_links, document_symbols, references

__all__ = ["ExecsqlLanguageServer", "create_server"]

# Pause after the last keystroke before linting, so a burst of typing lints once.
LINT_DELAY_SECONDS = 0.2


class ExecsqlLanguageServer(LanguageServer):
    """Holds what the handlers share: lint rule selection and pending lint tasks."""

    def __init__(self) -> None:
        super().__init__("execsql", __version__)
        self.select: tuple[str, ...] = ()
        self.ignore: tuple[str, ...] = ()
        self.pending: dict[str, asyncio.Task[Any]] = {}

    def load_settings(self, root: str | None) -> None:
        """Read ``[lint]`` select / ignore the way ``execsql lint`` run from *root* would.

        execsql reads config files from the working directory, so the server
        works from the workspace root.  A config error is shown to the user
        and leaves every rule on.
        """
        from execsql.cli.lint import resolve_selectors
        from execsql.cli.run import _tool_config

        if root and os.path.isdir(root):
            os.chdir(root)
        try:
            conf = _tool_config(None)
            self.select = resolve_selectors([conf.lint_select]) if conf.lint_select else ()
            self.ignore = resolve_selectors([conf.lint_ignore]) if conf.lint_ignore else ()
        except Exception as exc:  # a bad config must not take the server down
            self.window_show_message(
                types.ShowMessageParams(type=types.MessageType.Warning, message=f"execsql config: {exc}"),
            )

    def index(self, uri: str) -> ScriptIndex:
        """The current document's index (rebuilt per request: a few milliseconds)."""
        document = self.workspace.get_text_document(uri)
        return index_script(document.source, to_fs_path(uri))

    def supports_snippets(self) -> bool:
        caps = self.client_capabilities.text_document
        item = caps.completion.completion_item if caps and caps.completion else None
        return bool(item and item.snippet_support)

    def publish(self, uri: str) -> None:
        """Lint the document's current text and publish the result."""
        document = self.workspace.get_text_document(uri)
        found = diagnostics(document.source, to_fs_path(uri), self.select, self.ignore)
        self.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, version=document.version, diagnostics=found),
        )

    def publish_later(self, uri: str) -> None:
        """Lint after :data:`LINT_DELAY_SECONDS` without another change."""
        previous = self.pending.pop(uri, None)
        if previous is not None:
            previous.cancel()

        async def run() -> None:
            await asyncio.sleep(LINT_DELAY_SECONDS)
            self.pending.pop(uri, None)
            self.publish(uri)

        self.pending[uri] = asyncio.ensure_future(run())


def create_server() -> ExecsqlLanguageServer:
    """A server with every feature registered."""
    server = ExecsqlLanguageServer()

    @server.feature(types.INITIALIZED)
    def initialized(ls: ExecsqlLanguageServer, params: types.InitializedParams) -> None:
        ls.load_settings(ls.workspace.root_path)

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def did_open(ls: ExecsqlLanguageServer, params: types.DidOpenTextDocumentParams) -> None:
        ls.publish(params.text_document.uri)

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(ls: ExecsqlLanguageServer, params: types.DidChangeTextDocumentParams) -> None:
        ls.publish_later(params.text_document.uri)

    @server.feature(types.TEXT_DOCUMENT_DID_SAVE)
    def did_save(ls: ExecsqlLanguageServer, params: types.DidSaveTextDocumentParams) -> None:
        ls.publish(params.text_document.uri)

    @server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
    def did_close(ls: ExecsqlLanguageServer, params: types.DidCloseTextDocumentParams) -> None:
        uri = params.text_document.uri
        pending = ls.pending.pop(uri, None)
        if pending is not None:
            pending.cancel()
        ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(uri=uri, diagnostics=[]))

    @server.feature(
        types.TEXT_DOCUMENT_COMPLETION,
        types.CompletionOptions(trigger_characters=["!", "(", "{", "$", " "]),
    )
    def completion(ls: ExecsqlLanguageServer, params: types.CompletionParams) -> types.CompletionList:
        uri = params.text_document.uri
        source = ls.workspace.get_text_document(uri).source
        return completions(
            ls.index(uri),
            source,
            params.position.line,
            params.position.character,
            snippets=ls.supports_snippets(),
        )

    @server.feature(types.TEXT_DOCUMENT_HOVER)
    def on_hover(ls: ExecsqlLanguageServer, params: types.HoverParams) -> types.Hover | None:
        uri = params.text_document.uri
        source = ls.workspace.get_text_document(uri).source
        return hover(ls.index(uri), source, params.position.line, params.position.character)

    @server.feature(types.TEXT_DOCUMENT_DEFINITION)
    def on_definition(ls: ExecsqlLanguageServer, params: types.DefinitionParams) -> list[types.Location]:
        uri = params.text_document.uri
        return definition(ls.index(uri), uri, params.position.line, params.position.character)

    @server.feature(types.TEXT_DOCUMENT_REFERENCES)
    def on_references(ls: ExecsqlLanguageServer, params: types.ReferenceParams) -> list[types.Location]:
        uri = params.text_document.uri
        return references(
            ls.index(uri),
            uri,
            params.position.line,
            params.position.character,
            include_declaration=params.context.include_declaration,
        )

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def on_symbols(ls: ExecsqlLanguageServer, params: types.DocumentSymbolParams) -> list[types.DocumentSymbol]:
        uri = params.text_document.uri
        return document_symbols(ls.index(uri), ls.workspace.get_text_document(uri).source)

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_LINK)
    def on_links(ls: ExecsqlLanguageServer, params: types.DocumentLinkParams) -> list[types.DocumentLink]:
        return document_links(ls.index(params.text_document.uri))

    return server
