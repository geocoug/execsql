"""Secrets stay out of ``execsql.log`` wherever they enter a run.

Each secret is registered with the run's log when it arrives — ``-a`` values,
passwords from a DSN or config file, a password typed at a prompt or read
from the keyring, ``PROMPT CREDENTIALS``, and ``SUB_DECRYPT`` output — so a
later SQL statement (``LOG_SQL ON``), ``SYSTEM_CMD`` echo or error message
that contains it is logged with ``***``.  The ``run`` record at the top of each
run lists only how many ``-a`` values were given.
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

# Built at runtime so secret scanners do not flag the test source.
SECRET = "sk_" + "live_" + "Zq7Rv2Lm9Px4"

_ENV = {**os.environ, "NO_COLOR": "1", "COLUMNS": "200", "TERM": "dumb"}


def _execsql(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "execsql", *args],
        capture_output=True,
        text=True,
        env=_ENV,
        cwd=cwd,
        timeout=120,
    )


def _logger(tmp_path, monkeypatch):
    import execsql.state as _state
    from execsql.utils.fileio import Logger

    monkeypatch.setattr(_state, "logfile_encoding", "utf-8", raising=False)
    log = Logger("<inline>", "db", None, {}, log_file_name=str(tmp_path / "execsql.log"))
    monkeypatch.setattr(_state, "exec_log", log)
    return log


def _log_text(log) -> str:
    log.log_file.flush()
    with open(log.log_file_name, encoding="utf-8") as f:
        return f.read()


class TestCommandLine:
    def test_arg_value_is_not_in_the_log_or_console(self, tmp_path):
        system_cmd = (
            f'-- !x! SYSTEM_CMD ("{sys.executable}" -c "import sys" !!$ARG_1!!)\n' if os.name == "posix" else ""
        )
        (tmp_path / "s.sql").write_text(
            "-- !x! CONFIG LOG_SQL ON\n"
            "select '!!$ARG_1!!' as token;\n"
            f"{system_cmd}"
            "select '!!$ARG_1!! !!no_such_var!!' as warned;\n",
        )
        result = _execsql("run", "s.sql", "t.db", "-t", "l", "-n", "-a", SECRET, cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        log = (tmp_path / "execsql.log").read_text()
        assert SECRET not in log
        assert "sub_vars: 1 value(s)" in log
        assert "select '***' as token;" in log
        assert "potential un-substituted variable" in result.stdout
        assert SECRET not in result.stdout + result.stderr

    def test_decrypted_value_is_not_in_the_log(self, tmp_path):
        from execsql.utils.crypto import Encrypt

        (tmp_path / "s.sql").write_text(
            f"-- !x! SUB_DECRYPT pw {Encrypt().encrypt(SECRET)}\n-- !x! CONFIG LOG_SQL ON\nselect '!!pw!!' as pw;\n",
        )
        result = _execsql("run", "s.sql", "t.db", "-t", "l", "-n", cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        assert SECRET not in (tmp_path / "execsql.log").read_text()


class TestPasswordSources:
    def test_dsn_and_config_passwords(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        from execsql.cli.run import _setup_logging
        from execsql.script.variables import SubVarSet

        import execsql.state as _state

        monkeypatch.setattr(_state, "logfile_encoding", "utf-8", raising=False)
        monkeypatch.chdir(tmp_path)
        smtp_secret = SECRET + "_smtp"
        conf = SimpleNamespace(
            db="db",
            server=None,
            user_logfile=False,
            files_read=[],
            db_password=SECRET,
            smtp_password=smtp_secret,
        )
        with patch("execsql.cli.run.os.path.isfile", return_value=False):
            log = _setup_logging(
                conf,
                SubVarSet(),
                script_name="<inline>",
                sub_vars=None,
                boolean_int=None,
                make_dirs=None,
                database_encoding=None,
                script_encoding=None,
                output_encoding=None,
                import_encoding=None,
                user_logfile=False,
                new_db=False,
                port=None,
                scanlines=None,
                db_type="p",
                user=None,
                use_gui=None,
                no_passwd=False,
                import_buffer=None,
            )
        log.log_sql_query(f"alter role etl password '{SECRET}'; -- {smtp_secret}", "db")
        text = _log_text(log)
        assert SECRET not in text

    def test_prompted_database_password(self, tmp_path, monkeypatch, minimal_conf):
        import getpass

        from execsql.utils.auth import get_password

        minimal_conf.gui_level = 0
        log = _logger(tmp_path, monkeypatch)
        monkeypatch.setattr(getpass, "getpass", lambda prompt="": SECRET)
        assert get_password("PostgreSQL", "db", "etl", skip_keyring=True) == SECRET
        log.log_status_info(f"connected with {SECRET}")
        assert SECRET not in _log_text(log)

    def test_keyring_password(self, tmp_path, monkeypatch, minimal_conf):
        import execsql.utils.auth as auth

        minimal_conf.use_keyring = True
        log = _logger(tmp_path, monkeypatch)
        monkeypatch.setattr(auth, "_keyring_get", lambda service, user: SECRET)
        assert auth.get_password("PostgreSQL", "db", "etl") == SECRET
        log.log_status_info(f"connected with {SECRET}")
        assert SECRET not in _log_text(log)

    def test_prompt_enter_sub_password(self, tmp_path, monkeypatch, minimal_conf):
        import execsql.metacommands.prompt as prompt
        import execsql.state as _state
        from execsql.script.variables import SubVarSet

        class AnswerQueue:
            def put(self, spec):
                spec.return_queue.put({"button": 1, "return_value": SECRET})

        log = _logger(tmp_path, monkeypatch)
        monkeypatch.setattr(_state, "subvars", SubVarSet())
        monkeypatch.setattr(_state, "gui_manager_queue", AnswerQueue())
        monkeypatch.setattr(prompt, "enable_gui", lambda: None)
        monkeypatch.setattr(prompt, "current_script_line", lambda: ("s.sql", 1))
        prompt.x_prompt_enter(
            match_str="pw",
            message="Password",
            type=None,
            case=None,
            password="PASSWORD",
            schema=None,
            table=None,
            initial=None,
            help=None,
        )
        assert _state.subvars.varvalue("pw") == SECRET
        log.log_sql_query(f"create role etl password '{SECRET}'", "db")
        assert SECRET not in _log_text(log)

    def test_prompt_credentials(self, tmp_path, monkeypatch, minimal_conf):
        import builtins
        import getpass

        import execsql.state as _state
        from execsql.script.variables import SubVarSet
        from execsql.utils.gui import gui_credentials

        minimal_conf.gui_level = 0
        log = _logger(tmp_path, monkeypatch)
        monkeypatch.setattr(_state, "subvars", SubVarSet())
        monkeypatch.setattr(builtins, "input", lambda prompt="": "etl")
        monkeypatch.setattr(getpass, "getpass", lambda prompt="": SECRET)
        gui_credentials("Log in", username="user", pwtext="pw")
        log.log_user_msg(f"System command: psql -p {SECRET}")
        assert SECRET not in _log_text(log)


def test_redact_without_a_log_returns_the_text(monkeypatch):
    import execsql.state as _state
    from execsql.utils.fileio import redact, register_secret

    monkeypatch.setattr(_state, "exec_log", None)
    register_secret(SECRET)  # no log: nothing to do, no error
    assert redact(f"value {SECRET}") == f"value {SECRET}"


@pytest.mark.parametrize("value", [None, ""])
def test_empty_values_are_not_registered(tmp_path, monkeypatch, value):
    from execsql.utils.fileio import register_secret

    log = _logger(tmp_path, monkeypatch)
    register_secret(value)
    assert log._redaction_values == []
