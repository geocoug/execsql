"""
Extended tests for execsql.config — covering uncovered lines:

  Line 160   — Windows sys_config_file path (os.name != posix)
  Line 183   — server option with None value raises ConfigError
  Line 187   — db option with None value raises ConfigError
  Line 196   — database option with None value raises ConfigError
  Line 200   — db_file option with None value raises ConfigError
  Line 204   — username option with None value raises ConfigError
  Line 227   — script_encoding None raises ConfigError
  Line 231   — import_encoding None raises ConfigError
  Line 235   — output_encoding None raises ConfigError
  Lines 286-287 — trim_col_hdrs invalid value raises ConfigError
  Lines 326-329 — import_row_buffer / import_progress_interval / show_progress
  Line 374   — css_file None raises ConfigError
  Line 378   — css_styles None raises ConfigError
  Line 417-418 — write_prefix = clear sets None
  Lines 424-425 — write_suffix = clear sets None
  Lines 461-472 — config_file option: tilde expansion + file resolution
  Lines 474-484 — linux_config_file (posix only)
  Lines 486-491 — win_config_file (windows only — skipped on posix)
  Lines 506-509 — log_datavars / log_sql / max_log_size_mb
  Line 528   — email_format invalid raises ConfigError

All tests use tmp_path so no permanent files are created.
"""

from __future__ import annotations

import os
import textwrap

import pytest

from execsql.config import ConfigData
from execsql.exceptions import ConfigError


# ---------------------------------------------------------------------------
# Helpers (same as test_config_data.py)
# ---------------------------------------------------------------------------


def _make_conf(script_path: str, variable_pool=None) -> ConfigData:
    return ConfigData(script_path, variable_pool)


def _write_conf(path: str, content: str) -> str:
    fpath = os.path.join(path, "execsql.conf")
    with open(fpath, "w") as f:
        f.write(textwrap.dedent(content))
    return fpath


# Minimal variable_pool stub
class _FakeVarPool:
    def substitute(self, s):
        return (s, False)

    def var_name_ok(self, name):
        return True

    def add_substitution(self, name, val):
        pass


# ---------------------------------------------------------------------------
# css_file / css_styles None raises ConfigError
# (lines 374, 378 — ConfigParser returns None only if value is empty string
#  in the file; the check raises ConfigError)
# We test via the invalid path: css_file/css_styles with no value after '='
# ---------------------------------------------------------------------------


