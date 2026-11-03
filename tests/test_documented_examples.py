"""Execute documentation recipes that previously contained incomplete or incorrect code."""

import csv
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from execsql import run
from execsql.cli.lint import lint_source

DOCS = Path(__file__).resolve().parents[1] / "docs"


def _cookbook_text():
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted((DOCS / "guides/examples").glob("*.md")))


def _example_sql(number):
    text = _cookbook_text()
    section = re.search(rf"^###? .*\{{ #example{number} \}}\n(.*?)(?=^###? |\Z)", text, re.M | re.S)
    assert section, f"Example anchor example{number} missing"
    return "\n".join(re.findall(r"^```[ \t]*sql\n(.*?)^```[ \t]*$", section[1], re.M | re.S))


@pytest.mark.parametrize("number", range(1, 44))
def test_documented_metacommands_parse(number, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    errors = [
        issue
        for issue in lint_source(_example_sql(number), f"example{number}")
        if issue.code in {"P001", "P003", "P004"}
    ]
    assert not errors, errors


def test_debugging_recipe_exports_each_processed_order_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run(sql=_example_sql(36), dsn="sqlite:///:memory:")
    assert result.success, result.errors
    with (tmp_path / "reports/processed.csv").open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert sorted(int(row["order_id"]) for row in rows) == [1, 2, 3]
    assert all(row["processed"] == "1" for row in rows)


def test_documented_loop_terminates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run(sql=_example_sql(6), dsn="sqlite:///:memory:")
    assert result.success, result.errors
    assert result.variables["iteration"] == "4"


def test_nested_argument_recipe_terminates_without_self_include(tmp_path):
    script = tmp_path / "arguments.sql"
    script.write_text(_example_sql(7), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "run", "--dsn", "sqlite:///:memory:", "-a", "one", "-a", "two", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "$ARG_1 = one" in result.stdout
    assert "$ARG_2 = two" in result.stdout


@pytest.mark.parametrize("task", ["Share O'Brien's food", r"Keep C:\data\O'Brien.txt"])
def test_command_line_text_recipe_preserves_text(task, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    database = tmp_path / "todo.db"
    result = run(
        sql=_example_sql(9),
        dsn=f"sqlite:///{database}",
        new_db=True,
        variables={"arg_1": task, "arg_2": "2026-11-21"},
    )
    assert result.success, result.errors
    with sqlite3.connect(database) as conn:
        assert conn.execute("select todo, date_due from todo").fetchall() == [(task, "2026-11-21")]


def test_jinja_recipe_renders_the_documented_table(tmp_path, monkeypatch):
    pytest.importorskip("jinja2")
    monkeypatch.chdir(tmp_path)
    text = _cookbook_text()
    template = re.search(r"^```jinja\n(.*?)^```", text, re.M | re.S)[1]
    (tmp_path / "table.wiki.j2").write_text(template, encoding="utf-8")
    (tmp_path / "wiki.conf").write_text("[output]\ntemplate_processor = jinja\n", encoding="utf-8")
    result = run(sql=_example_sql(22), dsn="sqlite:///:memory:", config_file=tmp_path / "wiki.conf")
    assert result.success, result.errors
    wiki = (tmp_path / "planets.wiki").read_text(encoding="utf-8")
    assert '! scope="col" | name' in wiki
    assert "| Earth\n| 1\n" in wiki
    assert "| Mars\n| 2\n" in wiki


def test_first_script_imports_and_exports_its_supplied_fixture(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    text = (DOCS / "getting-started/first-script.md").read_text(encoding="utf-8")
    csv_blocks = re.findall(r"^```csv\n(.*?)^```", text, re.M | re.S)
    sql = re.search(r"^```sql\n(.*?)^```", text, re.M | re.S)[1]
    (tmp_path / "sales.csv").write_text(csv_blocks[0], encoding="utf-8")
    result = run(sql=sql, dsn="sqlite:///:memory:")
    assert result.success, result.errors
    output = (tmp_path / "totals.csv").read_text(encoding="utf-8-sig")
    assert list(csv.reader(output.splitlines())) == list(csv.reader(csv_blocks[1].splitlines()))


def test_optional_include_recipe_executes_its_companion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    text = _example_sql(5)
    main, companion = text.split("-- !x! ASSERT", 1)
    (tmp_path / "check_optional.sql").write_text("-- !x! ASSERT" + companion, encoding="utf-8")
    result = run(sql=main, dsn="sqlite:///:memory:")
    assert result.success, result.errors


@pytest.mark.parametrize("quantity,expected", [(-1, []), (2, [(2,)])])
def test_documented_batch_validation_commits_only_valid_rows(quantity, expected, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    text = _cookbook_text()
    section = text.split("{ #validate-before-commit }", 1)[1].split("\n## ", 1)[0]
    sql = re.search(r"^```sql\n(.*?)^```", section, re.M | re.S)[1].replace("values (-1)", f"values ({quantity})")
    database = tmp_path / "validation.sqlite"
    result = run(sql=sql, dsn=f"sqlite:///{database}", new_db=True)
    assert result.success is bool(expected), result.errors
    with sqlite3.connect(database) as conn:
        assert conn.execute("select quantity from validated").fetchall() == expected


def test_documented_adapter_implements_the_abstract_interface():
    text = (DOCS / "dev/adding_db_adapters.md").read_text(encoding="utf-8")
    code = re.search(r"^```python\n(.*?)^```", text, re.M | re.S)[1]
    namespace = {}
    exec(compile(code, "documented_adapter.py", "exec"), namespace)
    assert not namespace["MyDBDatabase"].__abstractmethods__


def test_python_recipe_supplies_its_data_and_keeps_connection_until_finished(tmp_path, monkeypatch):
    from execsql.api import ExecSqlError

    monkeypatch.chdir(tmp_path)
    text = (DOCS / "api/index.md").read_text(encoding="utf-8").split("{ #regional-summary }", 1)[1]
    sql = re.search(r"^```[ \t]*sql\n(.*?)^```", text, re.M | re.S)[1]
    blocks = re.findall(r"^```[ \t]*python\n(.*?)^```", text, re.M | re.S)
    (tmp_path / "regional_summary.sql").write_text(sql, encoding="utf-8")
    namespace = {}
    exec(compile(blocks[0], "regional_summary.py", "exec"), namespace)
    assert namespace["result"].success
    assert namespace["result"].variables["region_total"] == "1650.5"
    with pytest.raises(ExecSqlError):
        exec(compile(blocks[1], "error_handling.py", "exec"), namespace)
    assert namespace["conn"].conn is None


def test_access_summary_applies_nondetect_half_limit_once():
    # SQLite executes the displayed relational calculation with Access's IF function.
    with sqlite3.connect(":memory:") as conn:
        conn.create_function("if", 3, lambda condition, yes, no: yes if condition else no)
        conn.executescript(
            "create table dt_result (test_surrogate_key integer, cas_rn text, detect_flag text, "
            "method_detection_limit real, result_value real, lab_qualifiers text, "
            "detection_limit_unit text, result_unit text, reportable_result text);"
            "create table dt_test (test_surrogate_key integer, sys_sample_code text, lab_anl_method_name text);"
            "create table dt_sample (sys_sample_code text, sample_type_code text, sample_matrix_code text, "
            "sample_name text);"
            "create table dt_field_sample (sys_sample_code text, sys_loc_code text, sample_date text, "
            "start_depth real, end_depth real, depth_unit text);"
            "create table dt_location (sys_loc_code text, loc_name text);"
            "create table rt_analyte (cas_rn text, analyte_type text, chemical_name text);"
            "insert into rt_analyte values ('A', 'PCB', 'Analyte');"
            "insert into dt_location values ('L', 'SG1');",
        )
        for number, sample, detected, value in [
            (1, "below_limit", "N", 0),
            (2, "detected", "Y", 40),
            (3, "mixed", "N", 0),
            (4, "mixed", "Y", 40),
        ]:
            conn.execute("insert into dt_test values (?, ?, 'method')", (number, sample))
            conn.execute(
                "insert into dt_result values (?, 'A', ?, 100, ?, '', 'mg/kg', 'mg/kg', 'Yes')",
                (number, detected, value),
            )
        for sample in ("below_limit", "detected", "mixed"):
            conn.execute("insert into dt_sample values (?, 'N', 'SE', ?)", (sample, sample))
            conn.execute("insert into dt_field_sample values (?, 'L', '2026-01-01', 0, 1, 'm')", (sample,))
        sql = _example_sql(2).replace(
            "select\n  loc.loc_name",
            "create temporary view final_summary as select\n  loc.loc_name",
        )
        sql = sql.replace("like 'SG*'", "like 'SG%'").replace("like 'SC*'", "like 'SC%'")
        conn.executescript(sql)
        rows = dict(conn.execute("select sample_name, conc from final_summary"))
        assert rows == {"below_limit": 50.0, "detected": 40.0, "mixed": 45.0}


def test_documented_adapter_drops_prequoted_table(tmp_path):
    text = (DOCS / "dev/adding_db_adapters.md").read_text(encoding="utf-8")
    code = re.search(r"^```python\n(.*?)^```", text, re.M | re.S)[1]
    namespace = {}
    exec(compile(code, "documented_adapter.py", "exec"), namespace)
    adapter = namespace["MyDBDatabase"].__new__(namespace["MyDBDatabase"])
    with sqlite3.connect(tmp_path / "adapter.sqlite") as conn:
        conn.execute("create table target (id integer)")
        adapter.execute = conn.execute
        adapter.drop_table('"target"')
        assert conn.execute("select name from sqlite_master where name='target'").fetchall() == []


def test_supplied_connection_recipe_prints_its_result(capsys):
    text = (DOCS / "api/index.md").read_text(encoding="utf-8")
    section = text.split("### Connection ownership", 1)[1].split("### Variables", 1)[0]
    code = re.search(r"^```python\n(.*?)^```", section, re.M | re.S)[1]
    namespace = {}
    exec(compile(code, "supplied_connection.py", "exec"), namespace)
    assert namespace["result"].success
    assert namespace["connection"].conn is None
    assert capsys.readouterr().out.splitlines() == ["2"]


def test_config_prompt_common_columns_option_executes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    template = (DOCS.parent / "templates/example_config_prompt.sql").read_text(encoding="utf-8")
    line = next(line.strip() for line in template.splitlines() if "sub_defined(~import_common)" in line)
    (tmp_path / "input.csv").write_text("id,ignored\n2,extra\n", encoding="utf-8")
    sql = (
        "create table target (id integer);\n"
        "-- !x! SUB ~import_common YES\n"
        f"{line}\n"
        "-- !x! IMPORT TO target FROM input.csv\n"
        "-- !x! ASSERT ROW_COUNT_EQ(target, 1)\n"
    )
    result = run(sql=sql, dsn="sqlite:///:memory:")
    assert result.success, result.errors
