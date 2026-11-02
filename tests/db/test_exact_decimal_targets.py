"""Existing decimal destinations preserve exact source numbers independently of scanning."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path

import pytest

import execsql
from execsql.db.target_types import existing_table_converter
from execsql.exceptions import DataTypeError, ErrInfo
from execsql.models import DataTable
from execsql.types import DT_Boolean, DT_Decimal, DT_Float, DT_Long, DT_Text
from tests.live_db import open_backend


@pytest.fixture(autouse=True)
def load_settings(minimal_conf):
    minimal_conf.import_row_buffer = 1
    minimal_conf.import_progress_interval = 0
    minimal_conf.show_progress = False


@pytest.mark.parametrize("scanned", [DT_Float, DT_Text, DT_Decimal, DT_Long])
@pytest.mark.parametrize("value", ["0.1", " +1.2345678901234567891e5 ", "001.20", Decimal("0.1"), 7])
def test_exact_source_value_overrides_scanned_conversion(scanned, value):
    def reject_default(value):
        pytest.fail("An exact source number must not use the scanned converter")

    convert = existing_table_converter(DT_Decimal, scanned, reject_default, "v", "t")
    result = convert(value)
    assert result == Decimal(value)
    assert isinstance(result, (int, Decimal)) and not isinstance(result, bool)
    if isinstance(value, Decimal):
        assert result is value


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "abc",
        "NaN",
        "Infinity",
        Decimal("NaN"),
        Decimal("Infinity"),
        True,
        False,
        0.1,
        float("inf"),
        float("nan"),
        "1e99999999999999999999",
        b"0.1",
        datetime.date(2026, 1, 2),
    ],
)
def test_values_without_exact_numeric_source_keep_previous_conversion(value):
    calls = []
    sentinel = object()

    def default(item):
        calls.append(item)
        return sentinel

    convert = existing_table_converter(DT_Decimal, DT_Text, default, "v", "t")
    assert convert(value) is sentinel
    assert len(calls) == 1 and calls[0] is value


def test_boolean_scanned_column_keeps_its_existing_number_conversion():
    convert = existing_table_converter(DT_Decimal, DT_Boolean, lambda value: value == "yes", "v", "t")
    assert convert("yes") == 1
    assert convert("no") == 0


DECLARATIONS = ["DECIMAL(10,2)", "DECIMAL(38,18)", "DECIMAL(38,30)", "NUMERIC", "DOUBLE", "INTEGER", "TEXT"]
CASES = {
    "text_mixed_scale": ["0.1", "0.20"],
    "text_positive_exponent": ["1e3", "0.20"],
    "text_long_trailing_zeros": ["0.1" + "0" * 40, "0.20"],
    "typed_long_coefficient": [Decimal("0." + "1234567890" * 4), Decimal("0.20")],
    "text_exponent": ["1.2345678901234567891e5", "0.20"],
    "text_leading_zeros": ["0001.20", "0.20"],
    "text_spaces": [" +0.10 ", "0.20"],
    "text_scale_rounding": ["0.125", "0.20"],
    "text_high_precision": ["0.1234567890123456789012", "0.20"],
    "text_overflow": ["123456789012345678901", "0.20"],
    "text_malformed": ["abc", "0.20"],
    "text_empty": ["", "0.20"],
    "text_and_null": ["0.1", None],
    "typed_mixed_scale": [Decimal("0.1"), Decimal("0.20")],
    "typed_decimal_and_integer": [Decimal("0.1"), 7],
    "typed_integer": [7, 20],
    "typed_big_integer": [2**63, 20],
    "typed_float": [0.1, 0.2],
    "typed_bool": [True, False],
    "typed_float_and_text": [0.1, "0001.20"],
    "typed_bytes": [b"0.1", b"0.20"],
    "typed_date": [datetime.date(2026, 1, 2), datetime.date(2026, 1, 3)],
    "typed_datetime": [datetime.datetime(2026, 1, 2, 3, 4), datetime.datetime(2026, 1, 3, 3, 4)],
}
_RECORDS = Path(__file__).resolve().parents[1] / "data" / "exact_decimal_targets"


def load_values(db, declaration, values, *, existing=True, infer_strings=False):
    name = "exact_target_values"
    db.rollback()
    db.execute(f"DROP TABLE IF EXISTS {name}")
    db.execute(f"CREATE TABLE {name}(i INTEGER, v {declaration})")
    rows = [(i, v) for i, v in enumerate(values, start=100)]
    try:
        db.populate_table(
            None,
            name,
            rows,
            ["i", "v"],
            lambda: DataTable(["i", "v"], rows, infer_strings=infer_strings),
            existing_table=existing,
        )
        db.commit()
    except (ErrInfo, DataTypeError):
        db.rollback()
        return "ERROR"
    return [repr(row[0]) for row in db.select_data(f"SELECT v FROM {name} ORDER BY i")[1]]


@pytest.mark.parametrize("exact", [False, True], ids=["scan-inexact", "scan-exact"])
@pytest.mark.parametrize("declaration", DECLARATIONS)
@pytest.mark.parametrize("case", CASES)
def test_decimal_target_differential_record(tmp_path, minimal_conf, case, declaration, exact):
    minimal_conf.exact_decimals = exact
    db = open_backend("duckdb", tmp_path)
    try:
        actual = load_values(db, declaration, CASES[case], infer_strings=case.startswith("text"))
    finally:
        db.close()
    key = f"{case} -> {declaration} / exact={exact}"
    baseline = json.loads((_RECORDS / "duckdb.json").read_text())
    changes = json.loads((_RECORDS / "changes.json").read_text())
    if key in changes:
        assert changes[key]["before"] == baseline[key]
        assert changes[key]["why"]
        assert actual == changes[key]["after"]
    else:
        assert actual == baseline[key]


@pytest.mark.parametrize("dbms", ["duckdb", "postgres", "mysql", "sqlserver"])
@pytest.mark.parametrize("exact", [False, True], ids=["scan-inexact", "scan-exact"])
@pytest.mark.parametrize("format", ["csv", "json-text", "ods", "typed", "copy"])
@pytest.mark.parametrize(
    "declaration,value",
    [("DECIMAL(38,30)", "0.1"), ("DECIMAL(38,18)", "1.2345678901234567891e5"), ("DECIMAL(38,18)", "1e3")],
)
def test_exact_existing_target_across_formats_and_backends(dbms, tmp_path, exact, format, declaration, value):
    db = open_backend(dbms, tmp_path)
    name = "exact_target_integration"
    try:
        db.execute(f"DROP TABLE IF EXISTS {name}")
        db.execute(f"CREATE TABLE {name}(i INTEGER, v {declaration})")
        if format == "typed":
            # A typed COPY source can supply Decimals with different scales.
            rows = [(100, Decimal(value)), (101, Decimal("0.20"))]
            import execsql.state as state

            state.conf.exact_decimals = exact
            db.populate_table(
                None,
                name,
                rows,
                ["i", "v"],
                lambda: DataTable(["i", "v"], rows, infer_strings=False),
                existing_table=True,
            )
            db.commit()
        else:
            if format == "copy":
                if dbms == "postgres":
                    # PostgreSQL's unconstrained NUMERIC retains each row's scale.
                    db.execute("DROP TABLE IF EXISTS exact_copy_source")
                    db.execute("CREATE TABLE exact_copy_source(i INTEGER, v NUMERIC)")
                    db.execute(f"INSERT INTO exact_copy_source VALUES (100, {value}), (101, 0.20)")
                    command = f"COPY exact_copy_source FROM initial TO {name} IN initial"
                else:
                    pytest.importorskip("duckdb")
                    import duckdb

                    path = tmp_path / "copy.duckdb"
                    source = duckdb.connect(str(path))
                    try:
                        source.execute(f"CREATE TABLE source(i INTEGER, v {declaration})")
                        source.execute(
                            "INSERT INTO source VALUES (100, ?), (101, ?)",
                            [value, "0.20"],
                        )
                    finally:
                        source.close()
                    command = (
                        f'CONNECT TO DUCKDB(FILE="{path}") AS src\n-- !x! COPY source FROM src TO {name} IN initial'
                    )
            elif format == "csv":
                path = tmp_path / "source.csv"
                path.write_text(f"i,v\n100,{value}\n101,0.20\n")
                command = f'IMPORT TO {name} FROM "{path}"'
            elif format == "json-text":
                path = tmp_path / "source.json"
                path.write_text(json.dumps([{"i": 100, "v": value}, {"i": 101, "v": "0.20"}]))
                command = f'IMPORT TO {name} FROM JSON "{path}"'
            else:
                pytest.importorskip("odf.opendocument")
                from execsql.exporters.ods import OdsFile

                path = tmp_path / "source.ods"
                workbook = OdsFile()
                workbook.open(str(path))
                sheet = workbook.new_sheet("source")
                for i, row in enumerate([["i", "v"], [100, value], [101, "0.20"]]):
                    workbook.add_row_to_sheet(row, sheet, header=(i == 0))
                workbook.add_sheet(sheet)
                workbook.save_close()
                command = f'IMPORT TO {name} FROM "{path}" SHEET source'
            result = execsql.run(
                sql=f"-- !x! CONFIG EXACT_DECIMALS {'YES' if exact else 'NO'}\n-- !x! {command}\n",
                connection=db,
            )
            assert result.success, result.errors
        result = db.select_data(f"SELECT v FROM {name} ORDER BY i")[1]
        assert [row[0] for row in result] == [Decimal(value), Decimal("0.20")]
    finally:
        db.rollback()
        db.execute(f"DROP TABLE IF EXISTS {name}")
        if format == "copy" and dbms == "postgres":
            db.execute("DROP TABLE IF EXISTS exact_copy_source")
        db.close()


@pytest.mark.parametrize("exact", [False, True])
def test_new_table_inference_still_obeys_exact_decimals(tmp_path, exact):
    path = tmp_path / "source.csv"
    path.write_text("i,v\n100,0.1\n101,0.20\n")
    db = open_backend("duckdb", tmp_path)
    try:
        result = execsql.run(
            sql=(f'-- !x! CONFIG EXACT_DECIMALS {"YES" if exact else "NO"}\n-- !x! IMPORT TO NEW t FROM "{path}"\n'),
            connection=db,
        )
        assert result.success, result.errors
        assert db.column_kinds("t")["v"] is (DT_Decimal if exact else DT_Float)
        values = [row[0] for row in db.select_data("SELECT v FROM t ORDER BY i")[1]]
        assert values == ([Decimal("0.1"), Decimal("0.20")] if exact else [0.1, 0.2])
    finally:
        db.close()


@pytest.mark.parametrize("exact", [False, True])
@pytest.mark.parametrize(
    "declaration",
    [value for value in DECLARATIONS if value.startswith("DECIMAL") or value == "NUMERIC"],
)
@pytest.mark.parametrize("case", CASES)
def test_new_decimal_binding_retains_previous_scanned_values(tmp_path, minimal_conf, exact, declaration, case):
    minimal_conf.exact_decimals = exact
    db = open_backend("duckdb", tmp_path)
    try:
        actual = load_values(db, declaration, CASES[case], existing=False, infer_strings=case.startswith("text"))
    finally:
        db.close()
    baseline = json.loads((_RECORDS / "duckdb.json").read_text())
    assert actual == baseline[f"{case} -> {declaration} / exact={exact}"]


@pytest.mark.parametrize(
    "value",
    ["1e3", "-1e3", "1.00e3", Decimal("1e3"), Decimal("-1e3"), Decimal("0e999999999"), Decimal("-0e999999999")],
)
def test_positive_decimal_exponents_are_expanded_within_driver_capacity(value):
    convert = existing_table_converter(
        DT_Decimal,
        DT_Float,
        lambda value: value,
        "v",
        "t",
        decimal_binding_precision=38,
    )
    actual = convert(value)
    assert actual == Decimal(value)
    assert actual.as_tuple().exponent == 0


@pytest.mark.parametrize("value", ["1e38", "1e999999999", Decimal("1e999999999")])
def test_oversized_positive_exponent_fails_without_expanding_it(value):
    convert = existing_table_converter(
        DT_Decimal,
        DT_Float,
        lambda value: value,
        "v",
        "t",
        decimal_binding_precision=38,
    )
    with pytest.raises(ErrInfo, match="column v.*38 decimal digits"):
        convert(value)


@pytest.mark.parametrize(
    "value",
    [Decimal("0.1" + "0" * 40), Decimal("0." + "1234567890" * 4), Decimal("1e-999999999")],
)
def test_decimal_outside_native_binding_capacity_uses_exact_sql_text(value):
    convert = existing_table_converter(
        DT_Decimal,
        DT_Float,
        lambda value: value,
        "v",
        "t",
        decimal_binding_precision=38,
    )
    assert convert(value) == str(value)


@pytest.mark.parametrize("value", [Decimal("0e-999999999999"), Decimal("-0e-999999999999")])
def test_zero_parameters_do_not_expand_huge_scales(value):
    convert = existing_table_converter(
        DT_Decimal,
        DT_Float,
        lambda value: value,
        "v",
        "t",
        decimal_binding_precision=38,
    )
    actual = convert(value)
    assert actual == 0 and actual.as_tuple().exponent == 0
    assert actual.is_signed() == value.is_signed()


@pytest.mark.parametrize("exact", [False, True])
def test_small_exact_values_at_maximum_duckdb_scale(tmp_path, minimal_conf, exact):
    minimal_conf.exact_decimals = exact
    values = [Decimal("1e-38"), Decimal("2e-38"), Decimal("0." + "0" * 20 + "123456789012345678")]
    db = open_backend("duckdb", tmp_path)
    try:
        actual = load_values(db, "DECIMAL(38,38)", values)
    finally:
        db.close()
    assert actual == [repr(value) for value in values]


@pytest.mark.parametrize("value", [Decimal("1e-38"), Decimal("2e-38"), Decimal("0." + "0" * 20 + "123456789012345678")])
def test_maximum_scale_binding_text_has_no_scientific_exponent(value):
    convert = existing_table_converter(
        DT_Decimal,
        DT_Float,
        lambda value: value,
        "v",
        "t",
        decimal_binding_precision=38,
    )
    assert convert(value) == format(value, "f")
