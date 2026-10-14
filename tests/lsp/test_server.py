"""The language server over the real protocol: ``execsql lsp`` in a subprocess."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pygls")
pytest_lsp = pytest.importorskip("pytest_lsp")

from lsprotocol import types  # noqa: E402
from pygls.protocol import default_converter  # noqa: E402
from pytest_lsp import ClientServerConfig, LanguageClient  # noqa: E402
from pytest_lsp.client import DEFAULT_CLIENT_FEATURES, register_lsp_features  # noqa: E402

BAD = "-- !x! EXPROT orders TO out.csv AS CSV\n"
GOOD = "-- !x! EXPORT orders TO out.csv AS CSV\n"


def _recording_client() -> LanguageClient:
    """pytest-lsp's test client, also keeping every published URI in ``client.published``, in order.

    ``wait_for_notification`` only sees a notification that arrives after it
    is called, so a test expecting several (one per open script) can miss
    one that arrives with another and wait forever.
    """

    def on_publish(client: LanguageClient, params: types.PublishDiagnosticsParams) -> None:
        client.diagnostics[params.uri] = params.diagnostics
        client.published.append(params.uri)

    client = LanguageClient(converter_factory=default_converter)
    client.published = []
    register_lsp_features(client, {**DEFAULT_CLIENT_FEATURES, types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS: on_publish})
    return client


SERVER = ClientServerConfig(
    server_command=[sys.executable, "-m", "execsql", "lsp", "--stdio"],
    client_factory=_recording_client,
)


@pytest_lsp.fixture(config=SERVER)
async def client(lsp_client: LanguageClient, tmp_path_factory):
    root = tmp_path_factory.mktemp("workspace")
    await lsp_client.initialize_session(
        types.InitializeParams(capabilities=types.ClientCapabilities(), root_uri=root.as_uri()),
    )
    lsp_client.root = root
    yield
    await lsp_client.shutdown_session()


async def _published(client: LanguageClient, since: int, *uris: str) -> None:
    """Wait until each of *uris* has been published after ``client.published[since]``."""
    for _ in range(200):
        if set(uris) <= set(client.published[since:]):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"not published: {set(uris) - set(client.published[since:])}")


def _open(client: LanguageClient, name: str, text: str) -> str:
    uri = (client.root / name).as_uri()
    client.text_document_did_open(
        types.DidOpenTextDocumentParams(
            text_document=types.TextDocumentItem(uri=uri, language_id="sql", version=1, text=text),
        ),
    )
    return uri


def _change(client: LanguageClient, uri: str, version: int, text: str) -> None:
    client.text_document_did_change(
        types.DidChangeTextDocumentParams(
            text_document=types.VersionedTextDocumentIdentifier(uri=uri, version=version),
            content_changes=[types.TextDocumentContentChangeWholeDocument(text=text)],
        ),
    )


@pytest.mark.asyncio
async def test_opening_a_script_publishes_its_findings(client: LanguageClient):
    uri = _open(client, "a.sql", BAD)
    await client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    assert [d.code for d in client.diagnostics[uri]] == ["P003"]


@pytest.mark.asyncio
async def test_an_edit_updates_the_findings(client: LanguageClient):
    uri = _open(client, "b.sql", BAD)
    await client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    _change(client, uri, 2, GOOD)
    await client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    assert not client.diagnostics[uri]


@pytest.mark.asyncio
async def test_closing_a_script_clears_its_findings(client: LanguageClient):
    uri = _open(client, "c.sql", BAD)
    await client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    client.text_document_did_close(
        types.DidCloseTextDocumentParams(text_document=types.TextDocumentIdentifier(uri=uri)),
    )
    await client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    assert not client.diagnostics[uri]


@pytest_lsp.fixture(config=SERVER)
async def configured_client(lsp_client: LanguageClient, tmp_path_factory):
    root = tmp_path_factory.mktemp("configured")
    (root / "execsql.conf").write_text("[lint]\nignore = P003\n\n[format]\nindent = 2\n")
    await lsp_client.initialize_session(
        types.InitializeParams(capabilities=types.ClientCapabilities(), root_uri=root.as_uri()),
    )
    lsp_client.root = root
    yield
    await lsp_client.shutdown_session()


@pytest.mark.asyncio
async def test_lint_settings_come_from_the_workspace_config(configured_client: LanguageClient):
    """The [lint] section of execsql.conf in the workspace root applies, as for `execsql lint` run there."""
    uri = _open(configured_client, "d.sql", BAD + "-- !x! IF(hasrowz(t))\n-- !x! ENDIF\n")
    await configured_client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    assert [d.code for d in configured_client.diagnostics[uri]] == ["P004"]


@pytest.mark.asyncio
async def test_completion_after_the_metacommand_marker(client: LanguageClient):
    uri = _open(client, "e.sql", "-- !x! SUB report_dir /tmp\n-- !x! exp\n")
    result = await client.text_document_completion_async(
        types.CompletionParams(
            text_document=types.TextDocumentIdentifier(uri=uri),
            position=types.Position(line=1, character=10),
        ),
    )
    labels = {item.label for item in result.items}
    assert {"EXPORT", "EXPORT QUERY"} <= labels


@pytest.mark.asyncio
async def test_hover_over_a_metacommand(client: LanguageClient):
    uri = _open(client, "f.sql", "-- !x! EXPORT t TO x.csv AS CSV\n")
    result = await client.text_document_hover_async(
        types.HoverParams(
            text_document=types.TextDocumentIdentifier(uri=uri),
            position=types.Position(line=0, character=9),
        ),
    )
    assert result.contents.value.startswith("**EXPORT**")


@pytest.mark.asyncio
async def test_go_to_definition_and_the_outline(client: LanguageClient):
    uri = _open(client, "g.sql", '-- !x! SUB out /tmp\n-- !x! WRITE "!!out!!"\n')
    found = await client.text_document_definition_async(
        types.DefinitionParams(
            text_document=types.TextDocumentIdentifier(uri=uri),
            position=types.Position(line=1, character=16),
        ),
    )
    assert [(d.uri, d.range.start.line) for d in found] == [(uri, 0)]
    symbols = await client.text_document_document_symbol_async(
        types.DocumentSymbolParams(text_document=types.TextDocumentIdentifier(uri=uri)),
    )
    assert [s.name for s in symbols] == ["out"]


@pytest.mark.asyncio
async def test_a_quick_fix_for_a_finding(client: LanguageClient):
    uri = _open(client, "h.sql", BAD)
    await client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    found = client.diagnostics[uri]
    actions = await client.text_document_code_action_async(
        types.CodeActionParams(
            text_document=types.TextDocumentIdentifier(uri=uri),
            range=found[0].range,
            context=types.CodeActionContext(diagnostics=list(found)),
        ),
    )
    assert [a.title for a in actions] == ["Change EXPROT to EXPORT"]


@pytest.mark.asyncio
async def test_format_document_uses_the_workspace_format_settings(configured_client: LanguageClient):
    uri = _open(configured_client, "i.sql", '-- !x! if(hasrows(t))\n-- !x! write "x"\n-- !x! endif\n')
    edits = await configured_client.text_document_formatting_async(
        types.DocumentFormattingParams(
            text_document=types.TextDocumentIdentifier(uri=uri),
            options=types.FormattingOptions(tab_size=8, insert_spaces=True),
        ),
    )
    assert edits[0].new_text == '-- !x! IF (hasrows(t))\n  -- !x! WRITE "x"\n-- !x! ENDIF\n'


def test_the_late_cancel_filter_matches_the_message_pygls_logs():
    """_DropLateCancels matches pygls's text; a pygls that rewords it must fail here, not flood editors."""
    import inspect

    from pygls.protocol import json_rpc

    assert "'Cancel notification for unknown message id \"%s\"'" in inspect.getsource(json_rpc)


