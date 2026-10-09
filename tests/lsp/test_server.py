"""The language server over the real protocol: ``execsql lsp`` in a subprocess."""

from __future__ import annotations

import asyncio
import logging
import sys

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


@pytest.mark.asyncio
async def test_opening_a_script_publishes_its_findings(client: LanguageClient):
    uri = _open(client, "a.sql", BAD)
    await client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    assert [d.code for d in client.diagnostics[uri]] == ["P003"]


@pytest.mark.asyncio
async def test_an_edit_updates_the_findings(client: LanguageClient):
    uri = _open(client, "b.sql", BAD)
    await client.wait_for_notification(types.TEXT_DOCUMENT_PUBLISH_DIAGNOSTICS)
    client.text_document_did_change(
        types.DidChangeTextDocumentParams(
            text_document=types.VersionedTextDocumentIdentifier(uri=uri, version=2),
            content_changes=[types.TextDocumentContentChangeWholeDocument(text=GOOD)],
        ),
    )
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


def _change(client: LanguageClient, uri: str, version: int, text: str) -> None:
    client.text_document_did_change(
        types.DidChangeTextDocumentParams(
            text_document=types.VersionedTextDocumentIdentifier(uri=uri, version=version),
            content_changes=[types.TextDocumentContentChangeWholeDocument(text=text)],
        ),
    )


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
