# Adding a New Exporter

Choose between an in-tree EXPORT format and a separately installed metacommand plugin. This guide describes the complete in-tree registration path. The example adds a `MYFORMAT` alias for CSV so registration, file handling and tests can be exercised without inventing a file format. A new encoding needs its own writer and value-preservation tests.

<a id="background-how-exporters-work"></a>
<a id="the-export-dispatch"></a>
<a id="the-core-pattern"></a>

## Follow the actual dispatch

Users write either:

```sql
-- !x! EXPORT t TO out.myformat AS MYFORMAT
-- !x! EXPORT QUERY <<select * from t;>> TO out.myformat AS MYFORMAT
```

These forms work **after** implementing and registering the format below. There is no `EXPORT SELECT ... FORMAT ...` form.

`metacommands/dispatch.py` accepts format names from constants in `metacommands/__init__.py`. Table and query handlers in `metacommands/io_export.py` both call `_dispatch_format()`. Adding a writer or handler branch alone does not make a format reachable: the grammar must accept its name too.

Writers may open their own row source or receive headers and an iterable of rows from the handler. For example, the Parquet branch receives the streaming row generator returned by `db.select_rowsource()`, not necessarily materialized rows. Follow the branch you extend; there is no universal writer signature.

<a id="step-by-step-adding-an-exporter"></a>
<a id="step-1-write-the-exporter-function"></a>

## Implement the writer

Create `src/execsql/exporters/myformat.py`:

```python
from typing import Any

import execsql.state as _state
from execsql.exporters.delimited import write_delimited_file


def write_query_to_myformat(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    """Write CSV using the existing CSV value and output rules."""
    headers, rows = db.select_rowsource(select_stmt)
    try:
        write_delimited_file(
            outfile, "csv", headers, rows,
            _state.conf.output_encoding, append, zipfile,
        )
    finally:
        rows.close()
```

Reusing the CSV writer retains its quoting, encoding, APPEND, stdout and ZIP behavior. It also handles coordination with pending background text writes. `desc` is deliberately ignored because CSV has no description header.

For a genuinely new writer, define null, number, timestamp, binary and text representations explicitly. Close the row source and output handles on failures; do not close stdout. Flush/close pending background writes with `filewriter_close(outfile)` before opening the same plain file synchronously. Use `ZipWriter` only if the format can be streamed into an archive. Import optional dependencies lazily and report expected failures as `ErrInfo`. Match existing stored/exported values rather than optimizing through a different conversion path.

<a id="step-2-register-the-format-in-the-export-handler"></a>
<a id="checklist"></a>

## Register grammar and dispatch

1. Add `"MYFORMAT"` to both `QUERY_EXPORT_FORMATS` and `TABLE_EXPORT_FORMATS` in `src/execsql/metacommands/__init__.py`. Names in these lists are uppercase. `ALL_EXPORT_FORMATS` is derived from them; do not create a competing list.

1. Import `write_query_to_myformat` in `src/execsql/metacommands/io_export.py`.

1. Add this branch to `_dispatch_format()` alongside the other named writers. Handler format values are lowercase:

    ```python
    elif filefmt == "myformat":
        write_query_to_myformat(
            select_stmt, db, outfile, append,
            desc=description, zipfile=zipfilename,
        )
    ```

1. Document the new AS format and its semantics in [EXPORT](../reference/metacommands.md#export). Update any syntax forms that enumerate formats in `metacommands/reference.py`; retain valid reference samples. If you add a separate metacommand rather than a format, follow the complete [metacommand registration checklist](adding_metacommands.md).

1. Run `just install-vscode` after changing the keyword vocabulary to regenerate the extension grammar. This command also installs/links the local development extension; use a development environment where that action is intended.

If a new format does not support ZIP, add it to `_NO_ZIP_FORMATS`, which `_check_zip_compat()` reads, in `io_export.py` and test rejection. If it does not support APPEND, reject that combination explicitly instead of silently overwriting or ignoring it. Follow the existing type-specific handlers if the format needs additional arguments, such as a destination table.

<a id="step-3-add-tests"></a>

## Test the whole path

After registration, use a temporary SQLite database and the real CLI. A test should cover table and query forms, not just a direct writer call:

```python
import csv
from typer.testing import CliRunner
from execsql.cli import app


def test_myformat_export(tmp_path):
    script = tmp_path / "export.sql"
    target = tmp_path / "out.myformat"
    script.write_text(
        "create table t (id integer, name text);\n"
        "insert into t values (1, 'alpha'), (2, 'O''Brien');\n"
        f'-- !x! EXPORT QUERY <<select * from t order by id;>> TO "{target}" AS MYFORMAT\n',
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["run", "--dsn", "sqlite:///:memory:", str(script)])
    assert result.exit_code == 0, result.output
    with target.open(newline="", encoding="utf-8-sig") as stream:
        assert list(csv.reader(stream)) == [["id", "name"], ["1", "alpha"], ["2", "O'Brien"]]
```

Add cases for empty results, delimiters/newlines/quotes in values, every supported value type, append, ZIP, stdout, encoding, invalid output paths and cleanup after an I/O error. For an optimization, compare the existing and new output over the full value/type/error matrix. Run the registry/reference tests and the applicable exporter tests, then the normal quality gates in [CONTRIBUTING](contributing.md).

## Plugin alternative

An installed plugin can register a custom metacommand and call its writer without editing core files; use `extras/plugin-template/` and [Adding Metacommands](adding_metacommands.md). Install it in the same Python environment as execsql. `execsql list plugins` lists installed entry-point names; it does not invoke exporter-registration callbacks or populate their registries. See the canonical [plugin lifecycle](architecture.md#plugin-system). Supply a metacommand handler for the custom format, or use the in-tree path above, and verify a real script invocation.
