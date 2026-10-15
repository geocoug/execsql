"""The compare templates: generate SQL that compares a staging table with its base table.

Each script stores a SELECT in the variable named by ``sql_var``; the tests
run it with EXPORT QUERY and check the rows.

The tables, by primary key:

    id  base       staging      what changed
    1   'x', 1     'x', 1       nothing
    2   'y', 2     'Y', 2       a: case only
    3   'z', 3     NULL, 3      a: value removed
    4   NULL, 4    'n', 4       a: value added
    5   'w', 5     (none)       row only in base
    6   (none)     'v', 6       row only in staging
"""

from __future__ import annotations

import pytest

from .conftest import known_bug, read_csv

BASE = ["(1, 'x', 1)", "(2, 'y', 2)", "(3, 'z', 3)", "(4, NULL, 4)", "(5, 'w', 5)"]
STAGING = ["(1, 'x', 1)", "(2, 'Y', 2)", "(3, NULL, 3)", "(4, 'n', 4)", "(6, 'v', 6)"]

_CASE = "the compare scripts use = under the case-insensitive default collation (MySQL, MariaDB, SQL Server): 'y' -> 'Y' reads as unchanged"


@pytest.fixture
def tables(target):
    for table in (target.base_table("t"), target.staging_table("t")):
        target.execute(f"create table {table} (id integer primary key, a varchar(10), b integer)")
    target.execute(*(f"insert into {target.base_table('t')} values {v}" for v in BASE))
    target.execute(*(f"insert into {target.staging_table('t')} values {v}" for v in STAGING))
    return target


def _compare(target, script: str, tmp_path, args: str = "") -> list[dict[str, str]]:
    body = (
        f"-- !x! EXECUTE SCRIPT {script} WITH ({target.staging_args}, table=t, sql_var=cmp_sql{args})\n"
        "-- !x! EXPORT QUERY <<!!cmp_sql!!;>> TO out.csv AS CSV\n"
    )
    result = target.run("compare", body, tmp_path=tmp_path)
    assert result.success, result.errors
    return sorted(read_csv(tmp_path / "out.csv"), key=lambda r: int(r["id"]))


def test_compare_common_tags_each_value(tables, tmp_path):
    known_bug(tables, ("mysql", "mariadb", "sqlserver"), _CASE)
    assert _compare(tables, "COMPARE_COMMON", tmp_path) == [
        {"id": "1", "a": "Same", "b": "Same"},
        {"id": "2", "a": "Different", "b": "Same"},
        {"id": "3", "a": "Old", "b": "Same"},
        {"id": "4", "a": "New", "b": "Same"},
    ]


def test_compare_common_vals_puts_old_and_new_side_by_side(tables, tmp_path):
    assert _compare(tables, "COMPARE_COMMON_VALS", tmp_path) == [
        {"id": "1", "a_old": "x", "a_new": "x", "b_old": "1", "b_new": "1"},
        {"id": "2", "a_old": "y", "a_new": "Y", "b_old": "2", "b_new": "2"},
        {"id": "3", "a_old": "z", "a_new": "", "b_old": "3", "b_new": "3"},
        {"id": "4", "a_old": "", "a_new": "n", "b_old": "4", "b_new": "4"},
    ]


def test_compare_changes_classifies_every_staging_row(tables, tmp_path):
    known_bug(tables, ("mysql", "mariadb", "sqlserver"), _CASE)
    assert _compare(tables, "COMPARE_CHANGES", tmp_path) == [
        {"id": "1", "changes": "Unchanged"},
        {"id": "2", "changes": "Changed"},
        {"id": "3", "changes": "Changed"},
        {"id": "4", "changes": "Changed"},
        {"id": "6", "changes": "NewRow"},
    ]


def test_compare_changed_classifies_every_base_row(tables, tmp_path):
    known_bug(tables, ("mysql", "mariadb", "sqlserver"), _CASE)
    assert _compare(tables, "COMPARE_CHANGED", tmp_path) == [
        {"id": "1", "changed": "Unchanged"},
        {"id": "2", "changed": "Changed"},
        {"id": "3", "changed": "Changed"},
        {"id": "4", "changed": "Changed"},
        {"id": "5", "changed": "NoNewRow"},
    ]


def test_exclude_cols_leaves_a_column_out(tables, tmp_path):
    rows = _compare(tables, "COMPARE_COMMON", tmp_path, args=", exclude_cols=\"'a'\"")
    assert rows == [{"id": str(i), "b": "Same"} for i in (1, 2, 3, 4)]


def test_include_cols_compares_only_those(tables, tmp_path):
    known_bug(tables, ("mysql", "mariadb", "sqlserver"), _CASE)
    rows = _compare(tables, "COMPARE_COMMON", tmp_path, args=", include_cols=\"'a'\"")
    assert [r["a"] for r in rows] == ["Same", "Different", "Old", "New"]
    assert all(set(r) == {"id", "a"} for r in rows)


def test_a_table_without_a_primary_key_halts(target, tmp_path, capfd):
    for table in (target.base_table("t"), target.staging_table("t")):
        target.execute(f"create table {table} (id integer, a varchar(10))")
    body = f"-- !x! EXECUTE SCRIPT COMPARE_COMMON WITH ({target.staging_args}, table=t, sql_var=cmp_sql)\n"
    result = target.run("compare", body, tmp_path=tmp_path, halt_on_error=False)
    assert not result.success
    # HALT MESSAGE writes its message to the console, not into the run's errors.
    out, err = capfd.readouterr()
    assert "Table t has no primary key columns." in out + err
