"""Unit tests for execsql metacommand handlers in metacommands/data.py.

Covers x_sub_ini, x_sub_querystring, x_sub_encrypt, x_sub_decrypt,
x_subdata, x_selectsub, counter operations, flag setters, and x_max_int.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.script import CounterVars, SubVarSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_subvars():
    sv = SubVarSet()
    _state.subvars = sv
    return sv


def _setup_exec_log():
    mock_log = MagicMock()
    _state.exec_log = mock_log
    return mock_log


def _setup_commandliststack():
    """Set up a commandliststack with a localvars for SUB LOCAL tests."""
    local_sv = SubVarSet()
    mock_cl = MagicMock()
    mock_cl.localvars = local_sv
    mock_cl.current_command.return_value = SimpleNamespace(
        current_script_line=lambda: ("test.sql", 1),
    )
    _state.commandliststack = [mock_cl]
    return local_sv


# ---------------------------------------------------------------------------
# x_sub_ini
# ---------------------------------------------------------------------------


class TestXSubIni:
    def test_loads_variables_from_ini(self, minimal_conf, tmp_path):
        from execsql.metacommands.data import x_sub_ini

        sv = _setup_subvars()
        ini = tmp_path / "test.ini"
        ini.write_text("[vars]\nfoo = bar\nbaz = 42\n")
        x_sub_ini(filename=str(ini), section="vars", metacommandline="SUB INI ...")
        assert sv.sub_exists("foo")
        assert sv.sub_exists("baz")

    def test_nonexistent_section_is_noop(self, minimal_conf, tmp_path):
        from execsql.metacommands.data import x_sub_ini

        _setup_subvars()
        ini = tmp_path / "test.ini"
        ini.write_text("[other]\nkey = val\n")
        x_sub_ini(filename=str(ini), section="missing", metacommandline="SUB INI ...")

    def test_invalid_var_name_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.data import x_sub_ini

        sv = _setup_subvars()
        ini = tmp_path / "test.ini"
        # A variable name with spaces or special chars may be invalid
        ini.write_text("[vars]\n!invalid name! = val\n")
        # var_name_ok should reject this
        with patch.object(sv, "var_name_ok", return_value=False), pytest.raises(ErrInfo):
            x_sub_ini(filename=str(ini), section="vars", metacommandline="SUB INI ...")


# ---------------------------------------------------------------------------
# x_sub_querystring
# ---------------------------------------------------------------------------


class TestXSubQuerystring:
    def test_parses_query_string(self, minimal_conf):
        from execsql.metacommands.data import x_sub_querystring

        sv = _setup_subvars()
        x_sub_querystring(qstr="name=Alice&age=30", metacommandline="SUB QUERYSTRING ...")
        assert sv.sub_exists("name")
        assert sv.sub_exists("age")

    def test_empty_query_string(self, minimal_conf):
        from execsql.metacommands.data import x_sub_querystring

        _setup_subvars()
        x_sub_querystring(qstr="", metacommandline="SUB QUERYSTRING ...")


# ---------------------------------------------------------------------------
# x_sub_encrypt / x_sub_decrypt
# ---------------------------------------------------------------------------


class TestXSubEncryptDecrypt:
    def test_encrypt_sets_variable(self, minimal_conf):
        from execsql.metacommands.data import x_sub_encrypt

        sv = _setup_subvars()
        x_sub_encrypt(match="$encrypted", plaintext="hello", metacommandline="SUB ENCRYPT ...")
        assert sv.sub_exists("$encrypted")

    def test_decrypt_sets_variable(self, minimal_conf):
        from execsql.metacommands.data import x_sub_encrypt, x_sub_decrypt

        sv = _setup_subvars()
        # First encrypt, then decrypt
        x_sub_encrypt(match="$enc", plaintext="secret", metacommandline="SUB ENCRYPT ...")
        encrypted_val = sv._subs_dict["$enc"]
        x_sub_decrypt(match="$dec", crypttext=encrypted_val, metacommandline="SUB DECRYPT ...")
        assert sv._subs_dict["$dec"] == "secret"


# ---------------------------------------------------------------------------
# x_subdata
# ---------------------------------------------------------------------------


class TestXSubdata:
    def test_subdata_sets_variable_from_query(self, minimal_conf):
        from execsql.metacommands.data import x_subdata

        sv = _setup_subvars()
        mock_db = MagicMock()
        mock_db.select_rowsource.return_value = (["col1"], iter([("value1",)]))
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        x_subdata(match="$result", datasource="mytable", metacommandline="SUBDATA ...")
        assert sv._subs_dict["$result"] == "value1"

    def test_subdata_no_rows(self, minimal_conf):
        from execsql.metacommands.data import x_subdata

        sv = _setup_subvars()
        mock_db = MagicMock()
        mock_db.select_rowsource.return_value = (["col1"], iter([]))
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        x_subdata(match="$result", datasource="emptytable", metacommandline="SUBDATA ...")
        # Variable should have been removed but not re-added
        assert not sv.sub_exists("$result")

    def test_subdata_none_value_becomes_empty_string(self, minimal_conf):
        from execsql.metacommands.data import x_subdata

        sv = _setup_subvars()
        mock_db = MagicMock()
        mock_db.select_rowsource.return_value = (["col1"], iter([(None,)]))
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        x_subdata(match="$result", datasource="tbl", metacommandline="SUBDATA ...")
        assert sv._subs_dict["$result"] == ""

    def test_subdata_numeric_value_becomes_string(self, minimal_conf):
        from execsql.metacommands.data import x_subdata

        sv = _setup_subvars()
        mock_db = MagicMock()
        mock_db.select_rowsource.return_value = (["col1"], iter([(42,)]))
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        x_subdata(match="$result", datasource="tbl", metacommandline="SUBDATA ...")
        assert sv._subs_dict["$result"] == "42"

    def test_subdata_db_exception_raises_errinfo(self, minimal_conf):
        from execsql.metacommands.data import x_subdata

        _setup_subvars()
        mock_db = MagicMock()
        mock_db.select_rowsource.side_effect = RuntimeError("db error")
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs

        with pytest.raises(ErrInfo):
            x_subdata(match="$result", datasource="tbl", metacommandline="SUBDATA ...")


# ---------------------------------------------------------------------------
# x_selectsub
# ---------------------------------------------------------------------------


class TestXSelectsub:
    def _setup_db(self, hdrs, rows):
        mock_db = MagicMock()
        mock_db.select_rowsource.return_value = (hdrs, iter(rows))
        mock_dbs = MagicMock()
        mock_dbs.current.return_value = mock_db
        _state.dbs = mock_dbs
        return mock_db

    def test_selectsub_sets_row_variables(self, minimal_conf):
        from execsql.metacommands.data import x_selectsub

        sv = _setup_subvars()
        _setup_exec_log()
        _setup_commandliststack()
        minimal_conf.log_datavars = False
        self._setup_db(["name", "age"], [("Alice", 30)])

        x_selectsub(datasource="people", metacommandline="SELECT SUB ...")
        assert sv._subs_dict["@name"] == "Alice"
        assert sv._subs_dict["@age"] == "30"

    def test_selectsub_no_rows_logs_info(self, minimal_conf):
        from execsql.metacommands.data import x_selectsub

        _setup_subvars()
        mock_log = _setup_exec_log()
        _setup_commandliststack()
        minimal_conf.log_datavars = False
        self._setup_db(["col1"], [])

        x_selectsub(datasource="empty", metacommandline="SELECT SUB ...")
        mock_log.log_status_info.assert_called()

    def test_selectsub_none_value_becomes_empty(self, minimal_conf):
        from execsql.metacommands.data import x_selectsub

        sv = _setup_subvars()
        _setup_exec_log()
        _setup_commandliststack()
        minimal_conf.log_datavars = False
        self._setup_db(["val"], [(None,)])

        x_selectsub(datasource="tbl", metacommandline="SELECT SUB ...")
        assert sv._subs_dict["@val"] == ""

    def test_selectsub_with_logging(self, minimal_conf):
        from execsql.metacommands.data import x_selectsub

        _setup_subvars()
        mock_log = _setup_exec_log()
        _setup_commandliststack()
        minimal_conf.log_datavars = True
        self._setup_db(["x"], [("42",)])

        x_selectsub(datasource="tbl", metacommandline="SELECT SUB ...")
        # Should log the substitution variable assignment
        assert mock_log.log_status_info.call_count >= 1

    def test_selectsub_removes_existing_vars(self, minimal_conf):
        from execsql.metacommands.data import x_selectsub

        sv = _setup_subvars()
        _setup_exec_log()
        _setup_commandliststack()
        minimal_conf.log_datavars = False
        sv.add_substitution("@col1", "old_value")
        self._setup_db(["col1"], [("new_value",)])

        x_selectsub(datasource="tbl", metacommandline="SELECT SUB ...")
        assert sv._subs_dict["@col1"] == "new_value"


# ---------------------------------------------------------------------------
# Counter operations
# ---------------------------------------------------------------------------


class TestCounterOps:
    def test_reset_counter(self, minimal_conf):
        from execsql.metacommands.data import x_reset_counter

        counters = CounterVars()
        counters.set_counter(1, 42)
        _state.counters = counters
        x_reset_counter(counter_no="1")
        assert counters._ctrid(1) not in counters.counters

    def test_reset_counters(self, minimal_conf):
        from execsql.metacommands.data import x_reset_counters

        counters = CounterVars()
        counters.set_counter(1, 10)
        counters.set_counter(2, 20)
        _state.counters = counters
        x_reset_counters()
        assert len(counters.counters) == 0

    def test_set_counter(self, minimal_conf):
        from execsql.metacommands.data import x_set_counter

        counters = CounterVars()
        _state.counters = counters
        x_set_counter(counter_no="3", value="100")
        assert counters.counters[counters._ctrid(3)] == 100

    def test_set_counter_expression(self, minimal_conf):
        from execsql.metacommands.data import x_set_counter

        counters = CounterVars()
        _state.counters = counters
        x_set_counter(counter_no="1", value="10 + 5")
        assert counters.counters[counters._ctrid(1)] == 15


# ---------------------------------------------------------------------------
# x_max_int
# ---------------------------------------------------------------------------


class TestXMaxInt:
    def test_max_int_sets_conf(self, minimal_conf):
        from execsql.metacommands.data import x_max_int

        x_max_int(maxint="999999")
        assert minimal_conf.max_int == 999999


# ---------------------------------------------------------------------------
# Flag setters
# ---------------------------------------------------------------------------


class TestFlagSetters:
    @pytest.mark.parametrize(
        "handler_name,conf_attr",
        [
            ("x_empty_strings", "empty_strings"),
            ("x_trim_strings", "trim_strings"),
            ("x_replace_newlines", "replace_newlines"),
            ("x_empty_rows", "empty_rows"),
            ("x_only_strings", "only_strings"),
            ("x_boolean_int", "boolean_int"),
            ("x_boolean_words", "boolean_words"),
            ("x_clean_col_hdrs", "clean_col_hdrs"),
            ("x_del_empty_cols", "del_empty_cols"),
            ("x_create_col_hdrs", "create_col_hdrs"),
            ("x_dedup_col_hdrs", "dedup_col_hdrs"),
            ("x_import_common_cols_only", "import_common_cols_only"),
            ("x_quote_all_text", "quote_all_text"),
        ],
    )
    @pytest.mark.parametrize(
        "value,expected",
        [("yes", True), ("on", True), ("true", True), ("1", True), ("no", False), ("off", False)],
    )
    def test_flag_setter(self, minimal_conf, handler_name, conf_attr, value, expected):
        import execsql.metacommands.data as data_mod

        handler = getattr(data_mod, handler_name)
        kwarg_name = "setting" if handler_name == "x_quote_all_text" else "yesno"
        handler(**{kwarg_name: value})
        assert getattr(minimal_conf, conf_attr) is expected

    def test_fold_col_hdrs(self, minimal_conf):
        from execsql.metacommands.data import x_fold_col_hdrs

        x_fold_col_hdrs(foldspec="lower")
        assert minimal_conf.fold_col_hdrs == "lower"

    def test_trim_col_hdrs(self, minimal_conf):
        from execsql.metacommands.data import x_trim_col_hdrs

        x_trim_col_hdrs(which="BOTH")
        assert minimal_conf.trim_col_hdrs == "both"
