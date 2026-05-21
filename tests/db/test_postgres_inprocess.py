"""In-process coverage tests for execsql.db.postgres.

These exercise the ``PostgresDatabase`` adapter directly against the CI
service container (``postgres:16``).  They cover the methods that the
existing ``tests/integration/test_postgres.py`` exercises *only via
subprocess* — subprocess execution yields no coverage credit, so those
~199 missed lines stay uncovered.

The module is skipped when:
  - psycopg2 is not installed, or
  - the test PostgreSQL instance (localhost:5432, database=execsql_test,
    user=execsql, password=execsql) is not reachable.

Override the connection target with EXECSQL_PG_HOST / EXECSQL_PG_PORT /
EXECSQL_PG_DATABASE / EXECSQL_PG_USER / EXECSQL_PG_PASSWORD env vars.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import execsql.state as _state


# ---------------------------------------------------------------------------
# Skip the entire module when the driver or server is unavailable
# ---------------------------------------------------------------------------

psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 not installed")

_PG_KW: dict = {
    "host": os.environ.get("EXECSQL_PG_HOST", "localhost"),
    "port": int(os.environ.get("EXECSQL_PG_PORT", "5432")),
    "dbname": os.environ.get("EXECSQL_PG_DATABASE", "execsql_test"),
    "user": os.environ.get("EXECSQL_PG_USER", "execsql"),
    "password": os.environ.get("EXECSQL_PG_PASSWORD", "execsql"),
    "connect_timeout": 3,
}


def _pg_reachable() -> bool:
    try:
        psycopg2.connect(**_PG_KW).close()
        return True
    except Exception:
        return False


if not _pg_reachable():
    pytest.skip(
        f"PostgreSQL test instance not reachable at {_PG_KW['host']}:{_PG_KW['port']}",
        allow_module_level=True,
    )


from execsql.db.postgres import PostgresDatabase  # noqa: E402
from execsql.exceptions import ErrInfo  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _state_setup():
    """Install the minimal state singletons that PostgresDatabase methods touch."""
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
    """Open a single PostgresDatabase connection for the module."""
    inst = PostgresDatabase(
        server_name=_PG_KW["host"],
        db_name=_PG_KW["dbname"],
        user_name=_PG_KW["user"],
        password=_PG_KW["password"],
        port=_PG_KW["port"],
        connect_timeout=_PG_KW["connect_timeout"],
    )
    yield inst
    try:
        inst.close()
    except Exception:
        pass


@pytest.fixture
def fresh_table(db):
    """Provide a unique table name and drop it before/after the test."""
    name = "execsql_inproc_t"
    with db._cursor() as curs:
        curs.execute(f"DROP TABLE IF EXISTS {name} CASCADE;")
    db.commit()
    yield name
    with db._cursor() as curs:
        curs.execute(f"DROP TABLE IF EXISTS {name} CASCADE;")
    db.commit()


# ---------------------------------------------------------------------------
# Construction + connection
# ---------------------------------------------------------------------------


class TestConstructionAndConnection:
    def test_repr_contains_server_and_db(self, db):
        r = repr(db)
        assert "PostgresDatabase" in r
        assert _PG_KW["host"] in r
        assert _PG_KW["dbname"] in r

    def test_name_format(self, db):
        # Database.name() should mention the dbms + db_name
        assert _PG_KW["dbname"] in db.name()

    def test_dbms_id(self, db):
        assert db.type.dbms_id.lower() == "postgres" or "postgres" in db.type.dbms_id.lower()

    def test_paramstr_is_percent_s(self, db):
        assert db.paramstr == "%s"

    def test_paramsubs(self, db):
        assert db.paramsubs(3) == "%s,%s,%s"

    def test_encode_commands_false(self, db):
        # PG accepts unicode strings directly
        assert db.encode_commands is False

    def test_encoding_set_from_server(self, db):
        # After open_db(), encoding mirrors the server's encoding (usually UTF8)
        assert db.encoding.upper().replace("-", "") == "UTF8"

    def test_open_db_connection_failure_raises(self):
        with pytest.raises(ErrInfo):
            PostgresDatabase(
                server_name=_PG_KW["host"],
                db_name="execsql_does_not_exist",
                user_name=_PG_KW["user"],
                password=_PG_KW["password"],
                port=_PG_KW["port"],
                connect_timeout=2,
            )


# ---------------------------------------------------------------------------
# Schema queries
# ---------------------------------------------------------------------------


class TestSchemaQueries:
    def test_schema_exists_public(self, db):
        assert db.schema_exists("public") is True

    def test_schema_exists_false(self, db):
        assert db.schema_exists("execsql_no_such_schema") is False

    def test_table_exists_true_and_false(self, db, fresh_table):
        assert db.table_exists(fresh_table) is False
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
        db.commit()
        assert db.table_exists(fresh_table) is True

    def test_table_exists_with_schema(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
        db.commit()
        assert db.table_exists(fresh_table, schema_name="public") is True
        assert db.table_exists(fresh_table, schema_name="information_schema") is False

    def test_view_exists(self, db, fresh_table):
        view = f"{fresh_table}_v"
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
            curs.execute(f"CREATE VIEW {view} AS SELECT * FROM {fresh_table};")
        db.commit()
        assert db.view_exists(view) is True
        assert db.view_exists(view, schema_name="public") is True
        assert db.view_exists("execsql_no_view") is False
        # Cleanup
        with db._cursor() as curs:
            curs.execute(f"DROP VIEW IF EXISTS {view};")
        db.commit()

    def test_column_exists(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, label TEXT);")
        db.commit()
        assert db.column_exists(fresh_table, "id") is True
        assert db.column_exists(fresh_table, "label") is True
        assert db.column_exists(fresh_table, "nope") is False

    def test_role_exists_current_user(self, db):
        # The connecting user must exist as a role
        assert db.role_exists(_PG_KW["user"]) is True
        assert db.role_exists("execsql_no_role_zzz") is False

    def test_table_columns(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, label TEXT, score NUMERIC);")
        db.commit()
        cols = [c.lower() for c in db.table_columns(fresh_table)]
        assert "id" in cols
        assert "label" in cols
        assert "score" in cols


# ---------------------------------------------------------------------------
# Identifier quoting + schema_qualified_table_name
# ---------------------------------------------------------------------------


class TestIdentifiers:
    def test_quote_identifier_simple(self, db):
        out = db.quote_identifier("plain")
        # PG uses double-quotes
        assert out == '"plain"' or "plain" in out

    def test_quote_identifier_with_double_quote(self, db):
        out = db.quote_identifier('weird"name')
        assert '"' in out

    def test_schema_qualified_with_schema(self, db):
        qn = db.schema_qualified_table_name("public", "mytable")
        assert "public" in qn
        assert "mytable" in qn

    def test_schema_qualified_no_schema(self, db):
        qn = db.schema_qualified_table_name(None, "mytable")
        assert "mytable" in qn


# ---------------------------------------------------------------------------
# Data access — select_data, select_rowsource
# ---------------------------------------------------------------------------


class TestDataAccess:
    def test_select_data_basic(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1, 'a'), (2, 'b');")
        db.commit()
        hdrs, rows = db.select_data(f"SELECT * FROM {fresh_table} ORDER BY id;")
        assert [h.lower() for h in hdrs] == ["id", "name"]
        assert rows == [(1, "a"), (2, "b")]

    def test_select_data_empty(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
        db.commit()
        _hdrs, rows = db.select_data(f"SELECT * FROM {fresh_table};")
        assert rows == []

    def test_select_data_bad_sql_raises(self, db):
        # base.Database.select_data() re-raises the driver exception directly
        # after rolling back; it does not wrap in ErrInfo.
        with pytest.raises(psycopg2.Error):
            db.select_data("SELECT * FROM execsql_no_such_table_xyz;")

    def test_select_rowsource_iterates(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1), (2), (3);")
        db.commit()
        hdrs, rs = db.select_rowsource(f"SELECT id FROM {fresh_table} ORDER BY id;")
        assert hdrs == ["id"] or [h.lower() for h in hdrs] == ["id"]
        all_rows = list(rs)
        assert len(all_rows) == 3
        assert all_rows[0][0] == 1

    def test_select_rowdict(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1, 'x');")
        db.commit()
        hdrs, gen = db.select_rowdict(f"SELECT id, name FROM {fresh_table};")
        assert [h.lower() for h in hdrs] == ["id", "name"]
        rows = list(gen)
        assert rows[0]["id"] == 1
        assert rows[0]["name"] == "x"


# ---------------------------------------------------------------------------
# exec_cmd — stored function dispatch
# ---------------------------------------------------------------------------


class TestExecCmd:
    def test_exec_cmd_dispatches_function_call(self, db):
        # Create a tiny PG function to call
        with db._cursor() as curs:
            curs.execute(
                "CREATE OR REPLACE FUNCTION execsql_ping() RETURNS INT AS "
                "$$ BEGIN RETURN 42; END; $$ LANGUAGE plpgsql;",
            )
        db.commit()
        try:
            db.exec_cmd("execsql_ping")
            # exec_cmd updates $LAST_ROWCOUNT — _state.subvars is a mock so
            # we just verify the call landed
            _state.subvars.add_substitution.assert_called()
        finally:
            with db._cursor() as curs:
                curs.execute("DROP FUNCTION IF EXISTS execsql_ping();")
            db.commit()

    def test_exec_cmd_unknown_function_rolls_back(self, db):
        with pytest.raises(psycopg2.Error):
            db.exec_cmd("execsql_no_such_function_xyz")


# ---------------------------------------------------------------------------
# vacuum — DDL outside transactions
# ---------------------------------------------------------------------------


class TestVacuum:
    def test_vacuum_runs(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1);")
        db.commit()
        # VACUUM with no args
        db.vacuum("")

    def test_vacuum_analyze(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
        db.commit()
        db.vacuum(f"ANALYZE {fresh_table}")


# ---------------------------------------------------------------------------
# import_entire_file — single column binary import
# ---------------------------------------------------------------------------


class TestImportEntireFile:
    def test_import_binary_file(self, db, fresh_table, tmp_path):
        # Create a BYTEA column to hold the binary blob
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (blob BYTEA);")
        db.commit()
        bin_file = tmp_path / "blob.bin"
        bin_file.write_bytes(b"\x00\x01\x02ABCDE\xff\xfe")
        db.import_entire_file(None, fresh_table, "blob", str(bin_file))
        db.commit()
        hdrs, rows = db.select_data(f"SELECT blob FROM {fresh_table};")
        assert rows
        # Round-trip: blob comes back as memoryview / bytes
        blob = bytes(rows[0][0])
        assert b"ABCDE" in blob


# ---------------------------------------------------------------------------
# import_tabular_file — exercises both the COPY path and the INSERT fallback
# ---------------------------------------------------------------------------


def _make_csv_file_obj(tmp_path, headers, rows, *, delimiter=",", quotechar='"', encoding="utf-8"):
    """Build a minimal csv_file_obj that supports the import_tabular_file protocol."""
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
    def test_copy_path_with_matching_encoding(self, db, fresh_table, tmp_path):
        # Headers + data lined up + UTF-8 → triggers the fast COPY branch
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
        db.commit()
        csv = _make_csv_file_obj(tmp_path, ["id", "name"], [(1, "a"), (2, "b")])
        db.import_tabular_file(None, fresh_table, csv, skipheader=True)
        db.commit()
        _hdrs, rows = db.select_data(f"SELECT id, name FROM {fresh_table} ORDER BY id;")
        assert rows == [(1, "a"), (2, "b")]

    def test_missing_table_raises(self, db, tmp_path):
        csv = _make_csv_file_obj(tmp_path, ["id"], [(1,)])
        with pytest.raises(ErrInfo):
            db.import_tabular_file(None, "execsql_no_table_xyz", csv, skipheader=True)

    def test_insert_fallback_path(self, db, fresh_table, tmp_path):
        # Force the slow INSERT path by enabling create_col_hdrs (one of the
        # config flags that disqualifies the fast COPY branch)
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
        db.commit()
        csv = _make_csv_file_obj(tmp_path, ["id", "name"], [(1, "a"), (2, "b")])
        _state.conf.create_col_hdrs = True
        try:
            db.import_tabular_file(None, fresh_table, csv, skipheader=True)
            db.commit()
            _h, rows = db.select_data(f"SELECT id, name FROM {fresh_table} ORDER BY id;")
            assert rows == [(1, "a"), (2, "b")]
        finally:
            _state.conf.create_col_hdrs = False

    def test_insert_fallback_with_trim(self, db, fresh_table, tmp_path):
        # Exercises the trim_strings branch in the INSERT fallback loop
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT, name TEXT);")
        db.commit()
        csv = _make_csv_file_obj(tmp_path, ["id", "name"], [(1, "  spaces  ")])
        _state.conf.trim_strings = True
        try:
            db.import_tabular_file(None, fresh_table, csv, skipheader=True)
            db.commit()
            _h, rows = db.select_data(f"SELECT name FROM {fresh_table};")
            assert rows[0][0] == "spaces"
        finally:
            _state.conf.trim_strings = False

    def test_unmatched_cols_raises(self, db, fresh_table, tmp_path):
        # CSV has a column that doesn't exist in the table → ErrInfo
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
        db.commit()
        csv = _make_csv_file_obj(tmp_path, ["id", "extra"], [(1, "x")])
        with pytest.raises(ErrInfo):
            db.import_tabular_file(None, fresh_table, csv, skipheader=True)

    def test_import_common_cols_only(self, db, fresh_table, tmp_path):
        # When config flag is set, unmatched cols are silently dropped
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
        db.commit()
        csv = _make_csv_file_obj(tmp_path, ["id", "extra"], [(1, "x"), (2, "y")])
        _state.conf.import_common_cols_only = True
        try:
            db.import_tabular_file(None, fresh_table, csv, skipheader=True)
            db.commit()
            _h, rows = db.select_data(f"SELECT id FROM {fresh_table} ORDER BY id;")
            assert rows == [(1,), (2,)]
        finally:
            _state.conf.import_common_cols_only = False


# ---------------------------------------------------------------------------
# Transaction control
# ---------------------------------------------------------------------------


class TestTransactionControl:
    def test_commit_with_autocommit_on(self, db, fresh_table):
        db.autocommit_on()
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
            curs.execute(f"INSERT INTO {fresh_table} VALUES (1);")
        db.commit()
        # Data should be visible
        _hdrs, rows = db.select_data(f"SELECT * FROM {fresh_table};")
        assert rows == [(1,)]

    def test_rollback_visible(self, db, fresh_table):
        with db._cursor() as curs:
            curs.execute(f"CREATE TABLE {fresh_table} (id INT);")
        db.commit()
        db.autocommit_off()
        try:
            with db._cursor() as curs:
                curs.execute(f"INSERT INTO {fresh_table} VALUES (99);")
            db.rollback()
            _hdrs, rows = db.select_data(f"SELECT * FROM {fresh_table};")
            assert rows == []
        finally:
            db.autocommit_on()


# ---------------------------------------------------------------------------
# Close + reopen
# ---------------------------------------------------------------------------


class TestCloseReopen:
    def test_close_clears_connection(self):
        inst = PostgresDatabase(
            server_name=_PG_KW["host"],
            db_name=_PG_KW["dbname"],
            user_name=_PG_KW["user"],
            password=_PG_KW["password"],
            port=_PG_KW["port"],
        )
        assert inst.conn is not None
        inst.close()
        assert inst.conn is None

    def test_close_logs_when_autocommit_off(self):
        # close() emits a warning via _state.exec_log when autocommit is off.
        inst = PostgresDatabase(
            server_name=_PG_KW["host"],
            db_name=_PG_KW["dbname"],
            user_name=_PG_KW["user"],
            password=_PG_KW["password"],
            port=_PG_KW["port"],
        )
        inst.autocommit_off()
        _state.exec_log.reset_mock()
        inst.close()
        # The warning log call should have happened
        assert any(
            "AUTOCOMMIT is OFF" in (call.args[0] if call.args else "")
            for call in _state.exec_log.log_status_info.call_args_list
        )
