"""DDL round trips use only synthetic objects in disposable test databases."""

from unittest.mock import MagicMock

import pytest

from execsql import inspect_schema
from execsql import inspect_file
from execsql.config import ConfigData
from execsql.models import DataTable
from tests.live_db import open_backend


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.setattr(ConfigData, "_search_paths", classmethod(lambda *args, **kwargs: []))


def _execute_sql(db, sql):
    # Session context emitted before the CREATE is separate from the opaque
    # native statement. Do not split semicolons inside defaults or expressions.
    while sql.startswith("SET "):
        context, sql = sql.split("\n", 1)
        with db._cursor() as cursor:
            cursor.execute(context)
    with db._cursor() as cursor:
        cursor.execute(sql)


def _inspect(db, name, schema=None):
    return inspect_schema(connection=db, table=name, schema=schema, include_sql=True, include_details=False)


@pytest.mark.parametrize("dbms", ["sqlite", "duckdb", "postgres", "mysql", "mariadb"])
def test_native_table_and_view_round_trip(dbms, tmp_path):
    db = open_backend(dbms, tmp_path)
    parent, child, view = "ddl_parent", "ddl_child", "ddl_view"
    try:
        if dbms == "sqlite":
            db.conn.execute("PRAGMA foreign_keys=ON")
        action = " ON DELETE CASCADE" if dbms != "duckdb" else ""
        db.execute(f"CREATE TABLE {parent}(a INT, b INT, PRIMARY KEY(b,a))")
        db.execute(
            f"CREATE TABLE {child}(id INT NOT NULL, x INT, y INT, label VARCHAR(12) DEFAULT 'a;b', "
            f"CONSTRAINT ddl_unique UNIQUE(id), CONSTRAINT ddl_check CHECK(id>0), "
            f"CONSTRAINT ddl_fk FOREIGN KEY(x,y) REFERENCES {parent}(b,a){action})",
        )
        db.execute(f"CREATE VIEW {view} AS SELECT id,label FROM {child}")
        db.commit()
        before = inspect_schema(connection=db, table=child)
        parent_result, table_result, view_result = _inspect(db, parent), _inspect(db, child), _inspect(db, view)
        assert parent_result["success"], parent_result
        assert table_result["success"], table_result
        assert view_result["success"], view_result
        assert "a;b" in table_result["sql"]
        db.execute(f"DROP VIEW {view}")
        db.execute(f"DROP TABLE {child}")
        db.execute(f"DROP TABLE {parent}")
        _execute_sql(db, parent_result["sql"])
        _execute_sql(db, table_result["sql"])
        _execute_sql(db, view_result["sql"])
        db.commit()
        after = inspect_schema(connection=db, table=child)
        assert after["tables"] == before["tables"]
        if action:
            assert "CASCADE" in table_result["sql"].upper()
            db.execute(f"INSERT INTO {parent}(a,b) VALUES(1,2)")
            db.execute(f"INSERT INTO {child}(id,x,y) VALUES(2,2,1)")
            db.execute(f"DELETE FROM {parent} WHERE a=1")
            with db._cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {child} WHERE id=2")
                assert cursor.fetchone()[0] == 0
        db.execute(f"INSERT INTO {child}(id) VALUES(1)")
        with db._cursor() as cursor:
            cursor.execute(f"SELECT id,label FROM {view}")
            assert tuple(cursor.fetchone()) == (1, "a;b")
        db.rollback()
    finally:
        db.rollback()
        for kind, name in (("VIEW", view), ("TABLE", child), ("TABLE", parent)):
            try:
                db.execute(f"DROP {kind} {name}")
                db.commit()
            except Exception:
                db.rollback()
        db.close()


