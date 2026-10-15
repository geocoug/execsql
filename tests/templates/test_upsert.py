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


def test_excluded_columns_are_neither_null_checked_nor_updated(tables, tmp_path):
    """exclude_null_checks lets a NULL through QA; exclude_cols keeps the update off that column.

    The pair is how the docs say to load a table whose column the database
    fills itself (a trigger, a default): the staging NULL never reaches it.
    """
    _stage(tables, books=["(10, 1, NULL)"])
    control = "#ups_control" if tables.server.prefix == "ss" else tables.base_table("ups_control")
    body = (
        f'-- !x! EXECUTE SCRIPT STAGED_TO_LOAD WITH (control_table={control}, table_list="books, authors")\n'
        f"update {control} set display_changes = 'No';\n"
        f"update {control} set exclude_cols = '''title''', exclude_null_checks = '''title''' "
        "where table_name = 'books';\n"
        f"-- !x! EXECUTE SCRIPT LOAD_STAGING WITH ({tables.staging_args}, control_table={control}, do_commit=Yes)\n"
    )
    result = tables.run("upsert", body, tmp_path=tmp_path)
    assert result.success, result.errors
    # The staging NULL never reaches book 10's title.  (An excluded column is
    # left out of inserts too, so a new row gets the column's default.)
    assert _base(tables)[1] == [(10, 1, "Old")]


def test_the_log_file_records_the_load(tables, tmp_path):
    _stage(tables)
    body = "-- !x! SUB logfile load.log\n-- !x! SUB log_changes Yes\n-- !x! SUB log_sql Yes\n"
    control = "#ups_control" if tables.server.prefix == "ss" else tables.base_table("ups_control")
    body += (
        f'-- !x! EXECUTE SCRIPT STAGED_TO_LOAD WITH (control_table={control}, table_list="books, authors")\n'
        f"update {control} set display_changes = 'No';\n"
        f"-- !x! EXECUTE SCRIPT LOAD_STAGING WITH ({tables.staging_args}, control_table={control}, do_commit=Yes)\n"
    )
    result = tables.run("upsert", body, tmp_path=tmp_path)
    assert result.success, result.errors
    log = (tmp_path / "load.log").read_text()
    assert "CHANGES COMMITTED" in log
    assert "books" in log and "authors" in log


@pytest.fixture
def pk_update(target):
    """authors (1, 'A'), (2, 'B') in base; staging lists old keys with their new_ values."""
    target.template("upsert")
    authors = target.base_table("authors")
    target.execute(
        f"create table {authors} (id integer primary key, name varchar(20) not null)",
        f"insert into {authors} values (1, 'A')",
        f"insert into {authors} values (2, 'B')",
        f"create table {target.staging_table('authors')} (id integer, new_id integer)",
    )
    return target


def _update_keys(target, tmp_path, *pairs):
    target.execute(*(f"insert into {target.staging_table('authors')} values ({old}, {new})" for old, new in pairs))
    body = (
        f"-- !x! EXECUTE SCRIPT UPDTPK_ONE WITH ({target.staging_args}, table=authors, "
        "display_errors=No, display_changes=No)\n"
    )
    result = target.run("upsert", body, tmp_path=tmp_path)
    assert result.success, result.errors
    return target.query(f"select id, name from {target.base_table('authors')} order by id")


def test_updtpk_one_changes_a_primary_key(pk_update, tmp_path):
    assert _update_keys(pk_update, tmp_path, (1, 10)) == [(2, "B"), (10, "A")]


def test_updtpk_one_refuses_a_key_that_is_already_taken(pk_update, tmp_path):
    # The QA (UPDTPKQA_ONE) finds the new key 2 already in use; nothing changes.
    assert _update_keys(pk_update, tmp_path, (1, 2)) == [(1, "A"), (2, "B")]
