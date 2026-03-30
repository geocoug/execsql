from __future__ import annotations

"""
Configuration management for execsql.

Provides three classes:

- :class:`StatObj` — lightweight status-flag container used throughout the
  metacommand runtime (halt-on-error, sql_error, dialog_canceled, etc.).
- :class:`ConfigData` — reads and merges ``execsql.conf`` INI files from
  system-, user-, script-, and working-directory locations, exposing all
  recognised options as attributes.
- :class:`WriteHooks` — thin wrapper around ``sys.stdout``/``sys.stderr``
  that lets the GUI (or tests) redirect or tee output without changing call
  sites.
"""

import os
import sys
from configparser import ConfigParser
from pathlib import Path

from execsql.exceptions import ConfigError
from execsql.utils.crypto import Encrypt

__all__ = [
    "StatObj",
    "ConfigData",
    "WriteHooks",
]


class StatObj:
    # A generic object to maintain status indicators.  These status
    # indicators are primarily those used in the metacommand
    # environment rather than for the program as a whole.
    def __init__(self) -> None:
        self.halt_on_err = True
        self.sql_error = False
        self.halt_on_metacommand_err = True
        self.metacommand_error = False
        self.cancel_halt = True
        self.dialog_canceled = False
        # BatchLevels is defined in the main module; defer import to avoid circular deps
        from execsql.script import BatchLevels

        self.batch = BatchLevels()


