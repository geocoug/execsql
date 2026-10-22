"""DISCONNECT refuses a database an open batch has used, and matches aliases in any case (#124)."""

from __future__ import annotations

import sqlite3

from execsql import run


def _run(tmp_path, sql):
    return run(sql=sql, dsn=f"sqlite:///{tmp_path / 'main.db'}", new_db=True)


def _rows(db, table):
    with sqlite3.connect(db) as conn:
        return [r[0] for r in conn.execute(f"select v from {table}")]


def test_disconnect_from_a_database_the_batch_used_halts_and_rolls_the_batch_back(tmp_path):
    b = tmp_path / "b.db"
    sql = (
        f"-- !x! CONNECT TO SQLITE(FILE={b}, NEW) AS b\n"
        "-- !x! USE b\ncreate table t (v text);\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('in the batch');\n"
        "-- !x! USE initial\n-- !x! DISCONNECT FROM b\n-- !x! END BATCH\n"
    )
    result = _run(tmp_path, sql)
    assert not result.success
    assert "currently used in a batch" in result.errors[0].message
    assert result.errors[0].message.startswith("**** Error in metacommand.")
    assert result.errors[0].message.count("DISCONNECT FROM b") == 1
    assert _rows(b, "t") == []


def test_refused_disconnect_with_halting_off_keeps_the_connection_but_fails_the_batch(tmp_path):
    b = tmp_path / "b.db"
    sql = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n-- !x! ERROR_HALT OFF\n"
        f"-- !x! CONNECT TO SQLITE(FILE={b}, NEW) AS b\n"
        "-- !x! USE b\ncreate table t (v text);\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('in the batch');\n"
        "-- !x! USE initial\n-- !x! DISCONNECT FROM b\n"
        "-- !x! IF (METACOMMAND_ERROR()) { USE b }\ninsert into t values ('still connected');\n"
        "-- !x! END BATCH\n"
    )
    result = _run(tmp_path, sql)
    # b stayed connected: the insert after the refusal ran on it.  The
    # refusal is an error inside the batch, so END BATCH rolls it back.
    assert _rows(b, "t") == []
    assert "The batch was not committed: an error on line 9 of <inline>." in result.errors[-1].message
    assert len(result.errors) == 2  # the refusal, then END BATCH: the insert on b ran


def test_disconnect_from_a_database_the_batch_has_not_used_is_allowed(tmp_path):
    b = tmp_path / "b.db"
    sql = (
        f"-- !x! CONNECT TO SQLITE(FILE={b}, NEW) AS b\n"
        "create table t (v text);\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('on initial');\n-- !x! DISCONNECT FROM b\n-- !x! END BATCH\n"
    )
    assert _run(tmp_path, sql).success
    with sqlite3.connect(tmp_path / "main.db") as conn:
        assert conn.execute("select v from t").fetchall() == [("on initial",)]


def test_disconnect_matches_the_alias_in_any_case(tmp_path):
    b = tmp_path / "b.db"
    sql = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        f"-- !x! CONNECT TO SQLITE(FILE={b}, NEW) AS b\n"
        "-- !x! DISCONNECT FROM B\n"
        "-- !x! USE b\n"
    )
    result = _run(tmp_path, sql)
    assert len(result.errors) == 1
    assert "Unrecognized database alias: b." in result.errors[0].message


def test_disconnect_from_an_alias_that_is_not_connected_is_a_metacommand_error(tmp_path):
    out = tmp_path / "out.txt"
    sql = (
        "-- !x! METACOMMAND_ERROR_HALT OFF\n"
        "-- !x! DISCONNECT FROM stagng\n"
        f'-- !x! IF (METACOMMAND_ERROR()) {{ WRITE "error seen" TO {out} }}\n'
        f'-- !x! WRITE "carried on" TO {out}\n'
    )
    _run(tmp_path, sql)
    assert out.read_text().splitlines() == ["error seen", "carried on"]


def test_disconnect_from_an_alias_that_is_not_connected_halts_by_default(tmp_path):
    result = _run(tmp_path, "-- !x! DISCONNECT FROM stagng\n")
    assert not result.success
    assert result.errors[0].message.startswith("**** Error in metacommand.")
    assert "Unrecognized database alias: stagng." in result.errors[0].message
    assert result.errors[0].message.count("DISCONNECT FROM stagng") == 1


def test_disconnect_from_initial_is_a_metacommand_error(tmp_path):
    result = _run(tmp_path, "-- !x! DISCONNECT FROM initial\n")
    assert not result.success
    assert result.errors[0].message.startswith("**** Error in metacommand.")
    assert "You may not disconnect from the initial database used." in result.errors[0].message


def test_bare_disconnect_of_the_current_database_the_batch_used_is_refused(tmp_path):
    b = tmp_path / "b.db"
    sql = (
        f"-- !x! CONNECT TO SQLITE(FILE={b}, NEW) AS b\n"
        "-- !x! USE b\ncreate table t (v text);\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('in the batch');\n-- !x! DISCONNECT\n-- !x! END BATCH\n"
    )
    result = _run(tmp_path, sql)
    assert not result.success
    assert "currently used in a batch" in result.errors[0].message
    assert _rows(b, "t") == []


def test_disconnect_inside_a_nested_batch_from_a_database_the_outer_batch_used_is_refused(tmp_path):
    b = tmp_path / "b.db"
    sql = (
        f"-- !x! CONNECT TO SQLITE(FILE={b}, NEW) AS b\n"
        "-- !x! USE b\ncreate table t (v text);\n"
        "-- !x! BEGIN BATCH\ninsert into t values ('outer');\n-- !x! USE initial\n"
        "-- !x! BEGIN BATCH\n-- !x! DISCONNECT FROM b\n-- !x! END BATCH\n-- !x! END BATCH\n"
    )
    result = _run(tmp_path, sql)
    assert not result.success
    assert "currently used in a batch" in result.errors[0].message
    assert _rows(b, "t") == []
