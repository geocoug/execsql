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
        assert m["statements"] == {"sql": 2, "metacommands": 8}  # INCLUDE counts
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

    def test_an_unwritable_path_fails_before_the_run(self, work):
        (work / "runs").write_text("a file, not a directory\n")
        result, _ = _run(work, "create table ran (x integer);\n", "--manifest", "runs/m.json")
        assert result.returncode == 2
        assert "Cannot write --manifest runs/m.json" in result.stderr
        assert not (work / "db.sqlite").exists()


def test_writing_ends_the_recording(tmp_path):
    import execsql.manifest as manifest_module

    manifest = manifest_module.start(str(tmp_path / "m.json"), "x.sql", [])
    assert manifest_module.current() is manifest
    manifest.finish(0)
    assert manifest_module.current() is None


def test_a_write_failure_is_reported_not_raised(tmp_path, capsys):
    (tmp_path / "blocker").write_text("x")
    manifest = RunManifest(str(tmp_path / "blocker" / "m.json"), "x.sql", [])
    manifest.finish(0)
    assert "could not write --manifest" in capsys.readouterr().err
    assert manifest.written


def test_check_writable(tmp_path):
    from execsql.manifest import check_writable

    assert check_writable(str(tmp_path / "new" / "m.json")) is None
    assert check_writable(str(tmp_path)) is not None
    (tmp_path / "f").write_text("x")
    assert check_writable(str(tmp_path / "f" / "m.json")) is not None


def test_finish_writes_once(tmp_path):
    manifest = RunManifest(str(tmp_path / "m.json"), "x.sql", [])
    manifest.finish(0)
    first = (tmp_path / "m.json").read_text()
    manifest.finish(1, RuntimeError("late"))
    assert (tmp_path / "m.json").read_text() == first


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal delivery")
@pytest.mark.parametrize("name,code", [("INT", 130), ("TERM", 143)])
def test_manifest_retains_signal_exit_status(work, name, code):
    result, manifest = _run(
        work,
        f"-- !x! SYSTEM_CMD (sh -c 'kill -{name} $PPID; sleep 1')\nselect 1;\n",
        "--manifest",
        "runs/m.json",
    )
    assert result.returncode == code
    assert manifest["exit_status"] == code
    assert manifest["statements"]["metacommands"] == 1
    log = (work / "execsql.log").read_text().splitlines()
    summary = next(line.split("\t") for line in log if "Run finished:" in line)
    assert summary[1] == manifest["run_id"]
    assert f"exit={code}; attempted=1;" in summary[-1]


@pytest.mark.parametrize("fail", [False, True])
def test_deferred_write_is_recorded_only_when_run(work, fail):
    script = '-- !x! ON ERROR_HALT WRITE "failed" TO error.txt\n'
    script += "select * from missing;\n" if fail else "select 1;\n"
    result, manifest = _run(work, script, "--manifest", "runs/m.json")
    assert result.returncode == int(fail)
    assert (work / "error.txt").exists() is fail
    assert [entry["path"] for entry in manifest["files_written"]] == (["error.txt"] if fail else [])
    if fail:
        assert manifest["files_written"][0]["line"] == 1
        assert manifest["files_written"][0]["by"] == "ON ERROR_HALT WRITE"


def test_failed_export_does_not_claim_an_existing_file_was_written(work):
    (work / "ghost.csv").write_text("original\n")
    script = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! EXPORT QUERY <<select * from missing;>> TO ghost.csv AS CSV\nselect 1;\n"
    )
    result, manifest = _run(work, script, "--manifest", "runs/m.json")
    assert result.returncode == 0
    assert manifest["errors"]
    assert manifest["files_written"] == []
    assert (work / "ghost.csv").read_text() == "original\n"


def test_failed_queued_write_is_not_a_completed_write(work):
    (work / "blocked").mkdir()
    result, manifest = _run(work, '-- !x! WRITE "lost" TO blocked\n', "--manifest", "runs/m.json")
    assert result.returncode != 0
    assert manifest["errors"]
    assert manifest["files_written"] == []


