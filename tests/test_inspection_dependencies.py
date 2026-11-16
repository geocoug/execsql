"""Optional driver failures are silent API results, rendered once by the CLI."""

import builtins
import json
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from execsql import inspect_schema
from execsql.cli import app


@pytest.mark.parametrize(
    "kind,module,extra",
    [
        ("l", "sqlite3", None),
        ("p", "psycopg", "postgres"),
        ("m", "pymysql", "mysql"),
        ("s", "pyodbc", "mssql"),
        ("k", "duckdb", "duckdb"),
        ("f", "firebird", "firebird"),
        ("o", "oracledb", "oracle"),
        ("d", "pyodbc", "odbc"),
        ("a", "win32com", "odbc"),
        ("a", "pyodbc", "odbc"),
    ],
)
@pytest.mark.parametrize("error_type", [ImportError, RuntimeError])
def test_missing_or_broken_driver_returns_one_safe_diagnostic(
    tmp_path,
    monkeypatch,
    capsys,
    kind,
    module,
    extra,
    error_type,
):
    import importlib
    from execsql.config import ConfigData

    config = tmp_path / "inspection.conf"
    config.write_text(f"[connect]\ndb_type={kind}\nserver=host\ndb=example\ndb_file={tmp_path}/input.db\n")
    (tmp_path / "input.db").touch()
    monkeypatch.setattr(ConfigData, "_search_paths", classmethod(lambda *a, **kw: [str(config)]))
    original_import = builtins.__import__
    original_module = importlib.import_module

    def blocked(name):
        return name == module or name.startswith(module + ".")

    def import_builtin(name, *args, **kwargs):
        if blocked(name):
            raise error_type("synthetic-private-driver-error")
        return original_import(name, *args, **kwargs)

    def import_module(name, *args, **kwargs):
        if blocked(name):
            raise error_type("synthetic-private-driver-error")
        if name == "win32com.client" and kind == "a":
            return SimpleNamespace()
        return original_module(name, *args, **kwargs)

    keyring = MagicMock(side_effect=AssertionError("must not access credentials"))
    monkeypatch.setattr("execsql.utils.auth._keyring_get", keyring)
    monkeypatch.setattr(builtins, "__import__", import_builtin)
    monkeypatch.setattr(importlib, "import_module", import_module)
    report = inspect_schema(config_file=config, include_database=True)
    assert capsys.readouterr() == ("", "")
    assert report["error"]["code"] == "dependency_error"
    hint = f"execsql2[{extra}]" if extra else "sqlite3"
    assert hint in report["error"]["message"]
    assert "synthetic-private" not in json.dumps(report)
    for output_format in ("text", "json"):
        result = CliRunner().invoke(
            app,
            ["inspect", "database", "--config", str(config), "--output-format", output_format],
        )
        assert result.exit_code == 1
        assert "synthetic-private" not in result.output
        assert "General error" not in result.output
        if output_format == "json":
            assert result.stderr == ""
            assert json.loads(result.stdout) == report
        else:
            assert result.stdout == ""
            assert result.stderr.count("Error:") == 1
            assert hint in result.stderr
    keyring.assert_not_called()
