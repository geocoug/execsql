from __future__ import annotations

"""
JSON import for execsql.

Provides :func:`import_json`, used by ``IMPORT … FORMAT json``.
Supports JSON arrays of objects (``[{…}, …]``) and newline-delimited
JSON (NDJSON, one object per line).  Nested objects are flattened with
dot-separated keys; nested arrays and non-object values are serialized
as JSON strings so every column maps to a scalar database value.
"""

import json
from pathlib import Path
from typing import Any

from execsql.db.base import Database
from execsql.exceptions import ErrInfo
from execsql.importers.base import import_data_table

__all__ = ["import_json"]


def _flatten(obj: Any, prefix: str = "", sep: str = ".") -> dict[str, Any]:
    """Recursively flatten a nested dict.

    Nested dicts produce dot-separated keys.  All other compound values
    (lists, nested lists-of-dicts) are serialized as JSON strings so the
    result is always ``{str: scalar}``.
    """
    items: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_key = f"{prefix}{sep}{key}" if prefix else key
            if isinstance(value, dict):
                items.update(_flatten(value, new_key, sep))
            elif isinstance(value, list):
                # Serialize arrays as JSON strings — tables are flat.
                items[new_key] = json.dumps(value, default=str)
            else:
                items[new_key] = value
    return items


def _parse_json_file(filename: str, encoding: str) -> list[dict[str, Any]]:
    """Read a JSON file and return a list of flat dicts.

    Accepts either a JSON array of objects or newline-delimited JSON
    (NDJSON).
    """
    text = Path(filename).read_text(encoding=encoding)
    stripped = text.strip()

    if stripped.startswith("["):
        # Standard JSON array.
        raw = json.loads(stripped)
        if not isinstance(raw, list):
            raise ErrInfo(type="error", other_msg="JSON file root is not an array of objects.")
        records = raw
    elif stripped.startswith("{"):
        # Try NDJSON (one object per line) or a single object.
        records = []
        for lineno, line in enumerate(stripped.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
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
    else:
        raise ErrInfo(
            type="error",
            other_msg="JSON import expects a file starting with '[' (array) or '{' (object/NDJSON).",
        )

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
    JSON strings.
    """
    from execsql.utils.errors import exception_desc

    import execsql.state as _state

    enc = encoding if encoding else _state.conf.import_encoding

    try:
        flat_records = _parse_json_file(filename, enc)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo(
            "exception",
            exception_msg=exception_desc(),
            other_msg=f"Can't parse JSON file {filename}",
        ) from e

    # Build a union of all keys across records (preserving first-seen order).
    seen: dict[str, None] = {}
    for rec in flat_records:
        for key in rec:
            if key not in seen:
                seen[key] = None
    hdrs = list(seen)

    # Build row data aligned to hdrs — missing keys become None.
    data = [[rec.get(h) for h in hdrs] for rec in flat_records]

    import_data_table(db, schemaname, tablename, is_new, hdrs, data)
