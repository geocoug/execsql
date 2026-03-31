# Adding a New Exporter

This guide walks through every step required to add a new export format to execsql. The process involves three files: write the exporter function, register the format string in the EXPORT handler, and add tests.

______________________________________________________________________

## Background: How Exporters Work

Exporters are standalone module-level functions. There is no base class to subclass — every exporter follows the same call signature and pattern, but is otherwise independent.

### The EXPORT dispatch

When a script runs `-- !x! EXPORT TO myfile.ext FORMAT myformat`, the handler in `src/execsql/metacommands/io.py` receives the format string and calls the corresponding exporter function directly via an `if`/`elif` chain. Adding a new format means adding a new `elif` branch to that chain.

### The core pattern

Every exporter does three things:

1. Call `db.select_rowsource(select_stmt)` to get a streaming `(headers, rows)` generator from the database.
1. Open an output file (or a `ZipWriter` wrapper if writing into a zip).
1. Iterate `rows`, write output, and close.

```python
def write_query_to_myformat(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    hdrs, rows = db.select_rowsource(select_stmt)
    # open output and write...
```

`db.select_rowsource()` returns a tuple of `(list[str], generator)`. The generator yields one row at a time as a list of Python values. Reading it is lazy — execsql never loads the entire result set into memory.

______________________________________________________________________

## Step-by-step: Adding an Exporter

### Step 1 — Write the exporter function

Create a new file `src/execsql/exporters/myformat.py` (or add to an existing module if the format is closely related to one that already exists).

Here is a minimal plain-text exporter as a working skeleton:

```python
# src/execsql/exporters/myformat.py
from __future__ import annotations

"""
Plain-text (tab-separated) export for execsql.

Provides :func:`write_query_to_myformat`.
"""

from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.exporters.zip import ZipWriter
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close


def write_query_to_myformat(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    """Export *select_stmt* result set to *outfile* in my custom format."""
    conf = _state.conf
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc())

    if zipfile is None:
        filewriter_close(outfile)
        from execsql.utils.fileio import EncodedFile

        ef = EncodedFile(outfile, conf.output_encoding)
        f = ef.open("at" if append else "wt")
    else:
        f = ZipWriter(zipfile, outfile, append)

    # Write header line
    f.write("\t".join(str(h) for h in hdrs) + "\n")

    # Write data rows
    for row in rows:
        f.write("\t".join("" if v is None else str(v) for v in row) + "\n")

    f.close()
```

Key points:

- **Always call `filewriter_close(outfile)` before opening** when writing to a plain file. This flushes any pending background write for the same path from a previous EXPORT in the same script run.
- **Support `append`** — open in `"at"` mode when `append=True`, `"wt"` otherwise.
- **Support `zipfile`** — use `ZipWriter` when a zip output path is provided.
- **Raise `ErrInfo`** for expected failure conditions rather than a bare `raise` or `sys.exit`.
- **Import lazily** if the format requires an optional dependency (e.g., `import mylib` inside the function body) so that execsql still runs for users who do not have the library installed.

The `desc` parameter is optional metadata passed from the EXPORT metacommand. Store it in the output header if your format supports it; otherwise ignore it.

### Step 2 — Register the format in the EXPORT handler

Open `src/execsql/metacommands/io.py`. At the top, import your new function:

```python
from execsql.exporters.myformat import write_query_to_myformat
```

Then find the `if filefmt in ("txt", "text"):` chain inside the `x_export` handler and add a new `elif` branch at the appropriate position:

```python
elif filefmt == "myformat":
    write_query_to_myformat(
        select_stmt,
        _state.dbs.current(),
        outfile,
        append,
        desc=description,
        zipfile=zipfilename,
    )
```

**Format string naming:** the format string is what the user writes after `FORMAT` in the EXPORT metacommand (`FORMAT myformat`). Use lowercase, no spaces. If you need to support multiple aliases (e.g., `myformat` and `myfmt`), use `elif filefmt in ("myformat", "myfmt"):`.

If your format does not support zip output, add a guard near the top of the function alongside the existing `feather` and `hdf5` checks:

```python
if zipfilename is not None:
    if filefmt == "myformat":
        raise ErrInfo("error", other_msg="Cannot export to myformat within a zipfile.")
```

### Step 3 — Add tests

Add a test class to `tests/exporters/test_myformat_exporter.py` (or the appropriate test file). Integration tests against a real SQLite database are preferred:

```python
import pytest
from pathlib import Path
from typer.testing import CliRunner
from execsql.cli import app


@pytest.fixture()
def runner():
    return CliRunner()


class TestMyFormatExporter:
    """EXPORT FORMAT myformat."""

    def test_basic_export(self, runner, tmp_path):
        db = tmp_path / "test.db"
        out = tmp_path / "out.myformat"
        script = tmp_path / "test.sql"
        script.write_text(
            "CREATE TABLE t (id INTEGER, name TEXT);\n"
            "INSERT INTO t VALUES (1, 'alpha'), (2, 'beta');\n"
            f"-- !x! EXPORT SELECT * FROM t TO {out} FORMAT myformat\n"
        )
        result = runner.invoke(app, ["-tl", str(script), str(db), "-n"])
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        assert "alpha" in content
        assert "beta" in content
```

______________________________________________________________________

## Checklist

- [ ] Exporter function written in `src/execsql/exporters/myformat.py`
- [ ] Function imported in `src/execsql/metacommands/io.py`
- [ ] `elif filefmt == "myformat":` branch added in `x_export()`
- [ ] Zip guard added if the format does not support zip output
- [ ] Test added to `tests/exporters/`
- [ ] `pytest` passes locally
- [ ] New format string documented in [Metacommands — EXPORT](../reference/metacommands.md#export)
- [ ] New library dependency (if any) added to `pyproject.toml` extras and documented in [Requirements](../getting-started/requirements.md#libraries)
