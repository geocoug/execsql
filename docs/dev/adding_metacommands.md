# Adding a New Metacommand

This guide walks through every step required to add a new metacommand to execsql. The process involves four files in a fixed sequence: write the handler, register the regex, export the handler, and add tests.

______________________________________________________________________

## Background: How Metacommands Work

### The dispatch table

At import time, `src/execsql/metacommands/__init__.py` calls `build_dispatch_table()`, which populates a `MetaCommandList` and assigns it to the module-level `DISPATCH_TABLE`. That singleton is consumed at runtime via `_state.metacommandlist`.

### MetaCommandList / MetaCommand

`MetaCommandList` is a singly-linked list of `MetaCommand` objects (defined in `src/execsql/script.py`). Each `MetaCommand` holds one compiled regex and one handler function. When `MetaCommandList.eval()` is called on a line of SQL script:

1. It walks the linked list until a regex matches.
1. It checks `_state.if_stack.all_true()` (skips execution when inside a false conditional branch, unless `run_when_false=True`).
1. It calls the handler, passing all named regex groups plus `"metacommandline"` as keyword arguments.
1. On success, it moves the matched node to the head of the list (LRU optimisation).

### Handler naming conventions

| Prefix | Purpose                                                                                                                        |
| ------ | ------------------------------------------------------------------------------------------------------------------------------ |
| `x_*`  | Metacommand handler — registered in `build_dispatch_table()`                                                                   |
| `xf_*` | Conditional test predicate — registered in `conditions.py`'s `build_conditional_table()` and used by `IF`/`ELSEIF` expressions |

______________________________________________________________________

## Step-by-step: Adding a Metacommand

### Step 1 — Write the handler function

Add the handler to whichever sibling module fits best:

| Module          | Handles                                               |
| --------------- | ----------------------------------------------------- |
| `connect.py`    | Database connections, `USE`, `DISCONNECT`             |
| `control.py`    | Control flow: `IF`, `LOOP`, `BREAK`, `HALT`, batch    |
| `data.py`       | Variable manipulation: `SUB`, `SUBDATA`, counters     |
| `io.py`         | File I/O: `EXPORT`, `IMPORT`, `INCLUDE`, `WRITE`      |
| `prompt.py`     | User interaction: `PROMPT`, `ASK`, `PAUSE`, `MSG`     |
| `system.py`     | OS interaction: `SYSTEM_CMD`, `LOG`, `EMAIL`, console |
| `debug.py`      | Debug output                                          |
| `script_ext.py` | Script extensions                                     |

If none of these fit, create a new module and follow the same structure.

**Handler signature:** all handlers accept only `**kwargs`. The keys are the named groups from the matching regex, plus `"metacommandline"` (the original unmodified command line).

```python
# src/execsql/metacommands/data.py
from typing import Any
import execsql.state as _state


def x_my_command(**kwargs: Any) -> None:
    target = kwargs["target"]          # from (?P<target>...) in the regex
    value  = kwargs["value"]           # from (?P<value>...) in the regex
    # Optional groups are None when absent — check before using.
    option = kwargs.get("option")

    # Interact with global state as needed.
    _state.subvars.add_substitution(target, value)
    return None
```

Key points:

- **Return `None`** unless there is a specific reason to return a value (very rare).
- **Optional regex groups** will be `None` when the group did not participate in the match. Always guard with `if option:` or `kwargs.get("option")`.
- **Raise `ErrInfo`** for expected failure conditions rather than using a bare `raise` or `sys.exit`.

```python
from execsql.exceptions import ErrInfo

def x_my_command(**kwargs: Any) -> None:
    if not some_condition:
        raise ErrInfo("cmd", command_text=kwargs["metacommandline"],
                      other_msg="MY_COMMAND: something went wrong")
```

### Step 2 — Register the regex in the dispatch table

Open `src/execsql/metacommands/__init__.py` and add a `mcl.add()` call inside `build_dispatch_table()`. **Order matters**: more specific patterns should appear before catch-all patterns. The linked list is traversed front-to-back and the first match wins.

```python
mcl.add(
    r"^\s*MY_COMMAND\s+(?P<target>\w+)\s+(?P<value>.+)$",
    x_my_command,
)
```

`MetaCommandList.add()` accepts these parameters:

| Parameter          | Type                       | Default  | Purpose                                                                                |
| ------------------ | -------------------------- | -------- | -------------------------------------------------------------------------------------- |
| `matching_regexes` | `str` or `tuple[str, ...]` | required | One regex string, or a tuple of strings all mapped to the same handler                 |
| `exec_func`        | callable                   | required | The handler function                                                                   |
| `description`      | `str \| None`              | `None`   | Human-readable label (shown in `DEBUG WRITE METACOMMANDLIST`)                          |
| `run_in_batch`     | `bool`                     | `False`  | Allow execution inside an open `BEGIN_BATCH`/`END_BATCH` block                         |
| `run_when_false`   | `bool`                     | `False`  | Execute even when the `IF`-stack condition is false (needed for `ELSE`, `ENDIF`, etc.) |
| `set_error_flag`   | `bool`                     | `True`   | Update `_state.status.metacommand_error` on success/failure                            |

