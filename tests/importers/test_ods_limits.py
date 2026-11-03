"""ODS imports reject archive and logical expansion before allocation or target changes."""

from __future__ import annotations

import zipfile
from unittest.mock import patch

import pytest

pytest.importorskip("odf.opendocument")
from odf.table import TableCell, TableRow  # noqa: E402
from odf.text import P, S  # noqa: E402

from execsql.exceptions import ErrInfo  # noqa: E402
from execsql.exporters.ods import OdsFile  # noqa: E402
from execsql.importers.ods import ods_data  # noqa: E402

DEFAULTS = {
    "ods_max_xml_mb": 100,
    "ods_max_compression_ratio": 100,
    "import_max_rows": 1_048_576,
    "import_max_columns": 16_384,
    "import_max_cells": 10_000_000,
    "import_max_cell_chars": 1_048_576,
    "import_max_text_chars": 268_435_456,
}


def cell(text=None, **attrs):
    result = TableCell(**attrs)
    if text is not None:
        result.addElement(P(text=text))
    return result


def row(*cells, **attrs):
    result = TableRow(**attrs)
    for value in cells:
        result.addElement(value)
    return result


def write_sheet(tmp_path, *rows):
    path = tmp_path / "values.ods"
    book = OdsFile()
    book.open(str(path))
    sheet = book.new_sheet("s")
    for value in rows:
        sheet.addElement(value)
    book.add_sheet(sheet)
    book.save_close()
    return path


@pytest.fixture(autouse=True)
def limits(minimal_conf):
    for name, value in DEFAULTS.items():
        setattr(minimal_conf, name, value)
    return minimal_conf


@pytest.mark.parametrize("name", list(DEFAULTS)[2:])
def test_each_logical_limit_rejects_expansion(tmp_path, limits, name):
    path = write_sheet(
        tmp_path,
        row(cell("h", numbercolumnsrepeated=3)),
        row(cell("data", numbercolumnsrepeated=3), numberrowsrepeated=3),
    )
    setattr(
        limits,
        name,
        {
            "import_max_rows": 2,
            "import_max_columns": 2,
            "import_max_cells": 8,
            "import_max_cell_chars": 3,
            "import_max_text_chars": 20,
        }[name],
    )
    with pytest.raises(ErrInfo, match=name):
        ods_data(str(path), "s")


@pytest.mark.parametrize(
    "name,value,payload",
    [
        ("ods_max_xml_mb", 1, b"x" * (2 * 1024 * 1024)),
        ("ods_max_compression_ratio", 2, b"x" * 10000),
    ],
    ids=["xml-size", "compression-ratio"],
)
def test_archive_limits_run_before_odf_parser(tmp_path, limits, name, value, payload):
    path = tmp_path / "archive.ods"
    setattr(limits, name, value)
    if name == "ods_max_xml_mb":
        limits.ods_max_compression_ratio = 0
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.xml", payload)
    with patch.object(OdsFile, "open", side_effect=AssertionError("Parser must not run")) as parser:
        with pytest.raises(ErrInfo, match=name):
            ods_data(str(path), "s")
        parser.assert_not_called()


def test_trailing_empty_repeats_are_not_materialized_or_counted(tmp_path, limits):
    path = write_sheet(
        tmp_path,
        row(cell("h"), cell(numbercolumnsrepeated=100000)),
        row(cell("x")),
        row(cell(), numberrowsrepeated=100000),
    )
    limits.import_max_rows = 2
    limits.import_max_columns = 1
    limits.import_max_cells = 2
    limits.import_max_cell_chars = 1
    limits.import_max_text_chars = 2
    assert ods_data(str(path), "s") == (["h"], [["x"]])


def test_skip_excludes_leading_repeated_rows(tmp_path, limits):
    path = write_sheet(tmp_path, row(cell("junk"), numberrowsrepeated=100), row(cell("h")), row(cell("x")))
    limits.import_max_rows = 2
    limits.import_max_cells = 2
    limits.import_max_cell_chars = 1
    limits.import_max_text_chars = 2
    assert ods_data(str(path), "s", 100) == (["h"], [["x"]])


def test_interior_empty_rows_and_padding_count(tmp_path, limits):
    path = write_sheet(tmp_path, row(cell("a"), cell("b")), row(cell(), numberrowsrepeated=3), row(cell("x")))
    limits.import_max_cells = 9
    with pytest.raises(ErrInfo, match="import_max_cells"):
        ods_data(str(path), "s")


def test_zero_disables_limits_without_truncating(tmp_path, limits):
    for name in DEFAULTS:
        setattr(limits, name, 0)
    path = write_sheet(tmp_path, row(cell("h")), row(cell("hello", numbercolumnsrepeated=3), numberrowsrepeated=4))
    limits.create_col_hdrs = True
    headers, data = ods_data(str(path), "s")
    assert len(headers) == 3
    assert data == [["hello"] * 3] * 4


