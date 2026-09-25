"""
VALUES export round trips, driven by a real database.

This exporter writes an ``INSERT ... VALUES`` statement, so its output is not
merely read by something — it is *executed*. That makes a true round trip
possible, and these tests take it: export the table, run the generated SQL back
into a second table, and compare the two.

A literal that is merely wrong is worse here than elsewhere. An unquoted date
is not a syntax error; ``2026-09-24`` is a valid SQL expression that evaluates
to 1993, so the row inserts and nobody is told.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from execsql.exporters.values import export_values

from .conftest import COLUMNS, HEADERS, TABLE_NAME, _ddl

COPY_TABLE = f"{TABLE_NAME}_copy"


def _generated_sql(db, outfile, columns="*"):
    hdrs, rows = db.select_data(f"select {columns} from {TABLE_NAME} order by id;")
    export_values(str(outfile), hdrs, iter(rows))
    return outfile.read_text(encoding="utf-8")


def _values_lines(sql):
    """The ``(...)`` tuples of the VALUES list."""
    return [ln.strip().rstrip(",") for ln in sql.splitlines() if ln.strip().startswith("(") and "INSERT" not in ln]


class TestGeneratedLiterals:
    def test_date_is_quoted(self, export_db, tmp_path):
        """Unquoted, ``2026-09-24`` is arithmetic — PostgreSQL inserts 1993."""
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        assert "'2026-09-24'" in sql, "date emitted without quotes"
        assert ", 2026-09-24," not in sql

    def test_timestamp_is_quoted(self, export_db, tmp_path):
        """Unquoted, the space in a timestamp is a syntax error."""
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        assert "'2026-09-24 13:45:56" in sql

    def test_numbers_are_not_quoted(self, export_db, tmp_path):
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        assert "-42" in sql
        assert "'-42'" not in sql, "a number was quoted as text"

    def test_null_is_the_null_keyword(self, export_db, tmp_path):
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        assert "NULL" in sql
        assert "'None'" not in sql

    def test_embedded_quote_is_doubled(self, export_db, tmp_path):
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        assert "O''Brien" in sql, "a single quote in a value was not escaped"


class TestGeneratedSqlActuallyRuns:
    """Execute the generated statement and compare the round trip.

    Reading the output proves it looks right; running it proves it is right.
    """

    def _run_into_copy(self, db, sql_text, dbms):
        """Create a copy table, execute the generated INSERT against it, return its rows."""
        insert_sql = sql_text.replace("!!target_table!!", COPY_TABLE)
        with db._cursor() as curs:
            curs.execute(f"drop table if exists {COPY_TABLE};")
            curs.execute(_ddl(dbms).replace(TABLE_NAME, COPY_TABLE))
        db.commit()
        with db._cursor() as curs:
            curs.execute(insert_sql)
        db.commit()
        return db.select_data(f"select * from {COPY_TABLE} order by id;")

    def test_the_statement_executes_without_error(self, export_db, tmp_path):
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        self._run_into_copy(export_db, sql, export_db.dbms_name)

    def test_every_row_arrives(self, export_db, tmp_path):
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        _, copied = self._run_into_copy(export_db, sql, export_db.dbms_name)
        assert len(copied) == 2

    def test_the_date_is_still_the_date(self, export_db, tmp_path):
        """The failure this guards was silent: the row inserted, with 1993 in it."""
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        _, copied = self._run_into_copy(export_db, sql, export_db.dbms_name)
        value = copied[0][HEADERS.index("d_date")]
        as_date = value if isinstance(value, datetime.date) else datetime.date.fromisoformat(str(value)[:10])
        assert as_date == datetime.date(2026, 9, 24)

    def test_the_numeric_value_survives(self, export_db, tmp_path):
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        _, copied = self._run_into_copy(export_db, sql, export_db.dbms_name)
        assert Decimal(str(copied[0][HEADERS.index("n_dec")])) == Decimal("1234.567")

    def test_the_awkward_text_survives(self, export_db, tmp_path):
        """Quote, comma, tab and newline, through a generated SQL statement."""
        _, original = export_db.select_data(f"select * from {TABLE_NAME} order by id;")
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        _, copied = self._run_into_copy(export_db, sql, export_db.dbms_name)
        col = HEADERS.index("t_awkward")
        assert copied[0][col] == original[0][col]

    def test_unicode_survives(self, export_db, tmp_path):
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        _, copied = self._run_into_copy(export_db, sql, export_db.dbms_name)
        assert copied[0][HEADERS.index("t_unicode")] == "café — naïve ± 30° ⚡"

    def test_nulls_arrive_as_nulls(self, export_db, tmp_path):
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        _, copied = self._run_into_copy(export_db, sql, export_db.dbms_name)
        nulls = [v for name, v in zip(HEADERS, copied[1]) if name != "id"]
        assert set(nulls) == {None}, f"a NULL did not survive: {copied[1]}"

    def test_zero_is_still_zero(self, export_db, tmp_path):
        sql = _generated_sql(export_db, tmp_path / "out.sql")
        _, copied = self._run_into_copy(export_db, sql, export_db.dbms_name)
        assert copied[0][HEADERS.index("n_zero")] == 0


def _cleanup(db):
    try:
        with db._cursor() as curs:
            curs.execute(f"drop table if exists {COPY_TABLE};")
        db.commit()
    except Exception:
        pass


def test_zz_drop_copy_table(export_db):
    """Leave no copy table behind for the next backend."""
    _cleanup(export_db)
    assert COLUMNS  # keeps the import meaningful