All regexes are compiled with `re.I` (case-insensitive) automatically.

**Passing multiple regex variants** is common when a value may be quoted or unquoted:

```python
mcl.add(
    (
        r'^\s*MY_COMMAND\s+(?P<target>\w+)\s+"(?P<value>[^"]+)"\s*$',
        r"^\s*MY_COMMAND\s+(?P<target>\w+)\s+(?P<value>\S+)\s*$",
    ),
    x_my_command,
    description="MY_COMMAND",
)
```

**Using regex composition helpers** (from `src/execsql/utils/regex.py`) avoids duplicating patterns for all quoting styles used by file-name arguments:

```python
from execsql.utils.regex import ins_fn_rxs, ins_table_rxs

# ins_fn_rxs(prefix, suffix) generates variants for bare, quoted, and
# bracket-quoted filenames captured as (?P<filename>...).
mcl.add(
    ins_fn_rxs(r"^\s*MY_COMMAND\s+TO\s+", r"\s*$"),
    x_my_command,
)
```

### Step 3 — Export the handler in `__init__.py`

Add the function to the relevant import block at the top of
`src/execsql/metacommands/__init__.py`:

```python
from execsql.metacommands.data import (
    ...
    x_my_command,   # add here
)
```

### Step 4 — Write tests

#### Integration tests (preferred)

Integration tests exercise the full CLI pipeline against a temporary SQLite database. Add a new test class to `tests/test_metacommands.py` (or the appropriate `test_metacommands_*.py` file):

```python
class TestMyCommand:
    """MY_COMMAND metacommand."""

    def test_basic(self, script_runner):
        result, db = script_runner("""
            -- !x! my_command greeting hello
            create table result (val text);
            insert into result values ('!!greeting!!');
        """)
        assert result.exit_code == 0, result.output
        assert qdb(db, "SELECT val FROM result") == [("hello",)]

    def test_error_case(self, script_runner):
        result, db = script_runner("""
            -- !x! my_command
        """)
        # Bad syntax should not crash; exit code depends on HALT_ON_METACOMMAND_ERR
        assert "MY_COMMAND" in result.output or result.exit_code != 0
```

The `script_runner` fixture:

- Writes the script to a temp `.sql` file.
- Invokes `execsql <script> <db> -t l -n` via `typer.testing.CliRunner`.
- Waits for the `FileWriter` subprocess to flush all pending writes.
- Returns `(result, db_path)`.

Use `qdb(db_path, sql)` to query the resulting SQLite database for assertions.

#### Unit tests

For handlers that are complex enough to warrant isolated testing, use direct function calls with mocked state. See `tests/test_metacommands_connect.py` for examples:

```python
from unittest.mock import patch, MagicMock
from execsql.metacommands.data import x_my_command


def test_x_my_command_sets_subvar(minimal_conf, tmp_path):
    # Set up the minimal state that the handler touches.
    from tests.conftest import _setup_subvars
    sv = _setup_subvars()

    x_my_command(
        target="greeting",
        value="hello",
        option=None,
        metacommandline="MY_COMMAND greeting hello",
    )

    assert sv.get_substitution("greeting") == "hello"
```

______________________________________________________________________

## Checklist

- [ ] Handler function added to the appropriate `src/execsql/metacommands/*.py` module
- [ ] Handler imported in `src/execsql/metacommands/__init__.py`
- [ ] `mcl.add(...)` call added in `build_dispatch_table()` at the right position
- [ ] Integration test added to `tests/test_metacommands.py` (or relevant file)
- [ ] `pytest` passes locally

______________________________________________________________________

## Adding a Conditional Test Predicate (`xf_*`)

If your new functionality needs to be usable in `IF`/`ELSEIF` expressions (e.g., `IF MY_TEST foo bar`), add an `xf_*` function instead. These live in `src/execsql/metacommands/conditions.py` and are registered in a separate `build_conditional_table()` function in the same file.

```python
def xf_my_test(**kwargs: Any) -> bool:
    """Return True if the condition is met."""
    return kwargs["value1"] == kwargs["value2"]
```

Then register it in `build_conditional_table()`:

```python
ctl.add(
    r"^\s*MY_TEST\s+(?P<value1>\S+)\s+(?P<value2>\S+)\s*$",
    xf_my_test,
)
```

The conditional table is exposed as `CONDITIONAL_TABLE` and consumed via `_state.conditionallist`.