def test_a_late_cancel_is_not_reported(caplog):
    from execsql.lsp.server import _DropLateCancels, create_server

    create_server()
    create_server()  # a second server adds no second filter
    rpc = logging.getLogger("pygls.protocol.json_rpc")
    assert sum(isinstance(f, _DropLateCancels) for f in rpc.filters) == 1
    with caplog.at_level(logging.WARNING):
        rpc.warning('Cancel notification for unknown message id "%s"', 29)
        rpc.warning("something else")
    assert [r.getMessage() for r in caplog.records] == ["something else"]


@pytest.mark.asyncio
async def test_a_script_nested_too_deeply_gets_one_finding_and_the_server_keeps_answering(client: LanguageClient):
    uri = _open(client, "deep.sql", "-- !x! IF(True)\n" * 3000)
    await client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    assert [d.message for d in client.diagnostics[uri]] == [
        "The script nests blocks or conditions too deeply to check.",
    ]
    symbols = await client.text_document_document_symbol_async(
        types.DocumentSymbolParams(text_document=types.TextDocumentIdentifier(uri=uri)),
    )
    assert symbols == []


@pytest.mark.asyncio
async def test_a_changed_config_file_is_read_again(client: LanguageClient):
    uri = _open(client, "conf.sql", BAD)
    await _published(client, 0, uri)
    assert [d.code for d in client.diagnostics[uri]] == ["P003"]
    conf = client.root / "execsql.conf"
    conf.write_text("[lint]\nignore = P003\n", encoding="utf-8")
    since = len(client.published)
    client.workspace_did_change_watched_files(
        types.DidChangeWatchedFilesParams(
            changes=[types.FileEvent(uri=conf.as_uri(), type=types.FileChangeType.Created)],
        ),
    )
    await _published(client, since, uri)
    assert not client.diagnostics[uri]


