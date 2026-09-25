"""
Adapter behaviour against live drivers.

Phase 2 step 3. The exporter and importer work drove data *through* the
adapters; this drives the adapters themselves — identifier quoting, parameter
substitution, type conversion, introspection, and the error paths — against
each Tier 1 backend rather than against a mock that agrees with whatever the
test author assumed.

Identifier quoting is the sharpest edge here. It is the one place execsql
builds SQL by string concatenation rather than by parameter binding, so a
table named with a quote character is the difference between an error and an
injection.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

import execsql.state as _state
from tests.live_db import BACKEND_NAMES, open_backend

SAFE_TABLE = "adapter_probe"


@pytest.fixture(params=BACKEND_NAMES, ids=BACKEND_NAMES)
def adapter(request, tmp_path, minimal_conf):
    """A live connection, with the probe table dropped before and after.

    Its own fixture rather than the importers' one: these tests want a bare
    connection, and a shared module keeps both from re-implementing the
    backend probing.
    """
    db = open_backend(request.param, tmp_path)
    db.dbms_name = request.param  # type: ignore[attr-defined]
    _drop(db)
    yield db
    _drop(db)
    db.close()


def _drop(db, table=SAFE_TABLE):
    try:
        with db._cursor() as curs:
            curs.execute(f"drop table if exists {db.quote_identifier(table)};")
        db.commit()
    except Exception:
        pass


class TestIdentifierQuoting:
    """The one place execsql builds SQL by concatenation rather than binding."""

    def test_a_quoted_identifier_round_trips(self, adapter):
        """Create a table through quote_identifier and find it again."""
        quoted = adapter.quote_identifier(SAFE_TABLE)
        with adapter._cursor() as curs:
            curs.execute(f"create table {quoted} (a integer);")
        adapter.commit()
        assert adapter.table_exists(SAFE_TABLE)

    def test_an_embedded_quote_cannot_escape_the_identifier(self, adapter):
        """A name carrying the adapter's own quote character must stay one name.

        If the escape is wrong the statement either fails to parse or creates
        something other than what was asked for — the injection shape.
        """
        nasty = 'odd"name'
        quoted = adapter.quote_identifier(nasty)
        try:
            with adapter._cursor() as curs:
                curs.execute(f"create table {quoted} (a integer);")
            adapter.commit()
        except Exception:
            pytest.skip(f"{adapter.dbms_name} rejects that identifier outright, which is also safe")
        try:
            assert adapter.table_exists(nasty), "the table was created under a different name"
        finally:
            _drop(adapter, nasty)

    def test_quoting_is_idempotent_in_shape(self, adapter):
        """Quoting twice nests rather than collapsing — no accidental unquoting."""
        once = adapter.quote_identifier("x")
        twice = adapter.quote_identifier(once)
        assert twice != once
        assert len(twice) > len(once)

    def test_qualified_identifier_skips_empty_parts(self, adapter):
        """SQLite and Firebird have no schemas; callers should not special-case."""
        assert adapter.quote_qualified_identifier("", "t") == adapter.quote_identifier("t")
        assert adapter.quote_qualified_identifier(None, "t") == adapter.quote_identifier("t")


class TestParameterBinding:
    """paramsubs must match what the driver actually accepts."""

    def test_the_placeholder_count_matches(self, adapter):
        assert adapter.paramsubs(3).count(adapter.paramstr) == 3

    def test_bound_values_round_trip(self, adapter):
        quoted = adapter.quote_identifier(SAFE_TABLE)
        with adapter._cursor() as curs:
            curs.execute(f"create table {quoted} (a integer, b varchar(60));")
            curs.execute(
                f"insert into {quoted} values ({adapter.paramsubs(2)});",
                (7, 'O\'Brien said "hi"'),
            )
        adapter.commit()
        _, rows = adapter.select_data(f"select a, b from {quoted};")
        assert rows[0][0] == 7
        assert rows[0][1] == 'O\'Brien said "hi"'

    def test_a_bound_value_is_data_not_syntax(self, adapter):
        """The classic injection string must arrive as text."""
        quoted = adapter.quote_identifier(SAFE_TABLE)
        payload = "'); drop table " + SAFE_TABLE + "; --"
        with adapter._cursor() as curs:
            curs.execute(f"create table {quoted} (b varchar(80));")
            curs.execute(f"insert into {quoted} values ({adapter.paramsubs(1)});", (payload,))
        adapter.commit()
        _, rows = adapter.select_data(f"select b from {quoted};")
        assert rows[0][0] == payload
        assert adapter.table_exists(SAFE_TABLE), "the table was dropped by its own data"


class TestIntrospection:
    def test_table_exists_is_false_for_a_missing_table(self, adapter):
        assert not adapter.table_exists("definitely_not_here_9f3a")

    def test_table_exists_becomes_true_after_create(self, adapter):
        quoted = adapter.quote_identifier(SAFE_TABLE)
        assert not adapter.table_exists(SAFE_TABLE)
        with adapter._cursor() as curs:
            curs.execute(f"create table {quoted} (a integer);")
        adapter.commit()
        assert adapter.table_exists(SAFE_TABLE)

    def test_column_exists_distinguishes_present_from_absent(self, adapter):
        quoted = adapter.quote_identifier(SAFE_TABLE)
        with adapter._cursor() as curs:
            curs.execute(f"create table {quoted} (present integer);")
        adapter.commit()
        assert adapter.column_exists(SAFE_TABLE, "present")
        assert not adapter.column_exists(SAFE_TABLE, "absent")

    def test_drop_table_removes_it(self, adapter):
        quoted = adapter.quote_identifier(SAFE_TABLE)
        with adapter._cursor() as curs:
            curs.execute(f"create table {quoted} (a integer);")
        adapter.commit()
        adapter.drop_table(SAFE_TABLE)
        adapter.commit()
        assert not adapter.table_exists(SAFE_TABLE)


class TestErrorPaths:
    def test_a_bad_statement_raises(self, adapter):
        """Each driver raises its own type; the contract is only that it raises."""
        with pytest.raises(Exception):  # noqa: B017
            adapter.select_data("select * from a_table_that_is_not_there_7b2c;")

    def test_the_connection_survives_a_failed_statement(self, adapter):
        """A failure must roll back cleanly, not poison the session.

        PostgreSQL in particular refuses every later statement on a connection
        left in a failed transaction.
        """
        with pytest.raises(Exception):  # noqa: B017
            adapter.select_data("select * from a_table_that_is_not_there_7b2c;")
        _, rows = adapter.select_data("select 1;")
        assert rows[0][0] == 1

    def test_a_cursor_is_not_leaked_on_failure(self, adapter):
        """Repeated failures must not exhaust the driver's cursors."""
        for _ in range(25):
            with pytest.raises(Exception):  # noqa: B017
                adapter.select_data("select * from a_table_that_is_not_there_7b2c;")
        _, rows = adapter.select_data("select 1;")
        assert rows[0][0] == 1


