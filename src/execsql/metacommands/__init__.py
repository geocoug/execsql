"""execsql metacommand dispatch table.

Importing this module populates a MetaCommandList (``DISPATCH_TABLE``) with
every metacommand regex and its handler function.  The dispatch table is
consumed by script.MetacommandStmt.run() via ``_state.metacommandlist``.

Handler functions live in the sibling modules:
  connect, conditions, control, data, debug, io, prompt, script_ext, system
"""

from __future__ import annotations

import execsql.state as _state  # noqa: F401

# Handler imports — grouped by module for readability.
from execsql.metacommands.connect import (
    x_connect_pg,  # noqa: F401
    x_connect_user_pg,  # noqa: F401
    x_connect_ssvr,  # noqa: F401
    x_connect_user_ssvr,  # noqa: F401
    x_connect_mysql,  # noqa: F401
    x_connect_user_mysql,  # noqa: F401
    x_connect_access,  # noqa: F401
    x_connect_fb,  # noqa: F401
    x_connect_user_fb,  # noqa: F401
    x_connect_ora,  # noqa: F401
    x_connect_user_ora,  # noqa: F401
    x_connect_duckdb,  # noqa: F401
    x_connect_sqlite,  # noqa: F401
    x_connect_dsn,  # noqa: F401
    x_use,  # noqa: F401
    x_disconnect,  # noqa: F401
    x_autocommit_on,  # noqa: F401
    x_autocommit_off,  # noqa: F401
    x_pg_vacuum,  # noqa: F401
    x_daoflushdelay,  # noqa: F401
)
from execsql.metacommands.control import (
    x_if,  # noqa: F401
    x_if_orif,  # noqa: F401
    x_if_andif,  # noqa: F401
    x_if_elseif,  # noqa: F401
    x_if_else,  # noqa: F401
    x_if_block,  # noqa: F401
    x_if_end,  # noqa: F401
    x_loop,  # noqa: F401
    x_halt,  # noqa: F401
    x_halt_msg,  # noqa: F401
    x_error_halt,  # noqa: F401
    x_metacommand_error_halt,  # noqa: F401
    x_begin_batch,  # noqa: F401
    x_end_batch,  # noqa: F401
    x_rollback,  # noqa: F401
    x_break,  # noqa: F401
    x_wait_until,  # noqa: F401
)
from execsql.metacommands.data import (
    x_sub,  # noqa: F401
    x_sub_add,  # noqa: F401
    x_sub_append,  # noqa: F401
    x_sub_empty,  # noqa: F401
    x_rm_sub,  # noqa: F401
    x_sub_local,  # noqa: F401
    x_sub_tempfile,  # noqa: F401
    x_sub_ini,  # noqa: F401
    x_sub_querystring,  # noqa: F401
    x_sub_encrypt,  # noqa: F401
    x_sub_decrypt,  # noqa: F401
    x_subdata,  # noqa: F401
    x_selectsub,  # noqa: F401
    x_prompt_selectsub,  # noqa: F401
    x_empty_strings,  # noqa: F401
    x_trim_strings,  # noqa: F401
    x_replace_newlines,  # noqa: F401
    x_empty_rows,  # noqa: F401
    x_only_strings,  # noqa: F401
    x_boolean_int,  # noqa: F401
    x_boolean_words,  # noqa: F401
    x_fold_col_hdrs,  # noqa: F401
    x_trim_col_hdrs,  # noqa: F401
    x_clean_col_hdrs,  # noqa: F401
    x_del_empty_cols,  # noqa: F401
    x_create_col_hdrs,  # noqa: F401
    x_dedup_col_hdrs,  # noqa: F401
    x_import_common_cols_only,  # noqa: F401
    x_quote_all_text,  # noqa: F401
    x_reset_counter,  # noqa: F401
    x_reset_counters,  # noqa: F401
    x_set_counter,  # noqa: F401
    x_max_int,  # noqa: F401
)
from execsql.metacommands.debug import (
    x_debug_write_metacommands,  # noqa: F401
    x_debug_commandliststack,  # noqa: F401
    x_debug_iflevels,  # noqa: F401
    x_debug_write_odbc_drivers,  # noqa: F401
    x_debug_log_subvars,  # noqa: F401
    x_debug_log_config,  # noqa: F401
    x_debug_write_subvars,  # noqa: F401
    x_debug_write_config,  # noqa: F401
)
from execsql.metacommands.io import (
    x_export,  # noqa: F401
    x_export_query,  # noqa: F401
    x_export_query_with_template,  # noqa: F401
    x_export_with_template,  # noqa: F401
    x_export_ods_multiple,  # noqa: F401
    x_export_metadata,  # noqa: F401
    x_export_metadata_table,  # noqa: F401
    x_import,  # noqa: F401
    x_import_file,  # noqa: F401
    x_import_ods,  # noqa: F401
    x_import_ods_pattern,  # noqa: F401
    x_import_xls,  # noqa: F401
    x_import_xls_pattern,  # noqa: F401
    x_import_parquet,  # noqa: F401
    x_import_feather,  # noqa: F401
    x_import_row_buffer,  # noqa: F401
    x_show_progress,  # noqa: F401
    x_export_row_buffer,  # noqa: F401
    x_write,  # noqa: F401
    x_write_create_table,  # noqa: F401
    x_write_create_table_ods,  # noqa: F401
    x_write_create_table_xls,  # noqa: F401
    x_write_create_table_alias,  # noqa: F401
    x_write_prefix,  # noqa: F401
    x_write_suffix,  # noqa: F401
    x_writescript,  # noqa: F401
    x_include,  # noqa: F401
    x_copy,  # noqa: F401
    x_copy_query,  # noqa: F401
    x_zip,  # noqa: F401
    x_zip_buffer_mb,  # noqa: F401
    x_rm_file,  # noqa: F401
    x_make_export_dirs,  # noqa: F401
    x_cd,  # noqa: F401
    x_scan_lines,  # noqa: F401
    x_hdf5_text_len,  # noqa: F401
    x_serve,  # noqa: F401
)
from execsql.metacommands.prompt import (
    x_prompt,  # noqa: F401
    x_prompt_enter,  # noqa: F401
    x_prompt_entryform,  # noqa: F401
    x_prompt_pause,  # noqa: F401
    x_prompt_compare,  # noqa: F401
    x_prompt_ask_compare,  # noqa: F401
    x_prompt_ask,  # noqa: F401
    x_prompt_map,  # noqa: F401
    x_prompt_action,  # noqa: F401
    x_prompt_savefile,  # noqa: F401
    x_prompt_openfile,  # noqa: F401
    x_prompt_directory,  # noqa: F401
    x_prompt_select_rows,  # noqa: F401
    x_prompt_credentials,  # noqa: F401
    x_prompt_connect,  # noqa: F401
    x_ask,  # noqa: F401
    x_pause,  # noqa: F401
    x_msg,  # noqa: F401
    x_reset_dialog_canceled,  # noqa: F401
)
from execsql.metacommands.script_ext import (
    x_extendscript,  # noqa: F401
    x_extendscript_metacommand,  # noqa: F401
    x_extendscript_sql,  # noqa: F401
    x_executescript,  # noqa: F401
)
from execsql.metacommands.system import (
    x_system_cmd,  # noqa: F401
    x_email,  # noqa: F401
    x_timer,  # noqa: F401
    x_log,  # noqa: F401
    x_logwritemessages,  # noqa: F401
    x_log_datavars,  # noqa: F401
    x_log_sql,  # noqa: F401
    x_console,  # noqa: F401
    x_consoleprogress,  # noqa: F401
    x_consolewait,  # noqa: F401
    x_consolewait_onerror,  # noqa: F401
    x_consolewait_whendone,  # noqa: F401
    x_console_hideshow,  # noqa: F401
    x_consolewidth,  # noqa: F401
    x_consoleheight,  # noqa: F401
    x_consolestatus,  # noqa: F401
    x_consolesave,  # noqa: F401
    x_cancel_halt,  # noqa: F401
    x_cancel_halt_write_clear,  # noqa: F401
    x_cancel_halt_write,  # noqa: F401
    x_cancel_halt_email_clear,  # noqa: F401
    x_cancel_halt_email,  # noqa: F401
    x_cancel_halt_exec,  # noqa: F401
    x_cancel_halt_exec_clear,  # noqa: F401
    x_error_halt_write_clear,  # noqa: F401
    x_error_halt_write,  # noqa: F401
    x_error_halt_email_clear,  # noqa: F401
    x_error_halt_email,  # noqa: F401
    x_error_halt_exec,  # noqa: F401
    x_error_halt_exec_clear,  # noqa: F401
    x_write_warnings,  # noqa: F401
    x_gui_level,  # noqa: F401
    x_execute,  # noqa: F401
)

