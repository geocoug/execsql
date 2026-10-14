"""The pygls server behind ``execsql lsp``."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path

from execsql import __version__
from execsql.lsp.cache import IndexCache
from execsql.lsp.code_actions import code_actions
from execsql.lsp.completion import completions
from execsql.lsp.diagnostics import diagnostics, failure_diagnostic, too_deep_diagnostic
from execsql.lsp.document import ScriptIndex, index_script, same_file_key
from execsql.lsp.folding import folding_ranges
from execsql.lsp.formatting import format_document
from execsql.lsp.hover import hover
from execsql.lsp.rename import RenameError, prepare_rename, rename
from execsql.lsp.navigation import definition, document_links, document_symbols, references

__all__ = ["ExecsqlLanguageServer", "create_server"]

_log = logging.getLogger(__name__)

# Pause after the last keystroke before linting, so a burst of typing lints once.
LINT_DELAY_SECONDS = 0.2

# Files whose change can alter an open script's findings or index: the config
# file (its [lint] and [format] sections) and any script it may INCLUDE.
WATCHED_FILES = ("**/execsql.conf", "**/*.sql")


class _DropLateCancels(logging.Filter):
    """Drops pygls's warning about a cancel for a request already answered.

    Editors cancel requests they no longer need (a hover after the cursor
    moves); the handlers answer in milliseconds, so the cancel usually
    arrives late.  That is normal, but the warning reaches the editor's
    output as an error.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Cancel notification for unknown message id")


@dataclass
class Settings:
    """What the configuration sets for one workspace folder: lint rule selection and format options."""

    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    format_options: dict[str, Any] = field(default_factory=dict)  # format_document keywords, from [format]
    config_files: tuple[str, ...] = ()  # the files read, lowest precedence first