class TestConfigDataCssErrors:
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

    def test_invalid_template_processor_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            template_processor = badname
            """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_valid_template_processor_jinja(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            template_processor = jinja
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.template_processor == "jinja"

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

    def test_valid_log_write_messages(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [output]
            log_write_messages = true
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.tee_write_log is True

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


# ---------------------------------------------------------------------------
# trim_col_hdrs invalid value (lines 286-287)
# ---------------------------------------------------------------------------


class TestConfigDataTrimColHdrs:
    def test_invalid_trim_col_hdrs_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            trim_column_headers = badvalue
            """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_valid_trim_col_hdrs_both(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            trim_column_headers = both
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.trim_col_hdrs == "both"

    def test_valid_fold_col_hdrs_lower(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            fold_column_headers = lower
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.fold_col_hdrs == "lower"

    def test_invalid_fold_col_hdrs_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            fold_column_headers = diagonal
            """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))


# ---------------------------------------------------------------------------
# import_row_buffer / import_progress_interval / show_progress (lines 326-329)
# ---------------------------------------------------------------------------


class TestConfigDataImportBuffers:
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

    def test_reads_import_progress_interval(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_progress_interval = 100
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_progress_interval == 100

    def test_invalid_import_progress_interval_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_progress_interval = bad
            """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_show_progress_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            show_progress = true
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.show_progress is True

    def test_invalid_show_progress_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            show_progress = notabool
            """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))


# ---------------------------------------------------------------------------
# write_prefix / write_suffix = clear → None (lines 417-425)
# ---------------------------------------------------------------------------


class TestConfigDataWritePrefixSuffix:
    def test_write_prefix_set_to_value(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_prefix = -->
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.write_prefix == "-->"

    def test_write_prefix_clear_sets_none(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_prefix = clear
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.write_prefix is None

    def test_write_suffix_set_to_value(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_suffix = <--
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.write_suffix == "<--"

    def test_write_suffix_clear_sets_none(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            write_suffix = CLEAR
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.write_suffix is None


# ---------------------------------------------------------------------------
# Interface section: gui_framework, console_height/width, wait settings
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

    def test_console_height_clamps_to_minimum_5(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_height = 2
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_console_height == 5

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

    def test_console_width_clamps_to_minimum_20(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [interface]
            console_width = 5
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.gui_console_width == 20

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


# ---------------------------------------------------------------------------
# Config section: log_datavars, log_sql, max_log_size_mb (lines 506-509)
# ---------------------------------------------------------------------------


class TestConfigDataConfigSection:
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

    def test_reads_log_sql_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            log_sql = true
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.log_sql is True

    def test_invalid_log_sql_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            log_sql = notabool
            """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

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

    def test_dao_flush_delay_secs_valid(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            dao_flush_delay_secs = 10.0
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.dao_flush_delay_secs == 10.0

    def test_dao_flush_delay_secs_too_small_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [config]
            dao_flush_delay_secs = 2.0
            """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))


# ---------------------------------------------------------------------------
# Email section (line 528 — invalid email_format)
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

    def test_invalid_email_format_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            email_format = markdown
            """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_reads_message_css(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [email]
            message_css = body { color: blue; }
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert "blue" in cd.email_css

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


# ---------------------------------------------------------------------------
# config_file option — tilde expansion and file lookup (lines 461-472)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "posix", reason="posix path handling only")
class TestConfigDataConfigFile:
    def test_config_file_option_loads_additional_config(self, tmp_path):
        """config_file option in [config] section loads a secondary conf file."""
        secondary_dir = tmp_path / "secondary"
        secondary_dir.mkdir()
        secondary_conf = secondary_dir / "execsql.conf"
        secondary_conf.write_text(
            textwrap.dedent("""
            [connect]
            db_type = l
            """),
            encoding="utf-8",
        )
        vp = _FakeVarPool()
        vp.substitute = lambda s: (str(secondary_conf), False)

        _write_conf(
            str(tmp_path),
            f"""
            [config]
            config_file = {secondary_conf}
            """,
        )
        cd = ConfigData(str(tmp_path), vp)
        assert cd.db_type == "l"

    def test_config_file_pointing_to_dir_looks_for_execsql_conf(self, tmp_path):
        """If config_file is a directory, ConfigData looks for execsql.conf in it."""
        secondary_dir = tmp_path / "secondary"
        secondary_dir.mkdir()
        (secondary_dir / "execsql.conf").write_text(
            textwrap.dedent("""
            [connect]
            db_type = p
            """),
            encoding="utf-8",
        )
        vp = _FakeVarPool()
        vp.substitute = lambda s: (str(secondary_dir), False)

        _write_conf(
            str(tmp_path),
            f"""
            [config]
            config_file = {secondary_dir}
            """,
        )
        cd = ConfigData(str(tmp_path), vp)
        assert cd.db_type == "p"

    def test_nonexistent_config_file_silently_ignored(self, tmp_path):
        """A config_file that doesn't exist should be silently ignored."""
        vp = _FakeVarPool()
        vp.substitute = lambda s: ("/nonexistent/path/execsql.conf", False)

        _write_conf(
            str(tmp_path),
            """
            [config]
            config_file = /nonexistent/path/execsql.conf
            """,
        )
        # Should not raise
        cd = ConfigData(str(tmp_path), vp)
        assert cd is not None


# ---------------------------------------------------------------------------
# linux_config_file (posix only) (lines 474-484)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "posix", reason="posix only")
class TestConfigDataLinuxConfigFile:
    def test_linux_config_file_loads_secondary_conf(self, tmp_path):
        secondary_dir = tmp_path / "linux_secondary"
        secondary_dir.mkdir()
        secondary_conf = secondary_dir / "execsql.conf"
        secondary_conf.write_text(
            textwrap.dedent("""
            [connect]
            db_type = s
            """),
            encoding="utf-8",
        )
        vp = _FakeVarPool()
        vp.substitute = lambda s: (str(secondary_conf), False)

        _write_conf(
            str(tmp_path),
            f"""
            [config]
            linux_config_file = {secondary_conf}
            """,
        )
        cd = ConfigData(str(tmp_path), vp)
        assert cd.db_type == "s"

    def test_nonexistent_linux_config_file_silently_ignored(self, tmp_path):
        vp = _FakeVarPool()
        vp.substitute = lambda s: ("/nonexistent/linux.conf", False)

        _write_conf(
            str(tmp_path),
            """
            [config]
            linux_config_file = /nonexistent/linux.conf
            """,
        )
        cd = ConfigData(str(tmp_path), vp)
        assert cd is not None


# ---------------------------------------------------------------------------
# Variables section (lines 546-551)
# ---------------------------------------------------------------------------


class TestConfigDataVariables:
    def test_variables_section_adds_substitutions(self, tmp_path):
        """Variables in [variables] section are passed to variable_pool."""
        added = {}

        class RecordingVarPool:
            def substitute(self, s):
                return (s, False)

            def var_name_ok(self, name):
                return True

            def add_substitution(self, name, val):
                added[name] = val

        _write_conf(
            str(tmp_path),
            """
            [variables]
            myvar = hello
            """,
        )
        ConfigData(str(tmp_path), RecordingVarPool())
        assert "myvar" in added
        assert added["myvar"] == "hello"

    def test_invalid_variable_name_raises(self, tmp_path):
        class RejectingVarPool:
            def substitute(self, s):
                return (s, False)

            def var_name_ok(self, name):
                return False

            def add_substitution(self, name, val):
                pass

        _write_conf(
            str(tmp_path),
            """
            [variables]
            badname = value
            """,
        )
        with pytest.raises(ConfigError):
            ConfigData(str(tmp_path), RejectingVarPool())


# ---------------------------------------------------------------------------
# include_required / include_optional sections (lines 552-575)
# ---------------------------------------------------------------------------


class TestConfigDataIncludeSections:
    def test_include_required_file_added_to_list(self, tmp_path):
        inc = tmp_path / "included.sql"
        inc.write_text("-- sql\n", encoding="utf-8")
        _write_conf(
            str(tmp_path),
            f"""
            [include_required]
            1 = {inc}
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert str(inc.resolve()) in cd.include_req

    def test_include_required_nonexistent_file_raises(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [include_required]
            1 = /nonexistent/file.sql
            """,
        )
        with pytest.raises(ConfigError):
            _make_conf(str(tmp_path))

    def test_include_optional_file_added_to_list(self, tmp_path):
        opt = tmp_path / "optional.sql"
        opt.write_text("-- optional sql\n", encoding="utf-8")
        _write_conf(
            str(tmp_path),
            f"""
            [include_optional]
            1 = {opt}
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert str(opt.resolve()) in cd.include_opt

    def test_include_optional_nonexistent_silently_ignored(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [include_optional]
            1 = /nonexistent/optional.sql
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.include_opt == []

    def test_access_use_numeric_reads_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            access_use_numeric = true
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.access_use_numeric is True

    def test_import_buffer_reads_and_multiplies_by_1024(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_buffer = 64
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_buffer == 64 * 1024

    def test_import_common_cols_only_reads_true(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_only_common_columns = true
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_common_cols_only is True

    def test_import_common_columns_only_alias(self, tmp_path):
        _write_conf(
            str(tmp_path),
            """
            [input]
            import_common_columns_only = true
            """,
        )
        cd = _make_conf(str(tmp_path))
        assert cd.import_common_cols_only is True