@pytest.mark.asyncio
async def test_saving_a_script_lints_the_scripts_that_include_it_again(client: LanguageClient):
    setup = client.root / "setup.sql"
    setup.write_text("SELECT 1;\n", encoding="utf-8")
    main = _open(client, "main.sql", "-- !x! INCLUDE setup.sql\nSELECT '!!region!!';\n")
    setup_uri = _open(client, "setup.sql", "SELECT 1;\n")
    await _published(client, 0, main, setup_uri)
    since = len(client.published)
    client.text_document_did_save(
        types.DidSaveTextDocumentParams(text_document=types.TextDocumentIdentifier(uri=setup_uri)),
    )
    await _published(client, since, main, setup_uri)


def _watched(client: LanguageClient, *paths) -> None:
    client.workspace_did_change_watched_files(
        types.DidChangeWatchedFilesParams(
            changes=[types.FileEvent(uri=p.as_uri(), type=types.FileChangeType.Changed) for p in paths],
        ),
    )


@pytest.mark.asyncio
async def test_one_save_lints_each_affected_script_once(client: LanguageClient):
    """The editor reports a save twice (didSave, then its file watcher); a script that does not include the file is left alone."""
    (client.root / "a.sql").write_text("SELECT 1;\n", encoding="utf-8")
    a = _open(client, "a.sql", "SELECT 1;\n")
    includer = _open(client, "includer.sql", "-- !x! INCLUDE a.sql\n")
    other = _open(client, "other.sql", "SELECT 2;\n")
    await _published(client, 0, a, includer, other)
    since = len(client.published)
    client.text_document_did_save(types.DidSaveTextDocumentParams(text_document=types.TextDocumentIdentifier(uri=a)))
    _watched(client, client.root / "a.sql")
    await asyncio.sleep(0.6)
    later = client.published[since:]
    assert (later.count(a), later.count(includer), later.count(other)) == (1, 1, 0)


@pytest.mark.asyncio
async def test_a_change_to_a_script_no_open_script_includes_lints_nothing(client: LanguageClient):
    a = _open(client, "a.sql", "-- !x! INCLUDE setup.sql\n")
    await _published(client, 0, a)
    since = len(client.published)
    (client.root / "unrelated.sql").write_text("SELECT 1;\n", encoding="utf-8")
    _watched(client, client.root / "unrelated.sql")
    await asyncio.sleep(0.6)
    assert client.published[since:] == []


@pytest.mark.asyncio
async def test_creating_an_included_file_clears_its_missing_include_finding(client: LanguageClient):
    a = _open(client, "a.sql", "-- !x! INCLUDE setup.sql\n")
    await _published(client, 0, a)
    assert [d.code for d in client.diagnostics[a]] == ["I001"]
    since = len(client.published)
    (client.root / "setup.sql").write_text("SELECT 1;\n", encoding="utf-8")
    _watched(client, client.root / "setup.sql")
    await _published(client, since, a)
    assert not client.diagnostics[a]