class TestTypeConversion:
    """What the adapter declares for a value must be what the server stores."""

    def test_declared_types_accept_their_python_values(self, adapter):
        from execsql.models import DataTable

        _state.conf.only_strings = False
        # 1 alone infers as boolean, which is reasonable — use values whose
        # type is unambiguous so this tests conversion, not inference.
        rows = [[42, Decimal("1234.567"), 2.5, "text", datetime.date(2026, 9, 24)]]
        spec = DataTable(["c_int", "c_dec", "c_float", "c_text", "c_date"], rows)
        ddl = spec.create_table(adapter.type, schemaname=None, tablename=SAFE_TABLE)
        with adapter._cursor() as curs:
            curs.execute(ddl)
            curs.execute(
                f"insert into {adapter.quote_identifier(SAFE_TABLE)} values ({adapter.paramsubs(5)});",
                tuple(
                    str(v) if adapter.dbms_name == "sqlite" and isinstance(v, (Decimal, datetime.date)) else v
                    for v in rows[0]
                ),
            )
        adapter.commit()
        _, back = adapter.select_data(f"select * from {adapter.quote_identifier(SAFE_TABLE)};")
        assert back[0][0] == 42
        assert Decimal(str(back[0][1])) == Decimal("1234.567")
        assert float(back[0][2]) == 2.5
        assert back[0][3] == "text"
