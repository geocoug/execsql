"""``execsql lsp`` without the lsp extra says how to install it."""

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


def test_lsp_is_a_command_not_a_script_name():
    from execsql.cli.dispatch import normalize

    assert normalize(["lsp"]) == ["lsp"]
