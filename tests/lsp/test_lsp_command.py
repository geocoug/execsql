"""``execsql lsp``: the flags editors start it with, and the message without the lsp extra."""

from __future__ import annotations

import sys
from unittest.mock import patch

from typer.testing import CliRunner

from execsql.cli import app


def test_without_pygls_it_names_the_extra():
    with (
        patch.dict(sys.modules, {"execsql.lsp.server": None}),
        patch(
            "execsql.cli.commands.lsp._lsp_libraries_installed",
            return_value=False,
        ),
    ):
        result = CliRunner().invoke(app, ["lsp"])
    assert result.exit_code == 1
    # Installed with the extras already there: a bare "execsql2[lsp]" would replace them.
    assert "execsql2[postgres,lsp]" in result.output
    assert "#adding-an-extra-later" in result.output.replace("\n", "")


def test_accepts_the_stdio_flag_editors_pass():
    with patch("execsql.lsp.server.create_server") as create:
        result = CliRunner().invoke(app, ["lsp", "--stdio"])
    assert result.exit_code == 0, result.output
    create.return_value.start_io.assert_called_once_with()


def test_lsp_is_a_command_not_a_script_name():
    from execsql.cli.dispatch import normalize

    assert normalize(["lsp"]) == ["lsp"]


def test_check_says_the_server_can_start():
    result = CliRunner().invoke(app, ["lsp", "--check"])
    assert result.exit_code == 0, result.output
    assert "execsql lsp is ready (pygls " in result.output


def test_check_fails_without_pygls():
    with (
        patch.dict(sys.modules, {"execsql.lsp.server": None}),
        patch(
            "execsql.cli.commands.lsp._lsp_libraries_installed",
            return_value=False,
        ),
    ):
        result = CliRunner().invoke(app, ["lsp", "--check"])
    assert result.exit_code == 1
    assert "needs the lsp extra" in result.output


def test_an_unusable_pygls_is_named_not_reported_missing():
    with (
        patch.dict(sys.modules, {"execsql.lsp.server": None}),
        patch(
            "execsql.cli.commands.lsp._lsp_libraries_installed",
            return_value=True,
        ),
    ):
        result = CliRunner().invoke(app, ["lsp", "--check"])
    assert result.exit_code == 1
    assert "cannot use the installed pygls" in result.output
    assert "needs the lsp extra" not in result.output
