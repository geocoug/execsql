"""CLI/API conformance for configuration effects applied before the main script."""

import sqlite3
import subprocess
import sys

import pytest

from execsql import run


def _execute(entry, tmp_path, config, sql, *, cli_options=()):
    main = tmp_path / "main.sql"
    main.write_text(sql, encoding="utf-8")
    conf = tmp_path / "settings.conf"
    conf.write_text(config, encoding="utf-8")
    database = tmp_path / "run.db"
    dsn = f"sqlite:///{database}"
    if entry == "api":
        result = run(script=main, dsn=dsn, new_db=True, config_file=conf)
        return result.success, "\n".join(error.message for error in result.errors), database
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "run", "--config", str(conf), "--dsn", dsn, "-n", *cli_options, str(main)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0, result.stdout + result.stderr, database


def _rows(database, query):
    connection = sqlite3.connect(database)
    try:
        return connection.execute(query).fetchall()
    finally:
        connection.close()


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_configured_variables_reach_the_running_script(entry, tmp_path):
    success, errors, database = _execute(
        entry,
        tmp_path,
        "[variables]\nanswer = configured\n",
        "create table seen (v text);\ninsert into seen values ('!!answer!!');\n",
    )
    assert success, errors
    assert _rows(database, "select v from seen") == [("configured",)]


