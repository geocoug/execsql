"""Input/output metacommand handlers for execsql.

This module is a **re-export façade**: the actual implementations live in
the sibling submodules listed below.  All public names are imported here so
that existing ``from execsql.metacommands.io import x_*`` paths continue to
work without changes.

Submodules
----------
- :mod:`~execsql.metacommands.io_export`   — EXPORT handlers
- :mod:`~execsql.metacommands.io_import`   — IMPORT handlers
- :mod:`~execsql.metacommands.io_write`    — WRITE / WRITESCRIPT handlers
- :mod:`~execsql.metacommands.io_fileops`  — file ops, COPY, ZIP, INCLUDE, SERVE, etc.
"""

from __future__ import annotations

# -- export handlers ---------------------------------------------------------
from execsql.metacommands.io_export import (  # noqa: F401
    _apply_output_dir,
    x_export,
    x_export_metadata,
    x_export_metadata_table,
    x_export_ods_multiple,
    x_export_query,
    x_export_query_with_template,
    x_export_row_buffer,
    x_export_with_template,
)

# -- import handlers ---------------------------------------------------------
from execsql.metacommands.io_import import (  # noqa: F401
    x_import,
    x_import_feather,
    x_import_file,
    x_import_ods,
    x_import_ods_pattern,
    x_import_parquet,
    x_import_row_buffer,
    x_import_xls,
    x_show_progress,
    x_import_xls_pattern,
)

# -- write handlers ----------------------------------------------------------
from execsql.metacommands.io_write import (  # noqa: F401
    x_write,
    x_write_create_table,
    x_write_create_table_alias,
    x_write_create_table_ods,
    x_write_create_table_xls,
    x_write_prefix,
    x_write_suffix,
    x_writescript,
)

# -- file / system operation handlers ----------------------------------------
from execsql.metacommands.io_fileops import (  # noqa: F401
    x_cd,
    x_copy,
    x_copy_query,
    x_hdf5_text_len,
    x_include,
    x_make_export_dirs,
    x_rm_file,
    x_scan_lines,
    x_serve,
    x_zip,
    x_zip_buffer_mb,
)
