"""AUTOCOMMIT OFF and BEGIN BATCH hold statements until commit, on every live backend.

Each test runs a real script through ``execsql.run()`` on one connection and
then looks at the database through a fresh one, so what it sees is what was
committed.  SQLite used to commit a CREATE TABLE at once, and DuckDB every
statement, because their drivers only open a transaction when asked to.

MySQL commits DDL on the server whatever the client does; there the table
survives a rollback, its rows do not, and a warning says so.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from execsql import run
from tests.live_db import BACKEND_NAMES, _server_listening, open_backend

TABLE = "txn_probe"


@pytest.fixture(scope="module", autouse=True)
def _stop_the_file_writer():
    """Stop the FileWriter ``run()`` leaves up for reuse.

    Later tests drive the CLI, which starts its own; sharing this one left
    their WRITE ... TO files unwritten and an EXPORT waiting forever.
    """
    yield
    import execsql.state as _state
    import execsql.utils.fileio as fileio

    fileio.filewriter_end()
    fileio.filewriter = _state.filewriter = None


#: Why SQL Server is unusable, once found: every test would otherwise wait out
#: the ODBC connect timeout again (Windows runners have the driver but no server,
#: which cost 62 s per test).
_sqlserver_unusable: list[str] = []


def _sqlserver_db(tmp_path):
    if _sqlserver_unusable:
        pytest.skip(_sqlserver_unusable[0])
    pytest.importorskip("pyodbc", reason="pyodbc not installed")
    from execsql.db.sqlserver import SqlServerDatabase

    host = os.environ.get("EXECSQL_MSSQL_HOST", "localhost")
    port = os.environ.get("EXECSQL_MSSQL_PORT", "1433")
    if not _server_listening(host, int(port)):
        _sqlserver_unusable.append(f"sqlserver not reachable: nothing listening at {host}:{port}")
        pytest.skip(_sqlserver_unusable[0])
    try:
        return SqlServerDatabase(
            server_name=f"{host},{port}",
            db_name=os.environ.get("EXECSQL_MSSQL_DATABASE", "execsql_test"),
            user_name=os.environ.get("EXECSQL_MSSQL_USER", "sa"),
            password=os.environ.get("EXECSQL_MSSQL_PASSWORD", "ExecSql_Test123!"),
        )
    except Exception as exc:
        _sqlserver_unusable.append(f"sqlserver not reachable: {type(exc).__name__}: {exc}")
        pytest.skip(_sqlserver_unusable[0])


def _open(dbms, tmp_path):
    return _sqlserver_db(tmp_path) if dbms == "sqlserver" else open_backend(dbms, tmp_path)


@pytest.fixture(params=[*BACKEND_NAMES, "sqlserver"])
def dbms(request, tmp_path, minimal_conf):
    db = _open(request.param, tmp_path)
    _drop(db)
    db.close()
    yield request.param
    db = _open(request.param, tmp_path)
    _drop(db)
    db.close()


def _drop(db):
    try:
        db.autocommit = True
        with db._cursor() as curs:
            curs.execute(f"drop table {TABLE}")
        db.conn.commit()
    except Exception:
        try:
            db.conn.rollback()
        except Exception:
            pass


def _script(dbms, tmp_path, sql):
    """Run *sql*; return the committed row count, or ``None`` if the table does not exist."""
    db = _open(dbms, tmp_path)
    with patch("execsql.utils.errors.write_warning") as warn:
        result = run(sql=sql.format(t=TABLE), connection=db)
    db.close()
    assert result.success, result.errors
    check = _open(dbms, tmp_path)
    try:
        with check._cursor() as curs:
            curs.execute(f"select count(*) from {TABLE}")
            return curs.fetchone()[0], warn
    except Exception:
        return None, warn
    finally:
        try:
            check.conn.rollback()
        except Exception:
            pass
        check.close()


def _ddl_survives(dbms):
    return dbms == "mysql"


class TestAutocommitOff:
    def test_rollback_undoes_create_table_and_rows(self, dbms, tmp_path):
        sql = "-- !x! autocommit off\ncreate table {t} (x integer);\ninsert into {t} values (1);\n-- !x! autocommit on with rollback\n"
        rows, warn = _script(dbms, tmp_path, sql)
        if _ddl_survives(dbms):
            assert rows == 0
            assert "commits CREATE TABLE immediately" in warn.call_args.args[0]
        else:
            assert rows is None
            warn.assert_not_called()

    def test_commit_keeps_both(self, dbms, tmp_path):
        sql = "-- !x! autocommit off\ncreate table {t} (x integer);\ninsert into {t} values (1);\n-- !x! autocommit on with commit\n"
        assert _script(dbms, tmp_path, sql)[0] == 1

    def test_work_not_committed_when_the_script_ends_is_lost(self, dbms, tmp_path):
        sql = "create table {t} (x integer);\n-- !x! autocommit off\ninsert into {t} values (1);\n"
        assert _script(dbms, tmp_path, sql)[0] == 0

    def test_a_scripts_own_commit_ends_the_transaction_and_holding_goes_on(self, dbms, tmp_path):
        sql = (
            "create table {t} (x integer);\n-- !x! autocommit off\ninsert into {t} values (1);\ncommit;\n"
            "insert into {t} values (2);\n-- !x! autocommit on with rollback\n"
        )
        assert _script(dbms, tmp_path, sql)[0] == 1


class TestBatch:
    def test_end_batch_commits(self, dbms, tmp_path):
        sql = "-- !x! begin batch\ncreate table {t} (x integer);\ninsert into {t} values (1);\n-- !x! end batch\n"
        assert _script(dbms, tmp_path, sql)[0] == 1

    def test_rollback_batch_undoes_create_table_and_rows(self, dbms, tmp_path):
        sql = (
            "-- !x! begin batch\ncreate table {t} (x integer);\ninsert into {t} values (1);\n"
            "-- !x! rollback batch\n-- !x! end batch\n"
        )
        rows, _ = _script(dbms, tmp_path, sql)
        assert rows == (0 if _ddl_survives(dbms) else None)


class TestAutocommitOn:
    def test_each_statement_is_committed(self, dbms, tmp_path):
        sql = "create table {t} (x integer);\ninsert into {t} values (1);\ninsert into {t} values (2);\n"
        rows, warn = _script(dbms, tmp_path, sql)
        assert rows == 2
        warn.assert_not_called()


class TestLastRowcount:
    """``$LAST_ROWCOUNT`` after each statement, the same on every backend."""

    def test_insert_update_delete(self, dbms, tmp_path):
        sql = (
            f"create table {TABLE} (x integer);\n"
            f"insert into {TABLE} values (1), (2), (3);\n-- !x! sub inserted !!$LAST_ROWCOUNT!!\n"
            f"update {TABLE} set x = 9 where x > 1;\n-- !x! sub updated !!$LAST_ROWCOUNT!!\n"
            f"delete from {TABLE} where x = 9;\n-- !x! sub deleted !!$LAST_ROWCOUNT!!\n"
        )
        db = _open(dbms, tmp_path)
        result = run(sql=sql, connection=db)
        db.close()
        assert result.success, result.errors
        assert [result.variables[k] for k in ("inserted", "updated", "deleted")] == ["3", "2", "2"]


# ---------------------------------------------------------------------------
# The pieces, without a live server
# ---------------------------------------------------------------------------


class TestStatementStart:
    @pytest.mark.parametrize(
        "sql",
        ["create table t (x int)", "  \n-- note\ncreate table t (x int)", "/* a\nb */ -- c\n create table t (x int)"],
    )
    def test_skips_whitespace_and_comments(self, sql):
        from execsql.db.base import statement_start

        assert statement_start(sql).startswith("create table")


class TestSQLite:
    @pytest.fixture
    def db(self, tmp_path, minimal_conf):
        from execsql.db.sqlite import SQLiteDatabase

        db = SQLiteDatabase(str(tmp_path / "u.db"))
        db.autocommit = False
        yield db
        db.close()

    def test_create_table_after_a_comment_is_held(self, db):
        db.execute("-- set up\ncreate table t (x integer);")
        assert db.conn.in_transaction

    def test_pragma_runs_outside_a_transaction_so_it_takes_effect(self, db):
        db.execute("pragma foreign_keys = on;")
        assert not db.conn.in_transaction
        assert db.select_data("pragma foreign_keys;")[1] == [(1,)]

    def test_nothing_is_begun_while_not_holding(self, db):
        db.autocommit = True
        db.execute("create table t (x integer);")
        assert not db.conn.in_transaction


class TestDuckDB:
    @pytest.fixture
    def db(self, tmp_path, minimal_conf):
        pytest.importorskip("duckdb")
        from execsql.db.duckdb import DuckDBDatabase

        db = DuckDBDatabase(str(tmp_path / "u.duckdb"))
        yield db
        db.close()

    def test_a_scripts_own_begin_and_commit_are_tracked(self, db):
        db.execute("begin transaction;")
        assert db.in_transaction
        db.execute("create table t (x integer);")
        db.execute("commit;")
        assert not db.in_transaction
        assert db.table_exists("t")

    def test_a_scripts_own_begin_holds_until_rollback(self, db):
        db.execute("begin;")
        db.execute("create table t (x integer);")
        db.execute("rollback;")
        assert not db.table_exists("t")

    def test_while_open_statements_share_the_connection(self, db):
        from execsql.db.duckdb import _SharedCursor

        assert not isinstance(db.cursor(), _SharedCursor)
        db.autocommit = False
        db.execute("create table t (x integer);")
        curs = db.cursor()
        assert isinstance(curs, _SharedCursor)
        curs.close()  # leaves the connection, and its transaction, open
        assert db.in_transaction
        db.rollback()
        assert not db.in_transaction
        assert not db.table_exists("t")

    def test_the_count_duckdb_returns_is_the_rowcount(self, db):
        from unittest.mock import MagicMock

        import execsql.state as _state

        subvars = MagicMock()
        _state.subvars = subvars
        assert db.execute("create table t (x integer);") is None
        db.execute("insert into t values (1), (2);")
        subvars.add_substitution.assert_called_with("$LAST_ROWCOUNT", 2)
        # A query's own "Count" column is a result, not a rowcount.
        assert db.execute('select count(*) as "Count" from t;', fetch=True) == (["Count"], [(2,)])
        assert db.execute("select 1;") is None

    def test_a_failed_statement_ends_the_transaction(self, db):
        db.autocommit = False
        db.execute("create table t (x integer);")
        import duckdb

        with pytest.raises(duckdb.CatalogException):
            db.execute("select * from missing;")
        assert not db.in_transaction


class TestImplicitCommitRules:
    @pytest.mark.parametrize(
        ("sql", "named"),
        [
            ("create table t (x int)", "CREATE TABLE"),
            ("CREATE OR REPLACE VIEW v AS SELECT 1", "CREATE OR REPLACE VIEW"),
            ("create unique index i on t (x)", "CREATE UNIQUE INDEX"),
            ("drop table t", "DROP TABLE"),
            ("truncate table t", "TRUNCATE"),
            ("rename table a to b", "RENAME TABLE"),
            ("begin", "BEGIN"),
            ("set autocommit = 1", "SET AUTOCOMMIT"),
        ],
    )
    def test_mysql_names_the_statement(self, sql, named):
        from execsql.db.mysql import MySQLDatabase

        m = MySQLDatabase.implicit_commit_rx.match(sql)
        assert m and " ".join(m.group(0).upper().split()) == named

    @pytest.mark.parametrize(
        "sql",
        ["create temporary table t (x int)", "drop temporary table t", "insert into t values (1)", "select 1"],
    )
    def test_mysql_temporary_tables_and_dml_are_held(self, sql):
        from execsql.db.mysql import MySQLDatabase

        assert MySQLDatabase.implicit_commit_rx.match(sql) is None

    @pytest.mark.parametrize(
        "sql",
        [
            "create global temporary table t (x int)",
            "alter table t add y int",
            "comment on table t is 'x'",
            "grant select on t to u",
        ],
    )
    def test_oracle_ddl(self, sql):
        from execsql.db.oracle import OracleDatabase

        assert OracleDatabase.implicit_commit_rx.match(sql)

    def test_oracle_dml_is_held(self):
        from execsql.db.oracle import OracleDatabase

        assert OracleDatabase.implicit_commit_rx.match("update t set x = 1") is None


class TestCannotHold:
    def test_a_driver_without_transactions_warns_once(self, tmp_path, minimal_conf):
        from execsql.db.sqlite import SQLiteDatabase

        db = SQLiteDatabase(str(tmp_path / "u.db"))
        db.driver_autocommits = True
        db.autocommit = False
        with patch("execsql.utils.errors.write_warning") as warn:
            db.execute("create table t (x integer);")
            db.execute("insert into t values (1);")
        db.close()
        warn.assert_called_once()
        assert "cannot hold statements until COMMIT" in warn.call_args.args[0]

    def test_the_dsn_fallback_marks_the_connection(self):
        import inspect

        from execsql.db import dsn

        assert "self.driver_autocommits = True" in inspect.getsource(dsn.DsnDatabase.open_db)

    def test_an_access_temporary_query_warns_while_holding(self, minimal_conf):
        from unittest.mock import MagicMock

        from execsql.db.access import AccessDatabase

        db = object.__new__(AccessDatabase)
        db.conn, db.dao_conn, db.autocommit = MagicMock(), MagicMock(), False
        db.temp_query_names, db.last_dao_time = [], 0.0
        with patch("execsql.utils.errors.write_warning") as warn:
            db.execute("create temporary query q as select 1;")
        assert "reopens the Access connection" in warn.call_args.args[0]
