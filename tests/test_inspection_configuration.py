"""Connection configuration applies to discovery without executing run behavior."""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from execsql import inspect_schema, inspect_file
from execsql.cli import app
from execsql.config import ConfigData
from execsql import schema as discovery


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.setattr(
        ConfigData,
        "_search_paths",
        classmethod(lambda cls, script_path, config_file, start_dir=None: [str(config_file)] if config_file else []),
    )


@pytest.fixture
def project(tmp_path):
    db = tmp_path / "project.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE samples(id INTEGER PRIMARY KEY)")
    conf = tmp_path / "project.conf"
    conf.write_text(f"[connect]\ndb_type=l\ndb_file={db}\nnew_db=Yes\n")
    return db, conf


@pytest.mark.parametrize("scope", [["database"], ["schema", "main"], ["table", "samples"]])
@pytest.mark.parametrize("show_settings,show_config", [(False, False), (True, False), (False, True), (True, True)])
def test_every_scope_uses_config_and_independent_display_flags(project, monkeypatch, scope, show_settings, show_config):
    _, conf = project
    monkeypatch.setattr("execsql.cli.inspection._console.width", 60)
    args = ["inspect", *scope, "--config", str(conf)]
    if show_settings:
        args.append("--show-settings")
    if show_config:
        args.append("--show-config")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert ("Inspection settings:" in result.stdout) is show_settings
    assert ("Configuration files:" in result.stdout) is show_config
    assert (str(conf) in "".join(result.stdout.splitlines())) is show_config
    machine = CliRunner().invoke(app, [*args, "--output-format", "json"])
    assert machine.exit_code == 0, machine.output
    report = json.loads(machine.stdout)
    assert report["config_files"] == [str(conf)]
    assert report["settings"]["db_type"] == "l"
    assert report["settings"]["password_prompt"] is False
    assert any(t["name"] == "samples" for t in report["tables"])


def test_explicit_url_replaces_configured_target_without_merging_identity(project, tmp_path, monkeypatch):
    _, conf = project
    conf.write_text("[connect]\ndb_type=p\nserver=config-host\ndb=config-db\nusername=config-user\nport=9999\n")
    db = tmp_path / "explicit.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE explicit_target(v INT)")
    report = inspect_schema(dsn=f"sqlite:///{db}", config_file=conf)
    assert report["success"], report
    assert [t["name"] for t in report["tables"]] == ["explicit_target"]
    factory = MagicMock(side_effect=RuntimeError("stop before network"))
    monkeypatch.setattr("execsql.db.factory.db_Postgres", factory)
    inspect_schema(dsn="postgresql://url-host/url-db", config_file=conf)
    assert factory.call_args.args == ("url-host", "url-db")
    assert factory.call_args.kwargs["user"] is None
    assert factory.call_args.kwargs["port"] == 5432


@pytest.mark.parametrize("suffix", ["sqlite", "duckdb"])
def test_configured_missing_database_is_never_created(tmp_path, suffix):
    missing = tmp_path / f"absent.{suffix}"
    conf = tmp_path / "project.conf"
    conf.write_text(f"[connect]\ndb_type={'l' if suffix == 'sqlite' else 'k'}\ndb_file={missing}\nnew_db=Yes\n")
    report = inspect_schema(config_file=conf)
    assert not report["success"] and report["error"]["code"] == "connection_error"
    assert not missing.exists()


def test_default_config_search_and_chaining_never_execute_includes_or_expose_secrets(project, tmp_path, monkeypatch):
    db, conf = project
    chain = tmp_path / "chain.conf"
    chain.write_text("[connect]\nuse_keyring=No\n[input]\nboolean_int=No\n")
    startup = tmp_path / "startup.sql"
    startup.write_text("CREATE TABLE must_not_execute(v INT);\n")
    conf.write_text(
        f"[connect]\ndb_type=l\ndb_file={db}\n[config]\nconfig_file={chain}\n"
        "[email]\npassword=private-secret\n[variables]\nprivate=private-secret\n"
        f"[include_required]\n1={startup}\n",
    )
    monkeypatch.setattr(ConfigData, "_search_paths", classmethod(lambda *args, **kwargs: [str(conf)]))
    report = inspect_schema()
    assert report["success"], report
    assert report["config_files"] == [str(conf), str(chain)]
    assert report["settings"]["use_keyring"] is False
    assert "boolean_int" not in report["settings"]
    assert "private-secret" not in json.dumps(report)
    assert [t["name"] for t in report["tables"]] == ["samples"]


