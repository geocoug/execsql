"""Real-file inspection parity, bounded inference, ownership and error contracts."""

import codecs
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from execsql import inspect_file, run
from execsql import file_inspection
from execsql.config import ConfigData


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.setattr(
        ConfigData,
        "_search_paths",
        classmethod(lambda cls, script_path, config_file, start_dir=None: [str(config_file)] if config_file else []),
    )


def make_file(tmp_path, kind):
    path = tmp_path / f"input.{'txt' if kind == 'text' else kind}"
    headers, data = ["id", "label"], [[2, "alpha"], [3, "beta"]]
    if kind in ("csv", "tsv", "text"):
        delimiter = "\t" if kind == "tsv" else ","
        path.write_text(delimiter.join(headers) + "\n" + "\n".join(delimiter.join(map(str, row)) for row in data))
    elif kind in ("json", "jsonl"):
        records = [dict(zip(headers, row)) for row in data]
        path.write_text(json.dumps(records) if kind == "json" else "\n".join(map(json.dumps, records)))
    elif kind == "xlsx":
        openpyxl = pytest.importorskip("openpyxl")
        book = openpyxl.Workbook()
        book.active.title = "Data"
        for row in [headers, *data]:
            book.active.append(row)
        book.create_sheet("Other")
        book.save(path)
        book.close()
    elif kind == "xls":
        pytest.importorskip("xlrd")
        path.write_bytes((Path(__file__).parent / "data/file_inspection/legacy.xls").read_bytes())
    elif kind == "ods":
        document = pytest.importorskip("odf.opendocument")
        table = pytest.importorskip("odf.table")
        text = pytest.importorskip("odf.text")
        book = document.OpenDocumentSpreadsheet()
        sheet = table.Table(name="Data")
        for values in [headers, *data]:
            row = table.TableRow()
            for value in values:
                cell = table.TableCell(valuetype="string")
                cell.addElement(text.P(text=str(value)))
                row.addElement(cell)
            sheet.addElement(row)
        book.spreadsheet.addElement(sheet)
        book.save(str(path))
    else:
        pl = pytest.importorskip("polars")
        frame = pl.DataFrame({"id": [2, 3], "label": ["alpha", "beta"]})
        if kind == "parquet":
            frame.write_parquet(path)
        else:
            frame.write_ipc(path)
    return path


@pytest.mark.parametrize("kind", ["csv", "tsv", "text", "json", "jsonl", "xls", "xlsx", "ods", "parquet", "feather"])
def test_every_format_matches_real_import_headers_types_and_stored_rows(tmp_path, kind):
    path = make_file(tmp_path, kind)
    original = path.read_bytes()
    options = {"sheet": "Data"} if kind in ("xls", "xlsx", "ods") else {}
    result = inspect_file(path, **options)
    assert result["success"], result
    assert result["scan"]["rows_examined"] == 2 and result["scan"]["complete"]
    assert [(c["name"], c["inferred_type"]) for c in result["columns"]] == [("id", "integer"), ("label", "varchar(5)")]
    assert path.read_bytes() == original
    assert json.loads(json.dumps(result)) == result
    if kind in ("parquet", "feather"):
        assert [c["source_type"] for c in result["columns"]] == ["Int64", "String"]
    from_clause = f'"{path}"'
    if kind in ("xlsx", "xls"):
        from_clause = f'EXCEL "{path}" SHEET Data'
    elif kind == "ods":
        from_clause += " SHEET Data"
    elif kind in ("json", "jsonl", "parquet", "feather"):
        from_clause = f'{"JSON" if kind == "jsonl" else kind.upper()} "{path}"'
    db_path = tmp_path / "loaded.sqlite"
    imported = run(sql=f"-- !x! IMPORT TO NEW inspected FROM {from_clause}", dsn=f"sqlite:///{db_path}", new_db=True)
    assert imported.success, imported.errors
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT * FROM inspected ORDER BY id").fetchall() == [(2, "alpha"), (3, "beta")]
        assert [(row[1], row[2]) for row in db.execute("PRAGMA table_info(inspected)")] == [
            ("id", "INTEGER"),
            ("label", "varchar"),
        ]


