"""JSON number parsing preserves exact scalar digits and records stored-value changes."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from execsql.db.duckdb import DuckDBDatabase
from execsql.db.sqlite import SQLiteDatabase
from execsql.exceptions import ErrInfo
from execsql.importers.json import _parse_json_file, import_json
from execsql.types import DT_Decimal

CASES = {
    "mixed_scale": ["0.1", "0.20"],
    "precision": ["1234567890.1234567891", "0.20"],
    "positive_exponent": ["1e3", "2e2"],
    "mixed_exponent": ["1e3", "0.20"],
    "tiny": ["1e-20", "0.1"],
    "scale38": ["1e-38", "2e-38"],
    "trailing_zeros": ["1.000", "2.000"],
    "integer_edge": ["9007199254740993.0", "20.0"],
    "integer_fraction": ["1.0000000000000001", "2.0"],
    "integer": ["9007199254740993", "20"],
    "fraction": ["0.125", "0.20"],
    "overflow": ["1e400", "2.0"],
    "underflow": ["1e-400", "2.0"],
    "negative_zero": ["-0.0", "0.00"],
    "boolean": ["true", "false"],
    "null": ["null", "0.1"],
    "text": ['"hello"', '"world"'],
    "text_numeric": ['"0.1"', '"0.20"'],
    "nonfinite": ["NaN", "Infinity"],
    "arrays": ["[0.1,1e3,1.000,1234567890.1234567891,1e400]", '[{"v": 0.20},[1e-400],null]'],
    "nested": ['{"n": 1234567890.1234567891}', '{"n": 0.20}'],
}
TARGETS = ["NEW", "TEXT", "INTEGER", "DOUBLE", "NUMERIC", "DECIMAL(38,18)", "DECIMAL(38,30)"]
DATA = Path(__file__).resolve().parents[1] / "data" / "json_numbers"


def settings(conf):
    conf.import_row_buffer = 1
    conf.import_progress_interval = 0
    conf.show_progress = False
    conf.import_common_cols_only = False
    conf.scan_lines = 50
    conf.empty_rows = True


def stored_result(tmp_path, backend, target, case):
    db = DuckDBDatabase(":memory:") if backend == "duckdb" else SQLiteDatabase(":memory:")
    path = tmp_path / "values.json"
    path.write_text("[" + ",".join('{"v":' + token + "}" for token in CASES[case]) + "]")
    column = '"v.n"' if case == "nested" else "v"
    try:
        if target != "NEW":
            db.execute(f"CREATE TABLE t({column} {target})")
            db.commit()
        try:
            import_json(db, None, "t", str(path), is_new=1 if target == "NEW" else False)
        except (ErrInfo, OverflowError, ValueError):
            if target != "NEW":
                assert db.select_data("SELECT count(*) FROM t")[1][0][0] == 0
            return "ERROR"
        declaration = db.select_data("PRAGMA table_info('t')")[1][0][2]
        values = [repr(row[0]) for row in db.select_data(f"SELECT {column} FROM t")[1]]
        return {"type": declaration, "values": values}
    finally:
        db.close()


@pytest.mark.parametrize("format", ["array", "jsonl"])
@pytest.mark.parametrize("token", ["0.1", "1234567890.1234567891", "1e3", "1e400", "1e-400", "-0.00"])
def test_scalar_fraction_and_exponent_numbers_parse_exactly(tmp_path, format, token):
    path = tmp_path / "values.json"
    record = '{"v":' + token + ',"nested":{"v":' + token + '},"integer":9007199254740993}'
    path.write_text("[" + record + "]" if format == "array" else record + "\n")
    row = _parse_json_file(str(path), "utf-8")[0]
    assert isinstance(row["v"], Decimal)
    assert row["v"].as_tuple() == Decimal(token).as_tuple()
    assert row["nested.v"] == row["v"]
    assert type(row["integer"]) is int
    assert row["integer"] == 9007199254740993


@pytest.mark.parametrize("format", ["array", "jsonl"])
def test_nested_array_json_serialization_keeps_previous_numeric_output(tmp_path, format):
    path = tmp_path / "values.json"
    record = '{"v":' + CASES["arrays"][0] + ',"more":' + CASES["arrays"][1] + "}"
    path.write_text("[" + record + "]" if format == "array" else record)
    row = _parse_json_file(str(path), "utf-8")[0]
    legacy = json.loads(record)
    assert row == {key: json.dumps(value) for key, value in legacy.items()}


@pytest.mark.parametrize("value,precision,scale", [("1E3", 4, 0), ("1E400", 401, 0), ("-12E2", 4, 0), ("0.001", 4, 3)])
def test_decimal_positive_exponent_infers_integer_digits(value, precision, scale):
    datatype = DT_Decimal()
    datatype.from_data(Decimal(value))
    assert (datatype.precision, datatype.scale) == (precision, scale)


@pytest.mark.parametrize("backend", ["duckdb", "sqlite"])
@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("case", CASES)
def test_json_stored_value_differential(tmp_path, minimal_conf, backend, exact, target, case):
    if backend == "duckdb":
        pytest.importorskip("duckdb")
    settings(minimal_conf)
    minimal_conf.exact_decimals = exact
    key = f"{case} -> {target} / exact={exact}"
    baseline = json.loads((DATA / f"{backend}.json").read_text())
    changes = json.loads((DATA / "changes.json").read_text()).get(backend, {})
    expected = baseline[key]
    if key in changes:
        change = changes[key]
        assert change["before"] == expected
        assert change["why"]
        expected = change["after"]
    assert stored_result(tmp_path, backend, target, case) == expected


@pytest.mark.parametrize("backend", ["duckdb", "postgres", "mysql", "sqlserver"])
@pytest.mark.parametrize("format", ["array", "jsonl"])
@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize("token", ["1234567890.1234567891", "1e3"])
def test_new_json_numbers_store_exact_values_across_backends(tmp_path, backend, format, exact, token):
    import execsql
    from tests.live_db import open_backend

    db = open_backend(backend, tmp_path)
    path = tmp_path / "values.json"
    record = '{"v":' + token + "}"
    path.write_text("[" + record + "]" if format == "array" else record + "\n")
    name = "json_number_new"
    try:
        db.execute(f"DROP TABLE IF EXISTS {name}")
        result = execsql.run(
            sql=f'-- !x! CONFIG EXACT_DECIMALS {"YES" if exact else "NO"}\n-- !x! IMPORT TO NEW {name} FROM JSON "{path}"',
            connection=db,
        )
        assert result.success, result.errors
        value = db.select_data(f"SELECT v FROM {name}")[1][0][0]
        assert Decimal(value) == Decimal(token)
        assert isinstance(value, Decimal)
    finally:
        db.rollback()
        db.execute(f"DROP TABLE IF EXISTS {name}")
        db.close()


@pytest.mark.parametrize("format", ["array", "jsonl"])
@pytest.mark.parametrize("token", ["0.125", "1e-400", "1e400", "1e999999999999999999999"])
def test_failed_json_load_keeps_existing_rows(tmp_path, format, token):
    import execsql

    pytest.importorskip("duckdb")
    db = DuckDBDatabase(":memory:")
    path = tmp_path / "values.json"
    records = ['{"i":100,"v":1.00}', '{"i":101,"v":' + token + "}"]
    path.write_text("[" + ",".join(records) + "]" if format == "array" else "\n".join(records))
    try:
        db.execute("CREATE TABLE t(i INTEGER,v DECIMAL(10,2))")
        db.execute("INSERT INTO t VALUES (0,42)")
        result = execsql.run(sql=f'-- !x! IMPORT TO t FROM JSON "{path}"', connection=db)
        assert not result.success
        assert db.select_data("SELECT i,v FROM t")[1] == [(0, Decimal("42.00"))]
    finally:
        db.close()


def test_json_difference_records_are_complete_and_do_not_change_baselines():
    changes = json.loads((DATA / "changes.json").read_text())
    expected_keys = {
        f"{case} -> {target} / exact={exact}" for case in CASES for target in TARGETS for exact in [False, True]
    }
    for backend in ["duckdb", "sqlite"]:
        baseline = json.loads((DATA / f"{backend}.json").read_text())
        assert set(baseline) == expected_keys
        assert set(changes[backend]) <= expected_keys
        for key, change in changes[backend].items():
            assert change["before"] == baseline[key]
            assert change["before"] != change["after"]
            assert change["why"]


def test_new_decimal_declaration_keeps_zero_scale():
    from execsql.models import DataTable
    from execsql.types import dbt_duckdb

    table = DataTable(["v"], [[Decimal("1e3")], [Decimal("2e2")]])
    assert table.cols[0].column_type()[4:] == (4, 0)
    assert "NUMERIC(4,0)" in table.create_table(dbt_duckdb, None, "t").replace(" ", "")


@pytest.mark.parametrize("target", ["REAL", "NUMERIC", "DECIMAL(38,18)", "BOOLEAN", "DATE", "POINT"])
@pytest.mark.parametrize("existing", [False, True])
def test_sqlite_finite_decimal_overflow_never_stores_infinity(minimal_conf, target, existing):
    from execsql.models import DataTable

    settings(minimal_conf)
    db = SQLiteDatabase(":memory:")
    try:
        db.execute(f"CREATE TABLE t(v {target})")
        db.execute("INSERT INTO t VALUES (42)")
        db.commit()
        rows = [[Decimal("1.0")], [Decimal("1e400")]]
        with pytest.raises(ErrInfo, match="infinity|range"):
            db.populate_table(None, "t", rows, ["v"], lambda: DataTable(["v"], rows), existing_table=existing)
        assert db.select_data("SELECT v FROM t")[1] == [(42,)]
    finally:
        db.close()


@pytest.mark.parametrize("value", [Decimal("1e400"), Decimal("0." + "1234567890" * 4), Decimal("1e3")])
def test_exact_decimal_text_conversion_does_not_depend_on_driver(value):
    from execsql.db.target_types import existing_table_converter
    from execsql.types import DT_Text

    convert = existing_table_converter(DT_Text, DT_Decimal, lambda value: value, "v", "t")
    assert convert(value) == str(value)


@pytest.mark.parametrize("backend", ["duckdb", "postgres", "mysql", "sqlserver"])
@pytest.mark.parametrize("format", ["array", "jsonl"])
@pytest.mark.parametrize("token", ["1e400", "0.1234567890123456789012345678901234567890"])
def test_json_decimal_text_is_exact_across_backends(tmp_path, backend, format, token):
    import execsql
    from tests.live_db import open_backend

    db = open_backend(backend, tmp_path)
    name = "json_number_text"
    path = tmp_path / "values.json"
    record = '{"v":' + token + "}"
    path.write_text("[" + record + "]" if format == "array" else record + "\n")
    try:
        db.execute(f"DROP TABLE IF EXISTS {name}")
        db.execute(f"CREATE TABLE {name}(v TEXT)")
        result = execsql.run(sql=f'-- !x! IMPORT TO {name} FROM JSON "{path}"', connection=db)
        assert result.success, result.errors
        assert db.select_data(f"SELECT v FROM {name}")[1][0][0] == str(Decimal(token))
    finally:
        db.rollback()
        db.execute(f"DROP TABLE IF EXISTS {name}")
        db.close()
