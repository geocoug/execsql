"""Gap-fill coverage for execsql.api.

Targets:
- ``ScriptResult.raise_on_error`` with > 3 errors (formatting branch)
- ``_connect_from_dsn`` for every supported db_type (mocked factories)
- ``run`` with ``config_file=`` (real ConfigData branch)
- ``run`` with ``connection=`` (skip DSN parsing branch)
- generic Exception caught during execute()
- closeall() swallowed exception
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from execsql.api import (
    ExecSqlError,
    ScriptError,
    ScriptResult,
    _connect_from_dsn,
    run,
)


# ---------------------------------------------------------------------------
# ScriptResult.raise_on_error
# ---------------------------------------------------------------------------


class TestScriptResultRaiseOnError:
    def test_success_does_not_raise(self) -> None:
        r = ScriptResult(success=True, commands_run=1, elapsed=0.0, errors=[], variables={})
        r.raise_on_error()  # no-op

    def test_short_error_list(self) -> None:
        r = ScriptResult(
            success=False,
            commands_run=0,
            elapsed=0.0,
            errors=[ScriptError(message="boom", source="x", line=1, sql=None)],
            variables={},
        )
        with pytest.raises(ExecSqlError, match="boom"):
            r.raise_on_error()

    def test_long_error_list_truncates(self) -> None:
        errs = [ScriptError(message=f"err{i}", source="x", line=i, sql=None) for i in range(5)]
        r = ScriptResult(success=False, commands_run=0, elapsed=0.0, errors=errs, variables={})
        with pytest.raises(ExecSqlError) as exc_info:
            r.raise_on_error()
        # Should mention extra errors
        assert "more" in str(exc_info.value)
        assert exc_info.value.result is r


# ---------------------------------------------------------------------------
# _connect_from_dsn — exercise every db_type branch via mocked factories
# ---------------------------------------------------------------------------


class TestConnectFromDsn:
    """Each branch is exercised by mocking the corresponding factory function."""

    @pytest.mark.parametrize(
        "dsn,factory_name",
        [
            ("sqlite:///:memory:", "db_SQLite"),
            ("duckdb:///:memory:", "db_DuckDB"),
            ("postgresql://u:p@srv:5432/db", "db_Postgres"),
            ("mysql://u:p@srv:3306/db", "db_MySQL"),
            ("mssql://u:p@srv:1433/db", "db_SqlServer"),
            ("oracle://u:p@srv:1521/db", "db_Oracle"),
            ("firebird://u:p@srv:3050/db", "db_Firebird"),
        ],
    )
    def test_each_db_type(self, dsn, factory_name) -> None:
        # Factories are imported lazily inside _connect_from_dsn.
        with patch(f"execsql.db.factory.{factory_name}") as mock_factory:
            _connect_from_dsn(dsn)
        assert mock_factory.called

    def test_access_branch_via_injected_db_type(self) -> None:
        """The 'a' branch (Access) and 'd' branch (DSN) are unreachable via
        DSN URL schemes — exercise them by intercepting the parser."""
        with patch("execsql.api._parse_connection_string") as mp, patch("execsql.db.factory.db_Access") as mock_access:
            mp.return_value = {
                "db_type": "a",
                "server": None,
                "db": None,
                "db_file": "x.mdb",
                "user": None,
                "password": None,
                "port": None,
            }
            _connect_from_dsn("dummy://")
        assert mock_access.called

    def test_dsn_branch_via_injected_db_type(self) -> None:
        with patch("execsql.api._parse_connection_string") as mp, patch("execsql.db.factory.db_Dsn") as mock_dsn:
            mp.return_value = {
                "db_type": "d",
                "server": None,
                "db": "mydsn",
                "db_file": None,
                "user": "u",
                "password": "p",
                "port": None,
            }
            _connect_from_dsn("dummy://")
        assert mock_dsn.called

    def test_unsupported_type_raises(self) -> None:
        # Inject a bogus db_type by intercepting the parser.
        with patch("execsql.api._parse_connection_string") as mock_parse:
            mock_parse.return_value = {
                "db_type": "X",
                "server": None,
                "db": None,
                "db_file": None,
                "user": None,
                "password": None,
                "port": None,
            }
            with pytest.raises(ValueError, match="Unsupported"):
                _connect_from_dsn("bogus:///x")


# ---------------------------------------------------------------------------
# run() additional branches
# ---------------------------------------------------------------------------


class TestRunBranches:
    def test_run_with_connection_object(self) -> None:
        """When ``connection=`` is given, DSN parsing is skipped (line 464)."""
        from execsql.db.factory import db_SQLite

        db = db_SQLite(":memory:", new_db=True)
        result = run(
            sql="CREATE TABLE t (x INT);",
            connection=db,
        )
        assert result.success

    def test_run_with_config_file_branch(self, tmp_path: Path) -> None:
        """When ``config_file=`` is given, a real ConfigData is constructed."""
        cfg = tmp_path / "execsql.conf"
        cfg.write_text("[config]\nscript_encoding = utf-8\n")
        result = run(
            sql="CREATE TABLE t (x INT);",
            dsn="sqlite:///:memory:",
            config_file=cfg,
        )
        assert result.success

    def test_run_user_supplied_variables(self) -> None:
        result = run(
            sql='-- !x! WRITE "value=!!myvar!!"\n',
            dsn="sqlite:///:memory:",
            variables={"myvar": "hello"},
        )
        assert result.success
        assert result.variables.get("myvar") == "hello"

    def test_run_dollar_prefixed_var(self) -> None:
        # User variable names already starting with $ are accepted verbatim
        result = run(
            sql="CREATE TABLE t (x INT);",
            dsn="sqlite:///:memory:",
            variables={"$mine": "v"},
        )
        assert result.success
        assert result.variables.get("mine") == "v"

    def test_run_generic_exception_captured(self) -> None:
        """An unexpected Exception during execute() is captured as a ScriptError."""
        with patch("execsql.script.executor.execute", side_effect=RuntimeError("boom")):
            result = run(
                sql="SELECT 1;",
                dsn="sqlite:///:memory:",
            )
        assert result.success is False
        assert any("boom" in e.message for e in result.errors)
