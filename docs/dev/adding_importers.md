# Adding a New Importer

This guide walks through every step required to add support for a new import file format to execsql. The process involves two files: write the importer function and register the format string in the IMPORT handler.

______________________________________________________________________

## Background: How Importers Work

Importers are standalone module-level functions. There is no base class to subclass — every importer follows the same pattern: parse the source file into column headers and rows, then hand off to `import_data_table()` (the shared back-end in `src/execsql/importers/base.py`) to create the table and load the data.

### The shared back-end

`import_data_table(db, schemaname, tablename, is_new, hdrs, data)` handles everything after parsing:

- Cleans column headers according to config settings (trimming, folding, deduplication).
- Issues `CREATE TABLE` when `is_new` is `1` or `2`.
- Calls `db.populate_table()` to bulk-insert the rows.
- Commits the transaction.

Your importer just needs to open and parse the source file, then call `import_data_table()`.

### The IMPORT dispatch

When a script runs `-- !x! IMPORT myfile.ext TO mytable FORMAT myformat`, the IMPORT handler in `src/execsql/metacommands/io.py` reads the format string and calls the corresponding importer function. Adding a new format means adding a new `elif` branch to the dispatch in the handler.

______________________________________________________________________

## Step-by-step: Adding an Importer

### Step 1 — Write the importer function

Create `src/execsql/importers/myformat.py`:

```python
# src/execsql/importers/myformat.py
from __future__ import annotations

"""
MyFormat import for execsql.

Provides :func:`importtable_myformat`, which reads a `.myfmt` file and
loads it into a database table.
"""

from typing import Any

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.importers.base import import_data_table
import execsql.state as _state


def importtable_myformat(
    db: Database,
    schemaname: str | None,
    tablename: str,
    filename: str,
    is_new: Any,
    encoding: str | None = None,
) -> None:
    """Import *filename* (MyFormat) into *tablename*.

    Args:
        db: Active database connection.
        schemaname: Schema name, or ``None`` for the default schema.
        tablename: Target table name.
        filename: Path to the source file.
        is_new: ``1`` to CREATE the table, ``2`` to DROP and re-CREATE,
            ``0`` to append to an existing table.
        encoding: File encoding override. Falls back to the configured
            import encoding.
    """
    from pathlib import Path

    if not Path(filename).is_file():
        raise ErrInfo(
            type="error",
            other_msg=f"Non-existent file ({filename}) used with the IMPORT metacommand",
        )

    enc = encoding if encoding else _state.conf.import_encoding

    try:
        import myformat_lib  # lazy import of optional dependency
    except ImportError:
        raise ErrInfo(
            type="error",
            other_msg="The myformat_lib package is required to import MyFormat files.",
        )

    # Parse headers and rows from the source file.
    reader = myformat_lib.open(filename, encoding=enc)
    hdrs = reader.column_names()       # list[str]
    rows = reader.iter_rows()          # iterable of list[Any]

    import_data_table(db, schemaname, tablename, is_new, hdrs, rows)
```

Key points:

- **Call `import_data_table()`** — do not call `db.populate_table()` directly. The shared back-end handles column header cleaning, `CREATE TABLE`, and commit.
- **Import optional dependencies lazily** inside the function body so execsql still runs for users who do not have the library installed.
- **Raise `ErrInfo`** for expected failures rather than a bare `raise` or `sys.exit`.
- The `is_new` parameter values are: `0` = append to existing table, `1` = create new table, `2` = drop and re-create.

### Step 2 — Register the format in the IMPORT handler

Open `src/execsql/metacommands/io.py`. At the top, import your function:

```python
from execsql.importers.myformat import importtable_myformat
```

Then find the IMPORT format dispatch (the block that calls `importtable` for CSV, `importtable_ods` for ODS, etc.) and add a new `elif` branch:

```python
elif filefmt == "myformat":
    importtable_myformat(
        _state.dbs.current(),
        schemaname,
        tablename,
        filename,
        is_new,
        encoding=enc,
    )
```

**Format string naming:** the format string is what the user writes after `FORMAT` in the IMPORT metacommand (`FORMAT myformat`). Use lowercase, no spaces. If you need aliases, use `elif filefmt in ("myformat", "myfmt"):`.

### Step 3 — Add tests

```python
# tests/importers/test_myformat_importer.py
import pytest
from pathlib import Path
from typer.testing import CliRunner
from execsql.cli import app


@pytest.fixture()
def runner():
    return CliRunner()


class TestMyFormatImporter:
    """IMPORT FORMAT myformat."""

    def test_basic_import(self, runner, tmp_path):
        db = tmp_path / "test.db"
        src = tmp_path / "data.myfmt"
        src.write_text(...)  # write a minimal test file in your format
        script = tmp_path / "test.sql"
        script.write_text(
            f"-- !x! IMPORT {src} TO mytable FORMAT myformat NEW\n"
        )
        result = runner.invoke(app, ["-tl", str(script), str(db), "-n"])
        assert result.exit_code == 0, result.output
```

______________________________________________________________________

## Checklist

- [ ] Importer function written in `src/execsql/importers/myformat.py`
- [ ] Function imported in `src/execsql/metacommands/io.py`
- [ ] `elif filefmt == "myformat":` branch added in the IMPORT handler
- [ ] Test added to `tests/importers/`
- [ ] `pytest` passes locally
- [ ] New format string documented in [Metacommands — IMPORT](../metacommands.md#import)
- [ ] New library dependency (if any) added to `pyproject.toml` extras and documented in [Requirements](../requirements.md#libraries)
