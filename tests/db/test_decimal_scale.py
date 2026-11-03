"""Known decimal scales reject rounding while preserving exact input and trailing zeros."""

from __future__ import annotations

from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

import execsql.db.target_types as types
from execsql.db.duckdb import DuckDBDatabase
from execsql.exceptions import ErrInfo
from execsql.models import DataTable
from execsql.types import DT_Decimal, DT_Float, DT_Long, DT_Text, DT_Boolean


@pytest.mark.parametrize(
    "name,kind,scale",
    [
        ("DECIMAL(10,2)", DT_Decimal, 2),
        ("numeric(12, 3)", DT_Decimal, 3),
        ("number(10,-2)", DT_Decimal, -2),
        ("numeric(10,0)", DT_Long, 0),
        ("NUMERIC(10)", DT_Long, 0),
        ("numeric", DT_Decimal, None),
        ("money", DT_Decimal, None),
        ("double precision", DT_Float, None),
        ("varchar(10)", DT_Text, None),
        ("numeric(10,2)[]", None, None),
        ("decimal(10,bad)", DT_Decimal, None),
    ],
)
def test_declared_type_reports_kind_and_scale_without_changing_kind_api(name, kind, scale):
    assert types.kind_for_type_name(name) is kind
    assert types.kind_and_scale_for_type_name(name) == (kind, scale)


@pytest.mark.parametrize(
    "scale,value",
    [
        (2, "0.125"),
        (2, "1e-3"),
        (2, Decimal("1.2301")),
        (2, "-0.125"),
        (0, "0.1"),
        (-2, 1),
        (-2, "99"),
        (-2, Decimal("100.01")),
        (2, "1e-999999999"),
    ],
)
def test_nonzero_digits_beyond_scale_are_an_error(scale, value):
    convert = types.existing_table_converter(
        DT_Decimal,
        DT_Float,
        lambda value: value,
        "amount",
        "t",
        decimal_scale=scale,
    )
    with pytest.raises(ErrInfo, match="amount.*scale.*round"):
        convert(value)


@pytest.mark.parametrize(
    "scale,value",
    [
        (2, "1.000"),
        (2, "0.10"),
        (2, "1.2e2"),
        (2, Decimal("12345678901234567890.1200")),
        (2, 0),
        (2, "0e-999999999"),
        (-2, 100),
        (-2, "1e2"),
        (-2, Decimal("-200.000")),
        (None, "0.125"),
    ],
)
def test_values_that_fit_scale_are_not_quantized(scale, value):
    with localcontext() as context:
        context.prec = 2
        convert = types.existing_table_converter(
            DT_Decimal,
            DT_Float,
            lambda value: value,
            "amount",
            "t",
            decimal_scale=scale,
        )
        assert convert(value) == Decimal(value)


@pytest.mark.parametrize("value", [0.125, True, None, "word", Decimal("NaN"), Decimal("Infinity")])
def test_scale_check_retains_previous_nonexact_conversion(value):
    sentinel = object()
    convert = types.existing_table_converter(
        DT_Decimal,
        DT_Text,
        lambda value: sentinel,
        "amount",
        "t",
        decimal_scale=2,
    )
    assert convert(value) is sentinel


def test_boolean_number_conversion_respects_negative_scale():
    convert = types.existing_table_converter(
        DT_Decimal,
        DT_Boolean,
        lambda value: value == "yes",
        "amount",
        "t",
        decimal_scale=-2,
    )
    assert convert("no") == 0
    with pytest.raises(ErrInfo, match="scale"):
        convert("yes")


def test_column_metadata_is_a_compatible_kind_dictionary():
    kinds = types.ColumnMetadata({"v": (DT_Decimal, 2), "unlimited": (DT_Decimal, None), "label": (DT_Text, None)})
    assert kinds == {"v": DT_Decimal, "unlimited": DT_Decimal, "label": DT_Text}
    assert isinstance(kinds, dict)
    assert kinds.decimal_scales == {"v": 2}


@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize("value", ["0.125", "1e-3", Decimal("0.125")])
def test_failed_decimal_load_rolls_back_preceding_batches(tmp_path, minimal_conf, exact, value):
    pytest.importorskip("duckdb")
    minimal_conf.exact_decimals = exact
    minimal_conf.import_row_buffer = 1
    minimal_conf.import_progress_interval = 0
    minimal_conf.show_progress = False
    db = DuckDBDatabase(":memory:")
    try:
        db.execute("CREATE TABLE t(i INTEGER, amount DECIMAL(10,2))")
        db.execute("INSERT INTO t VALUES (0,42)")
        rows = [(100, "1.00"), (101, value)]
        with pytest.raises(ErrInfo, match="amount.*scale.*round"):
            db.populate_table(
                None,
                "t",
                rows,
                ["i", "amount"],
                lambda: DataTable(["i", "amount"], rows),
                existing_table=True,
            )
        assert db.select_data("SELECT amount FROM t")[1] == [(Decimal("42.00"),)]
    finally:
        db.close()


