"""The engine behind execsql's two prompts: ``execsql shell`` and the debug REPL.

Both prompts read input the same way and run it the same way: as the next
lines of the run in progress (:func:`~execsql.script.executor.execute_input`).
In ``execsql shell`` the run is the session itself; at a ``BREAKPOINT`` it is
the paused script, so input runs where the script paused, in its variable
scope and transaction.

What runs, and how it runs, follows script rules:

- SQL ends with ``;`` and may span lines. Variables are substituted, and each
  statement is committed unless ``AUTOCOMMIT OFF`` or a batch is in effect.
  Results print as tables.
- A metacommand is typed as in a script (``-- !x! EXPORT …``) or without the
  comment marker (``!x! EXPORT …``).
- A block (``IF`` … ``ENDIF``, ``LOOP``, ``BEGIN BATCH``, ``BEGIN SCRIPT``)
  keeps the prompt reading until it is closed, then runs as a whole.

The one difference from a script: an error that would halt the run ends only
the input that caused it. The prompt reports it and reads the next input.
``HALT`` still ends the run.

A line starting with ``.`` is a command to the prompt itself. :class:`Prompt`
holds what differs between the two prompts: their names and their own
commands. ``.vars``, ``.set``, ``.scripts`` and ``.cancel`` are common to both.

Display helpers (colors, tables, variable listings) live in
:mod:`execsql.debug.repl` and are reached through the module, so tests that
patch them there see every caller.
"""

from __future__ import annotations

import sys

import execsql.state as _state
from execsql.exceptions import ErrInfo

__all__ = ["Prompt", "read_eval_loop", "run_input", "uncommitted"]


class Prompt:
    """What differs between the prompts; subclassed by each.

    Attributes:
        name: The prompt text before ``>``, e.g. ``execsql``.
        source: The name input is given in messages and ``$CURRENT_SCRIPT``.
    """

    name = "execsql"
    source = "<prompt>"

    def dot_command(self, command: str, argument: str, line: str) -> bool:
        """Handle a ``.`` command; return ``False`` to leave the prompt.

        *command* is the lowercased word after the dot, *argument* the rest
        of the line as typed.
        """
        if not common_dot_command(command, argument, line):
            unknown_dot_command(line)
        return True


def uncommitted() -> bool:
    """Whether SQL run now waits for a commit: ``AUTOCOMMIT OFF`` or an open batch."""
    status = _state.status
    if status is not None and status.batch.in_batch():
        return True
    dbs = _state.dbs
    if dbs is None:
        return False
    try:
        db = dbs.current()
    except Exception:
        return False
    return db is not None and not db.autocommit


def _prompts(prompt: Prompt) -> tuple[str, str]:
    """The prompt and continuation-line strings; ``*`` marks uncommitted mode."""
    first = f"{prompt.name}{'*' if uncommitted() else ''}> "
    return first, "...> ".rjust(len(first))


