"""
Tests for execsql.exporters.yaml — YAML export function.

write_query_to_yaml — YAML sequence of mappings
"""

from __future__ import annotations

import zipfile as _zipfile
from unittest.mock import MagicMock, patch

import pytest
import yaml

from execsql.exporters.yaml import write_query_to_yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(headers, rows):
    """Return a mock db whose select_rowsource returns (headers, iter(rows))."""
    db = MagicMock()
    db.select_rowsource.return_value = (headers, iter(rows))
    return db


def _read_yaml(path) -> list:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# TestWriteQueryToYaml
# ---------------------------------------------------------------------------


class TestWriteQueryToYaml:
    def test_basic_output_is_list_of_dicts(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.yaml")
        db = _make_db(["id", "name", "score"], [[1, "Alice", 95.2], [2, "Bob", 87.0]])
        write_query_to_yaml("SELECT 1", db, outfile)
        data = _read_yaml(tmp_path / "out.yaml")
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0] == {"id": 1, "name": "Alice", "score": 95.2}
        assert data[1] == {"id": 2, "name": "Bob", "score": 87.0}

    def test_keys_match_column_headers(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.yaml")
        db = _make_db(["alpha", "beta"], [[10, 20]])
        write_query_to_yaml("SELECT 1", db, outfile)
        data = _read_yaml(tmp_path / "out.yaml")
        assert set(data[0].keys()) == {"alpha", "beta"}

    def test_none_values_become_null(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.yaml")
        db = _make_db(["x", "y"], [[1, None]])
        write_query_to_yaml("SELECT 1", db, outfile)
        data = _read_yaml(tmp_path / "out.yaml")
        assert data[0]["y"] is None

    def test_empty_result_set(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.yaml")
        db = _make_db(["id", "name"], [])
        write_query_to_yaml("SELECT 1", db, outfile)
        data = _read_yaml(tmp_path / "out.yaml")
        # yaml.safe_load of an empty list produces None or []
        assert data is None or data == []

    def test_numeric_types_preserved_not_stringified(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.yaml")
        db = _make_db(["i", "f"], [[42, 3.14]])
        write_query_to_yaml("SELECT 1", db, outfile)
        data = _read_yaml(tmp_path / "out.yaml")
        assert isinstance(data[0]["i"], int)
        assert isinstance(data[0]["f"], float)

    def test_unicode_data(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.yaml")
        db = _make_db(["name"], [["Ünïcödé"], ["日本語"]])
        write_query_to_yaml("SELECT 1", db, outfile)
        data = _read_yaml(tmp_path / "out.yaml")
        assert data[0]["name"] == "Ünïcödé"
        assert data[1]["name"] == "日本語"

    def test_append_mode_grows_file(self, noop_filewriter_close, tmp_path):
        outfile = str(tmp_path / "out.yaml")
        db1 = _make_db(["id"], [[1]])
        write_query_to_yaml("SELECT 1", db1, outfile)
        size1 = (tmp_path / "out.yaml").stat().st_size
        db2 = _make_db(["id"], [[2]])
        write_query_to_yaml("SELECT 1", db2, outfile, append=True)
        assert (tmp_path / "out.yaml").stat().st_size > size1

    def test_zip_output(self, noop_filewriter_close, tmp_path, minimal_conf):
        minimal_conf.zip_buffer_mb = 1
        zpath = str(tmp_path / "out.zip")
        member = "data.yaml"
        db = _make_db(["id", "val"], [[1, "hello"], [2, "world"]])
        write_query_to_yaml("SELECT 1", db, member, zipfile=zpath)
        assert _zipfile.is_zipfile(zpath)
        with _zipfile.ZipFile(zpath, "r") as zf:
            assert member in zf.namelist()
            content = zf.read(member).decode("utf-8")
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, list)
        assert parsed[0]["id"] == 1

    def test_db_error_raises_errinfo(self, noop_filewriter_close, tmp_path):
        from execsql.exceptions import ErrInfo

        outfile = str(tmp_path / "out.yaml")
        db = MagicMock()
        db.select_rowsource.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            write_query_to_yaml("SELECT 1", db, outfile)

    def test_import_error_raises_errinfo_when_pyyaml_missing(self, noop_filewriter_close, tmp_path):
        """Verify a helpful ErrInfo is raised when PyYAML is not installed."""
        from execsql.exceptions import ErrInfo

        outfile = str(tmp_path / "out.yaml")
        db = _make_db(["id"], [[1]])
        with patch.dict("sys.modules", {"yaml": None}), pytest.raises(ErrInfo):
            import importlib

            import execsql.exporters.yaml as yaml_mod

            importlib.reload(yaml_mod)
            yaml_mod.write_query_to_yaml("SELECT 1", db, outfile)

    def test_desc_parameter_accepted(self, noop_filewriter_close, tmp_path):
        """desc is accepted without error (currently ignored in YAML output)."""
        outfile = str(tmp_path / "out.yaml")
        db = _make_db(["id"], [[1]])
        write_query_to_yaml("SELECT 1", db, outfile, desc="my description")
        data = _read_yaml(tmp_path / "out.yaml")
        assert data[0]["id"] == 1
