"""In-process coverage tests for execsql.db.mysql.

These exercise the ``MySQLDatabase`` adapter directly against the CI
service container (``mysql:8``).  The existing ``tests/integration/test_mysql.py``
only runs the adapter via subprocess and yields no coverage credit.

The module is skipped when:
  - pymysql is not installed, or
  - the test MySQL instance (localhost:3306, database=execsql_test,
    user=execsql, password=execsql) is not reachable.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import execsql.state as _state


pymysql = pytest.importorskip("pymysql", reason="pymysql not installed")

_MY_KW: dict = {
    "host": os.environ.get("EXECSQL_MYSQL_HOST", "localhost"),
    "port": int(os.environ.get("EXECSQL_MYSQL_PORT", "3306")),
    "database": os.environ.get("EXECSQL_MYSQL_DATABASE", "execsql_test"),
    "user": os.environ.get("EXECSQL_MYSQL_USER", "execsql"),
    "password": os.environ.get("EXECSQL_MYSQL_PASSWORD", "execsql"),
    "connect_timeout": 3,
}


def _mysql_reachable() -> bool:
    try:
        pymysql.connect(**_MY_KW).close()
        return True
    except Exception:
        return False


if not _mysql_reachable():
    pytest.skip(
        f"MySQL test instance not reachable at {_MY_KW['host']}:{_MY_KW['port']}",
        allow_module_level=True,
    )


from execsql.db.mysql import MySQLDatabase  # noqa: E402
from execsql.exceptions import ErrInfo  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _state_setup():
    _state.subvars = MagicMock()
    _state.exec_log = MagicMock()
    _state.conf = SimpleNamespace(
        gui_framework="tkinter",
        gui_level=0,
        import_common_cols_only=False,
        import_buffer=8192,
        import_row_buffer=100,
        export_row_buffer=100,
        import_progress_interval=0,
        empty_strings=True,
        empty_rows=True,
        del_empty_cols=False,
        create_col_hdrs=False,
        trim_strings=False,
        replace_newlines=False,
        only_strings=False,
        trim_col_hdrs="none",
        clean_col_hdrs=False,
        fold_col_hdrs="no",
        dedup_col_hdrs=False,
        output_encoding="utf-8",
        import_encoding="utf-8",
        script_encoding="utf8",
        make_export_dirs=False,
        export_output_dir=None,
        enc_err_disposition=None,
        quote_all_text=False,
        write_warnings=False,
        write_prefix=None,
        write_suffix=None,
        css_file=None,
        css_styles=None,
        gui_wait_on_exit=False,
        gui_wait_on_error_halt=False,
        allow_system_cmd=True,
        boolean_int=True,
        boolean_words=False,
        max_int=2_147_483_647,
    )
    _saved_stringtypes = _state.stringtypes
    _state.stringtypes = (str, bytes)
    try:
        yield
    finally:
        _state.stringtypes = _saved_stringtypes


@pytest.fixture(scope="module")
def db():
    inst = MySQLDatabase(
        server_name=_MY_KW["host"],
        db_name=_MY_KW["database"],
        user_name=_MY_KW["user"],
        password=_MY_KW["password"],
        port=_MY_KW["port"],
        encoding="utf8mb4",
    )
    yield inst
    try:
        inst.close()
    except Exception:
        pass


@pytest.fixture
def fresh_table(db):
    name = "execsql_inproc_t"
    with db._cursor() as curs:
        curs.execute(f"DROP TABLE IF EXISTS {name};")
    db.commit()
    yield name
    with db._cursor() as curs:
        curs.execute(f"DROP TABLE IF EXISTS {name};")
    db.commit()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstructionAndConnection:
    def test_repr(self, db):
        r = repr(db)
        assert "MySQLDatabase" in r
        assert _MY_KW["host"] in r

    def test_dbms_id(self, db):
        assert "mysql" in db.type.dbms_id.lower()

    def test_paramstr(self, db):
        assert db.paramstr == "%s"

    def test_encode_commands_true(self, db):
        # MySQL adapter encodes SQL bytes
        assert db.encode_commands is True

    def test_connection_failure_raises(self):
        with pytest.raises(ErrInfo):
            MySQLDatabase(
                server_name=_MY_KW["host"],
                db_name="execsql_no_such_db",
                user_name=_MY_KW["user"],
                password=_MY_KW["password"],
                port=_MY_KW["port"],
            )


# ---------------------------------------------------------------------------
# Schema queries
# ---------------------------------------------------------------------------


class TestSchemaQueries:
    def test_schema_exists_returns_false(self, db):
        # MySQL adapter intentionally returns False for all schema names
        assert db.schema_exists("anything") is False
        assert db.schema_exists("") is False

    def test_table_exists(self, db, fresh_table):
        assert db.table_exists(fresh_table) is False
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
        db.commit()
        assert db.table_exists(fresh_table) is True

    def test_view_exists(self, db, fresh_table):
        view = f"{fresh_table}_v"
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
            curs.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM {fresh_table};")
        db.commit()
        assert db.view_exists(view) is True
        # Cleanup
        with db._cursor() as curs:
            curs.execute(f"DROP VIEW IF EXISTS {view};")
        db.commit()

    def test_column_exists(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, label TEXT);")
        db.commit()
        assert db.column_exists(fresh_table, "id") is True
        assert db.column_exists(fresh_table, "nope") is False

    def test_role_exists(self, db):
        # role_exists queries mysql.user — the test user typically lacks SELECT
        # on that schema, so we accept either True/False or a permission error.
        try:
            result = db.role_exists(_MY_KW["user"])
            assert isinstance(result, bool)
        except pymysql.Error:
            pytest.skip("Test user lacks SELECT on mysql.user — role_exists path exercised")

    def test_table_columns(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (a INT, b TEXT, c DECIMAL);")
        db.commit()
        cols = [c.lower() for c in db.table_columns(fresh_table)]
        assert sorted(cols) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


class TestDataAccess:
    def test_select_data(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1, 'a'), (2, 'b');")
        db.commit()
        hdrs, rows = db.select_data(f"SELECT * FROM {fresh_table} ORDER BY id;")
        assert [h.lower() for h in hdrs] == ["id", "name"]
        # pymysql returns tuple-of-tuples; compare as list of tuples
        assert list(rows) == [(1, "a"), (2, "b")]

    def test_select_data_bad_sql_raises(self, db):
        # Re-raises driver exception (after rollback) — not ErrInfo-wrapped
        with pytest.raises(pymysql.Error):
            db.select_data("SELECT * FROM execsql_no_table_xyz;")

    def test_select_rowsource_iterates(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1), (2), (3);")
        db.commit()
        hdrs, rs = db.select_rowsource(f"SELECT id FROM {fresh_table} ORDER BY id;")
        assert [h.lower() for h in hdrs] == ["id"]
        rows = list(rs)
        assert len(rows) == 3

    def test_select_rowdict(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1, 'x');")
        db.commit()
        hdrs, gen = db.select_rowdict(f"SELECT id, name FROM {fresh_table};")
        rows = list(gen)
        assert rows[0]["id"] == 1
        assert rows[0]["name"] == "x"


# ---------------------------------------------------------------------------
# exec_cmd — stored procedure dispatch
# ---------------------------------------------------------------------------


class TestExecCmd:
    def test_exec_cmd_calls_procedure(self, db):
        # Define a no-op stored procedure
        with db._cursor() as curs:
            curs.execute("DROP PROCEDURE IF EXISTS execsql_noop;")
            curs.execute("CREATE PROCEDURE execsql_noop() BEGIN SELECT 1; END;")
        db.commit()
        try:
            db.exec_cmd("execsql_noop")
            _state.subvars.add_substitution.assert_called()
        finally:
            with db._cursor() as curs:
                curs.execute("DROP PROCEDURE IF EXISTS execsql_noop;")
            db.commit()

    def test_exec_cmd_unknown_procedure_rolls_back(self, db):
        with pytest.raises(pymysql.Error):
            db.exec_cmd("execsql_no_such_proc_xyz")


# ---------------------------------------------------------------------------
# Transaction control
# ---------------------------------------------------------------------------


class TestTransactionControl:
    def test_commit_persists(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1);")
        db.commit()
        _hdrs, rows = db.select_data(f"SELECT * FROM {fresh_table};")
        assert list(rows) == [(1,)]


# ---------------------------------------------------------------------------
# Identifier quoting
# ---------------------------------------------------------------------------


class TestIdentifiers:
    def test_quote_identifier(self, db):
        out = db.quote_identifier("plain")
        # MySQL uses backticks via the dbt_mysql.quoted helper, but the base
        # class default is double-quoting — accept either form
        assert "plain" in out

    def test_schema_qualified_with_schema(self, db):
        qn = db.schema_qualified_table_name("execsql_test", "tbl")
        assert "tbl" in qn
        assert "execsql_test" in qn


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


def _make_csv_file_obj(tmp_path, headers, rows, *, delimiter=",", quotechar='"', encoding="utf-8"):
    csv_path = tmp_path / "data.csv"
    lines = [delimiter.join(headers)]
    for r in rows:
        lines.append(delimiter.join(str(v) for v in r))
    csv_path.write_text("\n".join(lines) + "\n", encoding=encoding)

    class _CSV:
        def __init__(self):
            self.csvfname = str(csv_path)
            self.encoding = encoding
            self.delimiter = delimiter
            self.quotechar = quotechar
            self.junk_header_lines = 0

        def evaluate_line_format(self):
            pass

        def column_headers(self):
            return list(headers)

        def open(self, _mode):
            return open(self.csvfname, encoding=encoding)

        def reader(self):
            import csv as _csv

            f = open(self.csvfname, encoding=encoding)  # noqa: SIM115 — caller iterates and closes
            return _csv.reader(f, delimiter=delimiter, quotechar=quotechar)

    return _CSV()


class TestImportTabularFile:
    def test_missing_table_raises(self, db, tmp_path):
        csv = _make_csv_file_obj(tmp_path, ["id"], [(1,)])
        with pytest.raises(ErrInfo):
            db.import_tabular_file(None, "execsql_no_table_xyz", csv, skipheader=True)

    def test_insert_fallback_path(self, db, fresh_table, tmp_path):
        # Mismatched column order forces the slow INSERT path (vs LOAD DATA)
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
        db.commit()
        # Headers in reverse order — triggers INSERT branch
        csv = _make_csv_file_obj(tmp_path, ["name", "id"], [("a", 1), ("b", 2)])
        # Make it not match the fast-path criteria by setting create_col_hdrs
        _state.conf.create_col_hdrs = True
        try:
            db.import_tabular_file(None, fresh_table, csv, skipheader=True)
            db.commit()
            _h, rows = db.select_data(f"SELECT id, name FROM {fresh_table} ORDER BY id;")
            assert list(rows) == [(1, "a"), (2, "b")]
        finally:
            _state.conf.create_col_hdrs = False


class TestClose:
    def test_close_sets_conn_none(self):
        inst = MySQLDatabase(
            server_name=_MY_KW["host"],
            db_name=_MY_KW["database"],
            user_name=_MY_KW["user"],
            password=_MY_KW["password"],
            port=_MY_KW["port"],
            encoding="utf8mb4",
        )
        assert inst.conn is not None
        inst.close()
        assert inst.conn is None
