"""``execsql lsp``: the flags editors start it with, and the message without the lsp extra."""

from __future__ import annotations

import sys
from unittest.mock import patch

from typer.testing import CliRunner

from execsql.cli import app


def test_without_pygls_it_names_the_extra():
    with patch.dict(sys.modules, {"execsql.lsp.server": None}):
        result = CliRunner().invoke(app, ["lsp"])
    assert result.exit_code == 1
    assert "execsql2[lsp]" in result.output


def test_accepts_the_stdio_flag_editors_pass():
    with patch("execsql.lsp.server.create_server") as create:
        result = CliRunner().invoke(app, ["lsp", "--stdio"])
    assert result.exit_code == 0, result.output
    create.return_value.start_io.assert_called_once_with()


def test_lsp_is_a_command_not_a_script_name():
    from execsql.cli.dispatch import normalize

    assert normalize(["lsp"]) == ["lsp"]
