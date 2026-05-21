"""Gap-fill tests for execsql.metacommands.conditions.

Targets the previously-uncovered ``xf_*`` predicate functions: directory /
table / role / view / column existence checks, sub_defined / sub_empty
variants for ``~local`` and ``#param`` prefixes, _row_count error paths,
and the newer-file/newer-date comparators.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo
from execsql.metacommands import conditions as _cond


@pytest.fixture
def fake_state():
    """Install fake db pool + status on _state."""
    db = MagicMock()
    db.schema_exists.return_value = True
    db.table_exists.return_value = True
    db.role_exists.return_value = True
    db.view_exists.return_value = True
    db.column_exists.return_value = True
    db.select_data.return_value = (["count"], [(3,)])
    db.type.dbms_id = "SQLite"
    db.name.return_value = "test.db"
    pool = MagicMock()
    pool.current.return_value = db
    pool.aliases.return_value = ["alias1", "alias2"]
    _state.dbs = pool
    sv = MagicMock()
    sv.sub_exists.return_value = True
    sv.varvalue.return_value = "val"
    _state.subvars = sv
    cmd = MagicMock()
    cmd.localvars = MagicMock()
    cmd.localvars.sub_exists.return_value = True
    cmd.localvars.varvalue.return_value = ""
    cmd.paramvals = MagicMock()
    cmd.paramvals.sub_exists.return_value = True
    cmd.paramvals.varvalue.return_value = "p"
    _state.commandliststack = [cmd]
    status = MagicMock()
    status.metacommand_error = False
    _state.status = status
    yield MagicMock(db=db, pool=pool, subvars=sv, cmd=cmd, status=status)


class TestExistencePredicates:
    def test_dir_exists_true(self, fake_state, tmp_path):
        assert _cond.xf_direxists(dirname=str(tmp_path)) is True

    def test_dir_exists_false(self, fake_state, tmp_path):
        assert _cond.xf_direxists(dirname=str(tmp_path / "missing")) is False

    def test_schema_exists(self, fake_state):
        assert _cond.xf_schemaexists(schema="public") is True

    def test_table_exists(self, fake_state):
        assert _cond.xf_tableexists(schema="", tablename="t") is True

    def test_role_exists(self, fake_state):
        assert _cond.xf_roleexists(role="admin") is True

    def test_view_exists(self, fake_state):
        assert _cond.xf_viewexists(viewname="v") is True

    def test_column_exists(self, fake_state):
        assert _cond.xf_columnexists(tablename="t", schema="", columnname="c") is True


class TestSubVariablePredicates:
    def test_sub_defined_plain(self, fake_state):
        assert _cond.xf_sub_defined(match_str="myvar") is True

    def test_sub_defined_local(self, fake_state):
        # ~local prefix consults commandliststack[-1].localvars
        assert _cond.xf_sub_defined(match_str="~loc") is True
        fake_state.cmd.localvars.sub_exists.assert_called()

    def test_sub_defined_param(self, fake_state):
        # #param prefix consults commandliststack[-1].paramvals
        assert _cond.xf_sub_defined(match_str="#p") is True
        fake_state.cmd.paramvals.sub_exists.assert_called()

    def test_sub_empty_returns_true_when_empty(self, fake_state):
        # ~local var has varvalue == "" in the fixture
        assert _cond.xf_sub_empty(match_str="~loc", metacommandline="X") is True

    def test_sub_empty_raises_when_undefined(self, fake_state):
        fake_state.subvars.sub_exists.return_value = False
        with pytest.raises(ErrInfo):
            _cond.xf_sub_empty(match_str="myvar", metacommandline="SUB_EMPTY")

    def test_sub_empty_param_branch(self, fake_state):
        # #param prefix consults commandliststack[-1].paramvals — covers line 261
        fake_state.cmd.paramvals.varvalue.return_value = ""
        assert _cond.xf_sub_empty(match_str="#param", metacommandline="X") is True


class TestHasRowsAndRowCount:
    def test_hasrows_true(self, fake_state):
        assert _cond.xf_hasrows(queryname="t") is True

    def test_hasrows_zero(self, fake_state):
        fake_state.db.select_data.return_value = (["count"], [(0,)])
        assert _cond.xf_hasrows(queryname="empty") is False

    def test_hasrows_db_error_wrapped(self, fake_state):
        fake_state.db.select_data.side_effect = RuntimeError("db down")
        with pytest.raises(ErrInfo):
            _cond.xf_hasrows(queryname="t")

    def test_hasrows_errinfo_propagates(self, fake_state):
        fake_state.db.select_data.side_effect = ErrInfo("db", "x")
        with pytest.raises(ErrInfo):
            _cond.xf_hasrows(queryname="t")

    def test_row_count_helper_db_error_wrapped(self, fake_state):
        fake_state.db.select_data.side_effect = RuntimeError("boom")
        with pytest.raises(ErrInfo):
            _cond._row_count("t", "select count(*) from t;", "ROW_COUNT")

    def test_row_count_helper_bad_result(self, fake_state):
        fake_state.db.select_data.return_value = (["count"], [("not-a-number",)])
        with pytest.raises(ErrInfo):
            _cond._row_count("t", "select count(*) from t;", "ROW_COUNT")


class TestMiscPredicates:
    def test_script_exists(self, fake_state):
        _state.savedscripts = {"main": object()}
        assert _cond.xf_script_exists(script_id="MAIN") is True
        assert _cond.xf_script_exists(script_id="missing") is False

    def test_alias_defined(self, fake_state):
        assert _cond.xf_aliasdefined(alias="alias1") is True
        assert _cond.xf_aliasdefined(alias="missing") is False

    def test_metacommand_error(self, fake_state):
        assert _cond.xf_metacommanderror() is False
        fake_state.status.metacommand_error = True
        assert _cond.xf_metacommanderror() is True

    def test_istrue_truthy_values(self):
        for v in ("yes", "y", "TRUE", "T", "1"):
            assert _cond.xf_istrue(value=v) is True

    def test_istrue_falsy_values(self):
        for v in ("no", "n", "false", "0", ""):
            assert _cond.xf_istrue(value=v) is False

    def test_dbms_match(self, fake_state):
        assert _cond.xf_dbms(dbms="sqlite") is True
        assert _cond.xf_dbms(dbms="postgres") is False

    def test_dbname_match(self, fake_state):
        assert _cond.xf_dbname(dbname="test.db") is True
        assert _cond.xf_dbname(dbname="other.db") is False


class TestFileComparators:
    def test_newer_file_true(self, fake_state, tmp_path):
        older = tmp_path / "older.txt"
        newer = tmp_path / "newer.txt"
        older.write_text("o")
        newer.write_text("n")
        # Force older to be older
        os.utime(older, (1, 1))
        assert _cond.xf_newer_file(file1=str(newer), file2=str(older)) is True

    def test_newer_file_missing_raises(self, fake_state, tmp_path):
        existing = tmp_path / "x.txt"
        existing.write_text("x")
        with pytest.raises(ErrInfo):
            _cond.xf_newer_file(file1=str(tmp_path / "missing"), file2=str(existing))
        with pytest.raises(ErrInfo):
            _cond.xf_newer_file(file1=str(existing), file2=str(tmp_path / "missing"))

    def test_newer_date_file_missing(self, fake_state, tmp_path):
        with pytest.raises(ErrInfo):
            _cond.xf_newer_date(file1=str(tmp_path / "missing"), datestr="2024-01-01")

    def test_newer_date_unparsable(self, fake_state, tmp_path):
        f = tmp_path / "f.txt"
        f.write_text("x")
        with pytest.raises(ErrInfo):
            _cond.xf_newer_date(file1=str(f), datestr="not-a-date")

    def test_newer_date_happy_path(self, fake_state, tmp_path):
        # File exists + valid date string → comparison branch (line 418)
        f = tmp_path / "now.txt"
        f.write_text("x")
        os.utime(f, (2_000_000_000, 2_000_000_000))  # ~2033
        # Compare against an old date — the file's mtime is newer
        assert _cond.xf_newer_date(file1=str(f), datestr="2000-01-01") is True


class TestXcmdTest:
    """Coverage for the module-level xcmd_test() (lines 858-863)."""

    @pytest.fixture(autouse=True)
    def _install_conditional_table(self):
        _state.conditionallist = _cond.CONDITIONAL_TABLE
        yield
        _state.conditionallist = None

    def test_truthy_condition(self, fake_state):
        # 'equals(a, a)' parses and evaluates True
        assert _cond.xcmd_test("equals(a, a)") is True

    def test_falsy_condition(self, fake_state):
        assert _cond.xcmd_test("equals(a, b)") is False

    def test_unrecognized_raises(self, fake_state):
        from execsql.exceptions import CondParserError

        # Invalid syntax raises CondParserError; we just want xcmd_test to run.
        with pytest.raises((ErrInfo, CondParserError)):
            _cond.xcmd_test("this is not a valid condition expression !!!")


class TestEqualsBranches:
    """xf_equals iterates through type converters — exercise int/float/bool/date paths."""

    def test_int_equal(self):
        assert _cond.xf_equals(string1="42", string2="42") is True

    def test_int_unequal(self):
        assert _cond.xf_equals(string1="42", string2="43") is False

    def test_float_equal(self):
        assert _cond.xf_equals(string1="3.14", string2="3.14") is True

    def test_string_fallback(self):
        # Neither convertible to a number — falls back to string compare
        assert _cond.xf_equals(string1="abc", string2="ABC") is True

    def test_bool_equal(self):
        assert (
            _cond.xf_equals(string1="true", string2="yes") is True
            or _cond.xf_equals(string1="true", string2="True") is True
        )