@pytest.mark.asyncio
async def test_an_included_file_open_in_the_editor_is_read_unsaved(client: LanguageClient):
    (client.root / "vars.sql").write_text("SELECT 1;\n", encoding="utf-8")  # the saved copy defines nothing
    vars_uri = _open(client, "vars.sql", "-- !x! SUB region north\n")
    main = _open(client, "uses.sql", "-- !x! INCLUDE vars.sql\nSELECT '!!region!!';\n")
    found = await client.text_document_definition_async(
        types.DefinitionParams(
            text_document=types.TextDocumentIdentifier(uri=main),
            position=types.Position(line=1, character=11),
        ),
    )
    assert [loc.uri for loc in found] == [vars_uri]


@pytest_lsp.fixture(config=SERVER)
async def watching_client(lsp_client: LanguageClient, tmp_path_factory):
    lsp_client.registrations = []

    @lsp_client.feature(types.CLIENT_REGISTER_CAPABILITY)
    def on_register(params: types.RegistrationParams) -> None:
        lsp_client.registrations.extend(params.registrations)

    root = tmp_path_factory.mktemp("workspace")
    capabilities = types.ClientCapabilities(
        workspace=types.WorkspaceClientCapabilities(
            did_change_watched_files=types.DidChangeWatchedFilesClientCapabilities(dynamic_registration=True),
        ),
    )
    await lsp_client.initialize_session(types.InitializeParams(capabilities=capabilities, root_uri=root.as_uri()))
    yield
    await lsp_client.shutdown_session()


@pytest.mark.asyncio
async def test_the_server_asks_to_watch_config_and_script_files(watching_client: LanguageClient):
    for _ in range(50):
        if watching_client.registrations:
            break
        await asyncio.sleep(0.05)
    [registration] = watching_client.registrations
    assert registration.method == types.WORKSPACE_DID_CHANGE_WATCHED_FILES
    assert [w["globPattern"] for w in registration.register_options["watchers"]] == ["**/execsql.conf", "**/*.sql"]


@pytest.mark.asyncio
async def test_rename_over_the_protocol(client: LanguageClient):
    uri = _open(client, "ren.sql", "-- !x! SUB region north\nSELECT '!!region!!';\n")
    doc = types.TextDocumentIdentifier(uri=uri)
    found = await client.text_document_prepare_rename_async(
        types.PrepareRenameParams(text_document=doc, position=types.Position(line=1, character=11)),
    )
    assert found == types.Range(start=types.Position(line=1, character=10), end=types.Position(line=1, character=16))
    edit = await client.text_document_rename_async(
        types.RenameParams(text_document=doc, position=types.Position(line=1, character=11), new_name="area"),
    )
    assert [e.new_text for e in edit.changes[uri]] == ["area", "area"]
    refused = await client.text_document_rename_async(
        types.RenameParams(text_document=doc, position=types.Position(line=1, character=11), new_name="a b"),
    )
    assert refused is None
    assert any("not a variable name" in m.message for m in client.messages)  # sent before the response