@pytest.mark.parametrize(
    "dbms,dialect",
    [
        ("sqlite", "sqlite"),
        ("duckdb", "duckdb"),
        ("postgres", "postgres"),
        ("mysql", "mysql"),
        ("mariadb", "mysql"),
    ],
)
def test_file_declarations_match_import_types_nullability_and_identifier_folding(dbms, dialect, tmp_path, monkeypatch):
    db = open_backend(dbms, tmp_path)
    path = tmp_path / "columns.csv"
    path.write_text("SampleID,Label Text,Price\n2,alpha,1.25\n3,,2.50\n")
    create = DataTable.create_table
    captured = {}

    def capture(table, *args, **kwargs):
        captured["table"] = table
        return create(table, *args, **kwargs)

    monkeypatch.setattr(DataTable, "create_table", capture)
    try:
        report = inspect_file(path, dialect=dialect, table_name="ddl_file")
        assert report["success"], report
        original = create(captured["table"], db.type, None, "ddl_file", pretty=True)
        _execute_sql(db, original)
        db.commit()
        before = inspect_schema(connection=db, table="ddl_file")
        db.execute("DROP TABLE ddl_file")
        _execute_sql(db, report["sql"])
        db.commit()
        after = inspect_schema(connection=db, table="ddl_file")
        assert before["success"] and after["success"]
        assert after["tables"] == before["tables"]
    finally:
        db.rollback()
        try:
            db.execute("DROP TABLE IF EXISTS ddl_file")
            db.commit()
        finally:
            db.close()


@pytest.mark.parametrize("dbms", ["mysql", "mariadb"])
def test_mysql_view_creation_collation_and_client_encoding_are_preserved(dbms, tmp_path):
    db = open_backend(dbms, tmp_path)
    try:
        db.conn.set_character_set("latin1")
        db.execute("CREATE VIEW ddl_encoding_view AS SELECT 'é' AS label")
        result = _inspect(db, "ddl_encoding_view")
        assert result["success"], result
        assert "SET NAMES" not in result["sql"]
        db.conn.set_character_set("utf8mb4")
        db.execute("DROP VIEW ddl_encoding_view")
        _execute_sql(db, result["sql"])
        with db._cursor() as cursor:
            cursor.execute("SELECT label, CHARSET(label) FROM ddl_encoding_view")
            assert tuple(cursor.fetchone()) == ("é", "latin1")
    finally:
        db.execute("DROP VIEW IF EXISTS ddl_encoding_view")
        db.commit()
        db.close()


@pytest.mark.xdist_group("live-postgres")
def test_postgres_identity_generated_columns_constraints_and_search_path_round_trip(tmp_path):
    from psycopg.errors import CheckViolation

    db = open_backend("postgres", tmp_path)
    try:
        db.conn.execute("CREATE SCHEMA ddl_special")
        db.conn.execute("SET search_path TO ddl_special,public")
        db.conn.execute("CREATE TYPE ddl_special.mood AS ENUM ('a','b')")
        db.conn.execute("""CREATE TABLE "Select"(
            id INT GENERATED ALWAYS AS IDENTITY (START WITH 9 INCREMENT BY 3 CACHE 5),
            amount numeric(9,2) DEFAULT 1.25 NOT NULL,
            status mood DEFAULT 'a',
            twice numeric GENERATED ALWAYS AS(amount*2) STORED,
            label varchar(12) COLLATE "C", nums integer[][],
            CONSTRAINT positive CHECK(amount>0), CONSTRAINT unique_id UNIQUE(id) DEFERRABLE
        )""")
        path = db.conn.execute("SHOW search_path").fetchone()[0]
        result = _inspect(db, "Select", "ddl_special")
        assert result["success"], result
        assert db.conn.execute("SHOW search_path").fetchone()[0] == path
        assert db.conn.info.transaction_status.name == "INTRANS"
        assert "integer[][]" in result["sql"] and 'COLLATE "pg_catalog"."C"' in result["sql"]
        db.conn.execute('DROP TABLE ddl_special."Select"')
        db.conn.execute("SET search_path TO public")
        _execute_sql(db, result["sql"])
        row = db.conn.execute(
            'INSERT INTO ddl_special."Select" DEFAULT VALUES RETURNING id,amount,status,twice',
        ).fetchone()
        assert row == (9, pytest.approx(1.25), "a", pytest.approx(2.5))
        with pytest.raises(CheckViolation):
            db.conn.execute('INSERT INTO ddl_special."Select"(amount) VALUES(-1)')
    finally:
        db.rollback()
        db.close()