def test_api_result_retains_configured_variables(tmp_path):
    conf = tmp_path / "settings.conf"
    conf.write_text("[variables]\nanswer = configured\n", encoding="utf-8")
    result = run(sql="-- !x! SUB captured !!answer!!\n", dsn="sqlite:///:memory:", config_file=conf)
    assert result.success, result.errors
    assert result.variables["answer"] == "configured"
    assert result.variables["captured"] == "configured"


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_required_then_optional_includes_run_once_before_main(entry, tmp_path):
    first, second = tmp_path / "required first.sql", tmp_path / "required-second.sql"
    first.write_text("create table sequence (v text);\ninsert into sequence values ('required-first-!!greeting!!');\n")
    second.write_text(
        "insert into sequence values ('required-second');\n"
        "-- !x! BEGIN SCRIPT configured_job\n"
        "insert into sequence values ('configured-job');\n"
        "-- !x! END SCRIPT\n",
    )
    optional1, optional2 = tmp_path / "optional-first.sql", tmp_path / "optional-second.sql"
    optional1.write_text("insert into sequence values ('optional-first');\n")
    optional2.write_text("insert into sequence values ('optional-second');\n")
    conf = (
        f"[variables]\ngreeting = configured\n[include_required]\n20 = {second}\n10 = {first}\n30 = {first}\n"
        f"[include_optional]\n20 = {optional2}\n10 = {optional1}\n30 = {second}\n"
    )
    success, errors, database = _execute(
        entry,
        tmp_path,
        conf,
        "-- !x! EXECUTE SCRIPT configured_job\ninsert into sequence values ('main');\n",
    )
    assert success, errors
    assert _rows(database, "select v from sequence order by rowid") == [
        (name,)
        for name in (
            "required-first-configured",
            "required-second",
            "optional-first",
            "optional-second",
            "configured-job",
            "main",
        )
    ]


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_missing_required_include_fails_before_connecting(entry, tmp_path):
    success, errors, database = _execute(
        entry,
        tmp_path,
        f"[include_required]\n1 = {tmp_path / 'missing.sql'}\n",
        "select 1;\n",
    )
    assert not success
    assert "Required include file" in errors
    assert not database.exists()


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_missing_optional_include_is_silent(entry, tmp_path):
    success, errors, database = _execute(
        entry,
        tmp_path,
        f"[include_optional]\n1 = {tmp_path / 'missing.sql'}\n",
        "create table main_ran (v text);\n",
    )
    assert success, errors
    assert _rows(database, "select name from sqlite_master where name='main_ran'") == [("main_ran",)]


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_error_in_present_optional_include_is_not_silently_skipped(entry, tmp_path):
    included = tmp_path / "optional.sql"
    included.write_text("select * from missing_setup_table;\n")
    success, errors, database = _execute(
        entry,
        tmp_path,
        f"[include_optional]\n1 = {included}\n",
        "create table main_ran (v text);\n",
    )
    assert not success
    assert "optional.sql" in errors
    assert _rows(database, "select name from sqlite_master where name='main_ran'") == []


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_configured_includes_obey_include_root(entry, tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    included = tmp_path / "outside.sql"
    included.write_text("create table outside_ran (v text);\n")
    success, errors, database = _execute(
        entry,
        tmp_path,
        f"[config]\ninclude_root = {allowed}\n[include_required]\n1 = {included}\n",
        "create table main_ran (v text);\n",
    )
    assert not success, errors
    assert _rows(database, "select name from sqlite_master where name in ('outside_ran', 'main_ran')") == []


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_configured_includes_detect_a_cycle_back_to_main(entry, tmp_path):
    included = tmp_path / "startup.sql"
    included.write_text(f'-- !x! INCLUDE "{tmp_path / "main.sql"}"\n')
    success, errors, database = _execute(
        entry,
        tmp_path,
        f"[include_required]\n1 = {included}\n",
        "create table main_ran (v text);\n",
    )
    assert not success
    assert "Circular INCLUDE" in errors
    assert _rows(database, "select name from sqlite_master where name='main_ran'") == []


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_main_file_is_not_automatically_included_twice(entry, tmp_path):
    success, errors, database = _execute(
        entry,
        tmp_path,
        f"[include_required]\n1 = {tmp_path / 'main.sql'}\n",
        "create table main_ran (v text);\n",
    )
    assert success, errors
    assert _rows(database, "select name from sqlite_master where name='main_ran'") == [("main_ran",)]


def test_dry_run_lists_configured_includes_without_executing_them(tmp_path):
    included = tmp_path / "startup.sql"
    included.write_text("create table startup_ran (v text);\n")
    success, output, database = _execute(
        "cli",
        tmp_path,
        f"[include_required]\n1 = {included}\n",
        "select 1;\n",
        cli_options=("--dry-run",),
    )
    assert success, output
    assert included.name in output
    assert output.index(included.name) < output.index("select 1;")
    assert not database.exists()


@pytest.mark.parametrize("gate", ["allow_system_cmd", "allow_rm_file", "allow_serve"])
@pytest.mark.parametrize("configured", [True, False])
@pytest.mark.parametrize("override", ["omitted", None, True, False])
def test_api_capability_arguments_preserve_or_explicitly_override_config(
    tmp_path,
    monkeypatch,
    gate,
    configured,
    override,
):
    conf = tmp_path / "settings.conf"
    conf.write_text(f"[config]\n{gate} = {'Yes' if configured else 'No'}\n", encoding="utf-8")
    observed = []

    def observe(_tree, *, ctx):
        observed.append(getattr(ctx.conf, gate))

    monkeypatch.setattr("execsql.script.executor.execute", observe)
    kwargs = {} if override == "omitted" else {gate: override}
    result = run(sql="select 1;", dsn="sqlite:///:memory:", config_file=conf, **kwargs)
    assert result.success, result.errors
    expected = configured if override in ("omitted", None) else override
    assert observed == [expected]


@pytest.mark.parametrize("gate", ["allow_system_cmd", "allow_rm_file", "allow_serve"])
def test_api_without_config_keeps_capabilities_enabled(monkeypatch, gate):
    observed = []

    def observe(_tree, *, ctx):
        observed.append(getattr(ctx.conf, gate))

    monkeypatch.setattr("execsql.script.executor.execute", observe)
    result = run(sql="select 1;", dsn="sqlite:///:memory:")
    assert result.success, result.errors
    assert observed == [True]


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_chained_config_includes_keep_global_required_optional_order(entry, tmp_path):
    root_required = tmp_path / "root-required.sql"
    root_required.write_text("create table sequence (v text);\ninsert into sequence values ('required-root');\n")
    chain_required = tmp_path / "chain-required.sql"
    chain_required.write_text("insert into sequence values ('required-chain');\n")
    root_optional = tmp_path / "root-optional.sql"
    root_optional.write_text("insert into sequence values ('optional-root');\n")
    chain_optional = tmp_path / "chain-optional.sql"
    chain_optional.write_text("insert into sequence values ('optional-chain');\n")
    chained = tmp_path / "chained.conf"
    chained.write_text(f"[include_required]\n1 = {chain_required}\n[include_optional]\n1 = {chain_optional}\n")
    conf = (
        f"[config]\nconfig_file = {chained}\n[include_required]\n1 = {root_required}\n"
        f"[include_optional]\n1 = {root_optional}\n"
    )
    success, errors, database = _execute(entry, tmp_path, conf, "insert into sequence values ('main');\n")
    assert success, errors
    assert _rows(database, "select v from sequence order by rowid") == [
        (name,) for name in ("required-root", "required-chain", "optional-root", "optional-chain", "main")
    ]


@pytest.mark.parametrize("entry", ["api", "cli"])
def test_configured_includes_preserve_main_error_line_numbers(entry, tmp_path):
    included = tmp_path / "startup.sql"
    included.write_text("select 1;\n")
    success, errors, _database = _execute(
        entry,
        tmp_path,
        f"[include_required]\n1 = {included}\n",
        "select 1;\nselect * from missing_main_table;\n",
    )
    assert not success
    assert "main.sql" in errors
    assert "Line 2" in errors
