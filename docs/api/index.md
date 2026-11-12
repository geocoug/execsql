# API Reference

The pages in this section are auto-generated from the source docstrings and show the full Python interface of the `execsql` package.

If you want to **extend** execsql — add a new exporter format, support a new database, or add an importer for a file type — start with the Contributing guides, which give you step-by-step walkthroughs and copy-paste skeletons. The API pages here serve as the detailed reference those guides link to.

For programmatic use, see the [Library API](#library-api) section below. For a high-level overview of how all the pieces fit together, start with the [Architecture & Design Guide](../dev/architecture.md).

## Library API

Use `execsql.inspect_schema(dsn=..., schema=..., table=...)` to inspect database
metadata without running a script. It also accepts `connection=` for an existing
execsql adapter. See [schema discovery](../reference/schema.md) for the shared
CLI/Python JSON contract, connection ownership and adapter coverage.

The primary public API is `execsql.run()`:

```python
from execsql import run, ScriptResult, ScriptError, ExecSqlError

result: ScriptResult = run(
    script="pipeline.sql",       # or sql="SELECT 1;"
    dsn="sqlite:///my.db",       # or connection=existing_db_object
    variables={"KEY": "value"},  # optional; referenced as !!$KEY!! in the script
    halt_on_error=True,          # stop on first error (default)
    new_db=False,                # require an existing database
)
```

The [regional-summary recipe](#regional-summary) supplies a script, input data and expected output. For a supplied connection and factory functions, see [Connection ownership](#connection-ownership) below.

### Connection ownership

With `dsn=`, `run()` owns the initial connection and closes it when the run ends. With `connection=`, the supplied connection remains open for the caller; the existing SQL-error and interrupt rollback rules still apply.

Connections the script opens with CONNECT belong to that run in either mode. At exit, their pending work is rolled back and they are closed, even under AUTOCOMMIT OFF. Commit work on these connections before the script ends if it must be kept. Cleanup does not commit or additionally roll back the borrowed initial connection.

For example, `db_SQLite()` returns an execsql adapter that can be reused across calls. This complete in-memory example closes it only after both runs finish:

```python
from execsql import run
from execsql.db.factory import db_SQLite

connection = db_SQLite(":memory:", new_db=True)
try:
    run(sql="create table counts (n integer);", connection=connection).raise_on_error()
    result = run(
        sql="insert into counts values (2);\n"
            "-- !x! SUBDATA saved_count counts\n",
        connection=connection,
    )
    result.raise_on_error()
    print(result.variables["saved_count"])
finally:
    connection.close()
```

The output is `2`. Supply an execsql `Database` adapter, not a raw driver connection. Other factories, such as `db_Postgres()`, are documented in the [database API](db.md); install their corresponding driver extras first.

### Variables

Each `variables` key becomes a `$` substitution variable, whether or not you write the `$`: `variables={"SCHEMA": "public"}` and `variables={"$SCHEMA": "public"}` both define `!!$SCHEMA!!`. (The CLI's `--var SCHEMA=public` defines `!!SCHEMA!!` instead.)

```python
run(sql='-- !x! WRITE "loading into !!$SCHEMA!!"\n', dsn="sqlite:///my.db", variables={"SCHEMA": "public"})
```

`result.variables` holds every variable's final value, keyed by lower-case name without the sigil: `result.variables["schema"]`.

### Configuration and startup scripts

Pass `config_file=` to use a configuration file's variables and ordered startup scripts. The configured `include_required` files run first, then `include_optional` files, then the main script. Startup files can define tables, variables and named scripts used by the main script. Missing required files fail the run; missing optional files are skipped. Configured files follow the same containment and recursion rules as explicit INCLUDE commands.

The `allow_system_cmd`, `allow_rm_file` and `allow_serve` arguments default to `None`: an omitted argument or `None` inherits the configuration file's value. An explicit `True` or `False` overrides that value. Without a configuration file, all three capabilities remain enabled unless explicitly disabled.

```python
result = run(script="load.sql", dsn="sqlite:///data.db", config_file="restricted.conf")
# A configured allow_system_cmd=No stays disabled.
```

### Errors

Expected configuration, connection and script-execution failures normally return `success=False`; `result.errors` lists what went wrong in the order it happened. Each `ScriptError` has a `message`, a `source`, a `line`, and, for a failed SQL statement, the statement in `sql`.

| `source`                   | What failed                                                                                |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| script path or `<inline>`  | The script could not be read or parsed, or a statement or metacommand in it failed; `line` is its line number |
| `<config>`                 | The `config_file` does not exist or has an invalid setting                                 |
| `<connect>`                | The `dsn` could not be parsed or the database could not be opened                          |
| `<output>`                 | A file written by `WRITE`, `EXPORT` or `TEE` could not be opened before `outfile_open_timeout`, or could not be written |

```python
result = run(sql="select * from nope;", dsn="sqlite:///my.db")
result.success            # False
result.errors[0].message  # "... no such table: nope ..."
result.errors[0].sql      # "select * from nope;"
```

An invalid combination of arguments (both or neither of `script`/`sql`, both or neither of `dsn`/`connection`) raises `ValueError`. Some setup failures can also propagate before a result is available: for example, a script containing invalid bytes for its selected encoding raises `UnicodeDecodeError`. A missing script is instead reported in `result.errors`. Catch decoding errors at the call boundary if input files may use an unexpected encoding; `result.raise_on_error()` only covers failures already recorded in a returned result.

```python
try:
    result = run(script="load.sql", dsn="sqlite:///data.db")
except UnicodeDecodeError:
    # Select the correct script encoding before retrying.
    raise
else:
    result.raise_on_error()
```

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

Four things are still shared by every thread in the process, so keep them apart yourself:

- **The working directory.** `CD` calls `os.chdir()`, which moves every thread while the script runs. Use absolute paths in scripts that run concurrently, or don't use `CD` in them. When a script that ran `CD` finishes, `run()` changes back to the directory it was in before that `CD`, so the caller ends where it started; a run without `CD` leaves the directory as it finds it.
- **The same output file.** Two runs writing one file at the same time can interleave their lines. Give each run its own output paths.
- **Interactive prompts.** `PROMPT` and the other GUI metacommands are not meant to be driven from several threads at once. On macOS, native Tk must initialize on the main thread; first selecting a GUI backend from a worker skips Tk and uses the existing Textual/console fallback, reporting the reason.
- **pyodbc's connection pooling.** Before its first SQL Server, Access or ODBC DSN connection, execsql turns pooling off (`pyodbc.pooling = False`), so every `CONNECT` and every `run()` gets a new database session: a temp table or `SET` option from one run is gone in the next. pyodbc reads the setting at the process's first pyodbc connection, so your own pyodbc connections are not pooled either, and if your program connects with pyodbc before execsql does, pooling stays on and runs against the same server can share a session.

### File Output { #file-output }

`WRITE ... TO <file>`, `TEE`, and the other metacommands that write text files hand their output to a background writer thread. Each `run()` starts its own. On a successful run, all output is flushed and closed and the thread stops before returning, so files are complete and readable when `run()` hands back control.

```python
from execsql import run

result = run(sql='-- !x! WRITE "done" to report.txt\nselect 1;\n', dsn="sqlite:///data.db")
assert result.success, result.errors
open("report.txt").read()   # "done\n" — readable immediately
```

The writer is a thread in your process, not a child process, so `run()` works the same from a `.py` file with or without an `if __name__ == "__main__":` guard, from a REPL, from a notebook, and from `python -c`.

If a file stays locked (by a sync client, a backup, or a spreadsheet that has it open) for longer than [`outfile_open_timeout`](../reference/configuration.md#setting_outfile_open_timeout), `run()` returns `success=False` with an error naming the file and how many lines were lost. A write that fails (a full disk, a dropped network share) is reported the same way, with the OS error, and the run's other files are still written.

If the worker blocks in an open, write, flush or close, the wait ends at [`outfile_open_timeout`](../reference/configuration.md#setting_outfile_open_timeout) plus five seconds, or the shorter halt deadline. Every status and error-report wait uses that same deadline. `run()` returns `success=False` with a `<output>` error naming the operation/file and queued destinations. It abandons the daemon rather than claiming to stop it, and does not wait for it again during cleanup. The I/O call in progress may finish later; no further opens or writes follow it. Queued text and abandoned buffers are discarded. A partial file can remain; WRITE/TEE outputs are incremental, not atomic publications. Other runs keep their own independent writers. EXPORT's synchronous I/O and stdout are outside this deadline.

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

## A complete Python recipe { #regional-summary }

**Runnable Python example.** Install `execsql2` in your Python project, save the SQL as `regional_summary.sql` beside the Python file, and run that file from the same directory. The source fixture is in memory and produces `region_total` equal to `"1650.5"`; no sales database is required. The final error-handling block intentionally reports a missing table.

execsql can be used as a Python library, embedding script execution in pipelines, notebooks, or applications. `run()` executes a script (or inline SQL) and returns a `ScriptResult`. Variables passed via the `variables=` dict are given a `$` prefix, so a key of `"REGION"` is referenced in the script as `!!$REGION!!`:

``` sql
-- regional_summary.sql
create temporary view region_sales as
    select sum(amount) as region_total
    from product_sales
    where region = !'!$REGION!'!;
-- !x! SUBDATA region_total region_sales
```

``` python
from execsql import run
from execsql.db.factory import db_SQLite

conn = db_SQLite(":memory:")
conn.execute("create table product_sales (region text, amount numeric);")
conn.execute("insert into product_sales values ('north', 1000), ('north', 650.5), ('south', 20);")

result = run(
    script="regional_summary.sql",
    connection=conn,
    variables={"REGION": "north"},
)
print(result.success)                       # True
print(result.variables["region_total"])    # "1650.5"

# Keep this connection open for the error-handling example below.
```

If the run is interrupted (Ctrl-C in a notebook), what the interrupted SQL statement, metacommand or `END BATCH` did is rolled back before the interrupt reaches your code, so your next commit on `conn` does not store it; only a commit the database had already finished when the interrupt arrived stays. A `SystemExit` that your own signal handler raises (a timeout, for example) is handled the same way, and `run()` returns a failed result instead of raising it. An interrupted SQL statement rolls back the connection's whole open transaction, as a failed one does, including any work of your own not yet committed; so does any interrupt that ends the run, on every connection with `AUTOCOMMIT` on. Under [AUTOCOMMIT](../reference/metacommands.md#autocommit) OFF, call `conn.rollback()` after the interrupt (or after a failed result from a `SystemExit`) unless you mean to keep what the script was holding.

`result.variables` holds the final state of all substitution variables (system variables have the leading `$` stripped), so values computed by the script — via [SUBDATA](../reference/metacommands.md#subdata), [SUB](../reference/metacommands.md#subcmd), or counters — flow back to Python.

Error handling follows the `halt_on_error` argument. With the default (`True`), execution stops at the first error; with `False`, execution continues and every non-halting error is collected:

``` python
result = run(sql="select * from nonexistent;", connection=conn, halt_on_error=False)
if not result.success:
    for err in result.errors:
        print(f"{err.source}:{err.line}: {err.message}")

try:
    result.raise_on_error()  # raises ExecSqlError for recorded errors
finally:
    conn.close()  # run() leaves a supplied connection open
```

Each `run()` call executes in an isolated context, so repeated or concurrent calls (from different threads) do not share variables or state. See the [Library API reference](../api/index.md#library-api) for the full argument list, including `dsn=` connection URLs and the `allow_system_cmd` / `allow_rm_file` / `allow_serve` safety switches.
