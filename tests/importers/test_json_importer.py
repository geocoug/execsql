"""
Tests for execsql.importers.json — JSON and NDJSON import.

Covers :func:`_flatten`, :func:`_parse_json_file`, and :func:`import_json`.
Uses an in-memory SQLiteDatabase so no external services are required.
"""

from __future__ import annotations

import json

import pytest

from execsql.db.sqlite import SQLiteDatabase
from execsql.exceptions import ErrInfo
from execsql.importers.json import _flatten, _parse_json_file, import_json


# ---------------------------------------------------------------------------
# Extra conf attributes required by import_data_table
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def importer_conf(minimal_conf):
    minimal_conf.del_empty_cols = False
    minimal_conf.create_col_hdrs = False
    minimal_conf.clean_col_hdrs = False
    minimal_conf.trim_col_hdrs = "none"
    minimal_conf.fold_col_hdrs = "no"
    minimal_conf.dedup_col_hdrs = False
    minimal_conf.import_encoding = "utf-8"
    minimal_conf.import_common_cols_only = False
    minimal_conf.quote_all_text = False
    minimal_conf.scan_lines = 50
    minimal_conf.empty_rows = True
    yield minimal_conf


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    d = SQLiteDatabase(path)
    yield d
    d.close()


# ---------------------------------------------------------------------------
# _flatten
# ---------------------------------------------------------------------------


class TestFlatten:
    def test_flat_dict_passes_through_unchanged(self):
        obj = {"a": 1, "b": "hello", "c": 3.14}
        result = _flatten(obj)
        assert result == {"a": 1, "b": "hello", "c": 3.14}

    def test_nested_dict_produces_dot_separated_keys(self):
        obj = {"address": {"city": "Denver", "zip": "80202"}}
        result = _flatten(obj)
        assert result == {"address.city": "Denver", "address.zip": "80202"}

    def test_deeply_nested_three_levels_produces_correct_keys(self):
        obj = {"a": {"b": {"c": 42}}}
        result = _flatten(obj)
        assert result == {"a.b.c": 42}

    def test_array_values_become_json_strings(self):
        obj = {"tags": ["python", "sql"]}
        result = _flatten(obj)
        assert "tags" in result
        parsed = json.loads(result["tags"])
        assert parsed == ["python", "sql"]

    def test_none_values_preserved(self):
        obj = {"name": None, "score": 0}
        result = _flatten(obj)
        assert result["name"] is None
        assert result["score"] == 0

    def test_mixed_scalar_types(self):
        obj = {"i": 1, "f": 2.5, "s": "text", "b": True, "n": None}
        result = _flatten(obj)
        assert result == {"i": 1, "f": 2.5, "s": "text", "b": True, "n": None}

    def test_empty_dict_returns_empty_dict(self):
        result = _flatten({})
        assert result == {}

    def test_nested_array_of_objects_becomes_json_string(self):
        obj = {"items": [{"id": 1}, {"id": 2}]}
        result = _flatten(obj)
        assert "items" in result
        parsed = json.loads(result["items"])
        assert parsed == [{"id": 1}, {"id": 2}]

    def test_custom_separator(self):
        obj = {"a": {"b": 1}}
        result = _flatten(obj, sep="__")
        assert "a__b" in result
        assert result["a__b"] == 1

    def test_prefix_prepended_to_top_level_keys(self):
        obj = {"x": 10}
        result = _flatten(obj, prefix="root")
        assert result == {"root.x": 10}


# ---------------------------------------------------------------------------
# _parse_json_file
# ---------------------------------------------------------------------------


