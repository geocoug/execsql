"""execsql metacommand dispatch table.

Importing this module populates a MetaCommandList (``DISPATCH_TABLE``) with
every metacommand regex and its handler function.  The dispatch table is
consumed by script.MetacommandStmt.run() via ``_state.metacommandlist``.

Handler functions live in the sibling modules:
  connect, conditions, control, data, debug, io, prompt, script_ext, system
"""

from __future__ import annotations

import re

import execsql.state as _state

# Handler imports — grouped by module for readability.
from execsql.metacommands.connect import (
    x_connect_pg,
    x_connect_user_pg,
    x_connect_ssvr,
    x_connect_user_ssvr,
    x_connect_mysql,
    x_connect_user_mysql,
    x_connect_access,
    x_connect_fb,
    x_connect_user_fb,
    x_connect_ora,
    x_connect_user_ora,
    x_connect_duckdb,
    x_connect_sqlite,
    x_connect_dsn,
    x_use,
    x_disconnect,
    x_autocommit_on,
    x_autocommit_off,
    x_pg_vacuum,
    x_daoflushdelay,
)
from execsql.metacommands.control import (
    x_if,
    x_if_orif,
    x_if_andif,
    x_if_elseif,
    x_if_else,
    x_if_block,
    x_if_end,
    x_loop,
    x_halt,
    x_halt_msg,
    x_error_halt,
    x_metacommand_error_halt,
    x_begin_batch,
    x_end_batch,
    x_rollback,
    x_break,
    x_wait_until,
)
from execsql.metacommands.data import (
    x_sub,
    x_sub_add,
    x_sub_append,
    x_sub_empty,
    x_rm_sub,
    x_sub_local,
    x_sub_tempfile,
    x_sub_ini,
    x_sub_querystring,
    x_sub_encrypt,
    x_sub_decrypt,
    x_subdata,
    x_selectsub,
    x_prompt_selectsub,
    x_empty_strings,
    x_trim_strings,
    x_replace_newlines,
    x_empty_rows,
    x_only_strings,
    x_boolean_int,
    x_boolean_words,
    x_fold_col_hdrs,
    x_trim_col_hdrs,
    x_clean_col_hdrs,
    x_del_empty_cols,
    x_create_col_hdrs,
    x_dedup_col_hdrs,
    x_import_common_cols_only,
    x_quote_all_text,
    x_reset_counter,
    x_reset_counters,
    x_set_counter,
    x_max_int,
)
from execsql.metacommands.debug import (
    x_debug_write_metacommands,
    x_debug_commandliststack,
    x_debug_iflevels,
    x_debug_write_odbc_drivers,
    x_debug_log_subvars,
    x_debug_log_config,
    x_debug_write_subvars,
    x_debug_write_config,
)
from execsql.metacommands.io import (
    x_export,
    x_export_query,
    x_export_query_with_template,
    x_export_with_template,
    x_export_ods_multiple,
    x_export_metadata,
    x_export_metadata_table,
    x_import,
    x_import_file,
    x_import_ods,
    x_import_ods_pattern,
    x_import_xls,
    x_import_xls_pattern,
    x_import_parquet,
    x_import_feather,
    x_import_row_buffer,
    x_export_row_buffer,
    x_write,
    x_write_create_table,
    x_write_create_table_ods,
    x_write_create_table_xls,
    x_write_create_table_alias,
    x_write_prefix,
    x_write_suffix,
    x_writescript,
    x_include,
    x_copy,
    x_copy_query,
    x_zip,
    x_zip_buffer_mb,
    x_rm_file,
    x_make_export_dirs,
    x_cd,
    x_scan_lines,
    x_hdf5_text_len,
    x_serve,
)
from execsql.metacommands.prompt import (
    x_prompt,
    x_prompt_enter,
    x_prompt_entryform,
    x_prompt_pause,
    x_prompt_compare,
    x_prompt_ask_compare,
    x_prompt_ask,
    x_prompt_map,
    x_prompt_action,
    x_prompt_savefile,
    x_prompt_openfile,
    x_prompt_directory,
    x_prompt_select_rows,
    x_prompt_credentials,
    x_prompt_connect,
    x_ask,
    x_pause,
    x_msg,
    x_reset_dialog_canceled,
)
from execsql.metacommands.script_ext import (
    x_extendscript,
    x_extendscript_metacommand,
    x_extendscript_sql,
    x_executescript,
)
from execsql.metacommands.system import (
    x_system_cmd,
    x_email,
    x_timer,
    x_log,
    x_logwritemessages,
    x_log_datavars,
    x_console,
    x_consoleprogress,
    x_consolewait,
    x_consolewait_onerror,
    x_consolewait_whendone,
    x_console_hideshow,
    x_consolewidth,
    x_consoleheight,
    x_consolestatus,
    x_consolesave,
    x_cancel_halt,
    x_cancel_halt_write_clear,
    x_cancel_halt_write,
    x_cancel_halt_email_clear,
    x_cancel_halt_email,
    x_cancel_halt_exec,
    x_cancel_halt_exec_clear,
    x_error_halt_write_clear,
    x_error_halt_write,
    x_error_halt_email_clear,
    x_error_halt_email,
    x_error_halt_exec,
    x_error_halt_exec_clear,
    x_write_warnings,
    x_gui_level,
    x_execute,
)

# Regex helper functions (from utils/regex.py)
from execsql.utils.regex import (
    ins_rxs,
    ins_quoted_rx,
    ins_schema_rxs,
    ins_table_rxs,
    ins_table_list_rxs,
    ins_fn_rxs,
)


