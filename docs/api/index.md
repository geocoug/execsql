# API Reference

The pages in this section are auto-generated from the source docstrings and show the full Python interface of the `execsql` package.

If you want to **extend** execsql — add a new exporter format, support a new database, or add an importer for a file type — start with the Contributing guides, which give you step-by-step walkthroughs and copy-paste skeletons. The API pages here serve as the detailed reference those guides link to.

For programmatic use, see the [Library API](#library-api) section below. For a high-level overview of how all the pieces fit together, start with the [Architecture & Design Guide](../dev/architecture.md).

## Library API

The primary public API is `execsql.run()`:

```python
from execsql import run, ScriptResult, ScriptError, ExecSqlError

result: ScriptResult = run(
    script="pipeline.sql",       # or sql="SELECT 1;"
    dsn="sqlite:///my.db",       # or connection=existing_db_object
    variables={"KEY": "value"},  # optional substitution variables
    halt_on_error=True,          # stop on first error (default)
    new_db=False,                # create DB if missing
)
```

See the [README](https://github.com/geocoug/execsql#library-api) for full examples.

### Thread Safety

`run()` is **thread-safe**. Each call creates an isolated `RuntimeContext` stored in thread-local storage, so concurrent calls from different threads do not share database connections, substitution variables, or execution state.

```python
import threading
from execsql import run

def etl_worker(script, dsn):
    result = run(script=script, dsn=dsn)
    print(f"{script}: {'OK' if result.success else 'FAIL'}")

threads = [
    threading.Thread(target=etl_worker, args=("load_us.sql", "postgresql://host/us_db")),
    threading.Thread(target=etl_worker, args=("load_eu.sql", "postgresql://host/eu_db")),
]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

Each thread gets its own database connections, IF/LOOP stacks, substitution variables, and error state. No locking is required.

### File Output { #file-output }

`WRITE ... TO <file>`, `TEE`, and the other metacommands that write text files hand their output to a separate FileWriter process. `run()` starts one if none is running, and flushes and closes every file before returning — so a file a script wrote is on disk and complete the moment `run()` hands back control.

```python
from execsql import run

result = run(sql='-- !x! WRITE "done" to report.txt\nselect 1;\n', dsn="sqlite:///data.db")
open("report.txt").read()   # "done\n" — readable immediately
```

The writer process stays up afterwards and is reused by later `run()` calls, exactly as the CLI keeps one for the life of the process; it is shut down automatically at interpreter exit. A writer you started yourself is left alone — `run()` neither replaces nor stops it.

!!! warning "Interactive interpreters"

    On macOS and Windows, Python starts subprocesses with the `spawn` method, which re-imports the calling program's `__main__` module. That fails in a REPL, a notebook, or `python -c`, so the writer cannot start and file output is discarded — with a warning on stderr rather than in silence. Run scripts that write files from a `.py` file, guarded by `if __name__ == "__main__":`.

## Extension Guides

| Extension type       | Guide                                                    | API reference                   |
| -------------------- | -------------------------------------------------------- | ------------------------------- |
| New export format    | [Adding Exporters](../dev/adding_exporters.md)           | [Exporters](exporters.md)       |
| New database adapter | [Adding Database Adapters](../dev/adding_db_adapters.md) | [Databases](db.md)              |
| New import format    | [Adding Importers](../dev/adding_importers.md)           | [Importers](importers.md)       |
| New metacommand      | [Adding Metacommands](../dev/adding_metacommands.md)     | [Metacommands](metacommands.md) |

## Modules

| Module                          | Description                                           |
| ------------------------------- | ----------------------------------------------------- |
| [CLI](cli.md)                   | Entry-point functions and argument parsing            |
| [Databases](db.md)              | `Database` ABC and `DatabasePool`                     |
| [Exporters](exporters.md)       | Export metadata, write specs, and format writers      |
| [Importers](importers.md)       | Data-import back-end used by all importer sub-modules |
| [Metacommands](metacommands.md) | Dispatch table and metacommand handler modules        |
