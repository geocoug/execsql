"""
Tests for execsql.config.ConfigData.

ConfigData reads one or more execsql.conf INI files.  Tests here either use
a temporary directory with no config files (exercising default values) or
write minimal config files to exercise specific option parsing.

All tests restore any global state they modify.
"""

from __future__ import annotations

import os
import textwrap

import pytest

from execsql.config import ConfigData
from execsql.exceptions import ConfigError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conf(script_path: str, variable_pool=None) -> ConfigData:
    """Construct ConfigData with no config files in the test path."""
    return ConfigData(script_path, variable_pool)


def _write_conf(path: str, content: str) -> str:
    """Write an execsql.conf file to *path* and return the file path."""
    fpath = os.path.join(path, "execsql.conf")
    with open(fpath, "w") as f:
        f.write(textwrap.dedent(content))
    return fpath


# ---------------------------------------------------------------------------
# Default values (no config files present)
# ---------------------------------------------------------------------------


class TestConfigDataDefaults:
    def test_no_config_files_read(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.files_read == []

    def test_default_db_type(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.db_type == "l"

    def test_default_server_none(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.server is None

    def test_default_port_none(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.port is None

    def test_default_db_none(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.db is None

    def test_default_username_none(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.username is None

    def test_default_passwd_prompt_true(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.passwd_prompt is True

    def test_default_output_encoding(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.output_encoding == "utf8"

    def test_default_script_encoding(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.script_encoding == "utf8"

    def test_default_import_encoding(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.import_encoding == "utf8"

    def test_default_max_int(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.max_int == 2_147_483_647

    def test_default_boolean_int_true(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.boolean_int is True

    def test_default_boolean_words_false(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.boolean_words is False

    def test_default_gui_level_zero(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.gui_level == 0

    def test_default_scan_lines(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.scan_lines == 100

    def test_default_make_export_dirs_false(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.make_export_dirs is False

    def test_default_empty_strings_true(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.empty_strings is True

    def test_default_include_lists_empty(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.include_req == []
        assert cd.include_opt == []


# ---------------------------------------------------------------------------
# Config file parsing — connect section
# ---------------------------------------------------------------------------


class TestConfigDataConnect:
    def test_reads_db_type(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            db_type = l
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.db_type == "l"

    def test_invalid_db_type_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            db_type = z
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_server(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            server = myserver
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.server == "myserver"

    def test_reads_db(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            db = mydb
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.db == "mydb"

    def test_reads_database_alias(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            database = altdb
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.db == "altdb"

    def test_reads_port(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            port = 5432
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.port == 5432

    def test_invalid_port_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            port = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_username(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            username = alice
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.username == "alice"

    def test_reads_new_db(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            new_db = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.new_db is True

    def test_reads_db_file(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            db_file = /tmp/test.db
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.db_file == "/tmp/test.db"

    def test_reads_access_username(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            access_username = admin
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.access_username == "admin"

    def test_reads_password_prompt_false(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            password_prompt = false
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.passwd_prompt is False

    def test_invalid_password_prompt_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            password_prompt = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_use_keyring_false(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            use_keyring = false
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.use_keyring is False

    def test_invalid_use_keyring_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            use_keyring = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_new_db_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [connect]
            new_db = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))


# ---------------------------------------------------------------------------
# Config file parsing — encoding section
# ---------------------------------------------------------------------------


class TestConfigDataEncoding:
    def test_reads_output_encoding(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [encoding]
            output = latin-1
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.output_encoding == "latin-1"

    def test_reads_script_encoding(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [encoding]
            script = utf-16
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.script_encoding == "utf-16"

    def test_reads_import_encoding(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [encoding]
            import = ascii
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_encoding == "ascii"

    def test_reads_database_encoding(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [encoding]
            database = latin-1
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.db_encoding == "latin-1"

    def test_reads_error_response_ignore(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [encoding]
            error_response = ignore
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.enc_err_disposition == "ignore"

    def test_invalid_error_response_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [encoding]
            error_response = badvalue
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))


# ---------------------------------------------------------------------------
# Config file parsing — output section
# ---------------------------------------------------------------------------


class TestConfigDataOutput:
    def test_reads_scan_lines(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            scan_lines = 200
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.scan_lines == 200

    def test_reads_make_export_dirs(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            make_export_dirs = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.make_export_dirs is True

    def test_reads_write_prefix(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_prefix = >>
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.write_prefix == ">>"


# ---------------------------------------------------------------------------
# Config file parsing — interface section
# ---------------------------------------------------------------------------


class TestConfigDataInterface:
    def test_reads_gui_level(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            gui_level = 1
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_level == 1

    def test_gui_level_out_of_range_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            gui_level = 9
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))


# ---------------------------------------------------------------------------
# Config file parsing — input section
# ---------------------------------------------------------------------------


class TestConfigDataInput:
    def test_reads_boolean_int_false(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            boolean_int = false
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.boolean_int is False

    def test_invalid_boolean_int_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            boolean_int = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_boolean_words_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            boolean_words = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.boolean_words is True

    def test_invalid_boolean_words_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            boolean_words = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_empty_strings_false(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            empty_strings = false
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.empty_strings is False

    def test_invalid_empty_strings_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            empty_strings = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_trim_strings_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            trim_strings = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.trim_strings is True

    def test_invalid_trim_strings_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            trim_strings = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_scan_lines(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            scan_lines = 500
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.scan_lines == 500

    def test_invalid_scan_lines_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            scan_lines = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_max_int(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            max_int = 999999
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.max_int == 999999

    def test_invalid_max_int_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            max_int = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_trim_column_headers(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            trim_column_headers = both
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.trim_col_hdrs == "both"

    def test_invalid_trim_column_headers_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            trim_column_headers = center
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_fold_column_headers_lower(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            fold_column_headers = lower
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.fold_col_hdrs == "lower"

    def test_invalid_fold_column_headers_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            fold_column_headers = mixed
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_import_buffer(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_buffer = 64
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_buffer == 64 * 1024

    def test_reads_delete_empty_columns_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            delete_empty_columns = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.del_empty_cols is True

    def test_reads_create_column_headers_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            create_column_headers = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.create_col_hdrs is True

    def test_reads_clean_column_headers_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            clean_column_headers = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.clean_col_hdrs is True

    def test_reads_dedup_column_headers_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            dedup_column_headers = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.dedup_col_hdrs is True

    def test_reads_only_strings_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            only_strings = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.only_strings is True

    def test_reads_only_strings_false(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            only_strings = false
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.only_strings is False

    def test_invalid_only_strings_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            only_strings = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_replace_newlines_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            replace_newlines = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.replace_newlines is True

    def test_reads_replace_newlines_false(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            replace_newlines = false
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.replace_newlines is False

    def test_invalid_replace_newlines_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            replace_newlines = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_import_row_buffer(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_row_buffer = 500
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_row_buffer == 500

    def test_default_import_row_buffer(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.import_row_buffer == 1000

    def test_invalid_import_row_buffer_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_row_buffer = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_empty_rows_false(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            empty_rows = false
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.empty_rows is False

    def test_invalid_empty_rows_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            empty_rows = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_access_use_numeric_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            access_use_numeric = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.access_use_numeric is True

    def test_invalid_access_use_numeric_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            access_use_numeric = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_import_common_columns_only(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_common_columns_only = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_common_cols_only is True

    def test_reads_import_only_common_columns(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_only_common_columns = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_common_cols_only is True

    def test_reads_import_progress_interval(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_progress_interval = 5000
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_progress_interval == 5000

    def test_default_import_progress_interval(self, tmp_path):
        cd = _make_conf(str(tmp_path))
        assert cd.import_progress_interval == 0

    def test_invalid_delete_empty_columns_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            delete_empty_columns = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_create_column_headers_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            create_column_headers = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_clean_column_headers_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            clean_column_headers = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_dedup_column_headers_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            dedup_column_headers = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_access_use_numeric_via_input_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            access_use_numeric = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_import_only_common_columns_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_only_common_columns = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_import_common_columns_only_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_common_columns_only = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_import_progress_interval_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_progress_interval = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))


# ---------------------------------------------------------------------------
# Config file parsing — extended output section
# ---------------------------------------------------------------------------


class TestConfigDataOutputExtended:
    def test_reads_quote_all_text_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            quote_all_text = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.quote_all_text is True

    def test_invalid_quote_all_text_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            quote_all_text = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_template_processor_jinja(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            template_processor = jinja
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.template_processor == "jinja"

    def test_invalid_template_processor_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            template_processor = mako
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_zip_buffer_mb(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            zip_buffer_mb = 50
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.zip_buffer_mb == 50

    def test_invalid_zip_buffer_mb_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            zip_buffer_mb = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_hdf5_text_len_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            hdf5_text_len = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_log_write_messages_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            log_write_messages = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_make_export_dirs_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            make_export_dirs = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_outfile_open_timeout_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            outfile_open_timeout = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_export_row_buffer_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            export_row_buffer = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_zip_buffer_mb_via_output_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            zip_buffer_mb = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_outfile_open_timeout(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            outfile_open_timeout = 120
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.outfile_open_timeout == 120

    def test_reads_export_row_buffer(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            export_row_buffer = 500
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.export_row_buffer == 500

    def test_reads_css_styles(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            css_styles = body { color: red; }
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.css_styles == "body { color: red; }"

    def test_reads_hdf5_text_len(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            hdf5_text_len = 2000
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.hdf5_text_len == 2000

    def test_reads_css_file(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            css_file = styles.css
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.css_file == "styles.css"

    def test_reads_log_write_messages_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            log_write_messages = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.tee_write_log is True


# ---------------------------------------------------------------------------
# Config file parsing — extended interface section
# ---------------------------------------------------------------------------


class TestConfigDataInterfaceExtended:
    def test_reads_gui_framework_textual(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            gui_framework = textual
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_framework == "textual"

    def test_reads_gui_framework_tkinter(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            gui_framework = tkinter
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_framework == "tkinter"

    def test_invalid_gui_framework_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            gui_framework = qt
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_write_suffix(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_suffix = <<
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.write_suffix == "<<"

    def test_write_suffix_clear(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_suffix = clear
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.write_suffix is None

    def test_write_prefix_clear(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_prefix = clear
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.write_prefix is None

    def test_reads_write_warnings_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_warnings = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.write_warnings is True

    def test_reads_console_height(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_height = 40
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_console_height == 40

    def test_console_height_minimum_clamped(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_height = 1
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_console_height == 5  # clamped to max(5, 1)

    def test_reads_console_width(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_width = 120
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_console_width == 120

    def test_console_width_minimum_clamped(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_width = 5
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_console_width == 20  # clamped to max(20, 5)

    def test_reads_console_wait_when_done(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_wait_when_done = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_wait_on_exit is True

    def test_invalid_write_warnings_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_warnings = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_console_height_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_height = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_console_width_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_width = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_console_wait_when_done_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_wait_when_done = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_console_wait_when_error_halt_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_wait_when_error_halt = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_console_wait_when_error_halt(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_wait_when_error_halt = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_wait_on_error_halt is True


# ---------------------------------------------------------------------------
# Config file parsing — config section
# ---------------------------------------------------------------------------


class TestConfigDataConfigSection:
    def test_reads_dao_flush_delay_secs(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            dao_flush_delay_secs = 10.0
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.dao_flush_delay_secs == 10.0

    def test_dao_flush_delay_too_small_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            dao_flush_delay_secs = 1.0
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_log_datavars_false(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            log_datavars = false
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.log_datavars is False

    def test_reads_user_logfile_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            user_logfile = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.user_logfile is True

    def test_reads_max_log_size_mb(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            max_log_size_mb = 50
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.max_log_size_mb == 50

    def test_invalid_max_log_size_mb_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            max_log_size_mb = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_log_datavars_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            log_datavars = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))


# ---------------------------------------------------------------------------
# Config file parsing — email section
# ---------------------------------------------------------------------------


class TestConfigDataEmail:
    def test_reads_smtp_host(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            host = mail.example.com
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.smtp_host == "mail.example.com"

    def test_reads_smtp_port(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            port = 587
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.smtp_port == 587

    def test_invalid_smtp_port_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            port = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_smtp_username(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            username = user@example.com
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.smtp_username == "user@example.com"

    def test_reads_smtp_password(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            password = secret
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.smtp_password == "secret"

    def test_reads_use_ssl_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            use_ssl = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.smtp_ssl is True

    def test_invalid_use_ssl_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            use_ssl = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_use_tls_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            use_tls = true
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.smtp_tls is True

    def test_reads_email_format_html(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            email_format = html
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.email_format == "html"

    def test_reads_email_css(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            message_css = body { color: blue; }
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.email_css == "body { color: blue; }"

    def test_invalid_use_tls_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            use_tls = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_use_ssl_via_email_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            use_ssl = notabool
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_invalid_import_buffer_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_buffer = notanumber
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_invalid_email_format_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            email_format = rtf
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))


# ---------------------------------------------------------------------------
# Config file parsing — include sections
# ---------------------------------------------------------------------------


class TestConfigDataVariables:
    def test_reads_variables_section(self, tmp_path):
        class FakePool:
            def var_name_ok(self, name):
                return True

            def add_substitution(self, sub, repl):
                self.last_sub = sub
                self.last_repl = repl

            def substitute(self, s):
                return (s,)

        pool = FakePool()
        _write_conf(
            str(tmp_path),
            """
            [variables]
            myvar = myvalue
        """,
        )
        _make_conf(str(tmp_path), variable_pool=pool)
        assert pool.last_sub == "myvar"
        assert pool.last_repl == "myvalue"

    def test_invalid_variable_name_raises(self, tmp_path):
        class FakePool:
            def var_name_ok(self, name):
                return False

            def substitute(self, s):
                return (s,)

        _write_conf(
            str(tmp_path),
            """
            [variables]
            bad!name = value
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path), variable_pool=FakePool())


class TestConfigDataIncludes:
    def test_include_req_nonexistent_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [include_required]
            1 = /no/such/file.sql
        """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_include_req_existing_file_added(self, tmp_path):
        inc = tmp_path / "inc.sql"
        inc.write_text("-- included")
        _write_conf(
            str(tmp_path),
            f"""
            [include_required]
            1 = {inc}
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert str(inc) in cd.include_req

    def test_include_opt_nonexistent_silently_ignored(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [include_optional]
            1 = /no/such/file.sql
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.include_opt == []

    def test_include_opt_existing_file_added(self, tmp_path):
        inc = tmp_path / "opt.sql"
        inc.write_text("-- optional")
        _write_conf(
            str(tmp_path),
            f"""
            [include_optional]
            1 = {inc}
        """,
        )
        cd = _make_conf(str(tmp_path))
        assert str(inc) in cd.include_opt


# ---------------------------------------------------------------------------
# Explicit --config file (config_file kwarg)
# ---------------------------------------------------------------------------


class TestConfigFileKwarg:
    """Tests for the ``config_file`` keyword argument added for ``--config``."""

    def test_explicit_config_file_is_loaded(self, tmp_path):
        """An explicit config file should be read even with no implicit configs."""
        conf = tmp_path / "custom.conf"
        conf.write_text("[connect]\ndb_type = p\n")
        cd = ConfigData(str(tmp_path), None, config_file=str(conf))
        assert cd.db_type == "p"
        assert str(conf.resolve()) in cd.files_read

    def test_explicit_config_file_not_given(self, tmp_path):
        """When config_file is None, behaviour is unchanged."""
        cd = ConfigData(str(tmp_path), None, config_file=None)
        assert cd.db_type == "l"  # default

    def test_explicit_config_overrides_cwd_config(self, tmp_path):
        """The --config file is loaded after the working-dir config, so it wins."""
        # Write a CWD config that sets db_type=s
        _write_conf(str(tmp_path), "[connect]\ndb_type = s\n")
        # Write an explicit config that sets db_type=p
        explicit = tmp_path / "override.conf"
        explicit.write_text("[connect]\ndb_type = p\n")
        cd = ConfigData(str(tmp_path), None, config_file=str(explicit))
        assert cd.db_type == "p"

    def test_explicit_config_overrides_cwd_partial(self, tmp_path):
        """Explicit config overrides only the keys it sets; others survive."""
        _write_conf(str(tmp_path), "[connect]\ndb_type = s\nserver = oldhost\n")
        explicit = tmp_path / "override.conf"
        explicit.write_text("[connect]\ndb_type = p\n")
        cd = ConfigData(str(tmp_path), None, config_file=str(explicit))
        assert cd.db_type == "p"
        assert cd.server == "oldhost"  # not overridden

    def test_explicit_config_chains_additional_files(self, tmp_path):
        """An explicit config file can chain further configs via [config] section."""

        class FakePool:
            def substitute(self, s):
                return (s,)

        chained = tmp_path / "chained.conf"
        chained.write_text("[connect]\nport = 9999\n")
        explicit = tmp_path / "main.conf"
        explicit.write_text(f"[config]\nconfig_file = {chained}\n")
        cd = ConfigData(str(tmp_path), FakePool(), config_file=str(explicit))
        assert cd.port == 9999

    def test_explicit_config_recorded_in_files_read(self, tmp_path):
        conf = tmp_path / "tracked.conf"
        conf.write_text("[connect]\ndb_type = l\n")
        cd = ConfigData(str(tmp_path), None, config_file=str(conf))
        assert str(conf.resolve()) in cd.files_read
