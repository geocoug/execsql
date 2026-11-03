# Adding a New Importer

This guide adds an in-tree `IMPORT ... FROM MYFORMAT` form. The concrete example reads pipe-delimited text through Python's CSV reader and sends headers and rows to the shared table loader. The form is available only after its handler and grammar are registered.

For a separately installed extension, a metacommand plugin can call the same loading function; see [Plugin alternative](#plugin-alternative).

<a id="background-how-importers-work"></a>
<a id="the-shared-back-end"></a>
<a id="the-import-dispatch"></a>

## Understand the existing paths

Plain `IMPORT TO [NEW|REPLACEMENT] table FROM file` reads delimited text. Its `x_import()` handler calls `importers.csv.importtable()` directly; it does not select a format from the file extension or a `filefmt` chain.

ODS, XLS/XLSX, JSON, Feather and Parquet have explicit syntax and separate handlers registered in `metacommands/dispatch.py`. Follow one of those patterns for a new format. There is no `IMPORT file TO table FORMAT name NEW` syntax.

Most row-based importers use `import_data_table()` in `importers/base.py`. It cleans/validates headers, handles NEW/REPLACEMENT table creation, selects target columns, delegates conversion/insertion to the adapter and commits according to the connection policy. CSV has a separate file-oriented path; it is not evidence that every importer calls this shared function.

NEW/REPLACEMENT infer column types from the source. Existing tables convert according to their target column types. Preserve the [data integrity rules](../reference/metacommands.md#import); a faster parser is not allowed to silently alter values, remove errors or round fractional integers.

<a id="step-by-step-adding-an-importer"></a>
<a id="step-1-write-the-importer-function"></a>

## Implement the reader

Create `src/execsql/importers/myformat.py`:

```python
import csv

import execsql.state as _state
from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.importers.base import import_data_table


def import_myformat(
    db: Database,
    schema: str | None,
    table: str,
    filename: str,
    is_new: int,
) -> None:
    """Read pipe-delimited text with a mandatory header row."""
    try:
        with open(filename, newline="", encoding=_state.conf.import_encoding) as stream:
            reader = csv.reader(stream, delimiter="|", strict=True)
            headers = next(reader, None)
            if not headers:
                raise ErrInfo(type="error", other_msg=f"Missing header row in {filename}")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ErrInfo(type="error", other_msg=f"Cannot read {filename}: {exc}") from exc
    import_data_table(db, schema, table, is_new, headers, rows)
```

This reader materializes its rows because the shared loader scans/indexes that collection; it is not a streaming import interface. Impose appropriate file/resource limits for a production format. Parse and validate source structure before modifying a destination. Optional parser dependencies belong inside the reader and in a documented optional extra, not at module import time.

`is_new` is `0` for an existing target, `1` for NEW and `2` for REPLACEMENT. REPLACEMENT can remove an existing target; make that consequence explicit in user documentation.

<a id="step-2-register-the-format-in-the-import-handler"></a>
<a id="checklist"></a>

## Add the handler and grammar

In `src/execsql/metacommands/io_import.py`, import your reader and add:

```python
from execsql.importers.myformat import import_myformat


def x_import_myformat(**kwargs):
    mode = (kwargs["new"] or "").lower()
    is_new = {"": 0, "new": 1, "replacement": 2}[mode]
    import_myformat(
        _state.dbs.current(), kwargs["schema"], kwargs["table"],
        kwargs["filename"], is_new,
    )
```

Re-export the handler from `metacommands/io.py` (including its `__all__`), then through the `metacommands/__init__.py` facade. Import it from `execsql.metacommands.io` in `dispatch.py`, alongside the other IMPORT handlers, then add a registration in `build_dispatch_table()` using the existing regex helpers:

```python
mcl.add(
    ins_table_rxs(
        r"^\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?",
        ins_fn_rxs(r"\s+FROM\s+MYFORMAT\s+", r"\s*$"),
    ),
    x_import_myformat,
    description="IMPORT",
    category="action",
)
```

The helpers supply `schema`, `table` and `filename`, including the quoted-name forms they accept. If the format needs encoding overrides, sheet names or other options, capture and validate them explicitly; do not invent an extension switch in `x_import()`.

Add the new syntax form to the IMPORT entry in `metacommands/reference.py` and document it under [IMPORT](../reference/metacommands.md#import). Update the public handler export list where applicable, optional dependencies/extras and requirements, then run `just install-vscode` to regenerate the keyword grammar (and install/link the local development extension). Follow [Adding Metacommands](adding_metacommands.md) for the full registry/reference checklist.

<a id="step-3-add-tests"></a>

## Verify a complete import

After registration, save `data.myfmt`:

```text
id|name
2|alpha
3|O'Brien
```

Save `load.sql` next to it:

```sql
-- !x! IMPORT TO NEW mytable FROM MYFORMAT data.myfmt
-- !x! ASSERT ROW_COUNT_EQ(mytable, 2) "Expected two rows"
-- !x! EXPORT mytable TO stdout AS CSV
```

Run from that directory: `execsql run --dsn sqlite:///:memory: load.sql`. Expected CSV rows are `2,alpha` and `3,O'Brien` beneath `id,name`. Add a real CLI/API test with this fixture to `tests/importers/`, not only a direct reader test.

Also cover existing target types, NEW conflicts, REPLACEMENT, malformed headers/rows, empty files, encodings, quotes/delimiters/newlines in values, null policy, optional dependency failures, rollback and resource cleanup. Use differential value × target-column-type tests for conversion changes. Run reference/registry tests and normal quality gates. Never test destructive replacement on a real shared database.

## Plugin alternative

Register a custom metacommand via the `execsql.metacommands` entry-point group and call `import_myformat()` from its handler. Install the plugin into the environment that runs execsql and verify both `execsql list plugins` and a complete script. The listing does not invoke importer-registration callbacks or populate their registries; see the canonical [plugin lifecycle](architecture.md#plugin-system). An importer entry-point name alone does not add an IMPORT form or route a built-in handler to your reader.