@pytest.mark.parametrize("limit,complete,count", [(1, False, 1), (2, False, 2), (3, True, 3), (4, True, 3)])
def test_sample_reports_limits_and_late_type_changes(tmp_path, limit, complete, count):
    path = tmp_path / "mixed.csv"
    path.write_text("v\n2\n3\nlate text\n")
    result = inspect_file(path, sample_rows=limit)
    assert result["success"], result
    assert result["scan"] == {
        "mode": "sample",
        "row_limit": limit,
        "rows_examined": count,
        "complete": complete,
        "total_rows": 3 if complete else None,
        "source_materialized": False,
    }
    assert result["columns"][0]["inferred_type"] == ("varchar(9)" if complete else "integer")
    assert inspect_file(path)["columns"][0]["inferred_type"] == "varchar(9)"


def test_json_union_flattening_decimal_precision_and_sample_materialization(tmp_path):
    path = tmp_path / "nested.jsonl"
    path.write_text('{"id":2,"site":{"code":"a"},"value":0.20}\n{"id":3,"late":"x","value":1.25}\n')
    result = inspect_file(path, sample_rows=1)
    assert result["success"], result
    assert result["scan"]["source_materialized"] is True
    assert result["scan"]["total_rows"] == 2 and not result["scan"]["complete"]
    assert [c["name"] for c in result["columns"]] == ["id", "site.code", "value", "late"]
    assert result["columns"][2]["inferred_type"] == "decimal(2,2)"
    assert result["columns"][3]["null_count"] == 1


def test_json_container_is_detected_from_content_not_its_extension(tmp_path):
    path = tmp_path / "lines.json"
    path.write_text('{"value":2}\n{"value":3}\n')
    result = inspect_file(path)
    assert result["success"], result
    assert result["format"] == "jsonl" and result["format_source"] == "detected"


@pytest.mark.parametrize("kind", ["xls", "xlsx", "ods"])
def test_workbooks_list_names_and_select_by_import_ordinal(tmp_path, kind):
    path = make_file(tmp_path, kind)
    listing = inspect_file(path)
    assert listing["success"], listing
    assert listing["worksheets"][0] == "Data"
    assert listing["scan"] is None and listing["columns"] == []
    selected = inspect_file(path, sheet="1", sample_rows=1)
    assert selected["success"] and selected["sheet"] == "Data"
    assert selected["scan"]["rows_examined"] == 1 and not selected["scan"]["complete"]
    missing = inspect_file(path, sheet="absent")
    assert not missing["success"] and missing["error"]["code"] == "read_error"
    assert missing["columns"] == [] and missing["scan"] is None


@pytest.mark.parametrize("kind", ["xls", "xlsx"])
def test_explicit_format_for_renamed_workbook(tmp_path, monkeypatch, kind):
    path = make_file(tmp_path, kind)
    renamed = path.parent / "a"
    path.rename(renamed)
    monkeypatch.chdir(tmp_path)
    result = inspect_file("a", file_format=kind, sheet="Data")
    assert result["success"], result
    assert result["format_source"] == "explicit" and result["scan"]["rows_examined"] == 2


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_csv_bom_and_quoted_multiline_values_follow_import_reader(tmp_path, encoding):
    path = tmp_path / "quoted.csv"
    path.write_text('id,label\n2,"caf\u00e9\nsecond line"\n', encoding=encoding)
    result = inspect_file(path)
    assert result["success"], result
    assert result["encoding"] == {"name": codecs.lookup(encoding).name, "source": "bom"}
    assert result["scan"]["rows_examined"] == 1 and result["delimiter"] == ","


