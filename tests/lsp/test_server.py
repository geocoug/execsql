"""The language server over the real protocol: ``execsql lsp`` in a subprocess."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("pygls")
pytest_lsp = pytest.importorskip("pytest_lsp")

from lsprotocol import types  # noqa: E402
from pytest_lsp import ClientServerConfig, LanguageClient  # noqa: E402

BAD = "-- !x! EXPROT orders TO out.csv AS CSV\n"
GOOD = "-- !x! EXPORT orders TO out.csv AS CSV\n"


@pytest_lsp.fixture(config=ClientServerConfig(server_command=[sys.executable, "-m", "execsql", "lsp"]))
async def client(lsp_client: LanguageClient, tmp_path_factory):
    root = tmp_path_factory.mktemp("workspace")
    await lsp_client.initialize_session(
        types.InitializeParams(capabilities=types.ClientCapabilities(), root_uri=root.as_uri()),
    )
    lsp_client.root = root
    yield
    await lsp_client.shutdown_session()


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


@pytest_lsp.fixture(config=ClientServerConfig(server_command=[sys.executable, "-m", "execsql", "lsp"]))
async def configured_client(lsp_client: LanguageClient, tmp_path_factory):
    root = tmp_path_factory.mktemp("configured")
    (root / "execsql.conf").write_text("[lint]\nignore = P003\n")
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