def build_dispatch_table() -> _state.MetaCommandList:
    """Construct and return the complete metacommand dispatch table."""
    mcl = _state.MetaCommandList()

    # ------------------------------------------------------------------
    # DEBUG metacommands
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(r"^\s*DEBUG\s+WRITE\s+METACOMMANDLIST\s+TO\s+", r"\s*$"),
        x_debug_write_metacommands,
    )
    mcl.add(r"^\s*DEBUG\s+WRITE\s+COMMANDLISTSTACK\s*$", x_debug_commandliststack)
    mcl.add(r"^\s*DEBUG\s+WRITE\s+IFLEVELS\s*$", x_debug_iflevels)
    mcl.add(
        ins_fn_rxs(
            r"^\s*DEBUG\s+WRITE\s+ODBC_DRIVERS(?:\s+(?P<append>APPEND\s+)?TO\s+",
            r")?\s*$",
        ),
        x_debug_write_odbc_drivers,
    )
    mcl.add(
        r"^\s*DEBUG\s+LOG(?:\s+(?P<local>LOCAL))?(?:\s+(?P<user>USER))?\s+SUBVARS\s*$",
        x_debug_log_subvars,
    )
    mcl.add(r"^\s*DEBUG\s+LOG\s+CONFIG\s*$", x_debug_log_config)
    mcl.add(
        ins_fn_rxs(
            r"^\s*DEBUG\s+WRITE(?:\s+(?P<local>LOCAL))?(?:\s+(?P<user>USER))?\s+SUBVARS"
            r"(?:\s+(?P<append>APPEND\s+)?TO\s+",
            r")?\s*$",
        ),
        x_debug_write_subvars,
    )
    mcl.add(
        ins_fn_rxs(
            r"^\s*DEBUG\s+WRITE\s+CONFIG(?:\s+(?P<append>APPEND\s+)?TO\s+",
            r")?\s*$",
        ),
        x_debug_write_config,
    )

    # ------------------------------------------------------------------
    # SERVE
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            r"^\s*SERVE\s+",
            r"\s+AS\s+(?P<format>BINARY|CSV|TXT|TEXT|ODS|JSON|HTML|PDF|ZIP)\s*$",
        ),
        x_serve,
    )

    # ------------------------------------------------------------------
    # Misc short commands
    # ------------------------------------------------------------------
    mcl.add(r"^\s*RESET\s+DIALOG_CANCELED\s*$", x_reset_dialog_canceled)
    mcl.add(r"^\s*SUB_QUERYSTRING\s+(?P<qstr>.+)\s*$", x_sub_querystring)
    mcl.add(r"^\s*BREAK\s*$", x_break)

    # ------------------------------------------------------------------
    # EXPORT QUERY (various formats)
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            r"^\s*EXPORT\s+QUERY\s+<<\s*(?P<query>.*;)\s*>>\s+(?P<tee>TEE\s+)?(?P<append>APPEND\s+)?TO\s+",
            ins_fn_rxs(
                r"(?:\s+IN\s+ZIPFILE\s+",
                r")?\s+AS\s*(?P<format>CSV|TAB|TSV|TABQ|TSVQ|UNITSEP|US|TXT|TXT-AND|PLAIN|ODS|JSON|"
                r'HTML|CGI-HTML|VALUES|LATEX|RAW|B64|FEATHER)(?:\s+DESCRIP(?:TION)?\s+"(?P<description>[^"]*)")?\s*$',
                symbolicname="zipfilename",
            ),
        ),
        x_export_query,
        "Write data from a query to a file.",
    )
    mcl.add(
        ins_fn_rxs(
            r"^\s*EXPORT\s+QUERY\s+<<\s*(?P<query>.*;)\s*>>\s+(?P<tee>TEE\s+)?(?P<append>APPEND\s+)?TO\s+",
            r"\s+AS\s*(?P<format>JSON_TS|JSON_TABLESCHEMA)(?:\s+(?P<notype>NOTYPE))?"
            r'(?:\s+DESCRIP(?:TION)?\s+"(?P<description>[^"]*)")?\s*$',
        ),
        x_export_query,
        "Write data from a query to a file.",
    )
    mcl.add(
        ins_fn_rxs(
            r"^\s*EXPORT\s+QUERY\s+<<\s*(?P<query>.*;)\s*>>\s+(?P<tee>TEE\s+)?(?P<append>APPEND\s+)?TO\s+",
            ins_fn_rxs(
                r"(?:\s+IN\s+ZIPFILE\s+",
                ins_fn_rxs(r")?\s+WITH\s+TEMPLATE\s+", r"\s*$", "template"),
                symbolicname="zipfilename",
            ),
        ),
        x_export_query_with_template,
    )

    # ------------------------------------------------------------------
    # EXPORT (table/view)
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*EXPORT\s+",
            ins_fn_rxs(
                r"\s+(?P<tee>TEE\s+)?(?P<append>APPEND\s+)?TO\s+",
                ins_fn_rxs(
                    r"(?:\s+IN\s+ZIPFILE\s+",
                    ins_fn_rxs(r")?\s+WITH\s+TEMPLATE\s+", r"\s*$", "template"),
                    symbolicname="zipfilename",
                ),
            ),
        ),
        x_export_with_template,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*EXPORT\s+",
            ins_fn_rxs(
                ins_fn_rxs(
                    r"\s+(?P<tee>TEE\s+)?(?P<append>APPEND\s+)?TO\s+",
                    r"(?:\s+IN\s+ZIPFILE\s+",
                ),
                r")?\s+AS\s+(?P<format>CSV|TAB|TSV|TABQ|TSVQ|UNITSEP|US|TXT|TXT-AND|PLAIN|JSON|XML|"
                r"VALUES|HTML|CGI-HTML|SQLITE|DUCKDB|LATEX|RAW|B64|FEATHER|HDF5)"
                r'(?:\s+DESCRIP(?:TION)?\s+"(?P<description>[^"]*)")?\s*$',
                symbolicname="zipfilename",
            ),
        ),
        x_export,
        "Write data from a table or view to a file.",
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*EXPORT\s+",
            ins_fn_rxs(
                ins_fn_rxs(
                    r"\s+(?P<tee>TEE\s+)?(?P<append>APPEND\s+)?TO\s+",
                    r"(?:\s+IN\s+ZIPFILE\s+",
                ),
                r")?\s+AS\s+(?P<format>JSON_TS|JSON_TABLESCHEMA)(?:\s+(?P<notype>NOTYPE))?"
                r'(?:\s+DESCRIP(?:TION)?\s+"(?P<description>[^"]*)")?\s*$',
                symbolicname="zipfilename",
            ),
        ),
        x_export,
        "Write data from a table or view to a file.",
    )
    mcl.add(
        ins_table_list_rxs(
            r"^\s*EXPORT\s+",
            ins_fn_rxs(
                r"\s+(?P<tee>TEE\s+)?(?P<append>APPEND\s+)?TO\s+",
                r'\s+AS\s+ODS(?:\s+DESCRIP(?:TION)?\s+"(?P<description>[^"]*)")?\s*$',
            ),
        ),
        x_export_ods_multiple,
        "Write data from tables or views to an ODS file.",
    )

    # ------------------------------------------------------------------
    # IMPORT_FILE
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*IMPORT_FILE\s+TO\s+TABLE\s+",
            ins_fn_rxs(
                r'\s+COLUMN\s+"(?P<columnname>[A-Za-z0-9_\-\: ]+)"\s+FROM\s+',
                r"\s*$",
            ),
        ),
        x_import_file,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*IMPORT_FILE\s+TO\s+TABLE\s+",
            ins_fn_rxs(
                r"\s+COLUMN\s+(?P<columnname>[A-Za-z0-9_\-\:]+)\s+FROM\s+",
                r"\s*$",
            ),
        ),
        x_import_file,
    )

    # ------------------------------------------------------------------
    # IMPORT ODS (pattern)
    # ------------------------------------------------------------------
    mcl.add(
        ins_schema_rxs(
            r"\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?TABLES\s+IN\s+(?:SCHEMA\s+)?",
            ins_fn_rxs(
                r"\s+FROM\s+",
                r"\s+SHEETS\s+MATCHING\s+(?P<patn>\S+)(?:\s+SKIP\s+(?P<skip>\d+))?\s*?",
            ),
        ),
        x_import_ods_pattern,
    )

    # ------------------------------------------------------------------
    # CD
    # ------------------------------------------------------------------
    mcl.add(r"^\s*CD\s+(?P<dir>.+)\s*$", x_cd)

    # ------------------------------------------------------------------
    # IMPORT ODS (single sheet)
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?",
            ins_fn_rxs(
                r"\s+FROM\s+",
                r'\s+SHEET\s+"(?P<sheetname>[A-Za-z0-9_\.\/\-\\ ]+)"'
                r"(?:\s+SKIP\s+(?P<skip>\d+))?\s*$",
            ),
        )
        + ins_table_rxs(
            r"^\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?",
            ins_fn_rxs(
                r"\s+FROM\s+",
                r"\s+SHEET\s+(?P<sheetname>[A-Za-z0-9_\.\/\-\\]+)"
                r"(?:\s+SKIP\s+(?P<skip>\d+))?\s*$",
            ),
        ),
        x_import_ods,
    )

    # ------------------------------------------------------------------
    # IMPORT XLS (pattern)
    # ------------------------------------------------------------------
    mcl.add(
        ins_schema_rxs(
            r"\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?TABLES\s+IN\s+(?:SCHEMA\s+)?",
            ins_fn_rxs(
                r"\s+FROM\s+EXCEL\s+",
                r"\s+SHEETS\s+MATCHING\s+(?P<patn>\S+)(?:\s+SKIP\s+(?P<skip>\d+))?"
                r"(?:\s+ENCODING\s+(?P<encoding>\w+))?\s*?",
            ),
        ),
        x_import_xls_pattern,
    )

    # ------------------------------------------------------------------
    # IMPORT XLS (single sheet)
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?",
            ins_fn_rxs(
                r"\s+FROM\s+EXCEL\s+",
                r'\s+SHEET\s+"(?P<sheetname>[A-Za-z0-9_\.\/\-\\ ]+)"'
                r"(?:\s+SKIP\s+(?P<skip>\d+))?(?:\s+ENCODING\s+(?P<encoding>\w+))?\s*$",
            ),
        )
        + ins_table_rxs(
            r"^\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?",
            ins_fn_rxs(
                r"\s+FROM\s+EXCEL\s+",
                r"\s+SHEET\s+(?P<sheetname>[A-Za-z0-9_\.\/\-\\]+)"
                r"(?:\s+SKIP\s+(?P<skip>\d+))?(?:\s+ENCODING\s+(?P<encoding>\w+))?\s*$",
            ),
        ),
        x_import_xls,
    )

    # ------------------------------------------------------------------
    # IMPORT PARQUET / FEATHER
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?",
            ins_fn_rxs(r"\s+FROM\s+PARQUET\s+", r"\s*$"),
        ),
        x_import_parquet,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?",
            ins_fn_rxs(r"\s+FROM\s+FEATHER\s+", r"\s*$"),
        ),
        x_import_feather,
    )

    # ------------------------------------------------------------------
    # PROMPT ACTION
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+ACTION\s+",
            ins_table_rxs(
                r'\s+MESSAGE\s+"(?P<message>(.|\n)*)"(?:\s+DISPLAY\s+',
                r")?(?:\s+COMPACT\s+(?P<compact>\d+))?(?:\s+(?P<continue>CONTINUE))?"
                r"(?:\s+HELP\s+(?P<help>[^\s]+))?\s*$",
                suffix="disp",
            ),
        ),
        x_prompt_action,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+ACTION\s+",
            ins_table_rxs(
                r'\s+MESSAGE\s+"(?P<message>(.|\n)*)"(?:\s+DISPLAY\s+',
                r")?(?:\s+COMPACT\s+(?P<compact>\d+))?(?:\s+(?P<continue>CONTINUE))?"
                r'(?:\s+HELP\s+"(?P<help>[^"]+)")?\s*$',
                suffix="disp",
            ),
        ),
        x_prompt_action,
    )

    # ------------------------------------------------------------------
    # PROMPT SAVEFILE / OPENFILE / DIRECTORY
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            r"^\s*PROMPT\s+SAVEFILE\s+SUB\s+(?P<match>~?\w+)(?:\s+(?P<fn_match>~?\w+))?"
            r"(?:\s+(?P<path_match>~?\w+))?(?:\s+(?P<ext_match>~?\w+))?"
            r"(?:\s+(?P<fnbase_match>~?\w+))?(?:\s+FROM\s+",
            r")?\s*$",
            symbolicname="startdir",
        ),
        x_prompt_savefile,
    )
    mcl.add(
        ins_fn_rxs(
            r"^\s*PROMPT\s+OPENFILE\s+SUB\s+(?P<match>~?\w+)(?:\s+(?P<fn_match>~?\w+))?"
            r"(?:\s+(?P<path_match>~?\w+))?(?:\s+(?P<ext_match>~?\w+))?"
            r"(?:\s+(?P<fnbase_match>~?\w+))?(?:\s+FROM\s+",
            r")?\s*$",
            symbolicname="startdir",
        ),
        x_prompt_openfile,
    )
    mcl.add(
        ins_fn_rxs(
            r"^\s*PROMPT\s+DIRECTORY\s+SUB\s+(?P<match>~?\w+)(?:\s+(?P<fullpath>FULLPATH))?"
            r"(?:\s+FROM\s+",
            r")?\s*$",
            symbolicname="startdir",
        ),
        x_prompt_directory,
    )

    # ------------------------------------------------------------------
    # PROMPT SELECT_ROWS
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+SELECT_ROWS\s+FROM\s+",
            ins_table_rxs(
                r"(?:\s+IN\s+(?P<alias1>\w+))?\s+INTO\s+",
                r'(?:\s+IN\s+(?P<alias2>\w+))?(?:\s+HELP\s+(?P<help>[^\s]+))?\s+MESSAGE\s+"(?P<msg>(.|\n)*)"\s*$',
                suffix="2",
            ),
            suffix="1",
        ),
        x_prompt_select_rows,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+SELECT_ROWS\s+FROM\s+",
            ins_table_rxs(
                r"(?:\s+IN\s+(?P<alias1>\w+))?\s+INTO\s+",
                r'(?:\s+IN\s+(?P<alias2>\w+))?(?:\s+HELP\s+"(?P<help>[^"]+)")?\s+MESSAGE\s+"(?P<msg>(.|\n)*)"\s*$',
                suffix="2",
            ),
            suffix="1",
        ),
        x_prompt_select_rows,
    )

    # ------------------------------------------------------------------
    # SUB_LOCAL / SUB_ENCRYPT / SUB_DECRYPT
    # ------------------------------------------------------------------
    mcl.add(
        r"^\s*SUB_LOCAL\s+(?P<match>~?\w+)\s+(?P<repl>.+)$",
        x_sub_local,
        "SUB",
        "Define a local variable consisting of a string to match and a replacement for it.",
    )
    mcl.add(r"^\s*SUB_ENCRYPT\s+(?P<match>[+~]?\w+)\s+(?P<plaintext>.+)\s*$", x_sub_encrypt)
    mcl.add(r"^\s*SUB_DECRYPT\s+(?P<match>[+~]?\w+)\s+(?P<crypttext>.+)\s*$", x_sub_decrypt)

    # ------------------------------------------------------------------
    # WAIT_UNTIL
    # ------------------------------------------------------------------
    mcl.add(
        r"^\s*WAIT_UNTIL\s+(?P<condition>.+)\s+(?P<end>HALT|CONTINUE)\s+AFTER\s+(?P<seconds>\d+)\s+SECONDS\s*$",
        x_wait_until,
    )

    # ------------------------------------------------------------------
    # CONFIG * (various settings)
    # ------------------------------------------------------------------
    mcl.add(
        r"^\s*CONFIG\s+LOG_WRITE_MESSAGES\s+(?P<setting>Yes|No|On|Off|True|False|0|1)\s*$",
        x_logwritemessages,
    )
    mcl.add(
        r"^\s*CONFIG\s+QUOTE_ALL_TEXT\s+(?P<setting>Yes|No|On|Off|True|False|0|1)\s*$",
        x_quote_all_text,
    )
    mcl.add(r"^\s*CONFIG\s+IMPORT_ROW_BUFFER\s+(?P<rows>[1-9][0-9]*)\s*$", x_import_row_buffer)
    mcl.add(r"^\s*CONFIG\s+EXPORT_ROW_BUFFER\s+(?P<rows>[1-9][0-9]*)\s*$", x_export_row_buffer)
    mcl.add(r"^\s*CONFIG\s+ZIP_BUFFER_MB\s+(?P<size>[1-9][0-9]*)\s*$", x_zip_buffer_mb)
    mcl.add(
        r"^\s*CONFIG\s+EMPTY_STRINGS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_empty_strings,
    )
    mcl.add(
        r"^\s*CONFIG\s+TRIM_STRINGS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_trim_strings,
    )
    mcl.add(
        r"^\s*CONFIG\s+REPLACE_NEWLINES\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_replace_newlines,
    )
    mcl.add(
        r"^\s*CONFIG\s+EMPTY_ROWS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_empty_rows,
    )
    mcl.add(
        r"^\s*CONFIG\s+ONLY_STRINGS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_only_strings,
    )
    mcl.add(
        r"^\s*(?:CONFIG\s+)?BOOLEAN_INT\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_boolean_int,
    )
    mcl.add(
        r"^\s*CONFIG\s+BOOLEAN_WORDS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_boolean_words,
    )
    mcl.add(
        r"^\s*CONFIG\s+FOLD_COLUMN_HEADERS\s+(?P<foldspec>no|lower|upper)\s*$",
        x_fold_col_hdrs,
    )
    mcl.add(
        r"^\s*CONFIG\s+TRIM_COLUMN_HEADERS\s+(?P<which>NONE|BOTH|LEFT|RIGHT)\s*$",
        x_trim_col_hdrs,
    )
    mcl.add(
        r"^\s*CONFIG\s+CLEAN_COLUMN_HEADERS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_clean_col_hdrs,
    )
    mcl.add(
        r"^\s*CONFIG\s+DELETE_EMPTY_COLUMNS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_del_empty_cols,
    )
    mcl.add(
        r"^\s*CONFIG\s+CREATE_COLUMN_HEADERS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_create_col_hdrs,
    )
    mcl.add(
        r"^\s*CONFIG\s+DEDUP_COLUMN_HEADERS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_dedup_col_hdrs,
    )
    mcl.add(
        r"^\s*CONFIG\s+IMPORT_ONLY_COMMON_COLUMNS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_import_common_cols_only,
    )
    mcl.add(
        r"^\s*CONFIG\s+MAKE_EXPORT_DIRS\s+(?P<setting>Yes|No|On|Off|True|False|0|1)\s*$",
        x_make_export_dirs,
    )
    mcl.add(
        r"^\s*CONFIG\s+WRITE_WARNINGS\s+(?P<yesno>YES|NO|ON|OFF|TRUE|FALSE|0|1)\s*$",
        x_write_warnings,
    )
    mcl.add(r"^\s*CONFIG\s+GUI_LEVEL\s+(?P<level>[0-2])\s*$", x_gui_level)
    mcl.add(r"^\s*CONFIG\s+WRITE_PREFIX\s+(?P<prefix>.*)\s*$", x_write_prefix)
    mcl.add(r"^\s*CONFIG\s+WRITE_SUFFIX\s+(?P<suffix>.*)\s*$", x_write_suffix)
    mcl.add(r"^\s*CONFIG\s+SCAN_LINES\s+(?P<scanlines>[0-9]+)\s*$", x_scan_lines)
    mcl.add(r"^\s*CONFIG\s+HDF5_TEXT_LEN\s+(?P<textlen>[0-9]+)\s*$", x_hdf5_text_len)
    mcl.add(
        r"^\s*CONFIG\s+LOG_DATAVARS\s+(?P<setting>Yes|No|On|Off|True|False|0|1)\s*$",
        x_log_datavars,
    )
    mcl.add(
        r"^\s*CONFIG\s+DAO_FLUSH_DELAY_SECS\s+(?P<secs>[0-9]*\.?[0-9]+)\s*$",
        x_daoflushdelay,
    )
    mcl.add(
        r"^\s*CONFIG\s+CONSOLE\s+WAIT_WHEN_ERROR\s+(?P<onoff>ON|OFF|YES|NO|TRUE|FALSE|0|1)\s*$",
        x_consolewait_onerror,
    )
    mcl.add(
        r"^\s*CONFIG\s+CONSOLE\s+WAIT_WHEN_DONE\s+(?P<onoff>ON|OFF|YES|NO|TRUE|FALSE|0|1)\s*$",
        x_consolewait_whendone,
    )

    # ------------------------------------------------------------------
    # CONNECT — MS Access
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            r"^CONNECT\s+TO\s+ACCESS\s*\(\s*FILE\s*=\s*",
            r"(?:\s*,\s*NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?"
            r"(?:\s*,\s+PASSWORD\s*=\s*(?P<password>[^\s]+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_access,
    )

    # ------------------------------------------------------------------
    # CONNECT — Firebird
    # ------------------------------------------------------------------
    mcl.add(
        (
            r"^CONNECT\s+USER\s+TO\s+FIREBIRD\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r'^CONNECT\s+USER\s+TO\s+FIREBIRD\s*\(\s*SERVER\s*=\s*"(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)"\s*,\s*'
            r'DB\s*=\s*"(?P<db_name>[A-Z][A-Z0-9_\- ]*)"(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?'
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_user_fb,
    )
    mcl.add(
        r"^CONNECT\s+TO\s+FIREBIRD\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
        r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*USER\s*=\s*(?P<user>[A-Z][A-Z0-9_@\-\.]*)\s*,\s*"
        r"NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
        r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        x_connect_fb,
    )

    # ------------------------------------------------------------------
    # CONNECT — Oracle
    # ------------------------------------------------------------------
    mcl.add(
        (
            r"^CONNECT\s+USER\s+TO\s+ORACLE\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r'^CONNECT\s+USER\s+TO\s+ORACLE\s*\(\s*SERVER\s*=\s*"(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)"\s*,\s*'
            r'DB\s*=\s*"(?P<db_name>[A-Z][A-Z0-9_\- ]*)"(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?'
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_user_ora,
    )
    mcl.add(
        (
            r"^CONNECT\s+TO\s+ORACLE\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*USER\s*=\s*(?P<user>[A-Z][A-Z0-9_\-@\.]*)\s*,\s*"
            r"NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s+PASSWORD\s*=\s*(?P<password>[^\s\)]+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r'^CONNECT\s+TO\s+ORACLE\s*\(\s*SERVER\s*=\s*"(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)"\s*,\s*'
            r'DB\s*=\s*"(?P<db_name>[A-Z][A-Z0-9_\-]*)"(?:\s*,\s*USER\s*=\s*"(?P<user>[A-Z][A-Z0-9_\-@\.]*)"\s*,\s*'
            r"NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r'(?:\s*,\s+PASSWORD\s*=\s*"(?P<password>[^\s\)]+)")?'
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_ora,
    )

    # ------------------------------------------------------------------
    # RUN / EXECUTE
    # ------------------------------------------------------------------
    mcl.add(
        r'^\s*EXEC(?:UTE)?\s+SCRIPT(?:\s+(?P<exists>IF\s+EXISTS))?\s+(?P<script_id>\w+)(?:(?:\s+WITH)?(?:\s+ARG(?:UMENT)?S?)?\s*\(\s*(?P<argexp>#?\w+\s*=\s*(?:(?:[^"\'\[][^,\)]*)|(?:"[^"]*")|(?:\'[^\']*\')|(?:\[[^\]]*\]))(?:\s*,\s*#?\w+\s*=\s*(?:(?:[^"\'\[][^,\)]*)|(?:"[^"]*")|(?:\'[^\']*\')|(?:\[[^\]]*\])))*)\s*\))?(?:\s+(?P<looptype>WHILE|UNTIL)\s*\(\s*(?P<loopcond>.+)\s*\))?\s*$',
        x_executescript,
    )
    mcl.add(
        r'^\s*RUN\s+SCRIPT(?:\s+(?P<exists>IF\s+EXISTS))?\s+(?P<script_id>\w+)(?:(?:\s+WITH)?(?:\s+ARG(?:UMENT)?S?)?\s*\(\s*(?P<argexp>#?\w+\s*=\s*(?:(?:[^"\'\[][^,\)]*)|(?:"[^"]*")|(?:\'[^\']*\')|(?:\[[^\]]*\]))(?:\s*,\s*#?\w+\s*=\s*(?:(?:[^"\'\[][^,\)]*)|(?:"[^"]*")|(?:\'[^\']*\')|(?:\[[^\]]*\])))*)\s*\))?(?:\s+(?P<looptype>WHILE|UNTIL)\s*\(\s*(?P<loopcond>.+)\s*\))?\s*$',
        x_executescript,
    )
    mcl.add(
        r"^\s*(?P<cmd>RUN|EXECUTE)\s+(?P<queryname>\#?\w+)\s*$",
        x_execute,
        "RUN|EXECUTE",
        "Run a database function, view, or action query (DBMS-dependent)",
    )

    # ------------------------------------------------------------------
    # ON ERROR_HALT / ON CANCEL_HALT
    # ------------------------------------------------------------------
    mcl.add(r"^\s*ON\s+ERROR_HALT\s+WRITE\s+CLEAR\s*$", x_error_halt_write_clear)
    mcl.add(
        ins_fn_rxs(
            r'^\s*ON\s+ERROR_HALT\s+WRITE\s+"(?P<text>([^"]|\n)*)"(?:(?:\s+(?P<tee>TEE))?\s+TO\s+',
            r")?\s*$",
        ),
        x_error_halt_write,
    )
    mcl.add(r"^\s*ON\s+ERROR_HALT\s+EMAIL\s+CLEAR\s*$", x_error_halt_email_clear)
    mcl.add(
        ins_fn_rxs(
            ins_fn_rxs(
                r"^\s*ON\s+ERROR_HALT\s+EMAIL\s+"
                r"FROM\s+(?P<from>[A-Za-z0-9_\-\.!#$%&\'*+/=?^`{|}~]+@[A-Za-z0-9]+(-[A-Za-z0-9]+)*(\.[A-Za-z0-9]+)*)\s+"
                r"TO\s+(?P<to>[A-Za-z0-9_\-\.!#$%&\'*+/=?^`{|}~]+@[A-Za-z0-9]+(-[A-Za-z0-9]+)*(\.[A-Za-z0-9]+)*"
                r"([;,]\s*[A-Za-z0-9\-\.!#$%&\'*+/=?^`{|}~]+@[A-Za-z0-9]+(-[A-Za-z0-9]+)*(\.[A-Za-z0-9]+)*)*)\s+"
                r'SUBJECT "(?P<subject>[^"]+)"\s+'
                r'MESSAGE\s+"(?P<msg>[^"]*)"'
                r"(\s+MESSAGE_FILE\s+",
                r")?(\s+ATTACH(MEANT)?_FILE\s+",
                "msg_file",
            ),
            r")?\s*$",
            "att_file",
        ),
        x_error_halt_email,
    )
    mcl.add(r"^\s*ON\s+ERROR_HALT\s+EXEC\s+CLEAR\s*$", x_error_halt_exec_clear)
    mcl.add(r"^\s*ON\s+CANCEL_HALT\s+WRITE\s+CLEAR\s*$", x_cancel_halt_write_clear)
    mcl.add(
        ins_fn_rxs(
            r'^\s*ON\s+CANCEL_HALT\s+WRITE\s+"(?P<text>([^"]|\n)*)"(?:(?:\s+(?P<tee>TEE))?\s+TO\s+',
            r")?\s*$",
        ),
        x_cancel_halt_write,
    )
    mcl.add(r"^\s*ON\s+CANCEL_HALT\s+EMAIL\s+CLEAR\s*$", x_cancel_halt_email_clear)
    mcl.add(
        ins_fn_rxs(
            ins_fn_rxs(
                r"^\s*ON\s+CANCEL_HALT\s+EMAIL\s+"
                r"FROM\s+(?P<from>[A-Za-z0-9_\-\.!#$%&\'*+/=?^`{|}~]+@[A-Za-z0-9]+(-[A-Za-z0-9]+)*(\.[A-Za-z0-9]+)*)\s+"
                r"TO\s+(?P<to>[A-Za-z0-9_\-\.!#$%&\'*+/=?^`{|}~]+@[A-Za-z0-9]+(-[A-Za-z0-9]+)*(\.[A-Za-z0-9]+)*"
                r"([;,]\s*[A-Za-z0-9\-\.!#$%&\'*+/=?^`{|}~]+@[A-Za-z0-9]+(-[A-Za-z0-9]+)*(\.[A-Za-z0-9]+)*)*)\s+"
                r'SUBJECT "(?P<subject>[^"]+)"\s+'
                r'MESSAGE\s+"(?P<msg>[^"]*)"'
                r"(\s+MESSAGE_FILE\s+",
                r")?(\s+ATTACH(MEANT)?_FILE\s+",
                "msg_file",
            ),
            r")?\s*$",
            "att_file",
        ),
        x_cancel_halt_email,
    )
    mcl.add(r"^\s*ON\s+CANCEL_HALT\s+EXEC\s+CLEAR\s*$", x_cancel_halt_exec_clear)

    # ------------------------------------------------------------------
    # SUB_TEMPFILE
    # ------------------------------------------------------------------
    mcl.add(r"^\s*SUB_TEMPFILE\s+(?P<match>[+~]?\w+)\s*$", x_sub_tempfile)

    # ------------------------------------------------------------------
    # WRITE CREATE_TABLE (ODS / XLS / CSV / alias)
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*WRITE\s+CREATE_TABLE\s+",
            ins_fn_rxs(
                r"\s+FROM\s+",
                ins_rxs(
                    (
                        r'"(?P<sheet>[A-Za-z0-9_\.\/\-\\ ]+)"',
                        r"(?P<sheet>[A-Za-z0-9_\.\/\-\\]+)",
                    ),
                    r"\s+SHEET\s+",
                    ins_fn_rxs(
                        r'(?:\s+SKIP\s+(?P<skip>\d+))?(?:\s+COMMENT\s+"(?P<comment>[^"]+)")?'
                        r"(?:\s+TO\s+",
                        r")?\s*$",
                        "outfile",
                    ),
                ),
            ),
        ),
        x_write_create_table_ods,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*WRITE\s+CREATE_TABLE\s+",
            ins_fn_rxs(
                r"\s+FROM\s+EXCEL\s+",
                ins_rxs(
                    (
                        r'"(?P<sheet>[A-Za-z0-9_\.\/\-\\ ]+)"',
                        r"(?P<sheet>[A-Za-z0-9_\.\/\-\\]+)",
                    ),
                    r"\s+SHEET\s+",
                    ins_fn_rxs(
                        r"(?:\s+SKIP\s+(?P<skip>\d+))?(?:\s+ENCODING\s+(?P<encoding>\w+))?"
                        r'(?:\s+COMMENT\s+"(?P<comment>[^"]+)")?(?:\s+TO\s+',
                        r")?\s*$",
                        "outfile",
                    ),
                ),
            ),
        ),
        x_write_create_table_xls,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*WRITE\s+CREATE_TABLE\s+",
            ins_table_rxs(
                r"\s+FROM\s+",
                ins_fn_rxs(
                    r'\s+IN\s+(?P<alias>[A-Z][A-Z0-9_]*)(?:\s+COMMENT\s+"(?P<comment>[^"]+)")?(?:\s+TO\s+',
                    r")?\s*$",
                ),
                "1",
            ),
        ),
        x_write_create_table_alias,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*WRITE\s+CREATE_TABLE\s+",
            ins_fn_rxs(
                r"\s+FROM\s+",
                ins_fn_rxs(
                    r'(?:\s+WITH\s+QUOTE\s+(?P<quotechar>NONE|\'|")\s+DELIMITER\s+(?P<delimchar>TAB|UNITSEP|US|,|;|\|))?'
                    r"(?:\s+ENCODING\s+(?P<encoding>\w+))?(?:\s+SKIP\s+(?P<skip>\d+))?"
                    r'(?:\s+COMMENT\s+"(?P<comment>[^"]+)")?(?:\s+TO\s+',
                    r")?\s*$",
                    "outfile",
                ),
            ),
        ),
        x_write_create_table,
    )

    # ------------------------------------------------------------------
    # RESET / SET COUNTER
    # ------------------------------------------------------------------
    mcl.add(r"^\s*RESET\s+COUNTER\s+(?P<counter_no>\d+)\s*$", x_reset_counter)
    mcl.add(r"^\s*RESET\s+COUNTERS\s*$", x_reset_counters)
    mcl.add(
        r"^\s*SET\s+COUNTER\s+(?P<counter_no>\d+)\s+TO\s+(?P<value>[0-9+\-*/() ]+)\s*$",
        x_set_counter,
    )

    # ------------------------------------------------------------------
    # PROMPT CREDENTIALS / CONNECT
    # ------------------------------------------------------------------
    mcl.add(
        (
            r'^\s*PROMPT(?:\s+MESSAGE\s+"(?P<message>(.|\n)*)")?\s+CREDENTIALS\s+(?P<user>\w+)\s+(?P<pw>\w+)\s*$',
            r'^\s*PROMPT(?:\s+"(?P<message>(.|\n)*)")?\s+CREDENTIALS\s+(?P<user>\w+)\s+(?P<pw>\w+)\s*$',
        ),
        x_prompt_credentials,
    )
    mcl.add(
        (
            r'^\s*PROMPT(?:\s+MESSAGE\s+"(?P<message>(.|\n)*)")?\s+CONNECT\s+AS\s+(?P<alias>\w+)(?:\s+HELP\s+(?P<help>[^\s]+))?\s*$',
            r'^\s*PROMPT(?:\s+MESSAGE\s+"(?P<message>(.|\n)*)")?\s+CONNECT\s+AS\s+(?P<alias>\w+)(?:\s+HELP\s+"(?P<help>[^"]+)")?\s*$',
            r'^\s*CONNECT\s+PROMPT(?:\s+MESSAGE\s+"(?P<message>(.|\n)*)")?\s+AS\s+(?P<alias>\w+)(?:\s+HELP\s+(?P<help>[^\s]+))?\s*$',
            r'^\s*CONNECT\s+PROMPT(?:\s+MESSAGE\s+"(?P<message>(.|\n)*)")?\s+AS\s+(?P<alias>\w+)(?:\s+HELP\s+"(?P<help>[^"]+)")?\s*$',
            r'^\s*PROMPT(?:\s+"(?P<message>(.|\n)*)")?\s+CONNECT\s+AS\s+(?P<alias>\w+)(?:\s+HELP\s+(?P<help>[^\s]+))?\s*$',
            r'^\s*PROMPT(?:\s+"(?P<message>(.|\n)*)")?\s+CONNECT\s+AS\s+(?P<alias>\w+)(?:\s+HELP\s+"(?P<help>[^"]+)")?\s*$',
            r'^\s*CONNECT\s+PROMPT(?:\s+"(?P<message>(.|\n)*)")?\s+AS\s+(?P<alias>\w+)(?:\s+HELP\s+(?P<help>[^\s]+))?\s*$',
            r'^\s*CONNECT\s+PROMPT(?:\s+"(?P<message>(.|\n)*)")?\s+AS\s+(?P<alias>\w+)(?:\s+HELP\s+"(?P<help>[^"]+)")?\s*$',
        ),
        x_prompt_connect,
    )

    # ------------------------------------------------------------------
    # TIMER / LOG / SUB_INI
    # ------------------------------------------------------------------
    mcl.add(r"^\s*TIMER\s+(?P<onoff>ON|OFF)\s*$", x_timer)
    mcl.add(r'^\s*LOG\s+"(?P<message>.+)"\s*$', x_log)
    mcl.add(
        ins_fn_rxs(r"^\s*SUB_INI\s+(?:FILE\s+)?", r"(?:\s+SECTION)?\s+(?P<section>\w+)\s*$"),
        x_sub_ini,
    )

    # ------------------------------------------------------------------
    # CONSOLE
    # ------------------------------------------------------------------
    mcl.add(r"^\s*CONSOLE\s+(?P<hideshow>HIDE|SHOW)\s*$", x_console_hideshow)
    mcl.add(r"^\s*CONSOLE\s+WIDTH\s+(?P<width>\d+)\s*$", x_consolewidth)
    mcl.add(r"^\s*CONSOLE\s+HEIGHT\s+(?P<height>\d+)\s*$", x_consoleheight)
    mcl.add(r'^\s*CONSOLE\s+STATUS\s+"(?P<message>.*)"\s*$', x_consolestatus)
    mcl.add(
        ins_fn_rxs(r"^\s*CONSOLE\s+SAVE(?:\s+(?P<append>APPEND))?\s+TO\s+", r"\s*$"),
        x_consolesave,
    )
    mcl.add(r'^\s*CONSOLE\s+WAIT(?:\s+"(?P<message>.+)")?\s*$', x_consolewait)
    mcl.add(
        r"^\s*CONSOLE\s+PROGRESS\s+(?P<num>[0-9]+(?:\.[0-9]+)?)(?:\s*/\s*(?P<total>[0-9]+(?:\.[0-9]+)?))?\s*$",
        x_consoleprogress,
    )
    mcl.add(r"^\s*CONSOLE\s+(?P<onoff>ON|OFF)\s*$", x_console)

    # ------------------------------------------------------------------
    # DISCONNECT / AUTOCOMMIT
    # ------------------------------------------------------------------
    mcl.add(r"^\s*DISCONNECT(?:(?:\s+FROM)?\s+(?P<alias>[A-Z][A-Z0-9_]*))?\s*$", x_disconnect)
    mcl.add(r"^\s*AUTOCOMMIT\s+OFF\s*$", x_autocommit_off)
    mcl.add(r"^\s*AUTOCOMMIT\s+ON(?:\s+WITH\s+(?P<action>COMMIT|ROLLBACK))?\s*$", x_autocommit_on)

    # ------------------------------------------------------------------
    # WRITE SCRIPT / MAX_INT / PG_VACUUM
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            r"^\s*(?:DEBUG\s+)?WRITE\s+SCRIPT\s+(?P<script_id>\w+)(?:\s+(?P<append>APPEND\s+)?TO\s+",
            r")?\s*$",
        ),
        x_writescript,
    )
    mcl.add(r"^\s*MAX_INT\s+(?P<maxint>[0-9]+)\s*$", x_max_int)
    mcl.add(r"^\s*PG_VACUUM(?P<vacuum_args>.*)\s*$", x_pg_vacuum)

    # ------------------------------------------------------------------
    # ZIP
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            r"^\s*ZIP\s+(?P<filename>[^ ]+)(?:\s+(?P<append>APPEND))?\s+TO\s+ZIPFILE\s+",
            r"\s*$",
            symbolicname="zipfilename",
        ),
        x_zip,
    )
    mcl.add(
        ins_fn_rxs(
            r'^\s*ZIP\s+"(?P<filename>[^"]+)"(?:\s+(?P<append>APPEND))?\s+TO\s+ZIPFILE\s+',
            r"\s*$",
            symbolicname="zipfilename",
        ),
        x_zip,
    )

    # ------------------------------------------------------------------
    # HALT (various forms)
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            r'^\s*HALT\s*(?:\s+MESSAGE)?(?:\s+"(?P<errmsg>.+)"(?:\s+(?P<tee>TEE\s+TO\s+',
            r"))?)?(?:\s+EXIT_STATUS\s+(?P<errorlevel>\d+))?\s*$",
        ),
        x_halt,
    )
    for errmsg_delim in (r"\[", r"\#", r"\`", r"\'", r"\~", r'"'):
        # Use the same open/close bracket pair for the errmsg capture
        open_c = errmsg_delim if not errmsg_delim.startswith("\\") else errmsg_delim[1:]
        close_c = "]" if open_c == "[" else open_c
        mcl.add(
            ins_table_rxs(
                ins_fn_rxs(
                    rf"^\s*HALT(?:\s+MESSAGE)?\s+{errmsg_delim}(?P<errmsg>(.|\n)*){re.escape(close_c)}"
                    r"(?:\s+(?P<tee>TEE\s+TO\s+",
                    r"))?(?:\s+DISPLAY\s+",
                ),
                r")?(?:\s+EXIT_STATUS\s+(?P<errorlevel>\d+))?\s*$",
            ),
            x_halt_msg,
        )

    # ------------------------------------------------------------------
    # BEGIN / END BATCH / ROLLBACK
    # ------------------------------------------------------------------
    mcl.add(r"^\s*BEGIN\s+BATCH\s*$", x_begin_batch)
    mcl.add(r"^\s*END\s+BATCH\s*$", x_end_batch, "END BATCH", run_in_batch=True)
    mcl.add(r"^\s*ROLLBACK(:?\s+BATCH)?\s*$", x_rollback, "ROLLBACK BATCH", run_in_batch=True)

    # ------------------------------------------------------------------
    # ERROR_HALT / METACOMMAND_ERROR_HALT / CANCEL_HALT
    # ------------------------------------------------------------------
    mcl.add(r"\s*ERROR_HALT\s+(?P<onoff>ON|OFF|YES|NO|TRUE|FALSE)\s*$", x_error_halt)
    mcl.add(
        r"\s*METACOMMAND_ERROR_HALT\s+(?P<onoff>ON|OFF|YES|NO|TRUE|FALSE)\s*$",
        x_metacommand_error_halt,
        set_error_flag=False,
    )
    mcl.add(r"^\s*CANCEL_HALT\s+(?P<onoff>ON|OFF|YES|NO|TRUE|FALSE)\s*$", x_cancel_halt)

    # ------------------------------------------------------------------
    # LOOP
    # ------------------------------------------------------------------
    mcl.add(r"^\s*LOOP\s+(?P<looptype>WHILE|UNTIL)\s*\(\s*(?P<loopcond>.+)\s*\)\s*$", x_loop)

    # ------------------------------------------------------------------
    # PAUSE
    # ------------------------------------------------------------------
    mcl.add(
        (
            r'^\s*PAUSE\s+"(?P<text>.+)"(?:\s+(?P<action>HALT|CONTINUE)\s+AFTER\s+(?P<countdown>\d+(?:\.\d*)?)\s+(?P<timeunit>SECONDS|MINUTES))?\s*$',
            r"^\s*PAUSE\s+'(?P<text>.+)'(?:\s+(?P<action>HALT|CONTINUE)\s+AFTER\s+(?P<countdown>\d+(?:\.\d*)?)\s+(?P<timeunit>SECONDS|MINUTES))?\s*$",
            r"^\s*PAUSE\s+\[(?P<text>.+)\](?:\s+(?P<action>HALT|CONTINUE)\s+AFTER\s+(?P<countdown>\d+(?:\.\d*)?)\s+(?P<timeunit>SECONDS|MINUTES))?\s*$",
        ),
        x_pause,
    )

    # ------------------------------------------------------------------
    # PROMPT ENTER_SUB
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r'^\s*PROMPT\s+ENTER_SUB\s+(?P<match_str>~?\w+)\s+(?:(?P<password>PASSWORD)\s+)?MESSAGE\s+"(?P<message>([^"]|\n)*)"(?:\s+DISPLAY\s+',
            r")?(?:\s+TYPE\s+(?P<type>INT|FLOAT|BOOL|IDENT))?(?:\s+(?P<case>LCASE|UCASE))?"
            r'(?:\s+INITIALLY\s+"(?P<initial>[^"]+)")?(?:\s+HELP\s+(?P<help>[^\s]+))?\s*$',
        ),
        x_prompt_enter,
    )
    mcl.add(
        ins_table_rxs(
            r'^\s*PROMPT\s+ENTER_SUB\s+(?P<match_str>~?\w+)\s+(?:(?P<password>PASSWORD)\s+)?MESSAGE\s+"(?P<message>([^"]|\n)*)"(?:\s+DISPLAY\s+',
            r")?(?:\s+TYPE\s+(?P<type>INT|FLOAT|BOOL|IDENT))?(?:\s+(?P<case>LCASE|UCASE))?"
            r'(?:\s+INITIALLY\s+"(?P<initial>[^"]+)")?(?:\s+HELP\s+"(?P<help>[^+]+)")?\s*$',
        ),
        x_prompt_enter,
    )

    # ------------------------------------------------------------------
    # PROMPT ENTRY_FORM
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+ENTRY_FORM\s+",
            ins_table_rxs(
                r'(?:\s+HELP\s+(?P<help>[^\s]+))?\s+MESSAGE\s+"(?P<message>(.|\n)*)"(?:\s+DISPLAY\s+',
                r")?\s*$",
                suffix="disp",
            ),
        ),
        x_prompt_entryform,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+ENTRY_FORM\s+",
            ins_table_rxs(
                r'(?:\s+HELP\s+"(?P<help>[^"]+)")?\s+MESSAGE\s+"(?P<message>(.|\n)*)"(?:\s+DISPLAY\s+',
                r")?\s*$",
                suffix="disp",
            ),
        ),
        x_prompt_entryform,
    )

    # ------------------------------------------------------------------
    # PROMPT SELECT_SUB
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+SELECT_SUB\s+",
            r'\s+MESSAGE\s+"(?P<msg>(.|\n)*)"(?:\s+(?P<cont>CONTINUE))?(?:\s+HELP\s(?P<help>[^\s]+))?\s*$',
        ),
        x_prompt_selectsub,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+SELECT_SUB\s+",
            r'\s+MESSAGE\s+"(?P<msg>(.|\n)*)"(?:\s+(?P<cont>CONTINUE))?(?:\s+HELP\s"(?P<help>[^"]+)")?\s*$',
        ),
        x_prompt_selectsub,
    )

    # ------------------------------------------------------------------
    # PROMPT PAUSE
    # ------------------------------------------------------------------
    mcl.add(
        (
            r'^\s*PROMPT\s+PAUSE\s+"(?P<text>.+)"(?:\s+(?P<action>HALT|CONTINUE)\s+AFTER\s+(?P<countdown>\d+(?:\.\d*)?)\s+(?P<timeunit>SECONDS|MINUTES))?\s*$',
            r"^\s*PROMPT\s+PAUSE\s+'(?P<text>.+)'(?:\s+(?P<action>HALT|CONTINUE)\s+AFTER\s+(?P<countdown>\d+(?:\.\d*)?)\s+(?P<timeunit>SECONDS|MINUTES))?\s*$",
            r"^\s*PROMPT\s+PAUSE\s+\[(?P<text>.+)\](?:\s+(?P<action>HALT|CONTINUE)\s+AFTER\s+(?P<countdown>\d+(?:\.\d*)?)\s+(?P<timeunit>SECONDS|MINUTES))?\s*$",
        ),
        x_prompt_pause,
    )

    # ------------------------------------------------------------------
    # ASK
    # ------------------------------------------------------------------
    mcl.add(
        (
            r'^\s*ASK\s+"(?P<question>.+)"\s+SUB\s+(?P<match>~?\w+)\s*$',
            r"^\s*ASK\s+'(?P<question>.+)'\s+SUB\s+(?P<match>~?\w+)\s*$",
            r"^\s*ASK\s+\[(?P<question>.+)\]\s+SUB\s+(?P<match>~?\w+)\s*$",
        ),
        x_ask,
    )

    # ------------------------------------------------------------------
    # PROMPT COMPARE / PROMPT ASK COMPARE
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+COMPARE\s+",
            ins_table_rxs(
                r"(?:\s+IN\s+(?P<alias1>\w+))?\s+(?P<orient>AND|BESIDE)\s+",
                r'(?:\s+IN\s+(?P<alias2>\w+))?\s+(?:PK|KEY)\s*\((?P<pks>(("[A-Z_0-9]+")|[A-Z_0-9]+)'
                r'(\s*,\s*(("[A-Z_0-9]+")|[A-Z_0-9]+))*)\)(?:\s+HELP\s+(?P<help>[^\s]+))?\s+MESSAGE\s+"(?P<msg>(.|\n)*)"\s*$',
                suffix="2",
            ),
            suffix="1",
        ),
        x_prompt_compare,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+COMPARE\s+",
            ins_table_rxs(
                r"(?:\s+IN\s+(?P<alias1>\w+))?\s+(?P<orient>AND|BESIDE)\s+",
                r'(?:\s+IN\s+(?P<alias2>\w+))?\s+(?:PK|KEY)\s*\((?P<pks>(("[A-Z_0-9]+")|[A-Z_0-9]+)'
                r'(\s*,\s*(("[A-Z_0-9]+")|[A-Z_0-9]+))*)\)(?:\s+HELP\s+"(?P<help>[^"]+)")?\s+MESSAGE\s+"(?P<msg>(.|\n)*)"\s*$',
                suffix="2",
            ),
            suffix="1",
        ),
        x_prompt_compare,
    )
    mcl.add(
        ins_table_rxs(
            r'^\s*PROMPT\s+ASK\s+"(?P<msg>(.|\n)*)"\s+SUB\s+(?P<match>~?\w+)\s+COMPARE\s+',
            ins_table_rxs(
                r"(?:\s+IN\s+(?P<alias1>\w+))?\s+(?P<orient>AND|BESIDE)\s+",
                r'(?:\s+IN\s+(?P<alias2>\w+))?\s+(?:PK|KEY)\s*\((?P<pks>(("[A-Z_0-9]+")|[A-Z_0-9]+)'
                r'(\s*,\s*(("[A-Z_0-9]+")|[A-Z_0-9]+))*)\)(?:\s+HELP\s+(?P<help>[^\s]+))?\s*$',
                suffix="2",
            ),
            suffix="1",
        ),
        x_prompt_ask_compare,
    )
    mcl.add(
        ins_table_rxs(
            r'^\s*PROMPT\s+ASK\s+"(?P<msg>(.|\n)*)"\s+SUB\s+(?P<match>~?\w+)\s+COMPARE\s+',
            ins_table_rxs(
                r"(?:\s+IN\s+(?P<alias1>\w+))?\s+(?P<orient>AND|BESIDE)\s+",
                r'(?:\s+IN\s+(?P<alias2>\w+))?\s+(?:PK|KEY)\s*\((?P<pks>(("[A-Z_0-9]+")|[A-Z_0-9]+)'
                r'(\s*,\s*(("[A-Z_0-9]+")|[A-Z_0-9]+))*)\)(?:\s+HELP\s+"(?P<help>[^"]+)")?\s*$',
                suffix="2",
            ),
            suffix="1",
        ),
        x_prompt_ask_compare,
    )

    # ------------------------------------------------------------------
    # PROMPT MAP
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r'^\s*PROMPT\s+MESSAGE\s+"(?P<message>(.|\n)*)"\s+MAP\s+',
            r"\s*LAT\s+(?P<lat_col>\w+)\s+LON\s+(?P<lon_col>\w+)"
            r"(?:\s+LABEL\s+(?P<label_col>\w+))?(?:\s+COLOR\s+(?P<color_col>\w+))?"
            r"(?:\s+SYMBOL\s+(?P<symbol_col>\w+))?\s*$",
        ),
        x_prompt_map,
    )
    mcl.add(
        ins_table_rxs(
            r'^\s*PROMPT\s+MESSAGE\s+"(?P<message>(.|\n)*)"\s+MAP\s+',
            r'\s*LAT\s+"(?P<lat_col>[\w+ ])"\s+LON\s+"(?P<lon_col>[\w+ ])"'
            r'(?:\s+LABEL\s+"(?P<label_col>[\w+ ])")?(?:\s+COLOR\s+"(?P<color_col>[\w+ ])")?'
            r'(?:\s+SYMBOL\s+"(?P<symbol_col>[\w+ ])")?\s*$',
        ),
        x_prompt_map,
    )

    # ------------------------------------------------------------------
    # EMAIL
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            ins_fn_rxs(
                r"^\s*EMAIL\s+"
                r"FROM\s+(?P<from>[A-Za-z0-9_\-\.!#$%&\'*+/=?^`{|}~]+@[A-Za-z0-9]+(-[A-Za-z0-9]+)*(\.[A-Za-z0-9]+)*)\s+"
                r"TO\s+(?P<to>[A-Za-z0-9_\-\.!#$%&\'*+/=?^`{|}~]+@[A-Za-z0-9]+(-[A-Za-z0-9]+)*(\.[A-Za-z0-9]+)*"
                r"([;,]\s*[A-Za-z0-9\-\.!#$%&\'*+/=?^`{|}~]+@[A-Za-z0-9]+(-[A-Za-z0-9]+)*(\.[A-Za-z0-9]+)*)*)\s+"
                r'SUBJECT "(?P<subject>[^"]+)"\s+'
                r'MESSAGE\s+"(?P<msg>[^"]*)"'
                r"(\s+MESSAGE_FILE\s+",
                r")?(\s+ATTACH(MEANT)?_FILE\s+",
                "msg_file",
            ),
            r")?\s*$",
            "att_file",
        ),
        x_email,
    )

    # ------------------------------------------------------------------
    # EXPORT_METADATA
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            ins_fn_rxs(
                r"^\s*EXPORT_METADATA(?:\s+(?P<append>APPEND))?(?:\s+(?P<all>ALL))?\s+TO\s+",
                r"(?:\s+IN\s+ZIPFILE\s+",
            ),
            r")?\s+AS\s+(?P<format>CSV|TAB|TSV|TABQ|TSVQ|TXT|TEXT)",
            symbolicname="zipfilename",
        ),
        x_export_metadata,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*EXPORT_METADATA(?:\s+(?P<all>ALL))?\s+INTO(?:\s+(?P<new>NEW|REPLACEMENT))?\s+TABLE\s+",
            r"\s*$",
        ),
        x_export_metadata_table,
    )

    # ------------------------------------------------------------------
    # SUB operations
    # ------------------------------------------------------------------
    mcl.add(r"^\s*SUB_EMPTY\s+(?P<match>[+~]?\w+)\s*$", x_sub_empty)
    mcl.add(
        r"^\s*SUB_ADD\s+(?P<match>[+~]?\w+)\s+(?P<increment>[+\-0-9\.*/() ]+)\s*$",
        x_sub_add,
    )
    mcl.add(r"^\s*SUB_APPEND\s+(?P<match>[+~]?\w+)\s(?P<repl>(.|\n)*)$", x_sub_append)

    # ------------------------------------------------------------------
    # IF / ORIF / ANDIF / ELSEIF / ELSE / ENDIF
    # ------------------------------------------------------------------
    mcl.add(r"^\s*ORIF\s*\(\s*(?P<condtest>.+)\s*\)\s*$", x_if_orif, run_when_false=True)
    mcl.add(r"^\s*ELSEIF\s*\(\s*(?P<condtest>.+)\s*\)\s*$", x_if_elseif, run_when_false=True)
    mcl.add(r"^\s*ANDIF\s*\(\s*(?P<condtest>.+)\s*\)\s*$", x_if_andif)
    mcl.add(r"^\s*ELSE\s*$", x_if_else, run_when_false=True)
    mcl.add(r"^\s*IF\s*\(\s*(?P<condtest>.+)\s*\)\s*{\s*(?P<condcmd>.+)\s*}\s*$", x_if)
    mcl.add(r"^\s*IF\s*\(\s*(?P<condtest>.+)\s*\)\s*$", x_if_block, run_when_false=True)
    mcl.add(r"^\s*ENDIF\s*$", x_if_end, run_when_false=True)

    # ------------------------------------------------------------------
    # CONNECT — SQL Server
    # ------------------------------------------------------------------
    mcl.add(
        (
            r"^CONNECT\s+USER\s+TO\s+SQLSERVER\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r'^CONNECT\s+USER\s+TO\s+SQLSERVER\s*\(\s*SERVER\s*=\s*"(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)"\s*,\s*'
            r'DB\s*=\s*"(?P<db_name>[A-Z][A-Z0-9_\- ]*)"(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?'
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_user_ssvr,
    )
    mcl.add(
        (
            r"^CONNECT\s+TO\s+SQLSERVER\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\/\\\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*USER\s*=\s*(?P<user>[A-Z][A-Z0-9_~`!@#$%^&\*\+=\/\?\.-]*)"
            r"\s*,\s*NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s+PASSWORD\s*=\s*(?P<password>[^\s\)]+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r'^CONNECT\s+TO\s+SQLSERVER\s*\(\s*SERVER\s*=\s*"(?P<server>[A-Z0-9][A-Z0-9_\/\\\s\-\.]*)"\s*,\s*'
            r'DB\s*=\s*"(?P<db_name>[A-Z][A-Z0-9_\-\s]*)"(?:\s*,\s*USER\s*=\s*(?P<user>[A-Z][A-Z0-9_~`!@#$%^&\*\+=\/\?\.-]*)'
            r"\s*,\s*NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s+PASSWORD\s*=\s*(?P<password>[^\s\)]+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_ssvr,
    )

    # ------------------------------------------------------------------
    # COPY QUERY / COPY
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^COPY QUERY\s+<<\s*(?P<query>.*;)\s*>>\s+FROM\s+(?P<alias1>[A-Z][A-Z0-9_]*)\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?",
            r" IN\s+(?P<alias2>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_copy_query,
    )
    mcl.add(
        (
            r"^COPY\s+(?:(?P<schema1>[A-Z][A-Z0-9_\-\/\:]*)\.)?(?P<table1>[A-Z][A-Z0-9_\-\/\:]*)\s+FROM\s+(?P<alias1>[A-Z][A-Z0-9_]*)\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?(?:(?P<schema2>[A-Z][A-Z0-9_\-\/\:]*)\.)?(?P<table2>[A-Z][A-Z0-9_\-\/\:]*)\s+IN\s+(?P<alias2>[A-Z][A-Z0-9_]*)\s*$",
            r'^COPY\s+(?:"(?P<schema1>[A-Z][A-Z0-9_\-\/\: ]*)"\.)?"(?P<table1>[A-Z][A-Z0-9_\-\/\: ]*)"\s+FROM\s+(?P<alias1>[A-Z][A-Z0-9_]*)\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?(?:"(?P<schema2>[A-Z][A-Z0-9_\-\/\:]*)"\.)?"(?P<table2>[A-Z][A-Z0-9_\-\/\:]*)"\s+IN\s+(?P<alias2>[A-Z][A-Z0-9_]*)\s*$',
            r'^COPY\s+(?:(?P<schema1>[A-Z][A-Z0-9_\-\/\:]*)\.)?(?P<table1>[A-Z][A-Z0-9_\-\/\:]*)\s+FROM\s+(?P<alias1>[A-Z][A-Z0-9_]*)\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?(?:"(?P<schema2>[A-Z][A-Z0-9_\-\/\:]*)"\.)?"(?P<table2>[A-Z][A-Z0-9_\-\/\:]*)"\s+IN\s+(?P<alias2>[A-Z][A-Z0-9_]*)\s*$',
            r'^COPY\s+(?:"(?P<schema1>[A-Z][A-Z0-9_\-\/\: ]*)"\.)?"(?P<table1>[A-Z][A-Z0-9_\-\/\: ]*)"\s+FROM\s+(?P<alias1>[A-Z][A-Z0-9_]*)\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?(?:(?P<schema2>[A-Z][A-Z0-9_\-\/\:]*)\.)?(?P<table2>[A-Z][A-Z0-9_\-\/\:]*)\s+IN\s+(?P<alias2>[A-Z][A-Z0-9_]*)\s*$',
            r"^COPY\s+(?:\[(?P<schema1>[A-Z][A-Z0-9_\-\/\: ]*)\]\.)?\[(?P<table1>[A-Z][A-Z0-9_\-\/\: ]*)\]\s+FROM\s+(?P<alias1>[A-Z][A-Z0-9_]*)\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?(?:\[(?P<schema2>[A-Z][A-Z0-9_\-\/\:]*)\]\.)?\[(?P<table2>[A-Z][A-Z0-9_\-\/\:]*)\]\s+IN\s+(?P<alias2>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_copy,
    )

    # ------------------------------------------------------------------
    # APPEND/EXTEND SCRIPT
    # ------------------------------------------------------------------
    mcl.add(
        r"\s*APPEND\s+SCRIPT\s+(?P<script1>\w+)\s+TO\s+(?P<script2>\w+)\s*$",
        x_extendscript,
    )
    mcl.add(
        r"\s*EXTEND\s+SCRIPT\s+(?P<script>\w+)\s+WITH\s+METACOMMAND\s+(?P<cmd>.+)\s*$",
        x_extendscript_metacommand,
    )
    mcl.add(
        r"\s*EXTEND\s+SCRIPT\s+(?P<script>\w+)\s+WITH\s+SQL\s+(?P<sql>.+;)\s*$",
        x_extendscript_sql,
    )

    # ------------------------------------------------------------------
    # CONNECT — DuckDB / SQLite / PostgreSQL / MySQL
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            r"^CONNECT\s+TO\s+DUCKDB\s*\(\s*FILE\s*=\s*",
            r"(?:\s*,\s*(?P<new>NEW))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_duckdb,
    )
    mcl.add(
        ins_fn_rxs(
            r"^CONNECT\s+TO\s+SQLITE\s*\(\s*FILE\s*=\s*",
            r"(?:\s*,\s*(?P<new>NEW))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_sqlite,
    )
    mcl.add(
        (
            r"^CONNECT\s+USER\s+TO\s+POSTGRESQL\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r'^CONNECT\s+USER\s+TO\s+POSTGRESQL\s*\(\s*SERVER\s*=\s*"(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)"\s*,\s*'
            r'DB\s*=\s*"(?P<db_name>[A-Z][A-Z0-9_\-]*)"(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?'
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_user_pg,
    )
    mcl.add(
        (
            r"^CONNECT\s+TO\s+POSTGRESQL\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*USER\s*=\s*(?P<user>[A-Z][A-Z0-9_\-@\.]*)\s*,\s*"
            r"NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s+PASSWORD\s*=\s*(?P<password>[^\s\)]+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?(?:\s*,\s*(?P<new>NEW))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r'^CONNECT\s+TO\s+POSTGRESQL\s*\(\s*SERVER\s*=\s*"(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)"\s*,\s*'
            r'DB\s*=\s*"(?P<db_name>[A-Z][A-Z0-9_\-]*)"(?:\s*,\s*USER\s*=\s*"(?P<user>[A-Z][A-Z0-9_\-@\.]*)"\s*,\s*'
            r"NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r'(?:\s*,\s+PASSWORD\s*=\s*"(?P<password>[^\s\)]+)")?'
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?(?:\s*,\s*(?P<new>NEW))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_pg,
    )
    mcl.add(
        (
            r"^CONNECT\s+USER\s+TO\s+MYSQL\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r'^CONNECT\s+USER\s+TO\s+MYSQL\s*\(\s*SERVER\s*=\s*"(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)"\s*,\s*'
            r'DB\s*=\s*"(?P<db_name>[A-Z][A-Z0-9_\-]*)"(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?'
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r"^CONNECT\s+USER\s+TO\s+MARIADB\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r'^CONNECT\s+USER\s+TO\s+MARIADB\s*\(\s*SERVER\s*=\s*"(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)"\s*,\s*'
            r'DB\s*=\s*"(?P<db_name>[A-Z][A-Z0-9_\-]*)"(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?'
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_user_mysql,
    )
    mcl.add(
        (
            r"^CONNECT\s+TO\s+MYSQL\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*USER\s*=\s*(?P<user>[A-Z][A-Z0-9_@\-\.]*)\s*,\s*"
            r"NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s+PASSWORD\s*=\s*(?P<password>[^\s]+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
            r"^CONNECT\s+TO\s+MARIADB\s*\(\s*SERVER\s*=\s*(?P<server>[A-Z0-9][A-Z0-9_\-\.]*)\s*,\s*"
            r"DB\s*=\s*(?P<db_name>[A-Z][A-Z0-9_\-]*)(?:\s*,\s*USER\s*=\s*(?P<user>[A-Z][A-Z0-9_&\-\.]*)\s*,\s*"
            r"NEED_PWD\s*=\s*(?P<need_pwd>TRUE|FALSE))?(?:\s*,\s*PORT\s*=\s*(?P<port>\d+))?"
            r"(?:\s*,\s+PASSWORD\s*=\s*(?P<password>[^\s]+))?"
            r"(?:\s*,\s*ENCODING\s*=\s*(?P<encoding>[A-Z][A-Z0-9_-]+))?\s*\)\s+AS\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$",
        ),
        x_connect_mysql,
    )

    # ------------------------------------------------------------------
    # USE / CONNECT DSN
    # ------------------------------------------------------------------
    mcl.add(r"^USE\s+(?P<db_alias>[A-Z][A-Z0-9_]*)\s*$", x_use)

    # ------------------------------------------------------------------
    # SYSTEM_CMD
    # ------------------------------------------------------------------
    mcl.add(
        r"^\s*SYSTEM_CMD\s*\(\s*(?P<command>.+)\s*\)(?:\s+(?P<continue>CONTINUE))?\s*$",
        x_system_cmd,
    )

    # ------------------------------------------------------------------
    # INCLUDE
    # ------------------------------------------------------------------
    mcl.add(ins_fn_rxs(r"^\s*INCLUDE(?P<exists>\s+IF\s+EXISTS?)?\s+", r"\s*$"), x_include)

    # ------------------------------------------------------------------
    # IMPORT (CSV / delimited)
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r"^\s*IMPORT\s+TO\s+(?:(?P<new>NEW|REPLACEMENT)\s+)?",
            ins_fn_rxs(
                r"\s+FROM\s+",
                r'(?:\s+WITH)?(?:\s+QUOTE\s+(?P<quotechar>NONE|\'|")\s+DELIMITER\s+'
                r"(?P<delimchar>TAB|UNITSEP|US|,|;|\|))?(?:\s+ENCODING\s+(?P<encoding>\w+))?"
                r"(?:\s+SKIP\s+(?P<skip>\d+))?\s*$",
            ),
        ),
        x_import,
    )

    # ------------------------------------------------------------------
    # RM_FILE / RM_SUB
    # ------------------------------------------------------------------
    mcl.add(
        (
            r"^RM_FILE\s+(?P<filename>.+)\s*$",
            r'^RM_FILE\s+"(?P<filename>.+)"\s*$',
        ),
        x_rm_file,
    )
    mcl.add(r"^\s*RM_SUB\s+(?P<match>~?\w+)\s*$", x_rm_sub)

    # ------------------------------------------------------------------
    # SELECT_SUB / SUBDATA
    # ------------------------------------------------------------------
    mcl.add(r"^\s*SELECT_SUB\s+(?P<datasource>.+)\s*$", x_selectsub)
    mcl.add(r"^\s*SUBDATA\s+(?P<match>[+~]?\w+)\s+(?P<datasource>.+)\s*$", x_subdata)

    # ------------------------------------------------------------------
    # PROMPT ASK (simple)
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r'^\s*PROMPT\s+ASK\s+"(?P<question>[^"]+)"\s+SUB\s+(?P<match>~?\w+)(?:\s+DISPLAY\s+',
            r')?(?:\s+HELP\s+"(?P<help>[^"]+)")?\s*$',
        ),
        x_prompt_ask,
    )

    # ------------------------------------------------------------------
    # PROMPT DISPLAY (table viewer)
    # ------------------------------------------------------------------
    mcl.add(
        ins_table_rxs(
            r'^\s*PROMPT\s+MESSAGE\s+"(?P<message>(.|\n)*)"\s+DISPLAY\s+',
            r"(?:\s+HELP\s+(?P<help>[^\s]+))?(?:\s+(?P<free>FREE))?\s*$",
        ),
        x_prompt,
    )
    mcl.add(
        ins_table_rxs(
            r'^\s*PROMPT\s+MESSAGE\s+"(?P<message>(.|\n)*)"\s+DISPLAY\s+',
            r'(?:\s+HELP\s+"(?P<help>[^"]+)")?(?:\s+(?P<free>FREE))?\s*$',
        ),
        x_prompt,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+DISPLAY\s+",
            r'\s+MESSAGE\s+"(?P<message>(.|\n)*)"(?:\s+HELP\s+(?P<help>[^\s]+))?(?:\s+(?P<free>FREE))?\s*$',
        ),
        x_prompt,
    )
    mcl.add(
        ins_table_rxs(
            r"^\s*PROMPT\s+DISPLAY\s+",
            r'\s+MESSAGE\s+"(?P<message>(.|\n)*)"(?:\s+HELP\s+"(?P<help>[^"]+)")?(?:\s+(?P<free>FREE))?\s*$',
        ),
        x_prompt,
    )

    # ------------------------------------------------------------------
    # PROMPT MESSAGE (simple message / MSG)
    # ------------------------------------------------------------------
    mcl.add(r'^\s*PROMPT(?:\s+MESSAGE)?\s+"(?P<message>(.|\n)*)"\s*$', x_msg)

    # ------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------
    mcl.add(
        ins_fn_rxs(
            r'^\s*WRITE\s+"(?P<text>([^"]|\n)*)"(?:(?:\s+(?P<tee>TEE))?\s+TO\s+',
            r")?\s*$",
        ),
        x_write,
    )

    # ------------------------------------------------------------------
    # SUB (top-level variable assignment — kept near end so more specific
    # SUB_* patterns above take precedence)
    # ------------------------------------------------------------------
    mcl.add(
        r"^\s*SUB\s+(?P<match>[+~]?\w+)\s+(?P<repl>.+)$",
        x_sub,
        "SUB",
        "Define a string to match and a replacement for it.",
    )

    return mcl


# ---------------------------------------------------------------------------
# Module-level DISPATCH_TABLE — built once at import time.
# ---------------------------------------------------------------------------
DISPATCH_TABLE = build_dispatch_table()