@pytest.mark.parametrize(
    "content",
    ["", "[connect]\ndb_type=p\nserver=only-host\n", "[connect]\nuse_keyring=private-secret\n"],
)
def test_invalid_or_missing_defaults_return_safe_configuration_errors(tmp_path, content):
    conf = tmp_path / "project.conf"
    conf.write_text(content)
    report = inspect_schema(config_file=conf)
    assert not report["success"] and report["error"]["code"] == "configuration_error"
    assert "private-secret" not in json.dumps(report)
    for output_format in ("text", "json"):
        result = CliRunner().invoke(
            app,
            ["inspect", "database", "--config", str(conf), "--output-format", output_format],
        )
        assert result.exit_code == 1
        assert "private-secret" not in result.output
        if output_format == "json":
            assert result.stderr == "" and json.loads(result.stdout)["error"]["code"] == "configuration_error"


@pytest.mark.parametrize("query,expected", [("", True), ("?trust_server_certificate=no", False)])
def test_url_certificate_override_and_configured_encoding(tmp_path, monkeypatch, query, expected):
    import execsql.state as state

    conf = tmp_path / "project.conf"
    conf.write_text("[connect]\ntrust_server_certificate=Yes\nuse_keyring=No\n[encoding]\ndatabase=utf8\n")
    captured = {}

    def factory(*args, **kwargs):
        captured.update(kwargs)
        captured["trust"] = state.conf.trust_server_certificate
        captured["keyring"] = state.conf.use_keyring
        raise RuntimeError("private-secret")

    monkeypatch.setattr("execsql.db.factory.db_SqlServer", factory)
    report = inspect_schema(dsn="mssql://host/project" + query, config_file=conf)
    assert report["settings"]["trust_server_certificate"] is expected
    assert captured["trust"] is expected
    assert captured["encoding"] == "utf8" and captured["keyring"] is False
    assert "private-secret" not in json.dumps(report)


@pytest.mark.parametrize("configured", [True, False])
@pytest.mark.parametrize("prompt_request", [True, False, None])
@pytest.mark.parametrize("terminal", [True, False])
def test_prompt_precedence_and_noninteractive_safety(tmp_path, monkeypatch, configured, prompt_request, terminal):
    conf = tmp_path / "project.conf"
    conf.write_text(f"[connect]\npassword_prompt={'Yes' if configured else 'No'}\n")
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: terminal))
    connect = MagicMock(side_effect=RuntimeError("stop before login"))
    monkeypatch.setattr("execsql.api._connect_from_dsn", connect)
    if prompt_request is True and not terminal:
        with pytest.raises(ValueError, match="interactive terminal"):
            inspect_schema(dsn="postgresql://user@host/db", config_file=conf, prompt_password=prompt_request)
        connect.assert_not_called()
    else:
        report = inspect_schema(dsn="postgresql://user@host/db", config_file=conf, prompt_password=prompt_request)
        expected = terminal and (configured if prompt_request is None else prompt_request)
        assert connect.call_args.kwargs["prompt_password"] is expected
        assert report["settings"]["password_prompt"] is expected


@pytest.mark.parametrize(
    "kind,factory_name",
    [
        ("l", "db_SQLite"),
        ("k", "db_DuckDB"),
        ("a", "db_Access"),
        ("d", "db_Dsn"),
        ("p", "db_Postgres"),
        ("m", "db_MySQL"),
        ("s", "db_SqlServer"),
        ("o", "db_Oracle"),
        ("f", "db_Firebird"),
    ],
)
def test_configured_connection_dispatches_every_adapter(tmp_path, monkeypatch, kind, factory_name):
    conf = tmp_path / "project.conf"
    conf.write_text(
        f"[connect]\ndb_type={kind}\nserver=host\ndb=project\ndb_file=project.db\nusername=user\n"
        "access_username=access-user\nnew_db=Yes\nuse_keyring=No\n[encoding]\ndatabase=utf8\n",
    )
    db = MagicMock()
    db.type.dbms_id = "SQLite"
    factory = MagicMock(return_value=db)
    monkeypatch.setattr(f"execsql.db.factory.{factory_name}", factory)
    monkeypatch.setitem(discovery._READERS, "SQLite", lambda *args: [])
    report = inspect_schema(config_file=conf)
    assert report["success"], report
    factory.assert_called_once()
    assert factory.call_args.kwargs["encoding"] == "utf8"
    if kind in ("p", "l", "k"):
        assert factory.call_args.kwargs["new_db"] is False
    if kind not in ("l", "k"):
        assert factory.call_args.kwargs["pw_needed"] is False
    db.close.assert_called_once()