class ExecsqlLanguageServer(LanguageServer):
    """Holds what the handlers share: each workspace folder's settings, pending lint tasks and the index cache."""

    def __init__(self) -> None:
        super().__init__("execsql", __version__)
        self.settings: dict[str, Settings] = {}  # by same_file_key of each workspace folder
        self.fallback = Settings()  # for a file in no workspace folder
        self.pending: dict[str, asyncio.Task[Any]] = {}
        self.cache = IndexCache()

    def load_settings(self) -> None:
        """Read ``[lint]`` and ``[format]`` for each workspace folder, as ``execsql lint`` / ``execsql format`` run there would.

        Each folder stands in for the working directory those commands read
        config from; the server's own working directory never changes.  A file
        in no folder gets the settings of :meth:`base_dir`.
        """
        self.fallback = self._read_settings(self.base_dir())
        _log_settings("files in no workspace folder", self.fallback)
        self.settings = {}
        for folder in self.workspace.folders.values():
            path = to_fs_path(folder.uri)
            if path and os.path.isdir(path):
                self.settings[same_file_key(path)] = settings = self._read_settings(path)
                _log_settings(path, settings)

    def base_dir(self) -> str | None:
        """The workspace root, if it still exists: an unsaved script's relative paths resolve there.

        ``None`` (no root) leaves them to the server's working directory.
        """
        root = self.workspace.root_path
        return root if root and os.path.isdir(root) else None

    def _read_settings(self, folder: str | None) -> Settings:
        """The settings ``execsql lint`` run from *folder* (the working directory if ``None``) reads.

        A config error is shown to the user and leaves every rule on.
        """
        from execsql.cli.lint import resolve_selectors
        from execsql.cli.run import _tool_config

        try:
            conf = _tool_config(None, start_dir=folder)
            return Settings(
                select=resolve_selectors([conf.lint_select]) if conf.lint_select else (),
                ignore=resolve_selectors([conf.lint_ignore]) if conf.lint_ignore else (),
                format_options={
                    "indent": conf.format_indent,
                    "use_sql": conf.format_sql,
                    "leading_comma": conf.format_leading_comma,
                    "rewrite_sql": conf.format_rewrite_sql,
                },
                config_files=tuple(conf.files_read),
            )
        except Exception as exc:  # a bad config must not take the server down
            _log.warning("execsql config for %s: %s", folder or "the working directory", exc)
            self.window_show_message(
                types.ShowMessageParams(type=types.MessageType.Warning, message=f"execsql config: {exc}"),
            )
            return Settings()

    def settings_for(self, uri: str) -> Settings:
        """The settings of the innermost workspace folder holding *uri*'s file, else :attr:`fallback`."""
        path = to_fs_path(uri)
        if path is None:
            return self.fallback
        key = same_file_key(path)
        holding = [f for f in self.settings if key == f or key.startswith(f.rstrip(os.sep) + os.sep)]
        return self.settings[max(holding, key=len)] if holding else self.fallback

    def index(self, uri: str) -> ScriptIndex:
        """The current document's index, rebuilt per request from :attr:`cache`d per-file facts.

        A script the parser cannot handle (nesting past Python's recursion
        limit) gets an empty index, so features fall back to what needs none.
        """
        document = self.workspace.get_text_document(uri)
        path = to_fs_path(uri)
        try:
            index = index_script(document.source, path, self.read_included, self.cache.facts, self.base_dir())
        except RecursionError:
            index = ScriptIndex(path=path)
        except Exception:  # the features that need an index answer with nothing; the cause goes to the log
            _log.exception("execsql lsp: could not index %s", uri)
            index = ScriptIndex(path=path)
        index.open_uris = self.open_uris()
        return index

    def open_uris(self) -> dict[str, str]:
        """The open documents' URIs as the client spelled them, by :func:`same_file_key` of their paths.

        A location in another open file is reported under this URI: one
        rebuilt from the path can differ (``file:///c:/``, ``file:///C:/`` on
        Windows), and a client may not match the two.
        """
        found: dict[str, str] = {}
        for uri in self.workspace.text_documents:
            fs_path = to_fs_path(uri)
            if fs_path is not None:
                found.setdefault(same_file_key(fs_path), uri)
        return found

    def read_included(self, path: Path) -> str | None:
        """An ``INCLUDE``d file's text: the editor's copy if it is open (saved or not), else the file's.

        Open documents are matched by path, not URI: clients spell the same
        file differently (``file:///c%3A/``, ``file:///C:/`` on Windows).
        """
        uri = self.open_uris().get(same_file_key(str(path)))
        if uri is not None:
            return self.workspace.get_text_document(uri).source
        return self.cache.text(path)

    def supports_snippets(self) -> bool:
        caps = self.client_capabilities.text_document
        item = caps.completion.completion_item if caps and caps.completion else None
        return bool(item and item.snippet_support)

    def publish(self, uri: str) -> None:
        """Lint the document's current text and publish the result."""
        document = self.workspace.get_text_document(uri)
        settings = self.settings_for(uri)
        try:
            found = diagnostics(document.source, to_fs_path(uri), settings.select, settings.ignore, self.base_dir())
        except RecursionError:
            found = [too_deep_diagnostic()]
        except Exception as exc:  # shown in the editor, not lost in an unawaited task
            _log.exception("execsql lsp: could not lint %s", uri)
            found = [failure_diagnostic(exc)]
        self.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, version=document.version, diagnostics=found),
        )

    def relint(self, changed: Iterable[str] | None = None) -> None:
        """Lint again, after :data:`LINT_DELAY_SECONDS`, each open document a change to the *changed* files can affect.

        Lint reads no included file's text; it checks only that each file a
        script ``INCLUDE``s exists.  So a document is affected by a change to
        itself or to a file it includes.  ``None`` means everything changed
        (the config, the workspace folders).  Going through the debounce, the
        editor's save and its file watcher's report of the same save lint once.
        """
        keys = None if changed is None else {same_file_key(path) for path in changed}
        for uri in list(self.workspace.text_documents):
            if keys is None or self._affected(uri, keys):
                self.publish_later(uri)

    def _affected(self, uri: str, keys: set[str]) -> bool:
        path = to_fs_path(uri)
        if path is None:
            return False
        if same_file_key(path) in keys:
            return True
        try:
            facts = self.cache.facts(self.workspace.get_text_document(uri).source, path)
        except Exception:  # when unsure, lint again
            return True
        return any(same_file_key(target) in keys for target in facts.includes)

    def watch_files(self) -> None:
        """Ask the client to report changes to :data:`WATCHED_FILES`, if it can."""
        caps = self.client_capabilities.workspace
        watched = caps.did_change_watched_files if caps else None
        if not (watched and watched.dynamic_registration):
            return
        self.client_register_capability(
            types.RegistrationParams(
                registrations=[
                    types.Registration(
                        id="execsql-watched-files",
                        method=types.WORKSPACE_DID_CHANGE_WATCHED_FILES,
                        register_options=types.DidChangeWatchedFilesRegistrationOptions(
                            watchers=[types.FileSystemWatcher(glob_pattern=g) for g in WATCHED_FILES],
                        ),
                    ),
                ],
            ),
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


def _log_settings(where: str, settings: Settings) -> None:
    _log.info(
        "settings for %s: config files %s; lint select %s, ignore %s; format %s",
        where,
        ", ".join(settings.config_files) or "none",
        ",".join(settings.select) or "all",
        ",".join(settings.ignore) or "none",
        settings.format_options or "defaults",
    )


def startup_record() -> str:
    """What a bug report needs first: which execsql, run by which Python, with which optional parts."""
    import sys
    from importlib.metadata import PackageNotFoundError, version
    from importlib.util import find_spec

    def installed(name: str) -> str:
        try:
            return version(name)
        except PackageNotFoundError:
            return "not installed"

    formatter = "available" if find_spec("sqlglot") is not None else "not installed (Format Document needs it)"
    return (
        f"execsql lsp {__version__}; Python {sys.version.split()[0]} at {sys.executable}; "
        f"pygls {installed('pygls')}; formatter {formatter}"
    )


def create_server() -> ExecsqlLanguageServer:
    """A server with every feature registered."""
    server = ExecsqlLanguageServer()
    rpc_logger = logging.getLogger("pygls.protocol.json_rpc")
    if not any(isinstance(f, _DropLateCancels) for f in rpc_logger.filters):
        rpc_logger.addFilter(_DropLateCancels())

    @server.feature(types.INITIALIZED)
    def initialized(ls: ExecsqlLanguageServer, params: types.InitializedParams) -> None:
        _log.info(startup_record())
        folders = [to_fs_path(f.uri) or f.uri for f in ls.workspace.folders.values()]
        _log.info("workspace folders: %s", ", ".join(folders) or "none")
        ls.load_settings()
        ls.watch_files()

    @server.feature(types.SHUTDOWN)
    def shutdown(ls: ExecsqlLanguageServer, params: None) -> None:
        # No diagnostics may follow the answer to shutdown.
        for task in ls.pending.values():
            task.cancel()
        ls.pending.clear()

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def did_open(ls: ExecsqlLanguageServer, params: types.DidOpenTextDocumentParams) -> None:
        ls.publish(params.text_document.uri)

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(ls: ExecsqlLanguageServer, params: types.DidChangeTextDocumentParams) -> None:
        ls.publish_later(params.text_document.uri)

    @server.feature(types.TEXT_DOCUMENT_DID_SAVE)
    def did_save(ls: ExecsqlLanguageServer, params: types.DidSaveTextDocumentParams) -> None:
        # Another open script may INCLUDE this one; a client that cannot watch files reports nothing else.
        path = to_fs_path(params.text_document.uri)
        ls.relint([path] if path else [])

    @server.feature(types.WORKSPACE_DID_CHANGE_WATCHED_FILES)
    def did_change_watched_files(ls: ExecsqlLanguageServer, params: types.DidChangeWatchedFilesParams) -> None:
        paths = [path for change in params.changes if (path := to_fs_path(change.uri))]
        for path in paths:
            ls.cache.forget(path)
        if any(Path(path).name.lower() == "execsql.conf" for path in paths):
            ls.load_settings()
            ls.relint()
        else:
            ls.relint(paths)

    @server.feature(types.WORKSPACE_DID_CHANGE_WORKSPACE_FOLDERS)
    def did_change_folders(ls: ExecsqlLanguageServer, params: types.DidChangeWorkspaceFoldersParams) -> None:
        # pygls has already updated ls.workspace.folders.
        ls.load_settings()
        ls.relint()

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
        try:
            return document_symbols(ls.index(uri), ls.workspace.get_text_document(uri).source)
        except RecursionError:  # nesting deeper than the outline can walk: no outline
            return []

    @server.feature(
        types.TEXT_DOCUMENT_CODE_ACTION,
        types.CodeActionOptions(code_action_kinds=[types.CodeActionKind.QuickFix]),
    )
    def on_code_action(ls: ExecsqlLanguageServer, params: types.CodeActionParams) -> list[types.CodeAction]:
        uri = params.text_document.uri
        source = ls.workspace.get_text_document(uri).source
        return code_actions(ls.index(uri), uri, source, params.context.diagnostics)

    @server.feature(types.TEXT_DOCUMENT_FORMATTING)
    def on_format(ls: ExecsqlLanguageServer, params: types.DocumentFormattingParams) -> list[types.TextEdit] | None:
        uri = params.text_document.uri
        source = ls.workspace.get_text_document(uri).source
        try:
            return format_document(source, **ls.settings_for(uri).format_options)
        except Exception as exc:  # e.g. the formatter extra missing: say so, change nothing
            ls.window_show_message(
                types.ShowMessageParams(type=types.MessageType.Error, message=f"execsql format: {exc}"),
            )
            return None

    @server.feature(types.TEXT_DOCUMENT_PREPARE_RENAME)
    def on_prepare_rename(ls: ExecsqlLanguageServer, params: types.PrepareRenameParams) -> types.Range | None:
        return prepare_rename(ls.index(params.text_document.uri), params.position.line, params.position.character)

    @server.feature(types.TEXT_DOCUMENT_RENAME, types.RenameOptions(prepare_provider=True))
    def on_rename(ls: ExecsqlLanguageServer, params: types.RenameParams) -> types.WorkspaceEdit | None:
        uri = params.text_document.uri
        try:
            return rename(ls.index(uri), uri, params.position.line, params.position.character, params.new_name)
        except RenameError as exc:
            ls.window_show_message(types.ShowMessageParams(type=types.MessageType.Warning, message=str(exc)))
            return None

    @server.feature(types.TEXT_DOCUMENT_FOLDING_RANGE)
    def on_folding(ls: ExecsqlLanguageServer, params: types.FoldingRangeParams) -> list[types.FoldingRange]:
        uri = params.text_document.uri
        try:
            return folding_ranges(ls.workspace.get_text_document(uri).source, to_fs_path(uri))
        except RecursionError:  # nesting deeper than the parser can walk: no folding
            return []

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_LINK)
    def on_links(ls: ExecsqlLanguageServer, params: types.DocumentLinkParams) -> list[types.DocumentLink]:
        return document_links(ls.index(params.text_document.uri))

    return server
