"""Offline checks for optional local and required CI database fixtures."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests import live_db
from tests.exporters import conftest as exporters
from tests.importers import conftest as importers
from tests.templates import conftest as templates


@contextmanager
def no_setup_skip():
    """A skipped regression case must fail rather than hide the defect it checks."""
    try:
        yield
    except pytest.skip.Exception as exc:
        raise AssertionError(f"Setup was skipped instead of failing: {exc}") from exc


@pytest.fixture(autouse=True)
def backend_policy(monkeypatch):
    monkeypatch.delenv("EXECSQL_REQUIRED_BACKENDS", raising=False)
    monkeypatch.setattr(live_db, "_unusable", {})
    monkeypatch.setattr(templates, "_REACHABLE", {})


@pytest.mark.parametrize("missing_driver", [False, True])
def test_required_connection_failure_is_not_skipped(monkeypatch, tmp_path, missing_driver):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "postgres")

    def unavailable(_path):
        if missing_driver:
            pytest.skip("driver absent")
        raise RuntimeError("adapter initialization failed")

    monkeypatch.setitem(live_db._BACKENDS, "postgres", unavailable)
    with no_setup_skip(), pytest.raises(pytest.fail.Exception, match="postgres"):
        live_db.open_backend("postgres", tmp_path)
    assert "postgres" not in live_db._unusable


def test_required_cached_unavailability_is_not_skipped(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "postgres")
    live_db._unusable["postgres"] = "postgres is unavailable"
    with no_setup_skip(), pytest.raises(pytest.fail.Exception, match="postgres"):
        live_db.open_backend("postgres", tmp_path)


def test_required_connection_success_is_preserved(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", " postgres, mysql ")
    db = object()
    monkeypatch.setitem(live_db._BACKENDS, "postgres", lambda _path: db)
    assert live_db.open_backend("postgres", tmp_path) is db


def test_unknown_required_name_fails_before_connecting(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "postgrez")
    connect = MagicMock()
    monkeypatch.setitem(live_db._BACKENDS, "postgres", connect)
    with pytest.raises(pytest.UsageError, match="postgrez"):
        live_db.open_backend("postgres", tmp_path)
    connect.assert_not_called()


def test_optional_unavailable_connection_is_probed_once(monkeypatch, tmp_path):
    connect = MagicMock(side_effect=ConnectionError("server absent"))
    monkeypatch.setitem(live_db._BACKENDS, "postgres", connect)
    for _ in range(2):
        with pytest.raises(pytest.skip.Exception, match="server absent"):
            live_db.open_backend("postgres", tmp_path)
    connect.assert_called_once_with(tmp_path)


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("stage", ["ddl", "seed"])
def test_export_setup_failure_is_visible_and_closes_connection(monkeypatch, tmp_path, required, stage):
    if required:
        monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "postgres")
    db = MagicMock()
    monkeypatch.setitem(exporters._BACKENDS, "postgres", lambda _path: db)
    if stage == "ddl":
        db._cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("broken setup")
    else:
        monkeypatch.setattr(exporters, "_insert", MagicMock(side_effect=RuntimeError("broken setup")))
    fixture = exporters.export_db.__wrapped__(SimpleNamespace(param="postgres"), tmp_path, None)
    with no_setup_skip(), pytest.raises(RuntimeError, match="broken setup"):
        next(fixture)
    db.close.assert_called_once()


@pytest.mark.parametrize("missing_driver", [False, True])
def test_required_export_connection_failure_is_not_skipped(monkeypatch, tmp_path, missing_driver):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "postgres")

    def unavailable(_path):
        if missing_driver:
            pytest.skip("driver absent")
        raise RuntimeError("adapter initialization failed")

    monkeypatch.setitem(exporters._BACKENDS, "postgres", unavailable)
    fixture = exporters.export_db.__wrapped__(SimpleNamespace(param="postgres"), tmp_path, None)
    with no_setup_skip(), pytest.raises(pytest.fail.Exception, match="postgres"):
        next(fixture)


@pytest.mark.parametrize("missing_driver", [False, True])
def test_required_template_connection_failure_is_not_skipped(monkeypatch, missing_driver):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "mariadb")

    def unavailable():
        if missing_driver:
            pytest.skip("driver absent")
        raise RuntimeError("broken initialization")

    monkeypatch.setitem(templates._SERVERS, "mariadb", unavailable)
    with no_setup_skip(), pytest.raises(pytest.fail.Exception, match="mariadb"):
        templates._server("mariadb")
    assert "mariadb" not in templates._REACHABLE


def test_optional_template_unavailability_is_cached(monkeypatch):
    connect = MagicMock(side_effect=ConnectionError("server absent"))
    monkeypatch.setitem(templates._SERVERS, "mariadb", connect)
    for _ in range(2):
        with pytest.raises(pytest.skip.Exception, match="server absent"):
            templates._server("mariadb")
    connect.assert_called_once()


def test_required_cached_template_unavailability_is_not_skipped(monkeypatch):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "mariadb")
    templates._REACHABLE["mariadb"] = "mariadb is unavailable"
    with no_setup_skip(), pytest.raises(pytest.fail.Exception, match="mariadb"):
        templates._server("mariadb")


def test_required_local_infile_cannot_skip(monkeypatch):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "mysql")
    db = MagicMock(dbms_name="mysql")
    db._cursor.return_value.__enter__.return_value.fetchone.return_value = ("local_infile", "OFF")
    with no_setup_skip(), pytest.raises(pytest.fail.Exception, match="local_infile"):
        importers.requires_local_infile(db)


def test_required_import_setup_failure_is_not_suppressed(monkeypatch):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "mysql")
    db = MagicMock(dbms_name="mysql")
    db._cursor.side_effect = RuntimeError("drop failed")
    with no_setup_skip(), pytest.raises(RuntimeError, match="drop failed"):
        importers._drop(db)


def test_import_setup_failure_closes_connection(monkeypatch, tmp_path, minimal_conf):
    monkeypatch.setenv("EXECSQL_REQUIRED_BACKENDS", "mysql")
    db = MagicMock()
    db._cursor.side_effect = RuntimeError("drop failed")
    monkeypatch.setattr(importers, "open_backend", lambda _name, _path: db)
    fixture = importers.import_db.__wrapped__(SimpleNamespace(param="mysql"), tmp_path, minimal_conf)
    with no_setup_skip(), pytest.raises(RuntimeError, match="drop failed"):
        next(fixture)
    db.close.assert_called_once()