# Regex helper functions (from utils/regex.py)
from execsql.utils.regex import (
    ins_rxs,  # noqa: F401
    ins_quoted_rx,  # noqa: F401
    ins_schema_rxs,  # noqa: F401
    ins_table_rxs,  # noqa: F401
    ins_table_list_rxs,  # noqa: F401
    ins_fn_rxs,  # noqa: F401
)
from execsql.script import MetaCommandList  # noqa: F401

# ---------------------------------------------------------------------------
# Export format constants — single source of truth.
# Used in dispatch table regex patterns and by io_export.py for validation.
# ---------------------------------------------------------------------------
DELIMITED_FORMATS = ["CSV", "TAB", "TSV", "TABQ", "TSVQ", "UNITSEP", "US"]
TEXT_FORMATS = ["TXT", "TXT-AND", "PLAIN"]
JSON_VARIANT_FORMATS = ["JSON_TS", "JSON_TABLESCHEMA"]

QUERY_EXPORT_FORMATS = (
    DELIMITED_FORMATS + TEXT_FORMATS + ["ODS", "JSON", "HTML", "CGI-HTML", "VALUES", "LATEX", "RAW", "B64", "FEATHER"]
)
TABLE_EXPORT_FORMATS = (
    DELIMITED_FORMATS
    + TEXT_FORMATS
    + ["JSON", "XML", "VALUES", "HTML", "CGI-HTML", "SQLITE", "DUCKDB", "LATEX", "RAW", "B64", "FEATHER", "HDF5"]
)
SERVE_FORMATS = ["BINARY", "CSV", "TXT", "TEXT", "ODS", "JSON", "HTML", "PDF", "ZIP"]
METADATA_FORMATS = ["CSV", "TAB", "TSV", "TABQ", "TSVQ", "TXT", "TEXT"]
ALL_EXPORT_FORMATS = sorted(
    set(QUERY_EXPORT_FORMATS + TABLE_EXPORT_FORMATS + JSON_VARIANT_FORMATS),
)

DATABASE_TYPES = [
    "POSTGRESQL",
    "MYSQL",
    "MARIADB",
    "ORACLE",
    "SQLSERVER",
    "FIREBIRD",
    "ACCESS",
    "DUCKDB",
    "SQLITE",
    "DSN",
]


# ---------------------------------------------------------------------------
# Module-level DISPATCH_TABLE — built once at import time.
# ---------------------------------------------------------------------------
from execsql.metacommands.dispatch import build_dispatch_table  # noqa: E402

DISPATCH_TABLE = build_dispatch_table()
