"""
Tests for execsql.db.base — Database abstract base and DatabasePool.

Database.open_db() requires a real driver connection; those tests are
deferred to integration tests.  Here we test:

- Database construction, repr, and pure-logic helpers.
- DatabasePool init, add, aliases, current, make_current, disconnect
  (using a lightweight fake ``Database`` subclass that never opens a
  connection).
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from execsql.db.base import Database, DatabasePool
from execsql.exceptions import ErrInfo, DatabaseNotImplementedError


# ---------------------------------------------------------------------------
# Fake database subclass — never connects to anything
# ---------------------------------------------------------------------------


class FakeDatabase(Database):
    """Minimal Database subclass for testing DatabasePool without a driver."""

    def __init__(self, server=None, db=None):
        super().__init__(server_name=server, db_name=db)
        # type must be set or name() will fail (self.type.dbms_id)
        self.type = SimpleNamespace(dbms_id="fake")

    def open_db(self):
        # Do not raise — pretend the connection succeeds instantly.
        pass

    def close(self):
        self.conn = None

    def rollback(self):
        pass


# ---------------------------------------------------------------------------
# Database base class
# ---------------------------------------------------------------------------


class TestDatabaseInit:
    def test_server_name_stored(self):
        db = FakeDatabase(server="myhost", db="mydb")
        assert db.server_name == "myhost"

    def test_db_name_stored(self):
        db = FakeDatabase(db="mydb")
        assert db.db_name == "mydb"

    def test_user_none_by_default(self):
        db = Database(server_name=None, db_name=None)
        assert db.user is None

    def test_password_none_initially(self):
        db = Database(server_name=None, db_name=None)
        assert db.password is None

    def test_conn_none_initially(self):
        db = Database(server_name=None, db_name=None)
        assert db.conn is None

    def test_autocommit_true_by_default(self):
        db = Database(server_name=None, db_name=None)
        assert db.autocommit is True

    def test_paramstr_default(self):
        db = Database(server_name=None, db_name=None)
        assert db.paramstr == "?"


class TestDatabaseRepr:
    def test_repr_contains_server_and_db(self):
        db = Database(server_name="myhost", db_name="mydb")
        r = repr(db)
        assert "myhost" in r
        assert "mydb" in r

    def test_repr_starts_with_database(self):
        db = Database(server_name=None, db_name=None)
        assert repr(db).startswith("Database(")


class TestDatabaseName:
    def test_name_with_server(self):
        db = FakeDatabase(server="myhost", db="mydb")
        name = db.name()
        assert "myhost" in name
        assert "mydb" in name

    def test_name_without_server(self):
        db = FakeDatabase(server=None, db="myfile.db")
        name = db.name()
        assert "myfile.db" in name


class TestDatabaseOpenDbNotImplemented:
    def test_open_db_raises_database_not_implemented(self):
        db = Database(server_name=None, db_name="x")
        db.type = SimpleNamespace(dbms_id="abstract")
        with pytest.raises(DatabaseNotImplementedError):
            db.open_db()


# ---------------------------------------------------------------------------
# quote_identifier
# ---------------------------------------------------------------------------


class TestQuoteIdentifier:
    def test_simple_identifier(self):
        db = Database(server_name=None, db_name=None)
        assert db.quote_identifier("my_table") == '"my_table"'

    def test_identifier_with_embedded_double_quote(self):
        db = Database(server_name=None, db_name=None)
        assert db.quote_identifier('my"table') == '"my""table"'

    def test_identifier_with_multiple_double_quotes(self):
        db = Database(server_name=None, db_name=None)
        assert db.quote_identifier('a"b"c') == '"a""b""c"'

    def test_empty_identifier(self):
        db = Database(server_name=None, db_name=None)
        assert db.quote_identifier("") == '""'

    def test_identifier_with_spaces(self):
        db = Database(server_name=None, db_name=None)
        assert db.quote_identifier("my table") == '"my table"'

    def test_identifier_with_special_chars(self):
        db = Database(server_name=None, db_name=None)
        assert db.quote_identifier("col; DROP TABLE--") == '"col; DROP TABLE--"'


# ---------------------------------------------------------------------------
# DatabasePool
# ---------------------------------------------------------------------------


class TestDatabasePoolInit:
    def test_pool_empty_initially(self):
        p = DatabasePool()
        assert p.aliases() == []

    def test_repr(self):
        p = DatabasePool()
        assert repr(p) == "DatabasePool()"

    def test_initial_db_none(self):
        p = DatabasePool()
        assert p.initial_db is None

    def test_current_db_none(self):
        p = DatabasePool()
        assert p.current_db is None

    def test_do_rollback_true(self):
        p = DatabasePool()
        assert p.do_rollback is True


class TestDatabasePoolAdd:
    def test_add_first_db_sets_initial_and_current(self):
        p = DatabasePool()
        db = FakeDatabase(server="s", db="d")
        p.add("main", db)
        assert p.initial_db == "main"
        assert p.current_db == "main"

    def test_add_second_db_does_not_change_initial_or_current(self):
        p = DatabasePool()
        db1 = FakeDatabase(server="s1", db="d1")
        db2 = FakeDatabase(server="s2", db="d2")
        p.add("main", db1)
        p.add("secondary", db2)
        assert p.initial_db == "main"
        assert p.current_db == "main"

    def test_add_lowercase_alias(self):
        p = DatabasePool()
        p.add("MAIN", FakeDatabase())
        assert "main" in p.aliases()

    def test_add_initial_to_nonempty_pool_raises(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        with pytest.raises(ErrInfo):
            p.add("initial", FakeDatabase())

    def test_aliases_returns_added_names(self):
        p = DatabasePool()
        p.add("a", FakeDatabase())
        p.add("b", FakeDatabase())
        assert set(p.aliases()) == {"a", "b"}


class TestDatabasePoolCurrent:
    def test_current_returns_first_added_db(self):
        p = DatabasePool()
        db = FakeDatabase(server="s", db="d")
        p.add("main", db)
        assert p.current() is db

    def test_current_alias_returns_string(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        assert p.current_alias() == "main"

    def test_initial_returns_first_db(self):
        p = DatabasePool()
        db = FakeDatabase()
        p.add("first", db)
        p.add("second", FakeDatabase())
        assert p.initial() is db

    def test_aliased_as_returns_correct_db(self):
        p = DatabasePool()
        db1 = FakeDatabase()
        db2 = FakeDatabase()
        p.add("a", db1)
        p.add("b", db2)
        assert p.aliased_as("b") is db2


class TestDatabasePoolMakeCurrent:
    def test_make_current_changes_current_db(self):
        p = DatabasePool()
        p.add("a", FakeDatabase())
        p.add("b", FakeDatabase())
        p.make_current("b")
        assert p.current_db == "b"

    def test_make_current_case_insensitive(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        p.make_current("MAIN")
        assert p.current_db == "main"

    def test_make_current_unknown_alias_raises(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        with pytest.raises(ErrInfo):
            p.make_current("unknown")


class TestDatabasePoolDisconnect:
    def test_disconnect_current_raises(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        with pytest.raises(ErrInfo):
            p.disconnect("main")

    def test_disconnect_nonexistent_alias_is_noop(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        # Should not raise — silently ignored
        p.disconnect("ghost")

    def test_disconnect_noncurrent_removes_alias(self):
        p = DatabasePool()
        p.add("main", FakeDatabase())
        p.add("secondary", FakeDatabase())
        p.disconnect("secondary")
        assert "secondary" not in p.aliases()


# ---------------------------------------------------------------------------
# Database deeper methods — exercised via SQLiteDatabase (no mocking)
# ---------------------------------------------------------------------------


class TestDatabaseDeeperMethods:
    """Tests for base-class methods not covered by the FakeDatabase tests above.

    These use a real in-memory SQLiteDatabase so the actual code paths in
    Database (not the stub overrides) are exercised.
    """

    @pytest.fixture
    def db(self):
        from execsql.db.sqlite import SQLiteDatabase

        d = SQLiteDatabase(":memory:")
        yield d
        d.close()

    def test_autocommit_off_then_on(self, db):
        db.autocommit_off()
        assert db.autocommit is False
        db.autocommit_on()
        assert db.autocommit is True

    def test_exec_cmd_raises_not_implemented(self):
        # exec_cmd is not implemented in the base class; SQLiteDatabase
        # overrides it so we test via FakeDatabase (which inherits the base).
        from execsql.exceptions import DatabaseNotImplementedError

        db = FakeDatabase(db="test")
        with pytest.raises(DatabaseNotImplementedError):
            db.exec_cmd("anything")

    def test_select_rowdict_returns_dicts(self, db):
        db.execute("CREATE TABLE t (a INTEGER, b TEXT);")
        db.execute("INSERT INTO t VALUES (1, 'hello');")
        db.execute("INSERT INTO t VALUES (2, 'world');")
        hdrs, dicts = db.select_rowdict("SELECT * FROM t ORDER BY a;")
        rows = list(dicts)
        assert hdrs == ["a", "b"]
        assert rows == [{"a": 1, "b": "hello"}, {"a": 2, "b": "world"}]

    def test_select_rowdict_empty_table(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        hdrs, dicts = db.select_rowdict("SELECT * FROM t;")
        rows = list(dicts)
        assert hdrs == ["id"]
        assert rows == []

    def test_cursor_returns_cursor_object(self, db):
        curs = db.cursor()
        assert curs is not None

    def test_role_exists_raises_not_implemented(self, db):
        from execsql.exceptions import DatabaseNotImplementedError

        with pytest.raises(DatabaseNotImplementedError):
            db.role_exists("some_role")

    def test_select_data_returns_headers_and_rows(self, db):
        db.execute("CREATE TABLE t (a INTEGER, b TEXT);")
        db.execute("INSERT INTO t VALUES (1, 'x');")
        hdrs, rows = db.select_data("SELECT a, b FROM t;")
        assert hdrs == ["a", "b"]
        assert len(rows) == 1
        assert rows[0][0] == 1

    def test_select_rowsource_returns_generator(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        db.execute("INSERT INTO t VALUES (10);")
        db.execute("INSERT INTO t VALUES (20);")
        hdrs, gen = db.select_rowsource("SELECT id FROM t ORDER BY id;")
        assert hdrs == ["id"]
        rows = list(gen)
        assert len(rows) == 2

    def test_execute_with_paramlist(self, db):
        db.execute("CREATE TABLE t (id INTEGER, name TEXT);")
        db.execute("INSERT INTO t VALUES (?, ?);", [1, "Alice"])
        _, rows = db.select_data("SELECT name FROM t WHERE id = 1;")
        assert rows[0][0] == "Alice"

    def test_paramsubs(self, db):
        result = db.paramsubs(3)
        assert result == "?,?,?"

    def test_paramsubs_single(self, db):
        result = db.paramsubs(1)
        assert result == "?"

    def test_schema_qualified_name_no_schema(self, db):
        # SQLiteDatabase has a proper type.quoted; no schema → just quoted table name
        result = db.schema_qualified_table_name(None, "mytable")
        assert "mytable" in result

    def test_schema_qualified_name_with_schema(self, db):
        result = db.schema_qualified_table_name("myschema", "mytable")
        assert "myschema" in result
        assert "mytable" in result

    def test_rollback_does_not_raise(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        # rollback on a connection that has no pending transaction is OK
        db.rollback()

    def test_drop_table_removes_table(self, db):
        db.execute("CREATE TABLE droptarget (id INTEGER);")
        db.execute("INSERT INTO droptarget VALUES (1);")
        db.drop_table("droptarget")
        # Table should no longer exist; select_data re-raises the raw driver exception
        with pytest.raises(sqlite3.OperationalError):
            db.select_data("SELECT * FROM droptarget;")

    def test_table_columns_returns_column_names(self, db):
        db.execute("CREATE TABLE t (alpha INTEGER, beta TEXT);")
        cols = db.table_columns("t")
        assert "alpha" in cols
        assert "beta" in cols

    def test_commit_no_error(self, db):
        db.execute("CREATE TABLE t (id INTEGER);")
        db.execute("INSERT INTO t VALUES (1);")
        db.commit()  # should not raise

    def test_autocommit_off_no_error(self, db):
        db.autocommit_off()
        assert db.autocommit is False
        db.autocommit_on()


class TestDatabasePoolCloseAll:
    def test_closeall_closes_all_connections(self):
        from execsql.db.sqlite import SQLiteDatabase

        p = DatabasePool()
        db1 = SQLiteDatabase(":memory:")
        db2 = SQLiteDatabase(":memory:")
        p.add("a", db1)
        p.add("b", db2)
        p.closeall()
        # After closeall, both connections should be None
        assert db1.conn is None
        assert db2.conn is None