def test_cancel_handler_write_records_its_registration_location(work):
    result, manifest = _run(
        work,
        '-- !x! ON CANCEL_HALT WRITE "cancelled" TO cancel.txt\n-- !x! HALT EXIT_STATUS 2\n',
        "--manifest",
        "runs/m.json",
    )
    assert result.returncode == 2
    assert (work / "cancel.txt").read_text().strip() == "cancelled"
    assert manifest["files_written"] == [
        {"source": "s.sql", "line": 1, "by": "ON CANCEL_HALT WRITE", "path": "cancel.txt"},
    ]


def test_stdout_script_dump_does_not_claim_a_file_write(work):
    script = "-- !x! BEGIN SCRIPT example\nselect 1;\n-- !x! END SCRIPT\n-- !x! WRITE SCRIPT example TO stdout\n"
    result, manifest = _run(work, script, "--manifest", "runs/m.json")
    assert result.returncode == 0, result.stderr
    assert "select 1" in result.stdout
    assert manifest["files_written"] == []


def test_queued_write_retains_literal_path_whitespace(work):
    result, manifest = _run(work, '-- !x! WRITE "hello" TO " spaced.txt "\n', "--manifest", "runs/m.json")
    assert result.returncode == 0, result.stderr
    assert (work / " spaced.txt ").read_text().strip() == "hello"
    assert [entry["path"] for entry in manifest["files_written"]] == [" spaced.txt "]


@pytest.mark.parametrize(
    "script",
    [
        "select * from missing;\n",
        "-- !x! HALT EXIT_STATUS 0\n",
        "-- !x! IF (EQUAL(a, a))\nselect 1;\n-- !x! ENDIF\n",
        "-- !x! BEGIN SCRIPT example\nselect 1;\n-- !x! END SCRIPT\n-- !x! EXECUTE SCRIPT example\n",
        "-- !x! LOOP WHILE (EQUAL(a, a))\n-- !x! BREAK\n-- !x! ENDLOOP\n",
        "-- !x! BEGIN SQL\nselect 1;\n-- !x! END SQL\n",
    ],
)
def test_counts_align_with_python_and_log_for_control_and_failure_paths(work, script):
    from execsql import run

    _, manifest = _run(work, script, "--manifest", "runs/m.json")
    result = run(sql=script, dsn="sqlite:///:memory:")
    assert sum(manifest["statements"].values()) == result.commands_run
    summary = next(line for line in (work / "execsql.log").read_text().splitlines() if "Run finished:" in line)
    assert f"attempted={result.commands_run};" in summary


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


class TestSecrets:
    """The manifest masks passwords and token shapes; -a / --var values stay, as they form paths."""

    def test_a_decrypted_value_in_a_failing_path_is_masked(self, work):
        from execsql.utils.crypto import Encrypt

        secret = "pw_" + "Zq7Rv2Lm9Px4"  # built at runtime so secret scanners do not flag it
        script = f"-- !x! SUB_DECRYPT pw {Encrypt().encrypt(secret)}\n-- !x! IMPORT TO NEW t FROM 'in_!!pw!!.csv'\n"
        _result, m = _run(work, script, "--manifest", "runs/m.json")
        assert secret not in (work / "runs" / "m.json").read_text()
        assert "in_***.csv" in m["errors"][0]["message"]

    def test_a_token_shape_in_an_error_is_masked(self, work):
        token = "ghp_" + "A" * 36
        _result, m = _run(work, f"-- !x! IMPORT TO NEW t FROM 'in-{token}.csv'\n", "--manifest", "runs/m.json")
        assert token not in (work / "runs" / "m.json").read_text()

    def test_an_argument_in_a_path_is_kept(self, work):
        _result, m = _run(work, OK, "--var", "region=west", "-a", "x", "--manifest", "runs/m.json")
        assert [f["path"] for f in m["files_written"]][0] == "out/west.csv"
        assert m["files_read"][0]["path"] == "in.csv"


