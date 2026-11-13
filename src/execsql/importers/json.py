from __future__ import annotations

"""
JSON import for execsql.

Provides :func:`import_json`, used by ``IMPORT … FROM JSON``.
Supports JSON arrays of objects (``[{…}, …]``) and `JSON Lines
<https://jsonlines.org/>`_ (JSONL, one object per line).  Nested
objects are flattened with dot-separated keys; nested arrays and
non-object values are serialized as JSON strings so every column
maps to a scalar database value.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.importers.base import import_data_table

__all__ = ["import_json"]


def _array_number(value: Any) -> Any:
    """Keep the established JSON text representation of numbers inside arrays."""
    return float(value) if isinstance(value, Decimal) else str(value)


def _flatten(obj: Any, prefix: str = "", sep: str = ".") -> dict[str, Any]:
    """Recursively flatten a nested dict.

    Nested dicts produce dot-separated keys.  All other compound values
    (lists, nested lists-of-dicts) are serialized as JSON strings so the
    result is always ``{str: scalar}``. Distinct paths that produce the
    same column name raise ErrInfo instead of discarding a value.
    """
    items: dict[str, Any] = {}
    source_paths: dict[str, tuple[str, ...]] = {}

    def visit(current: Any, parent: str, path: tuple[str, ...]) -> None:
        if not isinstance(current, dict):
            return
        for key, value in current.items():
            column = f"{parent}{sep}{key}" if parent else key
            source_path = (*path, key)
            if isinstance(value, dict):
                visit(value, column, source_path)
            else:
                if column in items:
                    raise ErrInfo(
                        type="error",
                        other_msg=(
                            f"JSON field paths {json.dumps(source_paths[column])} and {json.dumps(source_path)} "
                            f"flatten to the same column {column!r}. Rename the conflicting keys."
                        ),
                    )
                source_paths[column] = source_path
                items[column] = json.dumps(value, default=_array_number) if isinstance(value, list) else value

    visit(obj, prefix, ())
    return items


def json_format(filename: str, encoding: str) -> str:
    """Identify the same array/object-stream forms IMPORT accepts, ignoring suffix."""
    with open(filename, encoding=encoding) as fh:
        first_char = next((ch for ch in iter(lambda: fh.read(1), "") if not ch.isspace()), None)
    if first_char == "[":
        return "json"
    if first_char == "{":
        return "jsonl"
    raise ErrInfo(type="error", other_msg="JSON import expects a file starting with '[' (array) or '{' (object/JSONL).")


def _parse_json_file(filename: str, encoding: str) -> list[dict[str, Any]]:
    """Read a JSON file and return a list of flat dicts.

    Fractional and exponent scalar numbers retain their exact Decimal digits;
    integers remain int. Arrays retain their established JSON text encoding.
    Accepts either a JSON array of objects or `JSON Lines
    <https://jsonlines.org/>`_ (JSONL). The JSONL path streams the
    file line-by-line so the raw text isn't buffered alongside the
    parsed records (B19/F043). The array path still buffers the
    whole file — switching to a streaming parser would require
    ``ijson`` as a dependency.
    """
    kind = json_format(filename, encoding)
    if kind == "json":
        # Standard JSON array — must buffer the whole file (json.loads
        # has no streaming mode; ijson would be needed for that).
        text = Path(filename).read_text(encoding=encoding)
        raw = json.loads(text, parse_float=Decimal)
        if not isinstance(raw, list):
            raise ErrInfo(type="error", other_msg="JSON file root is not an array of objects.")
        records = raw
    else:
        # JSONL (JSON Lines) — stream the file line-by-line.
        records = []
        with open(filename, encoding=encoding) as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line, parse_float=Decimal)
                except json.JSONDecodeError as exc:
                    raise ErrInfo(
                        type="error",
                        other_msg=f"Invalid JSON on line {lineno}: {exc}",
                    ) from exc
                if not isinstance(obj, dict):
                    raise ErrInfo(
                        type="error",
                        other_msg=f"Line {lineno} is not a JSON object.",
                    )
                records.append(obj)
    if not records:
        raise ErrInfo(type="error", other_msg="JSON file contains no records.")

    # Validate that all records are dicts.
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise ErrInfo(
                type="error",
                other_msg=f"Record {i} in JSON file is not an object (got {type(rec).__name__}).",
            )

    return [_flatten(rec) for rec in records]


def json_data(filename: str, encoding: str) -> tuple[list[str], list[list[Any]]]:
    """Read, flatten and align JSON records using the IMPORT rules."""
    flat_records = _parse_json_file(filename, encoding)
    seen: dict[str, None] = {}
    for rec in flat_records:
        for key in rec:
            seen[key] = None
    hdrs = list(seen)
    return hdrs, [[rec.get(h) for h in hdrs] for rec in flat_records]


def import_json(
    db: Database,
    schemaname: str | None,
    tablename: str,
    filename: str,
    is_new: Any,
    encoding: str | None = None,
) -> None:
    """Import a JSON file into a database table.

    Objects are flattened so that nested keys become dot-separated column
    names (e.g. ``address.city``).  Arrays within objects are stored as
    JSON strings. Colliding paths within a record are rejected before
    any table is created, replaced or populated. Fractional and exponent scalar
    numbers are parsed as Decimal before table inference and target conversion.
    """
    from execsql.utils.errors import exception_desc

    import execsql.state as _state

    enc = encoding if encoding else _state.conf.import_encoding

    try:
        hdrs, data = json_data(filename, enc)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg=f"Can't parse JSON file {filename}",
        ) from e

    import_data_table(db, schemaname, tablename, is_new, hdrs, data)
