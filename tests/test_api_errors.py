"""What ``execsql.run()`` reports when a run fails.

The returned :class:`~execsql.api.ScriptResult` is the library API's error
channel: every failure, from a bad DSN to a halting SQL error, comes back as
``success=False`` with a :class:`~execsql.api.ScriptError` that says what went
wrong — never as an internal exception, and never as a bare "failed".
"""

from __future__ import annotations

import pytest

from execsql import api


def _dsn(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'err.db'}"


class TestSetupFailures:
    def test_unknown_dsn_scheme_is_a_failed_result(self):
        result = api.run(sql="select 1;", dsn="bogus://x")
        assert result.success is False
        assert result.errors[0].source == "<connect>"
        assert "bogus" in result.errors[0].message

    def test_unopenable_sqlite_file_is_a_failed_result(self, tmp_path):
        result = api.run(sql="select 1;", dsn=f"sqlite:///{tmp_path / 'no_such_dir' / 'x.db'}")
        assert result.success is False
        assert result.errors[0].source == "<connect>"
        assert result.errors[0].message

    def test_missing_script_file_is_a_failed_result(self, tmp_path):
        missing = tmp_path / "missing.sql"
        result = api.run(script=missing, dsn=_dsn(tmp_path), new_db=True)
        assert result.success is False
        assert result.errors[0].source == str(missing)
        assert "missing.sql" in result.errors[0].message

    def test_missing_config_file_is_a_failed_result(self, tmp_path):
        result = api.run(sql="select 1;", dsn=_dsn(tmp_path), new_db=True, config_file=tmp_path / "missing.conf")
        assert result.success is False
        assert result.errors[0].source == "<config>"
        assert "missing.conf" in result.errors[0].message

    def test_invalid_config_value_is_a_failed_result(self, tmp_path):
        conf = tmp_path / "execsql.conf"
        conf.write_text("[output]\noutfile_open_timeout=soon\n")
        result = api.run(sql="select 1;", dsn=_dsn(tmp_path), new_db=True, config_file=conf)
        assert result.success is False
        assert result.errors[0].source == "<config>"
        assert "outfile_open_timeout" in result.errors[0].message


class TestHaltingErrors:
    def test_failed_sql_reports_the_driver_message_and_statement(self, tmp_path):
        result = api.run(sql="select 1;\nselect * from nope_tbl;\n", dsn=_dsn(tmp_path), new_db=True)
        assert result.success is False
        (err,) = result.errors
        assert "nope_tbl" in err.message
        assert "Script execution failed" not in err.message
        assert err.sql is not None and "nope_tbl" in err.sql
        assert err.line == 2

    def test_failed_metacommand_reports_its_error(self, tmp_path):
        missing = tmp_path / "missing.sql"
        result = api.run(sql=f"-- !x! INCLUDE {missing}\n", dsn=_dsn(tmp_path), new_db=True)
        assert result.success is False
        (err,) = result.errors
        assert "missing.sql" in err.message
        assert err.sql is None
        assert err.line == 1

    def test_halt_reports_its_exit_status(self, tmp_path):
        result = api.run(sql="select 1;\n-- !x! HALT\n", dsn=_dsn(tmp_path), new_db=True)
        assert result.success is False
        assert "HALT" in result.errors[0].message

    def test_an_earlier_non_halting_error_is_not_blamed_for_a_halt(self, tmp_path):
        result = api.run(
            sql="select * from nope_tbl;\n-- !x! HALT\n",
            dsn=_dsn(tmp_path),
            new_db=True,
            halt_on_error=False,
        )
        assert result.success is False
        sql_error, halt = result.errors
        assert "nope_tbl" in sql_error.message
        assert "nope_tbl" not in halt.message


class TestVariablesKeys:
    """A ``variables`` key names a ``$`` variable, as ``-a``/``$ARG_n`` style sub-vars do."""

    @pytest.mark.parametrize("key", ["SCHEMA", "$SCHEMA"])
    def test_key_is_referenced_with_a_dollar_sign(self, tmp_path, key):
        out = tmp_path / "out.txt"
        result = api.run(
            sql=f'-- !x! WRITE "!!$SCHEMA!!" TO {out}\n',
            dsn=_dsn(tmp_path),
            new_db=True,
            variables={key: "staging"},
        )
        assert result.success, result.errors
        assert out.read_text() == "staging\n"
        assert result.variables["schema"] == "staging"
