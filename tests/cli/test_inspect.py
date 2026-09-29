"""``execsql inspect``: what a script needs and touches, without running it."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from execsql.cli import app

runner = CliRunner()

SCRIPT = """\
-- !x! CONNECT TO POSTGRESQL(SERVER=db.example.com, DB=warehouse, USER=etl, NEED_PWD=TRUE) AS wh
-- !x! INCLUDE common.sql
-- !x! INCLUDE missing.sql
-- !x! SUB outdir out/!!$ARG_1!!
-- !x! IMPORT TO REPLACEMENT staging.orders FROM data/orders.csv
-- !x! IMPORT TO staging.regions FROM "!!&DATA_HOME!!/regions.csv"
-- !x! USE wh
-- !x! EXPORT QUERY <<select * from orders where region = '!!region!!';>> TO !!outdir!!/summary.xlsx AS XLSX
-- !x! WRITE "done at !!$CURRENT_TIME!! run !!$COUNTER_1!!" TO run.log
-- !x! ZIP !!outdir!!/summary.xlsx TO ZIPFILE out/archive.zip
-- !x! RM_FILE out/old.csv
-- !x! BEGIN SCRIPT build_summary
select 1;
-- !x! END SCRIPT
-- !x! EXECUTE SCRIPT build_summary
-- !x! EXECUTE SCRIPT nowhere
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "orders.csv").write_text("")
    (tmp_path / "common.sql").write_text("select 1;\n")
    (tmp_path / "load.sql").write_text(SCRIPT)
    return tmp_path


def _json(*args: str) -> dict:
    result = runner.invoke(app, ["inspect", *args, "--output-format", "json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _touches(section: list[dict]) -> list[tuple]:
    return [(t["line"], t["by"], t["target"], t["detail"]) for t in section]


class TestReport:
    def test_needs(self, project):
        assert _json("load.sql")["needs"] == {
            "arguments": ["$ARG_1"],
            "environment": ["&DATA_HOME"],
            "variables": ["region"],
        }

    def test_defines(self, project):
        assert _json("load.sql")["defines"] == {"variables": ["OUTDIR"], "scripts": ["build_summary"]}

    def test_includes(self, project):
        assert _touches(_json("load.sql")["includes"]) == [
            (2, "INCLUDE", "common.sql", ""),
            (3, "INCLUDE", "missing.sql", "does not exist"),
            (15, "EXECUTE SCRIPT", "build_summary", "defined in this file"),
            (16, "EXECUTE SCRIPT", "nowhere", "not defined in this file"),
        ]

    def test_reads_writes_deletes(self, project):
        data = _json("load.sql")
        assert _touches(data["reads"]) == [
            (5, "IMPORT", "data/orders.csv", ""),
            (6, "IMPORT", "!!&DATA_HOME!!/regions.csv", ""),
            (10, "ZIP", "!!outdir!!/summary.xlsx", ""),
        ]
        assert _touches(data["writes"]) == [
            (8, "EXPORT QUERY", "!!outdir!!/summary.xlsx", ""),
            (9, "WRITE", "run.log", ""),
            (10, "ZIP", "out/archive.zip", ""),
        ]
        assert _touches(data["deletes"]) == [(11, "RM_FILE", "out/old.csv", "")]

    def test_connections(self, project):
        assert _touches(_json("load.sql")["connections"]) == [
            (1, "CONNECT", "wh: db.example.com/warehouse", "PostgreSQL, user etl"),
            (7, "USE", "wh", ""),
        ]

    def test_passwords_are_never_reported(self, project):
        (project / "p.sql").write_text(
            "-- !x! CONNECT TO POSTGRESQL(SERVER=db, DB=shop, USER=app, NEED_PWD=FALSE, PASSWORD=hunter2) AS shop\n",
        )
        for fmt in ("text", "json"):
            output = runner.invoke(app, ["inspect", "p.sql", "--output-format", fmt]).output
            assert "hunter2" not in output
            assert "shop" in output

    def test_agrees_with_lint_on_undefined_variables(self, project):
        """What inspect lists as needed from outside is what lint warns about as undefined (V001)."""
        lint = json.loads(runner.invoke(app, ["lint", "load.sql", "--output-format", "json"]).output)
        undefined = {i["message"].removeprefix("undefined variable ").strip("!") for i in lint if i["code"] == "V001"}
        assert undefined == set(_json("load.sql")["needs"]["variables"])


class TestCommand:
    def test_text_output(self, project):
        out = runner.invoke(app, ["inspect", "load.sql"]).output
        for heading in ("Needs from outside", "Includes", "Reads", "Writes", "Deletes", "Connections", "Defines"):
            assert heading in out
        assert "--var, [variables] in a config file, or SUB_INI" in out

    def test_nothing_found(self, project):
        (project / "plain.sql").write_text("select 1;\n")
        assert "Nothing found" in runner.invoke(app, ["inspect", "plain.sql"]).output

    def test_stdin(self):
        result = runner.invoke(
            app,
            ["inspect", "-", "--output-format", "json"],
            input='-- !x! WRITE "!!x!!" TO a.txt\n',
        )
        data = json.loads(result.output)
        assert data["script"] == "<stdin>"
        assert data["needs"]["variables"] == ["x"]

    def test_parse_error_exits_1_on_one_line(self, project):
        (project / "bad.sql").write_text("-- !x! IF (true)\n")
        result = runner.invoke(app, ["inspect", "bad.sql"])
        assert result.exit_code == 1
        assert "cannot parse bad.sql:1: Unmatched IF block" in " ".join(result.output.split())

    def test_missing_script_is_a_usage_error(self, project):
        assert runner.invoke(app, ["inspect", "nope.sql"]).exit_code == 2