class TestNonHaltingErrors:
    def test_sql_errors_are_kept_in_order_when_the_script_continues(self, work):
        script = "-- !x! ERROR_HALT OFF\nselect * from missing_first;\nselect * from missing_second;\nselect 1;\n"
        result, manifest = _run(work, script, "--manifest", "runs/m.json")
        assert result.returncode == 0, result.stderr
        assert manifest["exit_status"] == 0
        assert [e["line"] for e in manifest["errors"]] == [2, 3]
        assert [e["source"] for e in manifest["errors"]] == ["s.sql", "s.sql"]
        assert [e["command"] for e in manifest["errors"]] == [
            "select * from missing_first;",
            "select * from missing_second;",
        ]
        assert "missing_first" in manifest["errors"][0]["message"]
        assert "missing_second" in manifest["errors"][1]["message"]

    def test_metacommand_errors_do_not_disappear_after_successful_commands(self, work):
        script = (
            "-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! USE missing_one\n-- !x! USE missing_two\n"
            '-- !x! WRITE "continued" TO after.txt\n'
        )
        result, manifest = _run(work, script, "--manifest", "runs/m.json")
        assert result.returncode == 0, result.stderr
        assert (work / "after.txt").read_text().strip() == "continued"
        assert [e["line"] for e in manifest["errors"]] == [2, 3]
        assert [e["command"] for e in manifest["errors"]] == ["USE missing_one", "USE missing_two"]

    def test_non_halting_errors_precede_a_halting_error_without_duplicates(self, work):
        script = (
            "-- !x! ERROR_HALT OFF\nselect * from missing_first;\n"
            "-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! USE missing_alias\n"
            "-- !x! ERROR_HALT ON\nselect * from missing_last;\n"
        )
        result, manifest = _run(work, script, "--manifest", "runs/m.json")
        assert result.returncode == 1
        assert manifest["exit_status"] == 1
        assert [e["line"] for e in manifest["errors"]] == [2, 4, 6]

    def test_repeated_failures_at_the_same_source_location_are_distinct(self, work):
        script = (
            "-- !x! BEGIN SCRIPT broken\nselect * from missing_table;\n-- !x! END SCRIPT\n"
            "-- !x! ERROR_HALT OFF\n-- !x! EXECUTE SCRIPT broken\n-- !x! EXECUTE SCRIPT broken\n"
        )
        result, manifest = _run(work, script, "--manifest", "runs/m.json")
        assert result.returncode == 0, result.stderr
        assert [e["line"] for e in manifest["errors"]] == [2, 2]

    def test_non_halting_errors_use_the_existing_secret_redaction(self, work):
        from execsql.utils.crypto import Encrypt

        secret = "pw_" + "Zq7Rv2Lm9Px4"
        script = (
            f"-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! SUB_DECRYPT pw {Encrypt().encrypt(secret)}\n"
            '-- !x! IMPORT TO NEW t FROM "in_!!pw!!.csv"\n-- !x! WRITE "continued" TO after.txt\n'
        )
        result, manifest = _run(work, script, "--manifest", "runs/m.json")
        assert result.returncode == 0, result.stderr
        assert len(manifest["errors"]) == 1
        assert "in_***.csv" in manifest["errors"][0]["message"]
        assert secret not in (work / "runs" / "m.json").read_text()

    @pytest.mark.parametrize("handler_halts", [False, True])
    def test_original_error_precedes_errors_in_its_halt_handler(self, work, handler_halts):
        script = (
            f"-- !x! BEGIN SCRIPT on_error\n-- !x! ERROR_HALT {'ON' if handler_halts else 'OFF'}\nselect * from handler_missing;\n"
            "-- !x! END SCRIPT\n-- !x! ON ERROR_HALT EXECUTE SCRIPT on_error\n"
            "select * from original_missing;\n"
        )
        result, manifest = _run(work, script, "--manifest", "runs/m.json")
        assert result.returncode == 1, result.stderr
        assert [e["line"] for e in manifest["errors"]] == [6, 3]
        assert "original_missing" in manifest["errors"][0]["message"]
        assert "handler_missing" in manifest["errors"][1]["message"]