def test_duckdb_reports_scale_from_declared_type_without_losing_kind(tmp_path):
    pytest.importorskip("duckdb")
    db = DuckDBDatabase(":memory:")
    try:
        db.execute("CREATE TABLE t(a DECIMAL(10,2), b DECIMAL(38,30), c VARCHAR)")
        kinds = db.column_kinds("t")
        assert kinds == {"a": DT_Decimal, "b": DT_Decimal, "c": DT_Text}
        assert kinds.decimal_scales == {"a": 2, "b": 30}
    finally:
        db.close()


@pytest.mark.parametrize(
    "adapter,rows,expected",
    [
        ("postgres", [("v", "numeric(10,2)"), ("n", "numeric"), ("neg", "numeric(10,-2)")], {"v": 2, "neg": -2}),
        ("mysql", [("v", "decimal(10,2)"), ("n", "varchar(10)")], {"v": 2}),
        ("sqlserver", [("v", "decimal", 10, 2), ("cash", "money", 19, 4)], {"v": 2, "cash": 4}),
    ],
)
def test_catalog_metadata_retains_decimal_scales(monkeypatch, adapter, rows, expected):
    from importlib import import_module

    module = import_module("execsql.db." + adapter)
    cls = {"postgres": "PostgresDatabase", "mysql": "MySQLDatabase", "sqlserver": "SqlServerDatabase"}[adapter]
    db = object.__new__(getattr(module, cls))
    monkeypatch.setattr(db, "_column_type_query", lambda *args, **kwargs: (None, rows))
    kinds = db.column_kinds("t")
    assert kinds.decimal_scales == expected


@pytest.mark.parametrize(
    "adapter,description,expected",
    [
        ("generic", ("v", Decimal, None, None, 10, 2, True), 2),
        ("oracle", ("v", SimpleNamespace(name="DB_TYPE_NUMBER"), None, None, 10, -2, True), -2),
        ("oracle", ("v", SimpleNamespace(name="DB_TYPE_NUMBER"), None, None, 126, -127, True), None),
        ("firebird", ("v", Decimal, None, None, 10, -2, True), 2),
    ],
)
def test_description_scale_normalization(adapter, description, expected):
    from execsql.db.base import Database
    from execsql.db.firebird import FirebirdDatabase
    from execsql.db.oracle import OracleDatabase
    from execsql.db.sqlserver import SqlServerDatabase

    cls = {"generic": SqlServerDatabase, "oracle": OracleDatabase, "firebird": FirebirdDatabase}[adapter]
    db = object.__new__(cls)
    if adapter == "generic":
        actual = Database._described_column(db, description)
    else:
        actual = db._described_column(description)
    assert actual == (DT_Decimal, expected)