@pytest.mark.xdist_group("live-postgres")
@pytest.mark.parametrize(
    "creation",
    [
        "CREATE TABLE ddl_unsupported(id INT) PARTITION BY RANGE(id)",
        "CREATE TABLE ddl_base(id INT); CREATE TABLE ddl_unsupported() INHERITS(ddl_base)",
        "CREATE TABLE ddl_unsupported(id INT); ALTER TABLE ddl_unsupported ENABLE ROW LEVEL SECURITY",
        "CREATE TABLE ddl_unsupported(id INT) WITH(fillfactor=80)",
        "CREATE TABLE ddl_unsupported(id INT); ALTER TABLE ddl_unsupported ADD CONSTRAINT check_id CHECK(id>0) NOT VALID",
    ],
)
def test_postgres_unsupported_forms_fail_before_sql(creation, tmp_path):
    db = open_backend("postgres", tmp_path)
    try:
        db.conn.execute(creation)
        result = _inspect(db, "ddl_unsupported", "public")
        assert not result["success"] and result["error"]["code"] == "unsupported_sql_feature", result
        assert result["sql"] is None
        assert db.conn.info.transaction_status.name == "INTRANS"
    finally:
        db.rollback()
        db.close()


@pytest.mark.xdist_group("live-postgres")
def test_postgres_views_and_temporary_tables_preserve_session_context(tmp_path):
    db = open_backend("postgres", tmp_path)
    try:
        db.conn.execute("CREATE TEMP TABLE \"temp's\"(id INT PRIMARY KEY, value text DEFAULT 'x')")
        namespace = db.conn.execute("SELECT pg_my_temp_schema()::regnamespace::text").fetchone()[0]
        report = _inspect(db, "temp's", namespace)
        assert report["success"], report
        assert 'CREATE TEMP TABLE "temp\'s"' in report["sql"]
        db.conn.execute('DROP TABLE "temp\'s"')
        _execute_sql(db, report["sql"])
        db.conn.execute(
            'CREATE VIEW ddl_security_view ("Alias") WITH(security_barrier=true) AS SELECT id FROM "temp\'s"',
        )
        # A view referring to a temp table is itself temporary.
        view = _inspect(db, "ddl_security_view", namespace)
        assert view["success"], view
        assert "security_barrier=true" in view["sql"] and '"Alias"' in view["sql"]
        db.conn.execute("DROP VIEW ddl_security_view")
        _execute_sql(db, view["sql"])
        assert db.conn.info.transaction_status.name == "INTRANS"
    finally:
        db.rollback()
        db.close()


@pytest.mark.parametrize("adapter", ["Oracle", "SQL Server", "Firebird", "Access", "DSN"])
def test_unsupported_adapters_never_query_metadata(adapter):
    db = MagicMock()
    db.type.dbms_id = adapter
    result = _inspect(db, "samples")
    assert not result["success"] and result["error"]["code"] == "unsupported_sql"
    assert result["sql"] is None and result["tables"] == []
    db._cursor.assert_not_called()
    db.close.assert_not_called()


def test_missing_and_ambiguous_sqlite_objects_are_not_successful_empty_sql(tmp_path):
    db = open_backend("sqlite", tmp_path)
    try:
        db.conn.executescript(
            "ATTACH ':memory:' AS other; CREATE TABLE main.samples(x INT); CREATE TABLE other.samples(x INT);",
        )
        ambiguous, missing = _inspect(db, "samples"), _inspect(db, "absent")
        assert ambiguous["error"]["code"] == "ambiguous_object" and ambiguous["sql"] is None
        assert missing["error"]["code"] == "object_not_found" and missing["sql"] is None
        assert _inspect(db, "samples", "other")["success"]
    finally:
        db.close()
