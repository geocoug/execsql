"""Every run ends its section of ``execsql.log`` with exactly one ``exit`` record.

``exit_now`` closed the log before the ``atexit`` handler wrote the record,
so a run that failed, halted or was cancelled ended with no ``exit`` line
and could not be told apart from one still running or killed.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys

import pytest


def _run(tmp_path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "s.sql"
    script.write_text(body)
    return subprocess.run(
        [sys.executable, "-m", "execsql", "run", str(script), "--dsn", f"sqlite:///{tmp_path / 't.db'}", "-n"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=60,
    )


def _exit_records(tmp_path) -> list[list[str]]:
    lines = (tmp_path / "execsql.log").read_text().splitlines()
    return [line.split("\t") for line in lines if line.startswith("exit\t")]


@pytest.mark.parametrize(
    ("body", "exit_type"),
    [
        ("select 1;\n", "end_of_script"),
        ("select * from no_such_table;\n", "error"),
        ("-- !x! FROBNICATE\n", "error"),
        ('-- !x! HALT MESSAGE "stop here" EXIT_STATUS 3\n', "halt"),
    ],
    ids=["success", "sql-error", "metacommand-error", "halt"],
)
def test_one_exit_record_per_run(tmp_path, body, exit_type):
    _run(tmp_path, body)
    records = _exit_records(tmp_path)
    assert len(records) == 1, records
    assert records[0][2] == exit_type


def test_the_error_record_carries_the_message(tmp_path):
    _run(tmp_path, "select * from no_such_table;\n")
    (record,) = _exit_records(tmp_path)
    assert "no such table: no_such_table" in record[4]


@pytest.mark.skipif(not hasattr(signal, "SIGINT") or os.name == "nt", reason="POSIX signal delivery")
def test_ctrl_c_is_recorded_as_interrupted(tmp_path):
    _run(tmp_path, "-- !x! SYSTEM_CMD (sh -c 'kill -INT $PPID; sleep 5')\nselect 1;\n")
    records = _exit_records(tmp_path)
    assert len(records) == 1, records
    assert records[0][2] == "interrupted"


def test_run_db_file_names_the_database_file(tmp_path):
    """The run header says which database file the run used (it was blank for SQLite, DuckDB and Access)."""
    _run(tmp_path, "select 1;\n")
    lines = (tmp_path / "execsql.log").read_text().splitlines()
    (record,) = [line.split("\t") for line in lines if line.startswith("run_db_file\t")]
    assert record[2].endswith("t.db")
