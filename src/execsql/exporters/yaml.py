from __future__ import annotations

"""
YAML export for execsql.

Provides :func:`write_query_to_yaml` which serialises a query result set as a
YAML sequence of mappings (one mapping per row).

Requires the ``PyYAML`` package (``pip install PyYAML`` or
``pip install 'execsql2[formats]'``).
"""

from typing import Any

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.exporters.zip import ZipWriter
from execsql.utils.errors import exception_desc
from execsql.utils.fileio import filewriter_close

__all__ = ["write_query_to_yaml"]


def write_query_to_yaml(
    select_stmt: str,
    db: Any,
    outfile: str,
    append: bool = False,
    desc: str | None = None,
    zipfile: str | None = None,
) -> None:
    """Execute *select_stmt* and write the result set to *outfile* as YAML.

    The output is a YAML sequence of mappings — one mapping per row with
    column headers as keys.  Python types are preserved: integers stay
    integers, floats stay floats, ``None`` becomes ``null``.

    Args:
        select_stmt: SQL SELECT statement to execute.
        db: Database connection object exposing ``select_rowsource()``.
        outfile: Destination file path, or ``"stdout"``.
        append: When ``True`` the YAML sequence is appended to an existing
            file.  Note that concatenating two bare YAML sequences in one
            file produces a multi-document stream; callers are responsible
            for ensuring the resulting file is valid for their use-case.
        desc: Optional description string.  Ignored in plain YAML output
            (YAML does not have a standard metadata header), but accepted
            for API consistency with other exporters.
        zipfile: When provided, write *outfile* as a member of this zip
            archive instead of writing to the filesystem directly.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ErrInfo(
            "error",
            other_msg=("PyYAML is required for FORMAT YAML export. Install it with: pip install PyYAML"),
        ) from exc

    conf = _state.conf
    try:
        hdrs, rows = db.select_rowsource(select_stmt)
    except ErrInfo:
        raise
    except Exception as e:
        raise ErrInfo("db", select_stmt, exception_msg=exception_desc()) from e

    # Build the list of dicts in memory.  YAML output is human-readable and
    # typically used for small-to-medium result sets; loading into memory is
    # acceptable and required by yaml.dump().
    uhdrs = [str(h) for h in hdrs]
    data = [dict(zip(uhdrs, row)) for row in rows]
    yaml_text = yaml.dump(data, default_flow_style=False, allow_unicode=True)

    if zipfile is None:
        filewriter_close(outfile)
        from execsql.utils.fileio import EncodedFile

        ef = EncodedFile(outfile, conf.output_encoding)
        f = ef.open("at" if append else "wt")
    else:
        f = ZipWriter(zipfile, outfile, append)

    try:
        f.write(yaml_text)
    finally:
        f.close()