def test_explicit_dialect_skip_and_effective_configuration(tmp_path):
    path = tmp_path / "config.txt"
    path.write_bytes("junk\nNUMBER|LABEL\n1|caf\u00e9\n0|na\u00efve\n".encode("cp1252"))
    conf = tmp_path / "execsql.conf"
    conf.write_text("[encoding]\nimport=cp1252\n[input]\nboolean_int=No\nfold_column_headers=lower\n")
    result = inspect_file(path, delimiter="|", quote="none", skip_rows=1, config_file=conf)
    assert result["success"], result
    assert result["encoding"] == {"name": "cp1252", "source": "config"}
    assert result["settings"]["boolean_int"] is False
    assert result["config_files"] == [str(conf)]
    assert result["dialect_source"] == "explicit" and result["quote"] is None
    assert [c["name"] for c in result["columns"]] == ["number", "label"]
    assert result["columns"][0]["inferred_type"] == "integer"


def test_stored_types_remain_aligned_after_header_deletion(tmp_path):
    pl = pytest.importorskip("polars")
    path = tmp_path / "headers.parquet"
    pl.DataFrame({"": [2], "kept": ["word"]}).write_parquet(path)
    conf = tmp_path / "input.conf"
    conf.write_text("[input]\ndelete_empty_columns=Yes\n")
    result = inspect_file(path, config_file=conf)
    assert result["success"], result
    assert [(c["name"], c["source_type"]) for c in result["columns"]] == [("kept", "String")]


@pytest.mark.parametrize(
    "options",
    [
        {"sample_rows": 0},
        {"sample_rows": True},
        {"skip_rows": -1},
        {"encoding": "unknown-codec"},
        {"sheet": "Data"},
        {"quote": '"'},
        {"delimiter": "xx"},
        {"delimiter": ",", "quote": ","},
        {"file_format": "pdf"},
    ],
)
def test_invalid_arguments_raise_before_reading(tmp_path, options):
    with pytest.raises(ValueError):
        inspect_file(tmp_path / "missing.csv", **options)


@pytest.mark.parametrize("contents", ["", "a,b\n1,2,3\n", "a,\n1,2\n"])
def test_parse_failures_never_leave_partial_columns(tmp_path, contents):
    path = tmp_path / "bad.csv"
    path.write_text(contents)
    result = inspect_file(path)
    assert not result["success"] and result["error"]["code"] == "read_error"
    assert result["scan"] is None and result["columns"] == []


def test_missing_dependency_is_structured_without_printing(tmp_path, monkeypatch, capsys):
    path = tmp_path / "data.parquet"
    path.write_bytes(b"PAR1")
    monkeypatch.setattr(file_inspection.importlib, "import_module", MagicMock(side_effect=ImportError("not installed")))
    result = inspect_file(path)
    assert not result["success"] and result["error"]["code"] == "dependency_error"
    assert "execsql2[formats]" in result["error"]["message"]
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("interrupted", [False, True])
def test_context_and_handles_restore_on_error_and_interrupt(tmp_path, monkeypatch, interrupted):
    import execsql.state as state
    from execsql.exporters.delimited import CsvFile

    path = make_file(tmp_path, "csv")
    original = state.get_context()
    close = MagicMock(wraps=CsvFile.close)
    monkeypatch.setattr(
        file_inspection,
        "_scan",
        MagicMock(side_effect=KeyboardInterrupt() if interrupted else RuntimeError("bad")),
    )
    monkeypatch.setattr(CsvFile, "close", lambda self: close(self))
    monkeypatch.setattr(
        "execsql.api._connect_from_dsn",
        MagicMock(side_effect=AssertionError("inspection must not connect")),
    )
    if interrupted:
        with pytest.raises(KeyboardInterrupt):
            inspect_file(path)
    else:
        assert not inspect_file(path)["success"]
    assert state.get_context() is original
    close.assert_called_once()
    path.unlink()  # Also proves the file handle is closed on Windows.


def test_missing_and_unknown_files_are_structured(tmp_path):
    assert inspect_file(tmp_path / "missing.csv")["error"]["code"] == "file_error"
    unknown = tmp_path / "unknown.bin"
    unknown.write_bytes(b"not a recognized format")
    assert inspect_file(unknown)["error"]["code"] == "unsupported_format"
