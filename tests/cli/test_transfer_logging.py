"""Transfer logs describe actual attempts without changing values or I/O."""

from __future__ import annotations

from asyncio import CancelledError
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

import execsql.state as state
from execsql.utils.fileio import Logger
from execsql.utils.transfers import log_transfer, loaded_rows, payload_query, query_counter


def _run(directory, body, *, baseline=False, extra=()):
    directory.mkdir(exist_ok=True)
    script = directory / "s.sql"
    script.write_text(body, encoding="utf-8")
    if baseline:
        # Disable only the new lifecycle decorators before dispatch imports them.
        prefix = [
            sys.executable,
            "-c",
            (
                "import execsql.utils.transfers as t; t.log_transfer=lambda operation: lambda fn: fn; "
                "from execsql.cli import _legacy_main; _legacy_main()"
            ),
        ]
    else:
        prefix = [sys.executable, "-m", "execsql"]
    return subprocess.run(
        [*prefix, "run", str(script), "--dsn", f"sqlite:///{directory / 't.db'}", "-n", *extra],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _messages(directory):
    records = [line.split("\t") for line in (directory / "execsql.log").read_text().splitlines()]
    transfers = [
        r for r in records if len(r) >= 6 and r[0] == "status" and r[5].startswith(("IMPORT ", "EXPORT ", "COPY "))
    ]
    assert all(len(r) == 6 and r[4] == "info" for r in transfers)
    return [r[5] for r in transfers]


_SETUP = (
    "create table src (n integer, label text, f real);\ninsert into src values (1, 'Ünicode', 1.25),(2, 'two', NULL);\n"
)


@pytest.mark.parametrize(
    "fmt",
    [
        "csv",
        "tsv",
        "txt",
        "json",
        "jsonl",
        "json_ts",
        "xml",
        "yaml",
        "markdown",
        "values",
        "html",
        "latex",
        "parquet",
        "feather",
        "sqlite",
        "duckdb",
        "xlsx",
        "ods",
    ],
)
def test_export_reports_consumed_rows_without_tee_double_count(tmp_path, fmt):
    if fmt == "duckdb":
        pytest.importorskip("duckdb")
    result = _run(tmp_path, _SETUP + f"-- !x! EXPORT src TEE TO result.{fmt} AS {fmt}\n")
    assert result.returncode == 0, result.stdout + result.stderr
    started, completed = _messages(tmp_path)
    assert started.startswith("EXPORT started:")
    assert completed.startswith("EXPORT completed:")
    assert "source='initial:src'" in completed
    assert "rows_read=2" in completed
    assert "duration=" in completed
    assert f"{tmp_path / 's.sql'}:3" in completed


@pytest.mark.parametrize("fmt", ["csv", "tsv", "json", "jsonl", "json_ts", "xml", "yaml", "markdown", "values"])
def test_export_bytes_match_without_transfer_instrumentation(tmp_path, fmt):
    body = _SETUP + f"-- !x! EXPORT src TO result AS {fmt}\n"
    new, old = tmp_path / "new", tmp_path / "old"
    results = [_run(new, body), _run(old, body, baseline=True)]
    assert all(r.returncode == 0 for r in results), [(r.stdout, r.stderr) for r in results]
    assert (new / "result").read_bytes() == (old / "result").read_bytes()


def test_import_copy_query_and_import_file_counts_and_values(tmp_path):
    (tmp_path / "input.csv").write_text('n,label\n1,Ünicode\n2,"  padded  "\n', encoding="utf-8")
    (tmp_path / "blob").write_bytes(b"\x00\xff\r\n")
    result = _run(
        tmp_path,
        "-- !x! IMPORT TO NEW src FROM input.csv\n"
        "-- !x! COPY src FROM initial TO NEW copied IN initial\n"
        "-- !x! COPY QUERY <<select * from src;>> FROM initial TO NEW queried IN initial\n"
        "create table blobs (v blob);\n"
        "-- !x! IMPORT_FILE TO TABLE blobs COLUMN v FROM blob\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    messages = _messages(tmp_path)
    completed = [m for m in messages if " completed:" in m]
    assert len(completed) == 4
    assert all("rows_loaded=2" in m for m in completed[:3])
    assert "source='query on initial'" in completed[2]
    assert "rows_loaded=1" in completed[3]
    assert "COPY into" in (tmp_path / "execsql.log").read_text()
    with sqlite3.connect(tmp_path / "t.db") as db:
        assert (
            db.execute("select * from src").fetchall()
            == db.execute("select * from copied").fetchall()
            == db.execute("select * from queried").fetchall()
        )
        assert db.execute("select v from blobs").fetchone()[0] == b"\x00\xff\r\n"


@pytest.mark.parametrize(
    "command",
    [
        "IMPORT TO NEW dest FROM missing.csv",
        "COPY missing FROM initial TO NEW dest IN initial",
        "EXPORT QUERY <<select 'private-row-value' from missing;>> TO result AS CSV",
    ],
)
def test_failed_nonhalting_transfer_is_not_completed(tmp_path, command):
    result = _run(tmp_path, "-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! " + command + "\nselect 1;\n")
    assert result.returncode == 0, result.stdout + result.stderr
    started, failed = _messages(tmp_path)
    assert " started:" in started and " failed:" in failed
    assert "unknown" in failed
    assert " completed:" not in failed
    assert "private-row-value" not in started + failed


@pytest.mark.parametrize("fmt", ["xlsx", "ods"])
def test_multiple_sheets_sum_payloads_not_tee(tmp_path, fmt):
    result = _run(tmp_path, _SETUP + f"-- !x! EXPORT src,src TEE TO workbook.{fmt} AS {fmt}\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rows_read=4" in _messages(tmp_path)[-1]


def test_empty_export_is_zero_not_unknown(tmp_path):
    result = _run(tmp_path, "create table src (n int);\n-- !x! EXPORT src TO empty.csv AS CSV\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rows_read=0" in _messages(tmp_path)[-1]


@pytest.fixture
def logger(tmp_path):
    state.logfile_encoding = "utf-8"
    log = Logger("<inline>", "test", None, {}, log_file_name=str(tmp_path / "log"))
    state.exec_log = log
    state.dbs = None
    state.last_command = SimpleNamespace(source="a\tfile\n.sql", line_no=1)
    yield log
    log.close()


@pytest.mark.parametrize("error", [ValueError("bad"), KeyboardInterrupt(), SystemExit(143), CancelledError()])
def test_terminal_event_precedes_exception_and_scope_is_restored(logger, error):
    @log_transfer("IMPORT")
    def transfer(**kwargs):
        loaded_rows(12)
        raise error

    with pytest.raises(type(error)):
        transfer(filename="input", table="t")
    text = Path(logger.log_file_name).read_text()
    assert ("IMPORT failed:" if isinstance(error, ValueError) else "IMPORT interrupted:") in text
    assert "rows_loaded=unknown" in text
    assert "completed:" not in text
    with payload_query("select 1"):
        assert query_counter("select 1") is None


def test_redacted_fields_preserve_generated_counts_and_tsv(logger):
    logger.add_redaction_value("secret")
    logger.add_redaction_value("1", argument=True)

    @log_transfer("IMPORT")
    def transfer(**kwargs):
        loaded_rows(1)

    transfer(filename="secret\tfile\n.csv", table="t")
    text = Path(logger.log_file_name).read_text()
    transfers = [line.split("\t") for line in text.splitlines() if "IMPORT " in line]
    assert len(transfers) == 2 and all(len(r) == 6 for r in transfers)
    assert "secret" not in "".join(r[5] for r in transfers)
    assert "rows_loaded=1" in transfers[-1][5]
    assert r"\t" in transfers[-1][5] and r"\n" in transfers[-1][5]


@pytest.mark.parametrize(
    "fmt,source",
    [("json", "JSON"), ("parquet", "PARQUET"), ("feather", "FEATHER"), ("xlsx", "EXCEL"), ("ods", "")],
)
def test_import_formats_use_actual_loader_counts(tmp_path, fmt, source):
    sheet = " SHEET src" if fmt in ("xlsx", "ods") else ""
    result = _run(
        tmp_path,
        _SETUP
        + f"-- !x! EXPORT src TO input.{fmt} AS {fmt}\n-- !x! IMPORT TO NEW dest FROM {source} input.{fmt}{sheet}\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "IMPORT completed:" in _messages(tmp_path)[-1]
    assert "rows_loaded=2" in _messages(tmp_path)[-1]


@pytest.mark.parametrize("target", ["integer", "real", "text", "blob", "numeric"])
@pytest.mark.parametrize("value", ["NULL", "1", "2.25", "'00701'", "'  Ünicode  '", "X'00ff0d0a'"])
def test_logged_copy_matches_existing_values_and_errors(tmp_path, target, value):
    body = (
        f"create table src (v);\ninsert into src values ({value});\ncreate table dest (v {target});\n"
        "-- !x! COPY src FROM initial TO dest IN initial\n"
    )
    new, old = tmp_path / "new", tmp_path / "old"
    current, previous = _run(new, body), _run(old, body, baseline=True)
    assert current.returncode == previous.returncode

    def normalized_errors(result, directory):
        return re.sub(
            r"Error occurred at .*?\.",
            "Error occurred at <TIME>.",
            result.stderr.replace(str(directory), "<DIR>"),
        )

    assert normalized_errors(current, new) == normalized_errors(previous, old)
    with sqlite3.connect(new / "t.db") as a, sqlite3.connect(old / "t.db") as b:
        assert (
            a.execute("select v, typeof(v) from dest").fetchall()
            == b.execute("select v, typeof(v) from dest").fetchall()
        )


def test_exit_now_finalizes_transfer_before_exit_record(logger):
    from execsql.exceptions import ScriptExit

    @log_transfer("EXPORT")
    def transfer(**kwargs):
        logger.log_exit_error("missing dependency")
        logger.log_exit(1)
        logger.close()
        raise ScriptExit(1)

    with pytest.raises(ScriptExit):
        transfer(filename="out", query="select 'private'", format="xlsx")
    text = Path(logger.log_file_name).read_text()
    assert text.count("EXPORT failed:") == 1
    assert "private" not in text
    assert text.index("EXPORT failed:") < text.index("Run finished:") < text.index("exit\t")


@pytest.mark.parametrize("source", ["src", "QUERY <<select * from src;>>"])
def test_template_counts_and_tee(tmp_path, source):
    (tmp_path / "template").write_text("$n $label\n", encoding="utf-8")
    result = _run(tmp_path, _SETUP + f"-- !x! EXPORT {source} TEE TO result WITH TEMPLATE template\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rows_read=2" in _messages(tmp_path)[-1]


def test_metadata_exports_count_records_and_loaded_rows(tmp_path):
    result = _run(
        tmp_path,
        _SETUP
        + "-- !x! EXPORT src TO data.csv AS CSV\n-- !x! EXPORT_METADATA ALL TO metadata.csv AS CSV\n-- !x! EXPORT_METADATA ALL INTO NEW TABLE metadata\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    completed = [m for m in _messages(tmp_path) if " completed:" in m]
    assert "source='export metadata'" in completed[1]
    assert "rows_read=1" in completed[1] and "rows_loaded=1" in completed[2]


@pytest.mark.parametrize("fmt", ["raw", "b64"])
def test_raw_exports_report_rows_and_preserve_bytes(tmp_path, fmt):
    body = (
        f"create table src (v text);\ninsert into src values ('YQ=='),('Yg==');\n-- !x! EXPORT src TO result AS {fmt}\n"
    )
    new, old = tmp_path / "new", tmp_path / "old"
    results = [_run(new, body), _run(old, body, baseline=True)]
    assert all(r.returncode == 0 for r in results), [(r.stdout, r.stderr) for r in results]
    assert "rows_read=2" in _messages(new)[-1]
    assert (new / "result").read_bytes() == (old / "result").read_bytes()


def test_oracle_trailing_semicolon_does_not_lose_counts(logger):
    @log_transfer("EXPORT")
    def transfer(**kwargs):
        with payload_query("select * from t;"):
            completed = query_counter("select * from t")
            assert completed is not None
            completed(2)

    transfer(filename="out", table="t")
    assert "rows_read=2" in Path(logger.log_file_name).read_text()
