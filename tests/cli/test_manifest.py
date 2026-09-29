"""``execsql run --manifest FILE``: a JSON record of the run, written even when it fails."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from execsql.manifest import RunManifest


@pytest.fixture
def work(tmp_path):
    (tmp_path / "in.csv").write_text("id,name\n1,a\n2,b\n")
    (tmp_path / "inc.sql").write_text("select 1;\n")
    return tmp_path


def _run(work, script: str, *args: str) -> tuple[subprocess.CompletedProcess, dict | None]:
    (work / "s.sql").write_text(script)
    env = {**os.environ, "HOME": str(work), "USERPROFILE": str(work), "NO_COLOR": "1"}
    cmd = [sys.executable, "-m", "execsql", "run", "s.sql", "-tl", "db.sqlite", "-n", "-d", "y", *args]
    result = subprocess.run(cmd, cwd=work, capture_output=True, text=True, env=env)
    path = work / "runs" / "m.json"
    return result, json.loads(path.read_text()) if path.exists() else None


OK = """\
create table t (id integer, name text);
-- !x! IMPORT TO t FROM in.csv
-- !x! INCLUDE inc.sql
-- !x! EXPORT QUERY <<select * from t;>> TO out/!!region!!.csv AS CSV
-- !x! WRITE "hello" TO out/log.txt
-- !x! CONNECT TO SQLITE(FILE=other.db, NEW) AS other
-- !x! USE other
-- !x! USE initial
-- !x! RM_FILE out/log.txt
"""


class TestSuccess:
    def test_summary(self, work):
        result, m = _run(work, OK, "--var", "region=west", "-a", "x", "--manifest", "runs/m.json")
        assert result.returncode == 0, result.stderr
        assert m["exit_status"] == 0
        assert m["script"] == "s.sql"
        assert m["database"]["dbms"] == "SQLite"
        assert m["statements"] == {"sql": 2, "metacommands": 7}
        assert m["errors"] == []
        assert set(m) >= {"execsql_version", "started", "finished", "duration_s", "config_files"}

    def test_files_have_substituted_paths(self, work):
        _result, m = _run(work, OK, "--var", "region=west", "--manifest", "runs/m.json")
        assert [(f["line"], f["by"], f["path"]) for f in m["files_read"]] == [
            (2, "IMPORT", "in.csv"),
            (3, "INCLUDE", "inc.sql"),
        ]
        assert [(f["line"], f["by"], f["path"]) for f in m["files_written"]] == [
            (4, "EXPORT QUERY", "out/west.csv"),
            (5, "WRITE", "out/log.txt"),
        ]
        assert [(f["line"], f["path"]) for f in m["files_deleted"]] == [(9, "out/log.txt")]

    def test_connections(self, work):
        _result, m = _run(work, OK, "--var", "region=west", "--manifest", "runs/m.json")
        assert [(c["line"], c["by"], c["target"]) for c in m["connections"]] == [
            (6, "CONNECT", "other: other.db"),
            (7, "USE", "other"),
            (8, "USE", "initial"),
        ]

    def test_variable_values_are_never_written(self, work):
        _result, m = _run(work, OK, "--var", "region=west", "-a", "s3cret-token", "--manifest", "runs/m.json")
        assert m["variables"] == ["$ARG_1", "region"]
        assert "s3cret-token" not in (work / "runs" / "m.json").read_text()

    def test_no_temporary_files_left(self, work):
        _run(work, OK, "--var", "region=west", "--manifest", "runs/m.json")
        assert [p.name for p in (work / "runs").iterdir()] == ["m.json"]


class TestFailure:
    def test_written_with_the_error(self, work):
        script = (
            '-- !x! WRITE "before" TO before.txt\nselect * from missing_table;\n-- !x! WRITE "after" TO after.txt\n'
        )
        result, m = _run(work, script, "--manifest", "runs/m.json")
        assert result.returncode == 1
        assert m["exit_status"] == 1
        assert [f["path"] for f in m["files_written"]] == ["before.txt"]
        (error,) = m["errors"]
        assert error["line"] == 2
        assert error["command"] == "select * from missing_table;"
        assert "missing_table" in error["message"]
        assert "\n" not in error["message"]

    def test_halt_records_its_exit_status(self, work):
        result, m = _run(work, "-- !x! HALT\n", "--manifest", "runs/m.json")
        assert m["exit_status"] == result.returncode


class TestNotWritten:
    def test_dry_run_writes_no_manifest(self, work):
        result, m = _run(work, "select 1;\n", "--dry-run", "--manifest", "runs/m.json")
        assert result.returncode == 0
        assert m is None


def test_finish_writes_once(tmp_path):
    manifest = RunManifest(str(tmp_path / "m.json"), "x.sql", [])
    manifest.finish(0)
    first = (tmp_path / "m.json").read_text()
    manifest.finish(1, RuntimeError("late"))
    assert (tmp_path / "m.json").read_text() == first


def test_record_metacommand_classifies_with_the_dispatch_table(tmp_path):
    from execsql.metacommands import DISPATCH_TABLE

    manifest = RunManifest(str(tmp_path / "m.json"), "x.sql", ["region"])
    manifest.record_metacommand("EXPORT QUERY <<select 1;>> TO out/west.csv AS CSV", "x.sql", 4, DISPATCH_TABLE)
    manifest.record_metacommand("CONNECT TO SQLITE(FILE=o.db, NEW) AS other", "x.sql", 5, DISPATCH_TABLE)
    manifest.record_metacommand("RM_FILE old.csv", "x.sql", 6, DISPATCH_TABLE)
    manifest.record_metacommand("IMPORT TO t FROM in.csv", "x.sql", 7, DISPATCH_TABLE)
    manifest.record_metacommand("NOT A METACOMMAND AT ALL", "x.sql", 8, DISPATCH_TABLE)
    manifest.record_include("inc.sql", "x.sql", 9)
    manifest.record_sql()
    manifest.finish(1, RuntimeError("boom\nsecond line"))
    data = json.loads((tmp_path / "m.json").read_text())
    assert data["statements"] == {"sql": 1, "metacommands": 5}
    assert data["files_written"] == [{"source": "x.sql", "line": 4, "by": "EXPORT QUERY", "path": "out/west.csv"}]
    assert data["connections"][0]["target"] == "other: o.db"
    assert data["files_deleted"][0]["path"] == "old.csv"
    assert [f["path"] for f in data["files_read"]] == ["in.csv", "inc.sql"]
    assert data["errors"][0]["message"] == "boom second line"
    assert data["exit_status"] == 1