class ConfigData:
    config_file_name = "execsql.conf"
    _CONNECT_SECTION = "connect"
    _ENCODING_SECTION = "encoding"
    _INPUT_SECTION = "input"
    _OUTPUT_SECTION = "output"
    _INTERFACE_SECTION = "interface"
    _CONFIG_SECTION = "config"
    _EMAIL_SECTION = "email"
    _VARIABLES_SECTION = "variables"
    _INCLUDE_REQ_SECTION = "include_required"
    _INCLUDE_OPT_SECTION = "include_optional"

    def __init__(self, script_path: str, variable_pool: object) -> None:
        self.db_type = "a"
        self.server = None
        self.port = None
        self.db = None
        self.username = None
        self.access_username = None
        self.passwd_prompt = True
        self.use_keyring = True
        self.db_file = None
        self.new_db = False
        self.user_logfile = False
        self.db_encoding = None
        self.script_encoding = "utf8"
        self.output_encoding = "utf8"
        self.import_encoding = "utf8"
        self.enc_err_disposition = None
        self.import_common_cols_only = False
        self.max_int = 2147483647
        self.boolean_int = True
        self.boolean_words = False
        self.empty_strings = True
        self.only_strings = False
        self.empty_rows = True
        self.del_empty_cols = False
        self.create_col_hdrs = False
        self.trim_col_hdrs = "none"
        self.clean_col_hdrs = False
        self.fold_col_hdrs = "no"
        self.dedup_col_hdrs = False
        self.trim_strings = False
        self.replace_newlines = False
        self.access_use_numeric = False
        self.scan_lines = 100
        self.hdf5_text_len = 1000
        self.write_warnings = False
        self.write_prefix = None
        self.write_suffix = None
        self.gui_level = 0
        self.gui_framework = "tkinter"
        self.gui_wait_on_exit = False
        self.gui_wait_on_error_halt = False
        self.gui_console_height = 25
        self.gui_console_width = 100
        self.import_buffer = 32 * 1024
        self.css_file = None
        self.css_styles = None
        self.make_export_dirs = False
        self.outfile_open_timeout = 600
        self.quote_all_text = False
        self.import_row_buffer = 1000
        self.import_progress_interval = 0
        self.show_progress = False
        self.export_row_buffer = 1000
        self.template_processor = None
        self.tee_write_log = False
        self.log_datavars = True
        self.log_sql = False
        self.max_log_size_mb = 0
        self.smtp_host = None
        self.smtp_port = None
        self.smtp_username = None
        self.smtp_password = None
        self.smtp_ssl = False
        self.smtp_tls = False
        self.email_format = "plain"
        self.email_css = None
        self.include_req: list = []
        self.include_opt: list = []
        self.dao_flush_delay_secs = 5.0
        self.zip_buffer_mb = 10
        if os.name == "posix":
            sys_config_file = str(Path("/etc") / self.config_file_name)
        else:
            sys_config_file = str(Path(os.path.expandvars(r"%APPDATA%")) / self.config_file_name)
        current_script = str(Path(sys.argv[0]).resolve())
        user_config_file = str(Path("~/.config").expanduser() / self.config_file_name)
        script_config_file = str(Path(script_path) / self.config_file_name)
        startdir_config_file = str(Path(".").resolve() / self.config_file_name)
        if startdir_config_file != script_config_file:
            config_files = [sys_config_file, user_config_file, script_config_file, startdir_config_file]
        else:
            config_files = [sys_config_file, user_config_file, startdir_config_file]
        self.files_read: list = []
        for ix, configfile in enumerate(config_files):
            if configfile not in self.files_read and Path(configfile).is_file():
                self.files_read.append(configfile)
                cp = ConfigParser()
                cp.read(configfile)
                if cp.has_option(self._CONNECT_SECTION, "db_type"):
                    t = cp.get(self._CONNECT_SECTION, "db_type").lower()
                    if len(t) != 1 or t not in ("a", "d", "f", "k", "l", "m", "o", "p", "s"):
                        raise ConfigError(f"Invalid database type: {t}")
                    self.db_type = t
                if cp.has_option(self._CONNECT_SECTION, "server"):
                    self.server = cp.get(self._CONNECT_SECTION, "server")
                    if self.server is None:
                        raise ConfigError("The server name cannot be missing.")
                if cp.has_option(self._CONNECT_SECTION, "db"):
                    self.db = cp.get(self._CONNECT_SECTION, "db")
                    if self.db is None:
                        raise ConfigError("The database name cannot be missing.")
                if cp.has_option(self._CONNECT_SECTION, "port"):
                    try:
                        self.port = cp.getint(self._CONNECT_SECTION, "port")
                    except Exception as e:
                        raise ConfigError("Invalid port number.") from e
                if cp.has_option(self._CONNECT_SECTION, "database"):
                    self.db = cp.get(self._CONNECT_SECTION, "database")
                    if self.db is None:
                        raise ConfigError("The database name cannot be missing.")
                if cp.has_option(self._CONNECT_SECTION, "db_file"):
                    self.db_file = cp.get(self._CONNECT_SECTION, "db_file")
                    if self.db_file is None:
                        raise ConfigError("The database file name cannot be missing.")
                if cp.has_option(self._CONNECT_SECTION, "username"):
                    self.username = cp.get(self._CONNECT_SECTION, "username")
                    if self.username is None:
                        raise ConfigError("The user name cannot be missing.")
                if cp.has_option(self._CONNECT_SECTION, "access_username"):
                    self.access_username = cp.get(self._CONNECT_SECTION, "access_username")
                if cp.has_option(self._CONNECT_SECTION, "password_prompt"):
                    try:
                        self.passwd_prompt = cp.getboolean(self._CONNECT_SECTION, "password_prompt")
                    except Exception as e:
                        raise ConfigError("Invalid argument for password_prompt.") from e
                if cp.has_option(self._CONNECT_SECTION, "use_keyring"):
                    try:
                        self.use_keyring = cp.getboolean(self._CONNECT_SECTION, "use_keyring")
                    except Exception as e:
                        raise ConfigError("Invalid argument for use_keyring.") from e
                if cp.has_option(self._CONNECT_SECTION, "new_db"):
                    try:
                        self.new_db = cp.getboolean(self._CONNECT_SECTION, "new_db")
                    except Exception as e:
                        raise ConfigError("Invalid argument for new_db.") from e
                if cp.has_option(self._ENCODING_SECTION, "database"):
                    self.db_encoding = cp.get(self._ENCODING_SECTION, "database")
                if cp.has_option(self._ENCODING_SECTION, "script"):
                    self.script_encoding = cp.get(self._ENCODING_SECTION, "script")
                    if self.script_encoding is None:
                        raise ConfigError("The script encoding cannot be missing.")
                if cp.has_option(self._ENCODING_SECTION, "import"):
                    self.import_encoding = cp.get(self._ENCODING_SECTION, "import")
                    if self.import_encoding is None:
                        raise ConfigError("The import encoding cannot be missing.")
                if cp.has_option(self._ENCODING_SECTION, "output"):
                    self.output_encoding = cp.get(self._ENCODING_SECTION, "output")
                    if self.output_encoding is None:
                        raise ConfigError("The output encoding cannot be missing.")
                if cp.has_option(self._ENCODING_SECTION, "error_response"):
                    handler = cp.get(self._ENCODING_SECTION, "error_response").lower()
                    if handler not in ("ignore", "replace", "xmlcharrefreplace", "backslashreplace"):
                        raise ConfigError(f"Invalid encoding error handler: {handler}")
                    self.enc_err_disposition = handler
                if cp.has_option(self._INPUT_SECTION, "max_int"):
                    try:
                        maxint = cp.getint(self._INPUT_SECTION, "max_int")
                    except Exception as e:
                        raise ConfigError("Invalid argument to max_int.") from e
                    else:
                        self.max_int = maxint
                if cp.has_option(self._INPUT_SECTION, "boolean_int"):
                    try:
                        self.boolean_int = cp.getboolean(self._INPUT_SECTION, "boolean_int")
                    except Exception as e:
                        raise ConfigError("Invalid argument to boolean_int.") from e
                if cp.has_option(self._INPUT_SECTION, "boolean_words"):
                    try:
                        self.boolean_words = cp.getboolean(self._INPUT_SECTION, "boolean_words")
                    except Exception as e:
                        raise ConfigError("Invalid argument to boolean_words.") from e
                if cp.has_option(self._INPUT_SECTION, "empty_strings"):
                    try:
                        self.empty_strings = cp.getboolean(self._INPUT_SECTION, "empty_strings")
                    except Exception as e:
                        raise ConfigError("Invalid argument to empty_strings.") from e
                if cp.has_option(self._INPUT_SECTION, "only_strings"):
                    try:
                        self.only_strings = cp.getboolean(self._INPUT_SECTION, "only_strings")
                    except Exception as e:
                        raise ConfigError("Invalid argument to only_strings.") from e
                if cp.has_option(self._INPUT_SECTION, "empty_rows"):
                    try:
                        self.empty_rows = cp.getboolean(self._INPUT_SECTION, "empty_rows")
                    except Exception as e:
                        raise ConfigError("Invalid argument to empty_rows.") from e
                if cp.has_option(self._INPUT_SECTION, "delete_empty_columns"):
                    try:
                        self.del_empty_cols = cp.getboolean(self._INPUT_SECTION, "delete_empty_columns")
                    except Exception as e:
                        raise ConfigError("Invalid argument to delete_empty_columns.") from e
                if cp.has_option(self._INPUT_SECTION, "create_column_headers"):
                    try:
                        self.create_col_hdrs = cp.getboolean(self._INPUT_SECTION, "create_column_headers")
                    except Exception as e:
                        raise ConfigError("Invalid argument to create_column_headers.") from e
                if cp.has_option(self._INPUT_SECTION, "trim_column_headers"):
                    try:
                        self.trim_col_hdrs = cp.get(self._INPUT_SECTION, "trim_column_headers").lower()
                    except Exception as e:
                        raise ConfigError("Invalid argument to trim_column_headers.") from e
                    if self.trim_col_hdrs not in ("none", "both", "left", "right"):
                        raise ConfigError(f"Invalid argument to trim_column_headers: {self.trim_col_hdrs}.")
                if cp.has_option(self._INPUT_SECTION, "clean_column_headers"):
                    try:
                        self.clean_col_hdrs = cp.getboolean(self._INPUT_SECTION, "clean_column_headers")
                    except Exception as e:
                        raise ConfigError("Invalid argument to clean_column_headers.") from e
                if cp.has_option(self._INPUT_SECTION, "fold_column_headers"):
                    foldspec = cp.get(self._INPUT_SECTION, "fold_column_headers").lower()
                    if foldspec not in ("no", "lower", "upper"):
                        raise ConfigError(f"Invalid argument to fold_column_headers: {foldspec}.")
                    self.fold_col_hdrs = foldspec
                if cp.has_option(self._INPUT_SECTION, "dedup_column_headers"):
                    try:
                        self.dedup_col_hdrs = cp.getboolean(self._INPUT_SECTION, "dedup_column_headers")
                    except Exception as e:
                        raise ConfigError("Invalid argument to dedup_column_headers.") from e
                if cp.has_option(self._INPUT_SECTION, "trim_strings"):
                    try:
                        self.trim_strings = cp.getboolean(self._INPUT_SECTION, "trim_strings")
                    except Exception as e:
                        raise ConfigError("Invalid argument to trim_strings.") from e
                if cp.has_option(self._INPUT_SECTION, "replace_newlines"):
                    try:
                        self.replace_newlines = cp.getboolean(self._INPUT_SECTION, "replace_newlines")
                    except Exception as e:
                        raise ConfigError("Invalid argument to replace_newlines.") from e
                if cp.has_option(self._INPUT_SECTION, "import_row_buffer"):
                    try:
                        self.import_row_buffer = cp.getint(self._INPUT_SECTION, "import_row_buffer")
                    except Exception as e:
                        raise ConfigError("Invalid argument for import_row_buffer.") from e
                if cp.has_option(self._INPUT_SECTION, "import_progress_interval"):
                    try:
                        self.import_progress_interval = cp.getint(self._INPUT_SECTION, "import_progress_interval")
                    except Exception as e:
                        raise ConfigError("Invalid argument for import_progress_interval.") from e
                if cp.has_option(self._INPUT_SECTION, "show_progress"):
                    try:
                        self.show_progress = cp.getboolean(self._INPUT_SECTION, "show_progress")
                    except Exception as e:
                        raise ConfigError("Invalid argument for show_progress.") from e
                if cp.has_option(self._INPUT_SECTION, "access_use_numeric"):
                    try:
                        self.access_use_numeric = cp.getboolean(self._INPUT_SECTION, "access_use_numeric")
                    except Exception as e:
                        raise ConfigError("Invalid argument to access_use_numeric.") from e
                if cp.has_option(self._INPUT_SECTION, "import_only_common_columns"):
                    try:
                        self.import_common_cols_only = cp.getboolean(
                            self._INPUT_SECTION,
                            "import_only_common_columns",
                        )
                    except Exception as e:
                        raise ConfigError("Invalid argument to import_only_common_columns.") from e
                if cp.has_option(self._INPUT_SECTION, "import_common_columns_only"):
                    try:
                        self.import_common_cols_only = cp.getboolean(
                            self._INPUT_SECTION,
                            "import_common_columns_only",
                        )
                    except Exception as e:
                        raise ConfigError("Invalid argument to import_common_columns_only.") from e
                if cp.has_option(self._INPUT_SECTION, "scan_lines"):
                    try:
                        self.scan_lines = cp.getint(self._INPUT_SECTION, "scan_lines")
                    except Exception as e:
                        raise ConfigError("Invalid argument to scan_lines.") from e
                if cp.has_option(self._INPUT_SECTION, "import_buffer"):
                    try:
                        self.import_buffer = cp.getint(self._INPUT_SECTION, "import_buffer") * 1024
                    except Exception as e:
                        raise ConfigError("Invalid argument for import_buffer.") from e
                if cp.has_option(self._OUTPUT_SECTION, "log_write_messages"):
                    try:
                        self.tee_write_log = cp.getboolean(self._OUTPUT_SECTION, "log_write_messages")
                    except Exception as e:
                        raise ConfigError("Invalid argument to log_write_messages") from e
                if cp.has_option(self._OUTPUT_SECTION, "hdf5_text_len"):
                    try:
                        self.hdf5_text_len = cp.getint(self._OUTPUT_SECTION, "hdf5_text_len")
                    except Exception as e:
                        raise ConfigError("Invalid argument to log_write_messages") from e
                if cp.has_option(self._OUTPUT_SECTION, "css_file"):
                    self.css_file = cp.get(self._OUTPUT_SECTION, "css_file")
                    if self.css_file is None:
                        raise ConfigError("The css_file name is missing.")
                if cp.has_option(self._OUTPUT_SECTION, "css_styles"):
                    self.css_styles = cp.get(self._OUTPUT_SECTION, "css_styles")
                    if self.css_styles is None:
                        raise ConfigError("The css_styles are missing.")
                if cp.has_option(self._OUTPUT_SECTION, "make_export_dirs"):
                    try:
                        self.make_export_dirs = cp.getboolean(self._OUTPUT_SECTION, "make_export_dirs")
                    except Exception as e:
                        raise ConfigError("Invalid argument for make_export_dirs.") from e
                if cp.has_option(self._OUTPUT_SECTION, "quote_all_text"):
                    try:
                        self.quote_all_text = cp.getboolean(self._OUTPUT_SECTION, "quote_all_text")
                    except Exception as e:
                        raise ConfigError("Invalid argument for make_export_dirs.") from e
                if cp.has_option(self._OUTPUT_SECTION, "outfile_open_timeout"):
                    try:
                        self.outfile_open_timeout = cp.getint(self._OUTPUT_SECTION, "outfile_open_timeout")
                    except Exception as e:
                        raise ConfigError("Invalid argument for outfile_open_timeout.") from e
                if cp.has_option(self._OUTPUT_SECTION, "export_row_buffer"):
                    try:
                        self.export_row_buffer = cp.getint(self._OUTPUT_SECTION, "export_row_buffer")
                    except Exception as e:
                        raise ConfigError("Invalid argument for export_row_buffer.") from e
                if cp.has_option(self._OUTPUT_SECTION, "template_processor"):
                    tp = cp.get(self._OUTPUT_SECTION, "template_processor").lower()
                    if tp not in ("jinja",):
                        raise ConfigError(f"Invalid template processor name: {tp}")
                    self.template_processor = tp
                if cp.has_option(self._OUTPUT_SECTION, "zip_buffer_mb"):
                    try:
                        self.zip_buffer_mb = cp.getint(self._OUTPUT_SECTION, "zip_buffer_mb")
                    except Exception as e:
                        raise ConfigError("Invalid argument for zip_buffer_mb.") from e
                if cp.has_option(self._INTERFACE_SECTION, "write_warnings"):
                    try:
                        self.write_warnings = cp.getboolean(self._INTERFACE_SECTION, "write_warnings")
                    except Exception as e:
                        raise ConfigError("Invalid argument to write_warnings.") from e
                if cp.has_option(self._INTERFACE_SECTION, "write_prefix"):
                    try:
                        self.write_prefix = cp.get(self._INTERFACE_SECTION, "write_prefix")
                    except Exception as e:
                        raise ConfigError("Invalid or missing argument to write_prefix.") from e
                    if self.write_prefix.lower() == "clear":
                        self.write_prefix = None
                if cp.has_option(self._INTERFACE_SECTION, "write_suffix"):
                    try:
                        self.write_suffix = cp.get(self._INTERFACE_SECTION, "write_suffix")
                    except Exception as e:
                        raise ConfigError("Invalid or missing argument to write_suffix.") from e
                    if self.write_suffix.lower() == "clear":
                        self.write_suffix = None
                if cp.has_option(self._INTERFACE_SECTION, "gui_level"):
                    self.gui_level = cp.getint(self._INTERFACE_SECTION, "gui_level")
                    if self.gui_level not in (0, 1, 2, 3):
                        raise ConfigError(f"Invalid GUI level: {self.gui_level}")
                if cp.has_option(self._INTERFACE_SECTION, "gui_framework"):
                    fw = cp.get(self._INTERFACE_SECTION, "gui_framework").lower()
                    if fw not in ("tkinter", "textual"):
                        raise ConfigError("gui_framework must be 'tkinter' or 'textual'.")
                    self.gui_framework = fw
                if cp.has_option(self._INTERFACE_SECTION, "console_height"):
                    try:
                        self.gui_console_height = max(5, cp.getint(self._INTERFACE_SECTION, "console_height"))
                    except Exception as e:
                        raise ConfigError("Invalid argument for console_height.") from e
                if cp.has_option(self._INTERFACE_SECTION, "console_width"):
                    try:
                        self.gui_console_width = max(20, cp.getint(self._INTERFACE_SECTION, "console_width"))
                    except Exception as e:
                        raise ConfigError("Invalid argument for console_width.") from e
                if cp.has_option(self._INTERFACE_SECTION, "console_wait_when_done"):
                    try:
                        self.gui_wait_on_exit = cp.getboolean(self._INTERFACE_SECTION, "console_wait_when_done")
                    except Exception as e:
                        raise ConfigError("Invalid argument for console_wait_when_done.") from e
                if cp.has_option(self._INTERFACE_SECTION, "console_wait_when_error_halt"):
                    try:
                        self.gui_wait_on_error_halt = cp.getboolean(
                            self._INTERFACE_SECTION,
                            "console_wait_when_error_halt",
                        )
                    except Exception as e:
                        raise ConfigError("Invalid argument for console_wait_when_error_halt.") from e
                if cp.has_option(self._CONFIG_SECTION, "config_file"):
                    conffile = cp.get(self._CONFIG_SECTION, "config_file")
                    if os.name == "posix" and conffile[0] == "~":
                        if len(conffile) == 1:
                            conffile = str(Path("~").expanduser())
                        elif len(conffile) > 1 and conffile[1] == os.sep:
                            conffile = str(Path("~").expanduser() / conffile[2:])
                    conffile = variable_pool.substitute(conffile)[0]
                    if not Path(conffile).is_file():
                        conffile = str(Path(conffile) / self.config_file_name)
                    if Path(conffile).is_file():
                        # Silently ignore a non-existent file, for cross-OS compatibility.
                        config_files.insert(ix + 1, conffile)
                if os.name == "posix" and cp.has_option(self._CONFIG_SECTION, "linux_config_file"):
                    conffile = cp.get(self._CONFIG_SECTION, "linux_config_file")
                    if conffile[0] == "~":
                        if len(conffile) == 1:
                            conffile = str(Path("~").expanduser())
                        elif len(conffile) > 1 and conffile[1] == os.sep:
                            conffile = str(Path("~").expanduser() / conffile[2:])
                    conffile = variable_pool.substitute(conffile)[0]
                    if not Path(conffile).is_file():
                        conffile = str(Path(conffile) / self.config_file_name)
                    if Path(conffile).is_file():
                        config_files.insert(ix + 1, conffile)
                if os.name == "windows" and cp.has_option(self._CONFIG_SECTION, "win_config_file"):
                    conffile = cp.get(self._CONFIG_SECTION, "win_config_file")
                    conffile = variable_pool.substitute(conffile)[0]
                    if not Path(conffile).is_file():
                        conffile = str(Path(conffile) / self.config_file_name)
                    if Path(conffile).is_file():
                        config_files.insert(ix + 1, conffile)
                if cp.has_option(self._CONFIG_SECTION, "user_logfile"):
                    self.user_logfile = cp.getboolean(self._CONFIG_SECTION, "user_logfile")
                if cp.has_option(self._CONFIG_SECTION, "dao_flush_delay_secs"):
                    self.dao_flush_delay_secs = cp.getfloat(self._CONFIG_SECTION, "dao_flush_delay_secs")
                    if self.dao_flush_delay_secs < 5.0:
                        raise ConfigError(
                            f"Invalid DAO flush delay: {self.dao_flush_delay_secs}; must be >= 5.0.",
                        )
                if cp.has_option(self._CONFIG_SECTION, "log_datavars"):
                    try:
                        self.log_datavars = cp.getboolean(self._CONFIG_SECTION, "log_datavars")
                    except Exception as e:
                        raise ConfigError("Invalid argument to log_datavars setting.") from e
                if cp.has_option(self._CONFIG_SECTION, "log_sql"):
                    try:
                        self.log_sql = cp.getboolean(self._CONFIG_SECTION, "log_sql")
                    except Exception as e:
                        raise ConfigError("Invalid argument to log_sql setting.") from e
                if cp.has_option(self._CONFIG_SECTION, "max_log_size_mb"):
                    try:
                        self.max_log_size_mb = cp.getint(self._CONFIG_SECTION, "max_log_size_mb")
                    except Exception as e:
                        raise ConfigError("Invalid argument to max_log_size_mb setting.") from e
                if cp.has_option(self._EMAIL_SECTION, "host"):
                    self.smtp_host = cp.get(self._EMAIL_SECTION, "host")
                if cp.has_option(self._EMAIL_SECTION, "port"):
                    self.smtp_port = cp.get(self._EMAIL_SECTION, "port")
                    try:
                        self.smtp_port = cp.getint(self._EMAIL_SECTION, "port")
                    except Exception as e:
                        raise ConfigError("Invalid argument for email port.") from e
                if cp.has_option(self._EMAIL_SECTION, "username"):
                    self.smtp_username = cp.get(self._EMAIL_SECTION, "username")
                if cp.has_option(self._EMAIL_SECTION, "password"):
                    self.smtp_password = cp.get(self._EMAIL_SECTION, "password")
                if cp.has_option(self._EMAIL_SECTION, "enc_password"):
                    self.smtp_password = Encrypt().decrypt(cp.get(self._EMAIL_SECTION, "enc_password"))
                if cp.has_option(self._EMAIL_SECTION, "use_ssl"):
                    try:
                        self.smtp_ssl = cp.getboolean(self._EMAIL_SECTION, "use_ssl")
                    except Exception as e:
                        raise ConfigError("Invalid argument for email use_ssl.") from e
                if cp.has_option(self._EMAIL_SECTION, "use_tls"):
                    try:
                        self.smtp_tls = cp.getboolean(self._EMAIL_SECTION, "use_tls")
                    except Exception as e:
                        raise ConfigError("Invalid argument for email use_tls.") from e
                if cp.has_option(self._EMAIL_SECTION, "email_format"):
                    fmt = cp.get(self._EMAIL_SECTION, "email_format").lower()
                    if fmt not in ("plain", "html"):
                        raise ConfigError(f"Invalid email format: {fmt}")
                    self.email_format = fmt
                if cp.has_option(self._EMAIL_SECTION, "message_css"):
                    self.email_css = cp.get(self._EMAIL_SECTION, "message_css")
                if cp.has_section(self._VARIABLES_SECTION) and variable_pool:
                    varsect = cp.items(self._VARIABLES_SECTION)
                    for sub, repl in varsect:
                        if not variable_pool.var_name_ok(sub):
                            raise ConfigError(f"Invalid variable name: {sub}")
                        variable_pool.add_substitution(sub, repl)
                if cp.has_section(self._INCLUDE_REQ_SECTION):
                    imp_items = cp.items(self._INCLUDE_REQ_SECTION)
                    ord_items = sorted([(int(i[0]), i[1]) for i in imp_items], key=lambda x: x[0])
                    newfiles = [str(Path(f[1]).resolve()) for f in ord_items]
                    u_files = []
                    for f in newfiles:
                        if not (f in u_files or f in self.include_req or f in self.include_opt) and f != current_script:
                            if not Path(f).exists():
                                raise ConfigError(f"Required include file {f} does not exist.")
                            u_files.append(f)
                    self.include_req.extend(u_files)
                if cp.has_section(self._INCLUDE_OPT_SECTION):
                    imp_items = cp.items(self._INCLUDE_OPT_SECTION)
                    ord_items = sorted([(int(i[0]), i[1]) for i in imp_items], key=lambda x: x[0])
                    newfiles = [str(Path(f[1]).resolve()) for f in ord_items]
                    u_files = []
                    for f in newfiles:
                        if (
                            not (f in u_files or f in self.include_req or f in self.include_opt)
                            and f != current_script
                            and Path(f).exists()
                        ):
                            u_files.append(f)
                    self.include_opt.extend(u_files)


