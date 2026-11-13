"""The file command's human/JSON interface works for every built-in importer."""

import json

import pytest
from typer.testing import CliRunner

from execsql import inspect_file
from execsql.cli import app
from execsql.config import ConfigData
from tests.test_file_inspection import make_file


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.setattr(
        ConfigData,
        "_search_paths",
        classmethod(lambda cls, script_path, config_file, start_dir=None: [str(config_file)] if config_file else []),
    )


@pytest.mark.parametrize("kind", ["csv", "tsv", "text", "json", "jsonl", "xls", "xlsx", "ods", "parquet", "feather"])
@pytest.mark.parametrize("output_format", ["text", "json"])
def test_file_command_all_formats(tmp_path, monkeypatch, kind, output_format):
    path = make_file(tmp_path, kind)
    before = path.read_bytes()

    def must_not_connect(*args, **kwargs):
        pytest.fail("File inspection must never connect to a database")

    monkeypatch.setattr("execsql.api._connect_from_dsn", must_not_connect)
    args = ["inspect", "file", str(path), "--output-format", output_format]
    options = {}
    if kind in ("xls", "xlsx", "ods"):
        args += ["--sheet", "Data"]
        options["sheet"] = "Data"
    result = CliRunner().invoke(app, args, env={"COLUMNS": "80"})
    assert result.exit_code == 0, result.output
    assert result.stderr == "" and "alpha" not in result.stdout
    if output_format == "json":
        assert json.loads(result.stdout) == inspect_file(path, **options)
    else:
        assert "Format:" in result.stdout and "Scan: full" in result.stdout
        assert "id" in result.stdout and "label" in result.stdout
        assert "integer" in result.stdout and "varchar(5)" in result.stdout
        assert "Import settings:" in result.stdout
    assert path.read_bytes() == before


def test_workbook_listing_and_sampling_warning(tmp_path):
    path = make_file(tmp_path, "xlsx")
    listing = CliRunner().invoke(app, ["inspect", "file", str(path)])
    assert listing.exit_code == 0, listing.output
    assert "Worksheets:" in listing.stdout and "Data" in listing.stdout and "Other" in listing.stdout
    assert "Use --sheet NAME" in listing.stdout and "Scan:" not in listing.stdout
    sampled = CliRunner().invoke(app, ["inspect", "file", str(path), "--sheet", "Data", "--sample-rows", "1"])
    assert sampled.exit_code == 0, sampled.output
    assert "provisional" in sampled.stdout and "materialized" in sampled.stdout


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_missing_file_exit_and_output_streams(tmp_path, output_format):
    result = CliRunner().invoke(
        app,
        ["inspect", "file", str(tmp_path / "missing.csv"), "--output-format", output_format],
    )
    assert result.exit_code == 1
    if output_format == "json":
        assert json.loads(result.stdout)["error"]["code"] == "file_error"
        assert result.stderr == ""
    else:
        assert result.stdout == "" and "Error:" in result.stderr


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["some.csv", "--sample-rows", "0"],
        ["some.csv", "--skip-rows", "-1"],
        ["some.csv", "--quote", '"'],
        ["some.csv", "--dsn", "sqlite:///:memory:"],
        ["some.csv", "--sheet", "Data"],
        ["some.csv", "--format", "pdf"],
    ],
)
def test_invalid_file_command_arguments_exit_two(options):
    assert CliRunner().invoke(app, ["inspect", "file", *options]).exit_code == 2


def test_file_help_and_literal_catalog_text(tmp_path):
    help_result = CliRunner().invoke(app, ["inspect", "file", "--help"])
    assert help_result.exit_code == 0 and "--sample-rows" in help_result.stdout
    assert "--dsn" not in help_result.stdout
    path = tmp_path / "[bold]input.csv"
    path.write_text("[bold]name\x1b[2J,v\nsecret_value,2\n")
    result = CliRunner().invoke(app, ["inspect", "file", str(path)])
    assert result.exit_code == 0, result.output
    assert "[bold]name\\x1b[2J" in result.stdout and "\x1b" not in result.stdout
    assert "secret_value" not in result.stdout