@pytest.mark.parametrize("dbms", ["duckdb", "postgres", "mysql", "sqlserver"])
@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize("format", ["json-text", "ods", "copy", "typed"])
@pytest.mark.parametrize("value,valid", [("0.125", False), ("1.000", True)])
def test_declared_scale_across_load_paths(dbms, tmp_path, exact, format, value, valid):
    import execsql
    from tests.live_db import open_backend

    db = open_backend(dbms, tmp_path)
    name = "decimal_scale_target"
    try:
        db.execute(f"DROP TABLE IF EXISTS {name}")
        db.execute(f"CREATE TABLE {name}(i INTEGER, amount DECIMAL(10,2))")
        db.execute(f"INSERT INTO {name} VALUES (0,42)")
        db.commit()
        if format == "typed":
            import execsql.state as state

            state.conf.exact_decimals = exact
            state.conf.import_row_buffer = 1
            state.conf.import_progress_interval = 0
            state.conf.show_progress = False
            rows = [(100, Decimal("1.00")), (101, Decimal(value))]
            if valid:
                db.populate_table(
                    None,
                    name,
                    rows,
                    ["i", "amount"],
                    lambda: DataTable(["i", "amount"], rows, infer_strings=False),
                    existing_table=True,
                )
                db.commit()
            else:
                with pytest.raises(ErrInfo, match="amount.*scale.*round"):
                    db.populate_table(
                        None,
                        name,
                        rows,
                        ["i", "amount"],
                        lambda: DataTable(["i", "amount"], rows, infer_strings=False),
                        existing_table=True,
                    )
        else:
            if format == "json-text":
                import json

                path = tmp_path / "values.json"
                path.write_text(json.dumps([{"i": 100, "amount": "1.00"}, {"i": 101, "amount": value}]))
                command = f'IMPORT TO {name} FROM JSON "{path}"'
            elif format == "ods":
                pytest.importorskip("odf.opendocument")
                from execsql.exporters.ods import OdsFile

                path = tmp_path / "values.ods"
                workbook = OdsFile()
                workbook.open(str(path))
                sheet = workbook.new_sheet("values")
                for i, row in enumerate([["i", "amount"], [100, "1.00"], [101, value]]):
                    workbook.add_row_to_sheet(row, sheet, header=(i == 0))
                workbook.add_sheet(sheet)
                workbook.save_close()
                command = f'IMPORT TO {name} FROM "{path}" SHEET values'
            else:
                pytest.importorskip("duckdb")
                import duckdb

                path = tmp_path / "source.duckdb"
                source = duckdb.connect(str(path))
                try:
                    source.execute("CREATE TABLE source(i INTEGER,amount DECIMAL(10,3))")
                    source.execute("INSERT INTO source VALUES (100,?),(101,?)", ["1.00", value])
                finally:
                    source.close()
                command = f'CONNECT TO DUCKDB(FILE="{path}") AS src\n-- !x! COPY source FROM src TO {name} IN initial'
            result = execsql.run(
                sql=f"-- !x! CONFIG EXACT_DECIMALS {'YES' if exact else 'NO'}\n-- !x! {command}\n",
                connection=db,
            )
            assert result.success is valid, result.errors
            if not valid:
                assert "scale" in result.errors[0].message
        rows = db.select_data(f"SELECT amount FROM {name} ORDER BY i")[1]
        expected = [Decimal("42"), Decimal("1"), Decimal(value)] if valid else [Decimal("42")]
        assert [row[0] for row in rows] == expected
    finally:
        db.rollback()
        db.execute(f"DROP TABLE IF EXISTS {name}")
        db.close()


@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize("value,valid", [("0.125", False), ("1.000", True)])
def test_duckdb_csv_scale_validation(tmp_path, exact, value, valid):
    import execsql
    from tests.live_db import open_backend

    db = open_backend("duckdb", tmp_path)
    path = tmp_path / "values.csv"
    path.write_text("i,amount\n100,1.00\n101," + value + "\n")
    try:
        db.execute("CREATE TABLE t(i INTEGER, amount DECIMAL(10,2))")
        db.execute("INSERT INTO t VALUES (0,42)")
        result = execsql.run(
            sql=f'-- !x! CONFIG EXACT_DECIMALS {"YES" if exact else "NO"}\n-- !x! IMPORT TO t FROM "{path}"\n',
            connection=db,
        )
        assert result.success is valid, result.errors
        assert db.select_data("SELECT count(*) FROM t")[1][0][0] == (3 if valid else 1)
    finally:
        db.close()


def test_scale_validation_applies_only_to_loaded_columns(minimal_conf):
    pytest.importorskip("duckdb")
    minimal_conf.import_row_buffer = 1
    minimal_conf.import_progress_interval = 0
    minimal_conf.show_progress = False
    db = DuckDBDatabase(":memory:")
    try:
        db.execute("CREATE TABLE t(i INTEGER, amount DECIMAL(10,2) DEFAULT 0)")
        rows = [(100, "0.125")]
        db.populate_table(None, "t", rows, ["i"], lambda: DataTable(["i", "amount"], rows), existing_table=True)
        assert db.select_data("SELECT i,amount FROM t")[1] == [(100, Decimal("0.00"))]
    finally:
        db.close()


@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize("token", ["1e39", "-1e39", "1e999999999"])
def test_common_column_json_load_ignores_unbound_decimals(tmp_path, exact, token):
    import execsql

    pytest.importorskip("duckdb")
    db = DuckDBDatabase(":memory:")
    path = tmp_path / "values.json"
    path.write_text('[{"i":100,"unused":' + token + "}]")
    try:
        db.execute("CREATE TABLE t(i INTEGER)")
        result = execsql.run(
            sql=(
                "-- !x! IMPORT_COMMON_COLUMNS_ONLY YES\n"
                f"-- !x! CONFIG EXACT_DECIMALS {'YES' if exact else 'NO'}\n"
                f'-- !x! IMPORT TO t FROM JSON "{path}"\n'
            ),
            connection=db,
        )
        assert result.success, result.errors
        assert db.select_data("SELECT i FROM t")[1] == [(100,)]
    finally:
        db.close()