@pytest.mark.parametrize(
    "attribute,kind",
    [
        ("numberrowsrepeated", "row"),
        ("numbercolumnsrepeated", "cell"),
        ("numbercolumnsspanned", "cell"),
        ("numberrowsspanned", "cell"),
        ("c", "space"),
    ],
)
@pytest.mark.parametrize("value", ["-1", "bad", "1.5"])
@pytest.mark.parametrize("skip", [0, 2])
def test_invalid_expansion_attributes_identify_invalid_input(tmp_path, attribute, kind, value, skip):
    # odfpy validates types on construction; replace the saved XML to model hostile input.
    c = cell("x")
    attrs = {attribute: 123} if kind == "cell" else {}
    if kind == "space":
        c = TableCell()
        p = P()
        p.addElement(S(c=123))
        c.addElement(p)
    elif kind == "cell":
        c = cell("x", **attrs)
    r = row(c, **({attribute: 123} if kind == "row" else {}))
    path = write_sheet(tmp_path, row(cell("h")), r)
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["content.xml"] = entries["content.xml"].replace(b'="123"', f'="{value}"'.encode())
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    with pytest.raises(ErrInfo, match="Invalid.*(repeat|span|space|count|expansion)"):
        ods_data(str(path), "s", skip)


@pytest.mark.parametrize("name", DEFAULTS)
@pytest.mark.parametrize("value", [0, 1, 123])
def test_budget_config_file_values(tmp_path, name, value):
    from execsql.config import ConfigData

    path = tmp_path / "execsql.conf"
    path.write_text(f"[input]\n{name}={value}\n")
    with patch.object(ConfigData, "_search_paths", return_value=[str(path)]):
        config = ConfigData(str(tmp_path), None)
    assert getattr(config, name) == value
    assert config.defaults[name] == DEFAULTS[name]


@pytest.mark.parametrize("name", DEFAULTS)
@pytest.mark.parametrize("value", ["-1", "bad", "1.2"])
def test_budget_config_rejects_negative_or_noninteger(tmp_path, name, value):
    from execsql.config import ConfigData
    from execsql.exceptions import ConfigError

    path = tmp_path / "execsql.conf"
    path.write_text(f"[input]\n{name}={value}\n")
    with (
        patch.object(ConfigData, "_search_paths", return_value=[str(path)]),
        pytest.raises(ConfigError, match=name),
    ):
        ConfigData(str(tmp_path), None)


@pytest.mark.parametrize("name", DEFAULTS)
@pytest.mark.parametrize("mode", ["NEW", "REPLACEMENT", ""])
def test_runtime_budgets_preserve_all_target_modes(tmp_path, name, mode):
    import execsql
    from execsql.db.sqlite import SQLiteDatabase

    path = write_sheet(tmp_path, row(cell("a"), cell("b")), row(cell("hello"), cell("world")))
    if name == "ods_max_xml_mb":
        with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("extra.xml", b"x" * (2 * 1024 * 1024))
    db = SQLiteDatabase(":memory:")
    try:
        if mode != "NEW":
            db.execute("CREATE TABLE t(a TEXT,b TEXT)")
            db.execute("INSERT INTO t VALUES ('keep','me')")
        result = execsql.run(
            sql=f'-- !x! CONFIG {name.upper()} 1\n-- !x! IMPORT TO {mode} t FROM "{path}" SHEET s\n',
            connection=db,
        )
        assert not result.success
        assert name in result.errors[0].message
        if mode == "NEW":
            assert not db.table_exists("t")
        else:
            assert db.select_data("SELECT a,b FROM t")[1] == [("keep", "me")]
    finally:
        db.close()


@pytest.mark.parametrize("count_kind", ["cells", "rows", "spaces", "total_text", "repeated_text", "skipped_rows"])
def test_limit_checks_precede_expansion_allocations(tmp_path, limits, count_kind):
    import tracemalloc

    limits.import_max_rows = 0
    limits.import_max_columns = 0
    limits.import_max_cell_chars = 0
    if count_kind == "cells":
        path = write_sheet(
            tmp_path,
            row(cell("h")),
            row(cell("x", numbercolumnsrepeated=1000), numberrowsrepeated=10000),
        )
        limits.import_max_cells = 1000
        expected = "import_max_cells"
    elif count_kind == "rows":
        path = write_sheet(tmp_path, row(cell("h")), row(cell("x"), numberrowsrepeated=1000000))
        limits.import_max_rows = 10
        limits.import_max_cells = 0
        limits.import_max_text_chars = 0
        expected = "import_max_rows"
    elif count_kind == "repeated_text":
        path = write_sheet(tmp_path, row(cell("h")), row(cell("x", numbercolumnsrepeated=1000000)))
        limits.import_max_cells = 0
        limits.import_max_text_chars = 1000
        expected = "import_max_text_chars"
    elif count_kind in ("spaces", "total_text"):
        c = TableCell()
        p = P()
        p.addElement(S(c=10000000))
        c.addElement(p)
        path = write_sheet(tmp_path, row(cell("h")), row(c))
        expected = "import_max_cell_chars" if count_kind == "spaces" else "import_max_text_chars"
        setattr(limits, expected, 10)
    else:
        path = write_sheet(tmp_path, row(cell("junk"), numberrowsrepeated=1000000), row(cell("h")), row(cell("x")))
        limits.import_max_rows = 2
    tracemalloc.start()
    try:
        if count_kind == "skipped_rows":
            assert ods_data(str(path), "s", 1000000) == (["h"], [["x"]])
        else:
            with pytest.raises(ErrInfo, match=expected):
                ods_data(str(path), "s")
        assert tracemalloc.get_traced_memory()[1] < 2 * 1024 * 1024
    finally:
        tracemalloc.stop()