def _is_metacommand(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("--") and stripped[2:].lstrip().lower().startswith("!x!")


def _complete(line: str) -> bool:
    """Whether input ending with *line* may be whole: it ends with ``;`` or is a metacommand."""
    return line.rstrip().endswith(";") or _is_metacommand(line)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def describe_error(exc: BaseException) -> str:
    """One line for a prompt: the driver's or handler's own message, and where it came from."""
    from execsql.debug import repl as _ui

    label = "Error:"
    if isinstance(exc, ErrInfo):
        cause = exc.__cause__
        if isinstance(cause, Exception) and not isinstance(cause, ErrInfo) and str(cause):
            message = str(cause)
        else:
            message = exc.other or exc.exception or exc.type
            if exc.command and exc.command not in message:
                message = f"{message}: {exc.command}"
        if exc.cmdtype == "sql":
            label = "SQL error:"
        source = exc.script_file
        if source and not (source.startswith("<") and source.endswith(">")) and exc.script_line_no:
            message = f"{message} (line {exc.script_line_no} of {source})"
    else:
        message = str(exc) or type(exc).__name__
    return f"{_ui._c(_ui._RED, label)} {_one_line(message)}"


def _show_result(result: tuple[list[str], list] | None) -> None:
    """Print a statement's rows as a table, or how many rows it changed."""
    from execsql.debug import repl as _ui

    if result is not None:
        _ui._print_table(*result)
        return
    count = -1
    if _state.subvars is not None:
        try:
            count = int(_state.subvars.varvalue("$LAST_ROWCOUNT") or -1)
        except (TypeError, ValueError):
            count = -1
    word = "row" if count == 1 else "rows"
    _ui._write(f"  {_ui._c(_ui._DIM, f'({count} {word} affected)' if count >= 0 else '(statement executed)')}\n")


def run_input(text: str, source: str) -> None:
    """Parse *text* and run it as the next lines of the run; errors are raised."""
    from execsql.script.executor import execute_input
    from execsql.script.parser import parse_string

    execute_input(parse_string(text + "\n", source), _show_result)


def common_dot_command(command: str, argument: str, line: str) -> bool:
    """Handle a command both prompts share; return ``False`` if *command* is not one."""
    from execsql.debug import repl as _ui

    if command in ("vars", "v"):
        if argument.lower() == "all":
            _ui._print_all_vars(include_env=True)
        elif argument:
            _ui._print_var(argument)
        else:
            _ui._print_all_vars()
    elif command in ("set", "s"):
        parts = argument.split(None, 1)
        if not parts:
            _ui._write(f"  Usage: .{command} VAR VALUE\n")
        else:
            _ui._set_var(parts[0], parts[1] if len(parts) > 1 else "")
    elif command == "scripts":
        if argument:
            _ui._print_script_detail(argument)
        else:
            _ui._print_scripts()
    else:
        return False
    return True


def unknown_dot_command(line: str) -> None:
    from execsql.debug import repl as _ui

    _ui._write(f"  {_ui._c(_ui._RED, 'Unknown command:')} {line!r}. Type '.help' for available commands.\n")


def _read_line(prompt_text: str, interactive: bool) -> str:
    """One line of input, without its newline; ``EOFError`` at the end."""
    if interactive:
        return input(prompt_text)
    line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line.rstrip("\n")


def read_eval_loop(prompt: Prompt, *, interactive: bool) -> None:
    """Read and run inputs until the prompt's own command ends it, or input ends.

    With *interactive*, lines are read with ``input()`` (line editing, a
    prompt); Ctrl-D or Ctrl-C discards a half-typed input, and on an empty
    line leaves the prompt. Otherwise lines are read from stdin without a
    prompt, and input ending inside a statement or block is reported.
    """
    from execsql.debug import repl as _ui

    buffer: list[str] = []
    while True:
        first, more = _prompts(prompt)
        try:
            line = _read_line(more if buffer else first, interactive)
        except (EOFError, KeyboardInterrupt) as exc:
            if interactive and buffer:
                buffer.clear()
                _ui._write("\n  (input discarded)\n")
                continue
            if interactive:
                _ui._write("\n")
            elif buffer and isinstance(exc, EOFError):
                _ui._write(
                    f"  {_ui._c(_ui._RED, 'Error:')} input ended inside an unfinished statement or block; "
                    "it was not run.\n",
                )
            return
        stripped = line.strip()
        if not stripped and not buffer:
            continue
        if stripped.startswith("."):
            command, _, argument = stripped[1:].partition(" ")
            command = command.lower()
            if command == "cancel":
                if buffer:
                    buffer.clear()
                    _ui._write("  (input discarded)\n")
                continue
            try:
                if not prompt.dot_command(command, argument.strip(), stripped):
                    return
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as exc:
                _ui._write(f"  {describe_error(exc)}\n")
            continue
        if stripped.lower().startswith("!x!"):
            line = "-- " + stripped
        buffer.append(line)
        if not _complete(line):
            continue
        try:
            run_input("\n".join(buffer), prompt.source)
        except ErrInfo as exc:
            if "at end of file" in str(exc):
                continue  # a block is still open; keep reading
            _ui._write(f"  {describe_error(exc)}\n")
        except KeyboardInterrupt:
            _ui._write("\n  (interrupted)\n")
        except Exception as exc:
            _ui._write(f"  {describe_error(exc)}\n")
        buffer.clear()
