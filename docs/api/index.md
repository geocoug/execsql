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