@pytest.mark.asyncio
async def test_an_included_file_open_under_another_path_is_still_read_unsaved(client: LanguageClient):
    linked = client.root / "linked"
    try:
        linked.symlink_to(client.root, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create a symlink here")
    (client.root / "shared.sql").write_text("SELECT 1;\n", encoding="utf-8")
    shared = linked / "shared.sql"  # the editor opened it through the link
    client.text_document_did_open(
        types.DidOpenTextDocumentParams(
            text_document=types.TextDocumentItem(
                uri=shared.as_uri(),
                language_id="sql",
                version=1,
                text="-- !x! SUB region north\n",
            ),
        ),
    )
    main = _open(client, "uses2.sql", "-- !x! INCLUDE shared.sql\nSELECT '!!region!!';\n")
    found = await client.text_document_definition_async(
        types.DefinitionParams(
            text_document=types.TextDocumentIdentifier(uri=main),
            position=types.Position(line=1, character=11),
        ),
    )
    assert [loc.range.start.line for loc in found] == [0]


@pytest_lsp.fixture(config=SERVER)
async def two_folder_client(lsp_client: LanguageClient, tmp_path_factory):
    """A multi-root workspace: folder ``a`` ignores P003 and indents by 2, folder ``b`` has no config."""
    a = tmp_path_factory.mktemp("a")
    b = tmp_path_factory.mktemp("b")
    (a / "execsql.conf").write_text("[lint]\nignore = P003\n\n[format]\nindent = 2\n")
    await lsp_client.initialize_session(
        types.InitializeParams(
            capabilities=types.ClientCapabilities(),
            root_uri=a.as_uri(),
            workspace_folders=[
                types.WorkspaceFolder(uri=a.as_uri(), name="a"),
                types.WorkspaceFolder(uri=b.as_uri(), name="b"),
            ],
        ),
    )
    lsp_client.folders = a, b
    yield
    await lsp_client.shutdown_session()


def _open_at(client: LanguageClient, path, text: str) -> str:
    client.text_document_did_open(
        types.DidOpenTextDocumentParams(
            text_document=types.TextDocumentItem(uri=path.as_uri(), language_id="sql", version=1, text=text),
        ),
    )
    return path.as_uri()


@pytest.mark.asyncio
async def test_each_workspace_folder_lints_with_its_own_config(two_folder_client: LanguageClient):
    a, b = two_folder_client.folders
    in_a = _open_at(two_folder_client, a / "x.sql", BAD)
    in_b = _open_at(two_folder_client, b / "x.sql", BAD)
    await _published(two_folder_client, 0, in_a, in_b)
    assert not two_folder_client.diagnostics[in_a]
    assert [d.code for d in two_folder_client.diagnostics[in_b]] == ["P003"]


@pytest.mark.asyncio
async def test_each_workspace_folder_formats_with_its_own_config(two_folder_client: LanguageClient):
    a, b = two_folder_client.folders
    text = '-- !x! if(hasrows(t))\n-- !x! write "x"\n-- !x! endif\n'
    found = []
    for uri in (_open_at(two_folder_client, a / "f.sql", text), _open_at(two_folder_client, b / "f.sql", text)):
        edits = await two_folder_client.text_document_formatting_async(
            types.DocumentFormattingParams(
                text_document=types.TextDocumentIdentifier(uri=uri),
                options=types.FormattingOptions(tab_size=8, insert_spaces=True),
            ),
        )
        found.append(edits[0].new_text.splitlines()[1])
    assert found == ['  -- !x! WRITE "x"', '    -- !x! WRITE "x"']


@pytest.mark.asyncio
async def test_an_added_workspace_folder_brings_its_config(two_folder_client: LanguageClient, tmp_path_factory):
    c = tmp_path_factory.mktemp("c")  # no execsql.conf: every rule on
    uri = _open_at(two_folder_client, c / "x.sql", BAD)
    await _published(two_folder_client, 0, uri)
    assert not two_folder_client.diagnostics[uri]  # in no folder: the root's (folder a's) settings
    since = len(two_folder_client.published)
    two_folder_client.workspace_did_change_workspace_folders(
        types.DidChangeWorkspaceFoldersParams(
            event=types.WorkspaceFoldersChangeEvent(
                added=[types.WorkspaceFolder(uri=c.as_uri(), name="c")],
                removed=[],
            ),
        ),
    )
    await _published(two_folder_client, since, uri)
    assert [d.code for d in two_folder_client.diagnostics[uri]] == ["P003"]


def _offline_server(monkeypatch, source: str = "SELECT 1;\n"):
    """A server with no client: a one-document workspace, publishes recorded in a list."""
    from types import SimpleNamespace

    import execsql.lsp.server as server_module

    server = server_module.create_server()
    published: list[types.PublishDiagnosticsParams] = []
    monkeypatch.setattr(server, "text_document_publish_diagnostics", published.append)
    document = SimpleNamespace(source=source, version=3)
    workspace = SimpleNamespace(get_text_document=lambda uri: document, text_documents={}, root_path=None)
    monkeypatch.setattr(type(server), "workspace", property(lambda self: workspace))
    return server, published


def _broken_lint(monkeypatch):
    import execsql.lsp.server as server_module

    def broken(*_args, **_kwargs):
        raise OSError("disk on fire")

    monkeypatch.setattr(server_module, "diagnostics", broken)


def test_a_lint_failure_is_shown_as_one_diagnostic(monkeypatch):
    """An unexpected error while checking a script is reported in the editor, not lost in a log."""
    server, published = _offline_server(monkeypatch)
    _broken_lint(monkeypatch)
    server.publish("file:///tmp/x.sql")
    [params] = published
    assert len(params.diagnostics) == 1
    assert "could not check this script" in params.diagnostics[0].message
    assert "disk on fire" in params.diagnostics[0].message


@pytest.mark.asyncio
async def test_a_lint_failure_while_typing_replaces_the_findings_and_is_logged(monkeypatch, caplog):
    """The debounced lint runs in a task nobody awaits: its failure must still reach the editor and the log."""
    server, published = _offline_server(monkeypatch)
    _broken_lint(monkeypatch)
    with caplog.at_level(logging.ERROR, logger="execsql.lsp.server"):
        server.publish_later("file:///tmp/x.sql")
        await asyncio.sleep(0.4)
    [params] = published
    assert "could not check this script" in params.diagnostics[0].message
    assert any("could not lint" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_shutdown_cancels_a_pending_lint(monkeypatch):
    """No diagnostics follow the answer to shutdown."""
    server, published = _offline_server(monkeypatch)
    server.publish_later("file:///tmp/x.sql")
    for handler, args, kwargs in server.protocol.lsp_shutdown(None):  # pygls's shutdown, calling ours
        handler(*args, **(kwargs or {}))
    await asyncio.sleep(0.4)
    assert published == []
    assert server.pending == {}


def _workspace_server(monkeypatch, root, *folders):
    """A server with no client over a real pygls workspace rooted at *root*."""
    from pygls.workspace import Workspace

    import execsql.lsp.server as server_module

    server = server_module.create_server()
    workspace = Workspace(
        root.as_uri(),
        workspace_folders=[types.WorkspaceFolder(uri=f.as_uri(), name=f.name) for f in folders],
    )
    monkeypatch.setattr(type(server), "workspace", property(lambda self: workspace))
    monkeypatch.setattr(server, "window_show_message", lambda params: None)
    return server, workspace


def _folder_with_ignore(parent, name: str, ignore: str):
    folder = parent / name
    folder.mkdir()
    (folder / "execsql.conf").write_text(f"[lint]\nignore = {ignore}\n", encoding="utf-8")
    return folder


def test_settings_are_read_without_changing_the_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    a = _folder_with_ignore(tmp_path, "a", "V")
    server, _ = _workspace_server(monkeypatch, a, a)
    server.load_settings()
    assert os.getcwd() == str(tmp_path)
    assert server.settings_for((a / "x.sql").as_uri()).ignore == ("V",)


def test_two_folders_settings_read_at_once_stay_apart(monkeypatch, tmp_path):
    """Settings reads share no process state, so threads cannot mix one folder's config into another's."""
    from concurrent.futures import ThreadPoolExecutor

    a = _folder_with_ignore(tmp_path, "a", "V")
    b = _folder_with_ignore(tmp_path, "b", "P")
    server, _ = _workspace_server(monkeypatch, a, a, b)
    with ThreadPoolExecutor(8) as pool:
        found = list(pool.map(lambda folder: server._read_settings(str(folder)).ignore, [a, b] * 20))
    assert found == [("V",), ("P",)] * 20


def test_a_folder_added_after_the_root_is_deleted_brings_its_config(monkeypatch, tmp_path):
    import shutil

    monkeypatch.chdir(tmp_path)
    root = _folder_with_ignore(tmp_path, "root", "V")
    server, workspace = _workspace_server(monkeypatch, root, root)
    server.load_settings()
    workspace.remove_folder(root.as_uri())
    shutil.rmtree(root)
    added = _folder_with_ignore(tmp_path, "added", "P")
    workspace.add_folder(types.WorkspaceFolder(uri=added.as_uri(), name="added"))
    server.load_settings()
    assert server.settings_for((added / "x.sql").as_uri()).ignore == ("P",)


def test_an_unsaved_scripts_include_resolves_against_the_workspace_root(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import execsql.lsp.server as server_module

    root = tmp_path / "root"
    root.mkdir()
    (root / "setup.sql").write_text("-- !x! SUB region north\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    server = server_module.create_server()
    published: list[types.PublishDiagnosticsParams] = []
    monkeypatch.setattr(server, "text_document_publish_diagnostics", published.append)
    document = SimpleNamespace(source="-- !x! INCLUDE setup.sql\nSELECT '!!region!!';\n", version=1)
    workspace = SimpleNamespace(get_text_document=lambda uri: document, text_documents={}, root_path=str(root))
    monkeypatch.setattr(type(server), "workspace", property(lambda self: workspace))
    assert "REGION" in server.index("untitled:Untitled-1").definitions
    server.publish("untitled:Untitled-1")
    assert [d.code for d in published[0].diagnostics if d.code == "I001"] == []


_LOG_FILE = Path(tempfile.gettempdir()) / f"execsql-lsp-test-{os.getpid()}.log"
LOGGING_SERVER = ClientServerConfig(
    server_command=[sys.executable, "-m", "execsql", "lsp", "--stdio", "--log-file", str(_LOG_FILE)],
    client_factory=_recording_client,
    server_env={**os.environ, "EXECSQL_LSP_LOG_LEVEL": "info"},
)


@pytest_lsp.fixture(config=LOGGING_SERVER)
async def logging_client(lsp_client: LanguageClient, tmp_path_factory):
    _LOG_FILE.unlink(missing_ok=True)
    root = tmp_path_factory.mktemp("workspace")
    (root / "execsql.conf").write_text("[lint]\nignore = V\n", encoding="utf-8")
    await lsp_client.initialize_session(
        types.InitializeParams(
            capabilities=types.ClientCapabilities(),
            root_uri=root.as_uri(),
            workspace_folders=[types.WorkspaceFolder(uri=root.as_uri(), name="root")],
        ),
    )
    lsp_client.root = root
    yield
    await lsp_client.shutdown_session()
    _LOG_FILE.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_the_server_logs_what_a_bug_report_needs_at_info(logging_client: LanguageClient):
    """Version, interpreter, formatter, folders and each folder's config files, at EXECSQL_LSP_LOG_LEVEL=info."""
    from execsql import __version__

    # Paths compared as the OS does: Windows reports c:\ where pytest has C:\.
    root = os.path.normcase(str(logging_client.root))
    for _ in range(100):
        text = _LOG_FILE.read_text(encoding="utf-8") if _LOG_FILE.exists() else ""
        if "settings for" in text and root in os.path.normcase(text):
            break
        await asyncio.sleep(0.05)
    assert f"execsql lsp {__version__}" in text
    assert os.path.normcase(sys.executable) in os.path.normcase(text)
    assert "formatter" in text
    assert f"workspace folders: {root}" in os.path.normcase(text)
    assert os.path.normcase(str(logging_client.root / "execsql.conf")) in os.path.normcase(text)


@pytest.mark.parametrize(
    ("level", "execsql_level", "pygls_level"),
    [("warning", logging.WARNING, logging.WARNING), ("info", logging.INFO, logging.WARNING), ("debug", 10, 10)],
)
def test_pygls_logs_the_messages_it_sends_only_at_debug(monkeypatch, level, execsql_level, pygls_level):
    """pygls logs each message it sends, script text included, at info."""
    import execsql.cli.commands.lsp as lsp_module

    root, pygls = logging.getLogger(), logging.getLogger("pygls")
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(root, "level", root.level)
    monkeypatch.setattr(pygls, "level", pygls.level)
    lsp_module._configure_logging(lsp_module.LogLevel(level), None)
    assert len(root.handlers) == 1
    assert logging.getLogger("execsql.lsp.server").getEffectiveLevel() == execsql_level
    assert logging.getLogger("pygls.protocol.json_rpc").getEffectiveLevel() == pygls_level