def test_archive_xml_budget_excludes_binary_members_and_zero_disables(tmp_path):
    from execsql.utils.fileio import check_zip_decompression_ratio

    path = tmp_path / "file.ods"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("content.xml", "<xml/>")
        archive.writestr("image.bin", b"x" * (2 * 1024 * 1024))
    check_zip_decompression_ratio(path, max_uncompressed_mb=1, xml_only=True)
    with pytest.raises(ErrInfo):
        check_zip_decompression_ratio(path, max_uncompressed_mb=1)
    check_zip_decompression_ratio(path, max_uncompressed_mb=0, max_ratio=0)


def test_pattern_discovery_checks_archive_before_loading(tmp_path, limits):
    from execsql.metacommands.io_import import x_import_ods_pattern

    path = tmp_path / "bomb.ods"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.xml", b"x" * 100000)
    with patch.object(OdsFile, "open", side_effect=AssertionError("Parser must not run")) as parser:
        with pytest.raises(ErrInfo, match="ods_max_compression_ratio"):
            x_import_ods_pattern(new=None, schema=None, filename=str(path), patn=".*", skip=None)
        parser.assert_not_called()


@pytest.mark.parametrize("mode", ["NEW", "REPLACEMENT", ""])
def test_pattern_checks_later_sheet_before_any_target_change(tmp_path, mode):
    import execsql
    from execsql.db.sqlite import SQLiteDatabase

    path = tmp_path / "sheets.ods"
    book = OdsFile()
    book.open(str(path))
    for name, count in [("first", 1), ("second", 4)]:
        sheet = book.new_sheet(name)
        sheet.addElement(row(cell("v")))
        sheet.addElement(row(cell("x"), numberrowsrepeated=count))
        book.add_sheet(sheet)
    book.save_close()
    db = SQLiteDatabase(":memory:")
    try:
        if mode != "NEW":
            for name in ["first", "second"]:
                db.execute(f"CREATE TABLE {name}(v TEXT)")
                db.execute(f"INSERT INTO {name} VALUES ('keep')")
        result = execsql.run(
            sql=(
                f'-- !x! CONFIG IMPORT_MAX_CELLS 3\n-- !x! IMPORT TO {mode} TABLES IN SCHEMA main FROM "{path}" SHEETS MATCHING .*'
            ),
            connection=db,
        )
        assert not result.success
        assert "import_max_cells" in result.errors[0].message
        for name in ["first", "second"]:
            if mode == "NEW":
                assert not db.table_exists(name)
            else:
                assert db.select_data(f"SELECT v FROM {name}")[1] == [("keep",)]
    finally:
        db.close()


def test_exact_boundary_limits_accept_all_materialized_data(tmp_path, limits):
    path = write_sheet(tmp_path, row(cell("a"), cell("b")), row(cell("hi"), cell("x")))
    limits.import_max_rows = 2
    limits.import_max_columns = 2
    limits.import_max_cells = 4
    limits.import_max_cell_chars = 2
    limits.import_max_text_chars = 5
    assert ods_data(str(path), "s") == (["a", "b"], [["hi", "x"]])


def test_spans_and_nested_paragraphs_count_text_before_expansion(tmp_path, limits):
    from odf.text import Span

    c = TableCell(numbercolumnsspanned=2)
    p = P(text="ab")
    p.addElement(Span(text="cd"))
    c.addElement(p)
    c.addElement(P(text="ef"))
    path = write_sheet(tmp_path, row(cell("h", numbercolumnsrepeated=2)), row(c, numberrowsrepeated=2))
    limits.import_max_cell_chars = 7
    limits.import_max_text_chars = 29  # header 2 + two copies per row * two rows * seven chars = 30
    with pytest.raises(ErrInfo, match="import_max_text_chars"):
        ods_data(str(path), "s")
    limits.import_max_text_chars = 30
    assert ods_data(str(path), "s") == (["h", "h"], [["abcd\nef"] * 2] * 2)


def test_malformed_count_error_message_is_bounded(tmp_path):
    path = write_sheet(tmp_path, row(cell("h")), row(cell("x"), numberrowsrepeated=123))
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["content.xml"] = entries["content.xml"].replace(b'="123"', b'="' + b"invalid" * 10000 + b'"')
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    with pytest.raises(ErrInfo, match="Invalid ODS expansion count") as raised:
        ods_data(str(path), "s")
    assert len(str(raised.value)) < 400