def test_borrowed_connection_does_not_load_or_apply_configuration(monkeypatch):
    connect = MagicMock(side_effect=AssertionError("must not load config"))
    monkeypatch.setattr("execsql.cli.run._tool_config", connect)
    from execsql.db.sqlite import SQLiteDatabase

    db = SQLiteDatabase(":memory:")
    try:
        report = inspect_schema(connection=db)
        assert report["success"] and report["settings"] == {} and report["config_files"] == []
        connect.assert_not_called()
    finally:
        db.close()


@pytest.mark.parametrize("scope", [["database"], ["schema", "main"], ["table", "samples"], ["file", "input.csv"]])
@pytest.mark.parametrize("config_kind", ["missing", "directory", "unreadable"])
def test_explicit_invalid_config_fails_before_connection(tmp_path, monkeypatch, scope, config_kind):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "input.csv").write_text("v\n2\n")
    config = tmp_path / "config.conf"
    if config_kind == "directory":
        config.mkdir()
    elif config_kind == "unreadable":
        config.write_text("")
        original_open = Path.open

        def open_file(path, *args, **kwargs):
            if path == config:
                raise PermissionError("synthetic-private-value")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", open_file)
    connect = MagicMock(side_effect=AssertionError("must validate config first"))
    monkeypatch.setattr("execsql.api._connect_from_dsn", connect)
    args = ["inspect", *scope, "--config", str(config), "--output-format", "json"]
    if scope[0] != "file":
        args += ["--dsn", "sqlite:///:memory:"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout)["error"]["code"] == "configuration_error"
    assert result.stderr == ""
    assert "synthetic-private-value" not in result.output
    connect.assert_not_called()
    report = inspect_schema(dsn="sqlite:///:memory:", config_file=config)
    assert report["error"]["code"] == "configuration_error"
    connect.assert_not_called()


@pytest.mark.parametrize(
    "content",
    ["[email]\nprivate-marker-without-value\n", "[connect]\nuse_keyring=private-marker\n"],
)
def test_file_configuration_errors_never_echo_private_values(tmp_path, content):
    source = tmp_path / "input.csv"
    source.write_text("v\n2\n")
    conf = tmp_path / "private.conf"
    conf.write_text(content)
    report = inspect_file(source, config_file=conf)
    assert report["error"]["code"] == "configuration_error"
    assert "private-marker" not in json.dumps(report)
    for output_format in ("text", "json"):
        result = CliRunner().invoke(
            app,
            ["inspect", "file", str(source), "--config", str(conf), "--output-format", output_format],
        )
        assert result.exit_code == 1
        assert "private-marker" not in result.output
        assert "configuration" in result.output.lower()


@pytest.mark.parametrize("level", [1, 2, 3])
@pytest.mark.parametrize("failure", [None, RuntimeError("connect failed"), KeyboardInterrupt()])
@pytest.mark.parametrize("existing_backend", [False, True])
def test_repeated_owned_auth_ignores_gui_settings_and_preserves_host(
    tmp_path,
    monkeypatch,
    level,
    failure,
    existing_backend,
):
    import execsql.state as state
    from execsql.utils import gui, auth

    config = tmp_path / "inspection.conf"
    config.write_text(f"[connect]\nuse_keyring=No\n[interface]\ngui_level={level}\n")
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    terminal = MagicMock(return_value="synthetic-password")
    monkeypatch.setattr(auth.getpass, "getpass", terminal)
    backend = MagicMock() if existing_backend else None
    monkeypatch.setattr(gui, "_active_backend", backend)
    initialize = MagicMock(side_effect=AssertionError("must not initialize GUI"))
    monkeypatch.setattr(gui, "enable_gui", initialize)
    original = state.get_context()

    def connect(*args, **kwargs):
        assert state.conf.gui_level == 0
        assert auth.get_password("PostgreSQL", "db", "user", server_name="host") == "synthetic-password"
        if failure is not None:
            raise failure
        db = MagicMock()
        db.type.dbms_id = "SQLite"
        return db

    monkeypatch.setattr("execsql.api._connect_from_dsn", connect)
    monkeypatch.setitem(discovery._READERS, "SQLite", lambda *args: [])
    for _ in range(2):
        if isinstance(failure, KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                inspect_schema(dsn="postgresql://user@host/db", config_file=config, prompt_password=True)
        else:
            report = inspect_schema(dsn="postgresql://user@host/db", config_file=config, prompt_password=True)
            assert report["success"] is (failure is None), report
        assert state.get_context() is original
        assert gui._active_backend is backend
    initialize.assert_not_called()
    if backend is not None:
        assert backend.mock_calls == []
    assert terminal.call_count == 2