class WriteHooks:
    def __repr__(self) -> str:
        return f"WriteHooks({self.write_func!r}, {self.err_func!r}, {self.status_func!r})"

    def __init__(
        self,
        standard_output_func: object = None,
        error_output_func: object = None,
        status_output_func: object = None,
    ) -> None:
        # Arguments should be functions that take a single string and
        # write it to the desired destination.  Both stdout and stderr can be hooked.
        # If a hook function is not specified, the default of stdout or stderr will
        # be used.
        # The purpose is to allow writing to be redirected to a GUI.
        self.write_func = standard_output_func
        self.err_func = error_output_func
        self.status_func = status_output_func
        self.tee_stderr = True

    def reset(self) -> None:
        # Resets output to stdout and stderr.
        self.write_func = None
        self.err_func = None

    def redir_stdout(self, standard_output_func: object) -> None:
        self.write_func = standard_output_func

    def redir_stderr(self, error_output_func: object, tee: bool = True) -> None:
        self.err_func = error_output_func
        self.tee_stderr = tee

    def redir(self, standard_output_func: object, error_output_func: object) -> None:
        self.redir_stdout(standard_output_func)
        self.redir_stderr(error_output_func)

    def write(self, strval: str) -> None:
        if self.write_func:
            self.write_func(strval)
        else:
            sys.stdout.write(strval)
            sys.stdout.flush()

    def write_err(self, strval: str) -> None:
        if strval[-1] != "\n":
            strval += "\n"
        if self.err_func:
            self.err_func(strval)
            if self.tee_stderr:
                sys.stderr.write(strval)
                sys.stderr.flush()
        else:
            sys.stderr.write(strval)
            sys.stderr.flush()

    def write_status(self, strval: str) -> None:
        if self.status_func:
            self.status_func(strval)
