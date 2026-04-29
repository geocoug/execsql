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
    """Lightweight container for runtime status flags used by the metacommand engine.

    Tracks error conditions, halt-on-error policy, dialog cancellation state,
    and the current batch nesting level.
    """

    # A generic object to maintain status indicators.  These status
    # indicators are primarily those used in the metacommand
    # environment rather than for the program as a whole.
    def __init__(self) -> None:
        """Initialise all status flags to their default (non-error) values."""
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
    """Reads and merges ``execsql.conf`` INI files, exposing all options as attributes.

    Searches system, user, script-directory, and working-directory locations
    (in that order) and applies each file's settings cumulatively so that
    later files override earlier ones.
    """

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

    def _get_str(self, cp: ConfigParser, section: str, key: str, attr: str, *, required: bool = False) -> None:
        """Read a string option and set ``self.<attr>``.

        Args:
            cp: ConfigParser instance to read from.
            section: INI section name.
            key: Option key within the section.
            attr: Attribute name to set on ``self``.
            required: If ``True``, raise :class:`ConfigError` when the value is ``None``.
        """
        if cp.has_option(section, key):
            val = cp.get(section, key)
            if required and val is None:
                raise ConfigError(f"The {key} cannot be missing.")
            setattr(self, attr, val)

    def _get_enum(
        self,
        cp: ConfigParser,
        section: str,
        key: str,
        attr: str,
        choices: tuple,
        *,
        lower: bool = True,
    ) -> None:
        """Read a string option, validate against ``choices``, and set ``self.<attr>``.

        Args:
            cp: ConfigParser instance to read from.
            section: INI section name.
            key: Option key within the section.
            attr: Attribute name to set on ``self``.
            choices: Tuple of permitted values.
            lower: If ``True`` (default), lower-case the raw value before validation.
        """
        if cp.has_option(section, key):
            val = cp.get(section, key)
            if lower:
                val = val.lower()
            if val not in choices:
                raise ConfigError(f"Invalid argument to {key}: {val}")
            setattr(self, attr, val)

    def _get_bool(self, cp: ConfigParser, section: str, key: str, attr: str) -> None:
        """Read a boolean option and set ``self.<attr>``.

        Args:
            cp: ConfigParser instance to read from.
            section: INI section name.
            key: Option key within the section.
            attr: Attribute name to set on ``self``.

        Raises:
            ConfigError: If the value cannot be parsed as a boolean.
        """
        if cp.has_option(section, key):
            try:
                setattr(self, attr, cp.getboolean(section, key))
            except Exception as e:
                raise ConfigError(f"Invalid argument for {key}.") from e

    def _get_int(
        self,
        cp: ConfigParser,
        section: str,
        key: str,
        attr: str,
        *,
        multiply: int = 1,
        min_val: int | None = None,
    ) -> None:
        """Read an integer option, optionally multiply it, and set ``self.<attr>``.

        Args:
            cp: ConfigParser instance to read from.
            section: INI section name.
            key: Option key within the section.
            attr: Attribute name to set on ``self``.
            multiply: Multiply the parsed integer by this factor (default 1).
            min_val: If given, clamp the result to at least this value.

        Raises:
            ConfigError: If the value cannot be parsed as an integer.
        """
        if cp.has_option(section, key):
            try:
                val = cp.getint(section, key) * multiply
            except Exception as e:
                raise ConfigError(f"Invalid argument for {key}.") from e
            if min_val is not None:
                val = max(min_val, val)
            setattr(self, attr, val)

    def _get_float(
        self,
        cp: ConfigParser,
        section: str,
        key: str,
        attr: str,
        *,
        min_val: float | None = None,
    ) -> None:
        """Read a float option and set ``self.<attr>``.

        Args:
            cp: ConfigParser instance to read from.
            section: INI section name.
            key: Option key within the section.
            attr: Attribute name to set on ``self``.
            min_val: If given, raise :class:`ConfigError` when the value is below this minimum.

        Raises:
            ConfigError: If the value cannot be parsed as a float, or is below ``min_val``.
        """
        if cp.has_option(section, key):
            try:
                val = cp.getfloat(section, key)
            except Exception as e:
                raise ConfigError(f"Invalid argument for {key}.") from e
            if min_val is not None and val < min_val:
                raise ConfigError(f"Invalid {key}: {val}; must be >= {min_val}.")
            setattr(self, attr, val)

    def __init__(
        self,
        script_path: str,
        variable_pool: object,
        *,
        config_file: str | None = None,
    ) -> None:
        """Load and merge all discoverable execsql.conf files for the given script path.

        Args:
            script_path: Directory of the running script; used to locate a
                script-adjacent ``execsql.conf``.
            variable_pool: Substitution-variable registry used to expand
                ``config_file`` path values and to populate ``[variables]``
                sections.
            config_file: Optional explicit config file path (from ``--config``).
                Loaded after the implicit search paths so its values take
                precedence over system, user, script, and working-directory
                config files.
        """
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
        self.export_output_dir: str | None = None
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
        if config_file:
            config_files.append(str(Path(config_file).resolve()))
        from collections import deque

        _MAX_CONFIG_CHAIN = 20  # Guard against circular config_file references.
        config_queue: deque[str] = deque(config_files)
        self.files_read: list = []
        while config_queue:
            configfile = config_queue.popleft()
            if len(self.files_read) >= _MAX_CONFIG_CHAIN:
                break
            if configfile not in self.files_read and Path(configfile).is_file():
                self.files_read.append(configfile)
                cp = ConfigParser()
                cp.read(configfile)
                # --- [connect] ---
                if cp.has_option(self._CONNECT_SECTION, "db_type"):
                    t = cp.get(self._CONNECT_SECTION, "db_type").lower()
                    if t not in ("a", "d", "f", "k", "l", "m", "o", "p", "s"):
                        raise ConfigError(f"Invalid database type: {t}")
                    self.db_type = t
                self._get_str(cp, self._CONNECT_SECTION, "server", "server", required=True)
                self._get_str(cp, self._CONNECT_SECTION, "db", "db", required=True)
                self._get_int(cp, self._CONNECT_SECTION, "port", "port")
                self._get_str(cp, self._CONNECT_SECTION, "database", "db", required=True)
                self._get_str(cp, self._CONNECT_SECTION, "db_file", "db_file", required=True)
                self._get_str(cp, self._CONNECT_SECTION, "username", "username", required=True)
                self._get_str(cp, self._CONNECT_SECTION, "access_username", "access_username")
                self._get_bool(cp, self._CONNECT_SECTION, "password_prompt", "passwd_prompt")
                self._get_bool(cp, self._CONNECT_SECTION, "use_keyring", "use_keyring")
                self._get_bool(cp, self._CONNECT_SECTION, "new_db", "new_db")
                # --- [encoding] ---
                self._get_str(cp, self._ENCODING_SECTION, "database", "db_encoding")
                self._get_str(cp, self._ENCODING_SECTION, "script", "script_encoding", required=True)
                self._get_str(cp, self._ENCODING_SECTION, "import", "import_encoding", required=True)
                self._get_str(cp, self._ENCODING_SECTION, "output", "output_encoding", required=True)
                self._get_enum(
                    cp,
                    self._ENCODING_SECTION,
                    "error_response",
                    "enc_err_disposition",
                    ("ignore", "replace", "xmlcharrefreplace", "backslashreplace"),
                )
                # --- [input] ---
                self._get_int(cp, self._INPUT_SECTION, "max_int", "max_int")
                self._get_bool(cp, self._INPUT_SECTION, "boolean_int", "boolean_int")
                self._get_bool(cp, self._INPUT_SECTION, "boolean_words", "boolean_words")
                self._get_bool(cp, self._INPUT_SECTION, "empty_strings", "empty_strings")
                self._get_bool(cp, self._INPUT_SECTION, "only_strings", "only_strings")
                self._get_bool(cp, self._INPUT_SECTION, "empty_rows", "empty_rows")
                self._get_bool(cp, self._INPUT_SECTION, "delete_empty_columns", "del_empty_cols")
                self._get_bool(cp, self._INPUT_SECTION, "create_column_headers", "create_col_hdrs")
                self._get_enum(
                    cp,
                    self._INPUT_SECTION,
                    "trim_column_headers",
                    "trim_col_hdrs",
                    ("none", "both", "left", "right"),
                )
                self._get_bool(cp, self._INPUT_SECTION, "clean_column_headers", "clean_col_hdrs")
                self._get_enum(
                    cp,
                    self._INPUT_SECTION,
                    "fold_column_headers",
                    "fold_col_hdrs",
                    ("no", "lower", "upper"),
                )
                self._get_bool(cp, self._INPUT_SECTION, "dedup_column_headers", "dedup_col_hdrs")
                self._get_bool(cp, self._INPUT_SECTION, "trim_strings", "trim_strings")
                self._get_bool(cp, self._INPUT_SECTION, "replace_newlines", "replace_newlines")
                self._get_int(cp, self._INPUT_SECTION, "import_row_buffer", "import_row_buffer")
                self._get_int(cp, self._INPUT_SECTION, "import_progress_interval", "import_progress_interval")
                self._get_bool(cp, self._INPUT_SECTION, "show_progress", "show_progress")
                self._get_bool(cp, self._INPUT_SECTION, "access_use_numeric", "access_use_numeric")
                self._get_bool(cp, self._INPUT_SECTION, "import_only_common_columns", "import_common_cols_only")
                self._get_bool(cp, self._INPUT_SECTION, "import_common_columns_only", "import_common_cols_only")
                self._get_int(cp, self._INPUT_SECTION, "scan_lines", "scan_lines")
                self._get_int(cp, self._INPUT_SECTION, "import_buffer", "import_buffer", multiply=1024)
                # --- [output] ---
                self._get_bool(cp, self._OUTPUT_SECTION, "log_write_messages", "tee_write_log")
                self._get_int(cp, self._OUTPUT_SECTION, "hdf5_text_len", "hdf5_text_len")
                self._get_str(cp, self._OUTPUT_SECTION, "css_file", "css_file", required=True)
                self._get_str(cp, self._OUTPUT_SECTION, "css_styles", "css_styles", required=True)
                self._get_bool(cp, self._OUTPUT_SECTION, "make_export_dirs", "make_export_dirs")
                self._get_bool(cp, self._OUTPUT_SECTION, "quote_all_text", "quote_all_text")
                self._get_int(cp, self._OUTPUT_SECTION, "outfile_open_timeout", "outfile_open_timeout")
                self._get_int(cp, self._OUTPUT_SECTION, "export_row_buffer", "export_row_buffer")
                self._get_enum(
                    cp,
                    self._OUTPUT_SECTION,
                    "template_processor",
                    "template_processor",
                    ("jinja",),
                )
                self._get_int(cp, self._OUTPUT_SECTION, "zip_buffer_mb", "zip_buffer_mb")
                # --- [interface] ---
                self._get_bool(cp, self._INTERFACE_SECTION, "write_warnings", "write_warnings")
                # write_prefix / write_suffix have special "clear" → None handling
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
                # gui_level is an integer enum — keep inline to preserve exact error message
                if cp.has_option(self._INTERFACE_SECTION, "gui_level"):
                    self.gui_level = cp.getint(self._INTERFACE_SECTION, "gui_level")
                    if self.gui_level not in (0, 1, 2, 3):
                        raise ConfigError(f"Invalid GUI level: {self.gui_level}")
                # gui_framework has a specific error message — keep inline
                if cp.has_option(self._INTERFACE_SECTION, "gui_framework"):
                    fw = cp.get(self._INTERFACE_SECTION, "gui_framework").lower()
                    if fw not in ("tkinter", "textual"):
                        raise ConfigError("gui_framework must be 'tkinter' or 'textual'.")
                    self.gui_framework = fw
                self._get_int(cp, self._INTERFACE_SECTION, "console_height", "gui_console_height", min_val=5)
                self._get_int(cp, self._INTERFACE_SECTION, "console_width", "gui_console_width", min_val=20)
                self._get_bool(cp, self._INTERFACE_SECTION, "console_wait_when_done", "gui_wait_on_exit")
                self._get_bool(cp, self._INTERFACE_SECTION, "console_wait_when_error_halt", "gui_wait_on_error_halt")
                # --- [config] ---
                # config_file / OS-specific config files retain special chaining logic
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
                        config_queue.appendleft(conffile)
                # OS-specific additional config files.
                _os_config_key: str | None = None
                if sys.platform == "linux" and cp.has_option(self._CONFIG_SECTION, "linux_config_file"):
                    _os_config_key = "linux_config_file"
                elif sys.platform == "darwin" and cp.has_option(self._CONFIG_SECTION, "macos_config_file"):
                    _os_config_key = "macos_config_file"
                elif os.name == "nt" and cp.has_option(self._CONFIG_SECTION, "win_config_file"):
                    _os_config_key = "win_config_file"
                if _os_config_key:
                    conffile = cp.get(self._CONFIG_SECTION, _os_config_key)
                    if conffile and conffile[0] == "~":
                        if len(conffile) == 1:
                            conffile = str(Path("~").expanduser())
                        elif len(conffile) > 1 and conffile[1] == os.sep:
                            conffile = str(Path("~").expanduser() / conffile[2:])
                    conffile = variable_pool.substitute(conffile)[0]
                    if not Path(conffile).is_file():
                        conffile = str(Path(conffile) / self.config_file_name)
                    if Path(conffile).is_file():
                        config_queue.appendleft(conffile)
                self._get_bool(cp, self._CONFIG_SECTION, "user_logfile", "user_logfile")
                # dao_flush_delay_secs has a specific error message — keep inline
                if cp.has_option(self._CONFIG_SECTION, "dao_flush_delay_secs"):
                    self.dao_flush_delay_secs = cp.getfloat(self._CONFIG_SECTION, "dao_flush_delay_secs")
                    if self.dao_flush_delay_secs < 5.0:
                        raise ConfigError(
                            f"Invalid DAO flush delay: {self.dao_flush_delay_secs}; must be >= 5.0.",
                        )
                self._get_bool(cp, self._CONFIG_SECTION, "log_datavars", "log_datavars")
                self._get_bool(cp, self._CONFIG_SECTION, "log_sql", "log_sql")
                self._get_int(cp, self._CONFIG_SECTION, "max_log_size_mb", "max_log_size_mb")
                # --- [email] ---
                self._get_str(cp, self._EMAIL_SECTION, "host", "smtp_host")
                self._get_int(cp, self._EMAIL_SECTION, "port", "smtp_port")
                self._get_str(cp, self._EMAIL_SECTION, "username", "smtp_username")
                self._get_str(cp, self._EMAIL_SECTION, "password", "smtp_password")
                # enc_password has special decryption logic — keep inline
                if cp.has_option(self._EMAIL_SECTION, "enc_password"):
                    import warnings

                    warnings.warn(
                        "enc_password provides obfuscation only, not encryption. "
                        "Use keyring or environment variables for credential storage.",
                        DeprecationWarning,
                        stacklevel=1,
                    )
                    self.smtp_password = Encrypt().decrypt(cp.get(self._EMAIL_SECTION, "enc_password"))
                self._get_bool(cp, self._EMAIL_SECTION, "use_ssl", "smtp_ssl")
                self._get_bool(cp, self._EMAIL_SECTION, "use_tls", "smtp_tls")
                # email_format has a specific error message — keep inline
                if cp.has_option(self._EMAIL_SECTION, "email_format"):
                    fmt = cp.get(self._EMAIL_SECTION, "email_format").lower()
                    if fmt not in ("plain", "html"):
                        raise ConfigError(f"Invalid email format: {fmt}")
                    self.email_format = fmt
                self._get_str(cp, self._EMAIL_SECTION, "message_css", "email_css")
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
    """Thin wrapper around stdout/stderr that supports GUI or test-harness redirection.

    Each output hook is a callable that accepts a single string.  When a hook
    is ``None`` the default ``sys.stdout`` or ``sys.stderr`` is used.
    """

    def __repr__(self) -> str:
        return f"WriteHooks({self.write_func!r}, {self.err_func!r}, {self.status_func!r})"

    def __init__(
        self,
        standard_output_func: object = None,
        error_output_func: object = None,
        status_output_func: object = None,
    ) -> None:
        """Store optional hook callables; ``None`` means use the default stream.

        Args:
            standard_output_func: Callable to receive standard-output text, or
                ``None`` to use ``sys.stdout``.
            error_output_func: Callable to receive error-output text, or
                ``None`` to use ``sys.stderr``.
            status_output_func: Callable to receive status-line text, or
                ``None`` to suppress.
        """
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
        """Reset both output hooks to ``None``, restoring stdout/stderr behaviour."""
        # Resets output to stdout and stderr.
        self.write_func = None
        self.err_func = None

    def redir_stdout(self, standard_output_func: object) -> None:
        """Replace the standard-output hook with the given callable."""
        self.write_func = standard_output_func

    def redir_stderr(self, error_output_func: object, tee: bool = True) -> None:
        """Replace the error-output hook and optionally keep tee-to-stderr behaviour."""
        self.err_func = error_output_func
        self.tee_stderr = tee

    def redir(self, standard_output_func: object, error_output_func: object) -> None:
        """Redirect both stdout and stderr hooks in one call."""
        self.redir_stdout(standard_output_func)
        self.redir_stderr(error_output_func)

    def write(self, strval: str) -> None:
        """Write a string to the standard-output hook, or to sys.stdout if unset."""
        if self.write_func:
            self.write_func(strval)
        else:
            sys.stdout.write(strval)
            sys.stdout.flush()

    def write_err(self, strval: str) -> None:
        """Write an error string to the error-output hook, or to sys.stderr if unset."""
        if not strval.endswith("\n"):
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
        """Forward a status string to the status hook if one is registered."""
        if self.status_func:
            self.status_func(strval)
