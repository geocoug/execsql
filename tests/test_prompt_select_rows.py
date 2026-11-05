"""The real row-picker handler saves only confirmed selections, using typed parameters."""

from __future__ import annotations

import sqlite3

import pytest

from execsql import run
from execsql import state
from execsql.db.sqlite import SQLiteDatabase
from execsql.metacommands import prompt
from execsql.utils.gui import GUI_SELECTROWS

COMMAND = '-- !x! PROMPT SELECT_ROWS FROM source INTO destination MESSAGE "Choose"\n'


@pytest.fixture
def database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "picker.db"))
    db.conn.executescript(
        'create table source ("from" text, id integer, data blob);'
        "create table destination (extra text default 'new', data blob, id integer, \"from\" text);",
    )
    db.conn.executemany("insert into source values (?, ?, ?)", [("O'Brien", 2**60, b"\x00\xff"), (None, 2, b"")])
    db.conn.execute("insert into destination values (?, ?, ?, ?)", ("existing", b"old", 0, "keep"))
    db.conn.commit()
    yield db
    db.close()


def _respond(monkeypatch, response):
    class Manager:
        def put(self, spec):
            assert spec.gui_type == GUI_SELECTROWS
            spec.return_queue.put(response(spec.args) if callable(response) else response)

    monkeypatch.setattr(prompt, "enable_gui", lambda: setattr(state, "gui_manager_queue", Manager()))


def _rows(db):
    return db.conn.execute('select extra, data, id, "from" from destination').fetchall()


def test_continue_saves_typed_duplicates_and_preserves_existing_rows_and_defaults(database, monkeypatch):
    def choose(args):
        assert args["headers1"] == ["from", "id", "data"]
        assert args["headers2"] == ["extra", "data", "id", "from"]
        assert args["rows2"] == [("existing", b"old", 0, "keep")]
        return {"button": 1, "rows": [args["rows1"][0], args["rows1"][0], args["rows1"][1]]}

    _respond(monkeypatch, choose)
    result = run(sql=COMMAND, connection=database)
    assert result.success, result.errors
    expected = [
        ("existing", b"old", 0, "keep"),
        ("new", b"\x00\xff", 2**60, "O'Brien"),
        ("new", b"\x00\xff", 2**60, "O'Brien"),
        ("new", b"", 2, None),
    ]
    assert _rows(database) == expected
    observer = sqlite3.connect(database.db_name)
    try:
        assert observer.execute('select extra, data, id, "from" from destination').fetchall() == expected
    finally:
        observer.close()


def test_autocommit_off_keeps_selections_pending_and_rollback_removes_them(database, monkeypatch):
    _respond(monkeypatch, lambda args: {"button": 1, "rows": args["rows1"]})
    result = run(sql="-- !x! AUTOCOMMIT OFF\n" + COMMAND, connection=database)
    assert result.success, result.errors
    assert len(_rows(database)) == 3
    assert database.conn.in_transaction
    database.conn.rollback()
    assert _rows(database) == [("existing", b"old", 0, "keep")]


def test_end_batch_commits_selections_when_the_prompt_is_the_only_write(database, monkeypatch):
    _respond(monkeypatch, lambda args: {"button": 1, "rows": args["rows1"]})
    result = run(sql="-- !x! BEGIN BATCH\n" + COMMAND + "-- !x! END BATCH\n", connection=database)
    assert result.success, result.errors
    assert len(_rows(database)) == 3
    assert not database.conn.in_transaction


def test_cancel_halt_preserves_the_callers_transaction(database, monkeypatch):
    database.conn.execute("insert into destination (id, \"from\") values (9, 'pending')")
    before = _rows(database)
    _respond(monkeypatch, {"button": None})
    result = run(sql="-- !x! AUTOCOMMIT OFF\n" + COMMAND, connection=database)
    assert not result.success
    assert _rows(database) == before
    assert database.conn.in_transaction


@pytest.mark.parametrize("ending", ["-- !x! ROLLBACK BATCH\n-- !x! END BATCH\n", "-- !x! HALT\n-- !x! END BATCH\n"])
def test_batches_roll_back_selections_even_when_the_prompt_is_the_only_write(database, monkeypatch, ending):
    _respond(monkeypatch, lambda args: {"button": 1, "rows": args["rows1"]})
    result = run(sql="-- !x! BEGIN BATCH\n" + COMMAND + ending, connection=database)
    assert result.success == ("HALT" not in ending), result.errors
    assert _rows(database) == [("existing", b"old", 0, "keep")]


@pytest.mark.parametrize(
    "response",
    [{"button": 1, "rows": []}, {"button": 1, "rows": None}, {"button": None, "rows": [["ignored", 1, b""]]}],
)
def test_empty_unavailable_or_cancelled_selection_does_not_commit_pending_work(database, monkeypatch, response):
    database.conn.execute("insert into destination (id, \"from\") values (9, 'pending')")
    before = _rows(database)
    _respond(monkeypatch, response)
    result = run(sql="-- !x! CANCEL_HALT OFF\n" + COMMAND, connection=database)
    assert result.success, result.errors
    assert _rows(database) == before
    assert database.conn.in_transaction
    database.conn.rollback()
    assert _rows(database) == [("existing", b"old", 0, "keep")]


@pytest.mark.parametrize("response", [{"button": 1}, {"button": 1, "rows": [["wrong width"]]}])
def test_an_unhandled_or_malformed_response_is_an_error_not_an_empty_selection(database, monkeypatch, response):
    _respond(monkeypatch, response)
    result = run(sql=COMMAND, connection=database)
    assert not result.success
    assert "row-selection dialog" in result.errors[0].message
    assert _rows(database) == [("existing", b"old", 0, "keep")]


def test_a_late_constraint_error_rolls_back_the_whole_selection(database, monkeypatch):
    database.conn.execute("create unique index unique_id on destination (id)")
    database.conn.commit()
    _respond(monkeypatch, lambda args: {"button": 1, "rows": [args["rows1"][0]] * 2})
    result = run(sql=COMMAND, connection=database)
    assert not result.success
    assert "UNIQUE constraint" in result.errors[0].message
    assert _rows(database) == [("existing", b"old", 0, "keep")]
    assert not database.conn.in_transaction


@pytest.mark.parametrize("batch_rollback", [False, True])
def test_a_separate_destination_connection_uses_its_transaction(database, tmp_path, monkeypatch, batch_rollback):
    target = tmp_path / "target.db"
    with sqlite3.connect(target) as conn:
        conn.execute('create table destination (id integer, "from" text, data blob)')
    _respond(monkeypatch, lambda args: {"button": 1, "rows": args["rows1"]})
    command = COMMAND.replace("INTO destination", "INTO destination IN target")
    if batch_rollback:
        command = (
            "-- !x! BEGIN BATCH\n"
            + command
            + "-- !x! ROLLBACK BATCH\n-- !x! END BATCH\n-- !x! USE target\n"
            + "insert into destination (id, \"from\") values (9, 'after rollback');\n"
        )
    result = run(sql=f'-- !x! CONNECT TO SQLITE(FILE="{target}") AS target\n' + command, connection=database)
    assert result.success, result.errors
    with sqlite3.connect(target) as conn:
        expected = (
            [(9, "after rollback", None)] if batch_rollback else [(2**60, "O'Brien", b"\x00\xff"), (2, None, b"")]
        )
        assert conn.execute("select * from destination").fetchall() == expected
    assert _rows(database) == [("existing", b"old", 0, "keep")]
