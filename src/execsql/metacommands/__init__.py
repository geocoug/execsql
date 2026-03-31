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

__all__ = [
    # execsql.state
    "_state",
    # connect handlers
    "x_connect_pg",
    "x_connect_user_pg",
    "x_connect_ssvr",
    "x_connect_user_ssvr",
    "x_connect_mysql",
    "x_connect_user_mysql",
    "x_connect_access",
    "x_connect_fb",
    "x_connect_user_fb",
    "x_connect_ora",
    "x_connect_user_ora",
    "x_connect_duckdb",
    "x_connect_sqlite",
    "x_connect_dsn",
    "x_use",
    "x_disconnect",
    "x_autocommit_on",
    "x_autocommit_off",
    "x_pg_vacuum",
    "x_daoflushdelay",
    # control handlers
    "x_if",
    "x_if_orif",
    "x_if_andif",
    "x_if_elseif",
    "x_if_else",
    "x_if_block",
    "x_if_end",
    "x_loop",
    "x_halt",
    "x_halt_msg",
    "x_error_halt",
    "x_metacommand_error_halt",
    "x_begin_batch",
    "x_end_batch",
    "x_rollback",
    "x_break",
    "x_wait_until",
    # data handlers
    "x_sub",
    "x_sub_add",
    "x_sub_append",
    "x_sub_empty",
    "x_rm_sub",
    "x_sub_local",
    "x_sub_tempfile",
    "x_sub_ini",
    "x_sub_querystring",
    "x_sub_encrypt",
    "x_sub_decrypt",
    "x_subdata",
    "x_selectsub",
    "x_prompt_selectsub",
    "x_empty_strings",
    "x_trim_strings",
    "x_replace_newlines",
    "x_empty_rows",
    "x_only_strings",
    "x_boolean_int",
    "x_boolean_words",
    "x_fold_col_hdrs",
    "x_trim_col_hdrs",
    "x_clean_col_hdrs",
    "x_del_empty_cols",
    "x_create_col_hdrs",
    "x_dedup_col_hdrs",
    "x_import_common_cols_only",
    "x_quote_all_text",
    "x_reset_counter",
    "x_reset_counters",
    "x_set_counter",
    "x_max_int",
    # debug handlers
    "x_debug_write_metacommands",
    "x_debug_commandliststack",
    "x_debug_iflevels",
    "x_debug_write_odbc_drivers",
    "x_debug_log_subvars",
    "x_debug_log_config",
    "x_debug_write_subvars",
    "x_debug_write_config",
    # io handlers
    "x_export",
    "x_export_query",
    "x_export_query_with_template",
    "x_export_with_template",
    "x_export_ods_multiple",
    "x_export_metadata",
    "x_export_metadata_table",
    "x_import",
    "x_import_file",
    "x_import_ods",
    "x_import_ods_pattern",
    "x_import_xls",
    "x_import_xls_pattern",
    "x_import_parquet",
    "x_import_feather",
    "x_import_row_buffer",
    "x_show_progress",
    "x_export_row_buffer",
    "x_write",
    "x_write_create_table",
    "x_write_create_table_ods",
    "x_write_create_table_xls",
    "x_write_create_table_alias",
    "x_write_prefix",
    "x_write_suffix",
    "x_writescript",
    "x_include",
    "x_copy",
    "x_copy_query",
    "x_zip",
    "x_zip_buffer_mb",
    "x_rm_file",
    "x_make_export_dirs",
    "x_cd",
    "x_scan_lines",
    "x_hdf5_text_len",
    "x_serve",
    # prompt handlers
    "x_prompt",
    "x_prompt_enter",
    "x_prompt_entryform",
    "x_prompt_pause",
    "x_prompt_compare",
    "x_prompt_ask_compare",
    "x_prompt_ask",
    "x_prompt_map",
    "x_prompt_action",
    "x_prompt_savefile",
    "x_prompt_openfile",
    "x_prompt_directory",
    "x_prompt_select_rows",
    "x_prompt_credentials",
    "x_prompt_connect",
    "x_ask",
    "x_pause",
    "x_msg",
    "x_reset_dialog_canceled",
    # script_ext handlers
    "x_extendscript",
    "x_extendscript_metacommand",
    "x_extendscript_sql",
    "x_executescript",
    # system handlers
    "x_system_cmd",
    "x_email",
    "x_timer",
    "x_log",
    "x_logwritemessages",
    "x_log_datavars",
    "x_log_sql",
    "x_console",
    "x_consoleprogress",
    "x_consolewait",
    "x_consolewait_onerror",
    "x_consolewait_whendone",
    "x_console_hideshow",
    "x_consolewidth",
    "x_consoleheight",
    "x_consolestatus",
    "x_consolesave",
    "x_cancel_halt",
    "x_cancel_halt_write_clear",
    "x_cancel_halt_write",
    "x_cancel_halt_email_clear",
    "x_cancel_halt_email",
    "x_cancel_halt_exec",
    "x_cancel_halt_exec_clear",
    "x_error_halt_write_clear",
    "x_error_halt_write",
    "x_error_halt_email_clear",
    "x_error_halt_email",
    "x_error_halt_exec",
    "x_error_halt_exec_clear",
    "x_write_warnings",
    "x_gui_level",
    "x_execute",
    # regex helpers
    "ins_rxs",
    "ins_quoted_rx",
    "ins_schema_rxs",
    "ins_table_rxs",
    "ins_table_list_rxs",
    "ins_fn_rxs",
    # MetaCommandList
    "MetaCommandList",
    # format constants
    "DELIMITED_FORMATS",
    "TEXT_FORMATS",
    "JSON_VARIANT_FORMATS",
    "QUERY_EXPORT_FORMATS",
    "TABLE_EXPORT_FORMATS",
    "SERVE_FORMATS",
    "METADATA_FORMATS",
    "ALL_EXPORT_FORMATS",
    "DATABASE_TYPES",
    # dispatch
    "build_dispatch_table",
    "DISPATCH_TABLE",
]

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