class TestParseJsonFile:
    def test_standard_json_array_of_objects(self, tmp_path):
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        f = tmp_path / "data.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        records = _parse_json_file(str(f), "utf-8")
        assert len(records) == 2
        assert records[0]["id"] == 1
        assert records[1]["name"] == "Bob"

    def test_ndjson_one_object_per_line(self, tmp_path):
        lines = [
            json.dumps({"id": 1, "val": "a"}),
            json.dumps({"id": 2, "val": "b"}),
            json.dumps({"id": 3, "val": "c"}),
        ]
        f = tmp_path / "data.ndjson"
        f.write_text("\n".join(lines), encoding="utf-8")
        records = _parse_json_file(str(f), "utf-8")
        assert len(records) == 3
        assert records[2]["id"] == 3

    def test_single_json_object_treated_as_one_record(self, tmp_path):
        obj = {"key": "value", "num": 42}
        f = tmp_path / "single.json"
        f.write_text(json.dumps(obj), encoding="utf-8")
        records = _parse_json_file(str(f), "utf-8")
        assert len(records) == 1
        assert records[0]["key"] == "value"

    def test_empty_json_array_raises_errinfo(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("[]", encoding="utf-8")
        with pytest.raises(ErrInfo):
            _parse_json_file(str(f), "utf-8")

    def test_array_with_non_object_element_raises_errinfo(self, tmp_path):
        data = [{"id": 1}, "not_an_object", {"id": 3}]
        f = tmp_path / "bad.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ErrInfo):
            _parse_json_file(str(f), "utf-8")

    def test_invalid_json_raises_errinfo(self, tmp_path):
        f = tmp_path / "broken.json"
        f.write_text("{this is not valid json}", encoding="utf-8")
        with pytest.raises(ErrInfo):
            _parse_json_file(str(f), "utf-8")

    def test_file_not_starting_with_bracket_or_brace_raises_errinfo(self, tmp_path):
        f = tmp_path / "weird.json"
        f.write_text("42", encoding="utf-8")
        with pytest.raises(ErrInfo):
            _parse_json_file(str(f), "utf-8")

    def test_nested_objects_are_flattened(self, tmp_path):
        data = [{"user": {"name": "Alice", "age": 30}}]
        f = tmp_path / "nested.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        records = _parse_json_file(str(f), "utf-8")
        assert "user.name" in records[0]
        assert records[0]["user.name"] == "Alice"

    def test_file_with_leading_whitespace_is_parsed(self, tmp_path):
        data = [{"x": 1}]
        f = tmp_path / "padded.json"
        f.write_text("   \n" + json.dumps(data), encoding="utf-8")
        records = _parse_json_file(str(f), "utf-8")
        assert len(records) == 1

    def test_ndjson_with_blank_lines_skipped(self, tmp_path):
        lines = [
            json.dumps({"id": 1}),
            "",
            json.dumps({"id": 2}),
        ]
        f = tmp_path / "blanks.ndjson"
        f.write_text("\n".join(lines), encoding="utf-8")
        records = _parse_json_file(str(f), "utf-8")
        assert len(records) == 2


# ---------------------------------------------------------------------------
# import_json integration tests
# ---------------------------------------------------------------------------


class TestImportJson:
    def test_creates_new_table_and_inserts_rows(self, db, tmp_path):
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        f = tmp_path / "data.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        import_json(db, None, "people", str(f), is_new=1)
        _, rows = db.select_data("SELECT id, name FROM people ORDER BY id;")
        assert len(rows) == 2

    def test_row_values_are_correct(self, db, tmp_path):
        data = [{"x": 10, "y": "foo"}, {"x": 20, "y": "bar"}]
        f = tmp_path / "data.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        import_json(db, None, "tbl", str(f), is_new=1)
        _, rows = db.select_data("SELECT y FROM tbl ORDER BY x;")
        vals = [r[0] for r in rows]
        assert vals == ["foo", "bar"]

    def test_replaces_existing_table_when_is_new_2(self, db, tmp_path):
        data1 = [{"x": 1}, {"x": 2}]
        f1 = tmp_path / "data1.json"
        f1.write_text(json.dumps(data1), encoding="utf-8")
        import_json(db, None, "tbl", str(f1), is_new=1)

        data2 = [{"x": 99}]
        f2 = tmp_path / "data2.json"
        f2.write_text(json.dumps(data2), encoding="utf-8")
        import_json(db, None, "tbl", str(f2), is_new=2)

        _, rows = db.select_data("SELECT x FROM tbl;")
        assert len(rows) == 1

    def test_appends_to_existing_table_when_is_new_false(self, db, tmp_path):
        db.execute("CREATE TABLE tbl (id INTEGER, name TEXT);")
        db.execute("INSERT INTO tbl VALUES (1, 'existing');")
        db.commit()

        data = [{"id": 2, "name": "new"}]
        f = tmp_path / "data.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        import_json(db, None, "tbl", str(f), is_new=False)

        _, rows = db.select_data("SELECT name FROM tbl ORDER BY id;")
        names = [r[0] for r in rows]
        assert "existing" in names
        assert "new" in names

    def test_none_null_values_imported_correctly(self, db, tmp_path):
        data = [{"id": 1, "val": None}, {"id": 2, "val": "ok"}]
        f = tmp_path / "nulls.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        import_json(db, None, "tbl", str(f), is_new=1)
        _, rows = db.select_data("SELECT val FROM tbl ORDER BY id;")
        assert rows[0][0] is None
        assert rows[1][0] == "ok"

    def test_nested_objects_produce_dot_separated_column_names(self, db, tmp_path):
        data = [{"user": {"name": "Alice", "city": "Denver"}}]
        f = tmp_path / "nested.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        import_json(db, None, "tbl", str(f), is_new=1)
        _, rows = db.select_data('SELECT "user.name", "user.city" FROM tbl;')
        assert rows[0][0] == "Alice"
        assert rows[0][1] == "Denver"

    def test_arrays_stored_as_json_strings(self, db, tmp_path):
        data = [{"id": 1, "tags": ["python", "sql"]}]
        f = tmp_path / "arrays.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        import_json(db, None, "tbl", str(f), is_new=1)
        _, rows = db.select_data("SELECT tags FROM tbl;")
        stored = rows[0][0]
        parsed = json.loads(stored)
        assert parsed == ["python", "sql"]

    def test_records_with_different_keys_produce_superset_columns(self, db, tmp_path):
        data = [
            {"id": 1, "name": "Alice", "score": 95},
            {"id": 2, "name": "Bob"},
        ]
        f = tmp_path / "sparse.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        import_json(db, None, "tbl", str(f), is_new=1)
        _, rows = db.select_data("SELECT id, name, score FROM tbl ORDER BY id;")
        assert len(rows) == 2
        # Row for Bob should have NULL score
        bob_row = rows[1]
        assert bob_row[1] == "Bob"
        assert bob_row[2] is None

    def test_unicode_content_works(self, db, tmp_path):
        data = [{"greeting": "Héllo Wörld"}, {"greeting": "日本語"}]
        f = tmp_path / "unicode.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        import_json(db, None, "tbl", str(f), is_new=1)
        _, rows = db.select_data("SELECT greeting FROM tbl ORDER BY rowid;")
        greetings = [r[0] for r in rows]
        assert "Héllo Wörld" in greetings
        assert "日本語" in greetings

    def test_explicit_encoding_parameter_used(self, db, tmp_path):
        data = [{"val": "café"}]
        f = tmp_path / "latin.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="latin-1")
        import_json(db, None, "tbl", str(f), is_new=1, encoding="latin-1")
        _, rows = db.select_data("SELECT val FROM tbl;")
        assert rows[0][0] == "café"

    def test_ndjson_file_imported_correctly(self, db, tmp_path):
        lines = [
            json.dumps({"id": 1, "city": "Denver"}),
            json.dumps({"id": 2, "city": "Austin"}),
        ]
        f = tmp_path / "data.ndjson"
        f.write_text("\n".join(lines), encoding="utf-8")
        import_json(db, None, "cities", str(f), is_new=1)
        _, rows = db.select_data("SELECT city FROM cities ORDER BY id;")
        assert [r[0] for r in rows] == ["Denver", "Austin"]
