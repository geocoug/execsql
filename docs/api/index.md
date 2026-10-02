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

`run()` can be called from several threads at once. Each call gets its own `RuntimeContext` in thread-local storage, so concurrent runs do not share database connections, substitution variables, IF/LOOP stacks, error state, or file output.

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

Each run has its own [file writer](#file-output), so two runs writing files at the same time both get complete files, and a run that halts on an error stops only its own output. Plugin metacommands are registered once per process, not once per call, and a `--manifest` recorder belongs to the run that started it.

Three things are still shared by every thread in the process, so keep them apart yourself:

- **The working directory.** `CD` calls `os.chdir()`, which moves every thread. Use absolute paths in scripts that run concurrently, or don't use `CD` in them.
- **The same output file.** Two runs writing one file at the same time can interleave their lines. Give each run its own output paths.
- **Interactive prompts.** `PROMPT` and the other GUI metacommands are not meant to be driven from several threads at once.

### File Output { #file-output }

`WRITE ... TO <file>`, `TEE`, and the other metacommands that write text files hand their output to a background writer thread. Each `run()` starts its own, then flushes and closes every file and stops the thread before returning, so a file a script wrote is on disk and complete the moment `run()` hands back control.

```python
from execsql import run

result = run(sql='-- !x! WRITE "done" to report.txt\nselect 1;\n', dsn="sqlite:///data.db")
open("report.txt").read()   # "done\n" — readable immediately
```

The writer is a thread in your process, not a child process, so `run()` works the same from a `.py` file with or without an `if __name__ == "__main__":` guard, from a REPL, from a notebook, and from `python -c`.

If a file stays locked (by a sync client, a backup, or a spreadsheet that has it open) for longer than [`outfile_open_timeout`](../reference/configuration.md#setting_outfile_open_timeout), `run()` returns `success=False` with an error naming the file and how many lines were lost.

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
