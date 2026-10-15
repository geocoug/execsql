"""The upsert templates: QA-check staging tables, then update and insert their base tables.

There is no PostgreSQL template: the PG_UPSERT metacommand replaced
``pg_upsert.sql``, so the PostgreSQL cases skip.

Two tables, books referencing authors:

    authors  base: (1, 'A')                 staging: (1, 'A2'), (2, 'B')
    books    base: (10, 1, 'Old')           staging: (10, 1, 'New'), (11, 2, 'Second')

so a clean load updates one row and inserts one row in each table, and must
load authors before books for the new book's author to exist.
"""

from __future__ import annotations

import pytest

from .conftest import read_csv


AUTHORS = ["(1, 'A2')", "(2, 'B')"]
BOOKS = ["(10, 1, 'New')", "(11, 2, 'Second')"]


@pytest.fixture
def tables(target):
    target.template("upsert")  # skips PostgreSQL, which has no upsert template
    a, b = target.base_table("authors"), target.base_table("books")
    target.execute(
        f"create table {a} (id integer primary key, name varchar(20) not null)",
        f"create table {b} (id integer primary key, author_id integer not null, title varchar(20) not null, "
        f"constraint fk_books_author foreign key (author_id) references {a} (id))",
        f"create table {target.staging_table('authors')} (id integer, name varchar(20))",
        f"create table {target.staging_table('books')} (id integer, author_id integer, title varchar(20))",
        f"insert into {a} values (1, 'A')",
        f"insert into {b} values (10, 1, 'Old')",
    )
    return target


def _stage(target, authors=AUTHORS, books=BOOKS) -> None:
    target.execute(
        *(f"insert into {target.staging_table('authors')} values {v}" for v in authors),
        *(f"insert into {target.staging_table('books')} values {v}" for v in books),
    )


def _load(target, tmp_path, do_commit: str = "Yes") -> dict[str, tuple]:
    """STAGED_TO_LOAD then LOAD_STAGING; return the control table's rows by table name.

    The control table is read inside the run: on SQL Server it must be a
    temporary table (``#`` prefix), which no other connection can see.  CSV
    turns NULL into ``""`` and every value into text.
    """
    control = "#ups_control" if target.server.prefix == "ss" else target.base_table("ups_control")
    body = (
        f'-- !x! EXECUTE SCRIPT STAGED_TO_LOAD WITH (control_table={control}, table_list="books, authors")\n'
        # The default shows each table's changes in a GUI dialog for approval.
        f"update {control} set display_changes = 'No';\n"
        f"-- !x! EXECUTE SCRIPT LOAD_STAGING WITH ({target.staging_args}, control_table={control}, do_commit={do_commit})\n"
        "-- !x! EXPORT QUERY <<select table_name, null_errors, pk_errors, fk_errors, rows_updated, rows_inserted "
        f"from {control};>> TO control.csv AS CSV\n"
    )
    result = target.run("upsert", body, tmp_path=tmp_path)
    assert result.success, result.errors
    rows = read_csv(tmp_path / "control.csv")
    return {
        r["table_name"]: (r["null_errors"], r["pk_errors"], r["fk_errors"], r["rows_updated"], r["rows_inserted"])
        for r in rows
    }


def _base(target) -> tuple[list[tuple], list[tuple]]:
    return (
        target.query(f"select id, name from {target.base_table('authors')} order by id"),
        target.query(f"select id, author_id, title from {target.base_table('books')} order by id"),
    )


def test_a_clean_load_updates_and_inserts_in_foreign_key_order(tables, tmp_path):
    _stage(tables)
    control = _load(tables, tmp_path)
    assert control == {
        "authors": ("", "", "", "1", "1"),
        "books": ("", "", "", "1", "1"),
    }
    assert _base(tables) == ([(1, "A2"), (2, "B")], [(10, 1, "New"), (11, 2, "Second")])


def test_do_commit_no_leaves_the_base_tables_unchanged(tables, tmp_path, capfd):
    _stage(tables)
    if tables.server.prefix == "md":
        # MySQL/MariaDB commit at every CREATE/DROP, which the load runs: the
        # script refuses a dry run instead of committing it.
        control = tables.base_table("ups_control")
        body = (
            f'-- !x! EXECUTE SCRIPT STAGED_TO_LOAD WITH (control_table={control}, table_list="books, authors")\n'
            f"-- !x! EXECUTE SCRIPT LOAD_STAGING WITH ({tables.staging_args}, control_table={control}, do_commit=No)\n"
        )
        result = tables.run("upsert", body, tmp_path=tmp_path, halt_on_error=False)
        assert not result.success
        out, err = capfd.readouterr()
        assert "cannot run with do_commit=No on MySQL or MariaDB" in out + err
    else:
        _load(tables, tmp_path, do_commit="No")
    assert _base(tables) == ([(1, "A")], [(10, 1, "Old")])


def test_do_commit_no_still_reports_what_would_change(tables, tmp_path):
    if tables.server.prefix == "md":
        pytest.skip("MySQL/MariaDB refuse a dry run (see above)")
    _stage(tables)
    control = _load(tables, tmp_path, do_commit="No")
    assert control["authors"][3:] == ("1", "1")
    assert control["books"][3:] == ("1", "1")


def test_a_null_in_a_required_column_stops_the_load(tables, tmp_path):
    _stage(tables, books=["(10, 1, NULL)", "(11, 2, 'Second')"])
    control = _load(tables, tmp_path)
    assert control["books"][0] == "title (1)"
    assert _base(tables) == ([(1, "A")], [(10, 1, "Old")])


def test_a_duplicate_primary_key_stops_the_load(tables, tmp_path):
    _stage(tables, books=["(10, 1, 'New')", "(11, 2, 'Second')", "(11, 2, 'Again')"])
    control = _load(tables, tmp_path)
    assert control["books"][1] != ""
    assert _base(tables) == ([(1, "A")], [(10, 1, "Old")])


def test_a_missing_foreign_key_stops_the_load(tables, tmp_path):
    _stage(tables, books=["(10, 1, 'New')", "(12, 99, 'Orphan')"])
    control = _load(tables, tmp_path)
    assert "fk_books_author" in control["books"][2]
    assert _base(tables) == ([(1, "A")], [(10, 1, "Old")])


def test_a_foreign_key_satisfied_by_another_staging_table_passes(tables, tmp_path):
    # Book 11's author 2 is only in staging authors: QA must look there too.
    _stage(tables, books=["(11, 2, 'Second')"])
    control = _load(tables, tmp_path)
    assert control["books"][2] == ""
    assert _base(tables)[1] == [(10, 1, "Old"), (11, 2, "Second")]
