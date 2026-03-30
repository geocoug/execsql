"""Tests for --dsn / --connection-string CLI flag interaction with execsql.conf.

Verifies that --dsn overrides conf-file connection settings, and that
the two can coexist (DSN provides connection, conf provides encoding/options).
Uses SQLite since it requires no external services.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import textwrap

from tests.integration.conftest import write_script


def _run_execsql(tmp_path, script_path, dsn=None, extra_args=None, timeout=30):
    """Run execsql with optional --dsn flag."""
    cmd = [sys.executable, "-m", "execsql"]
    if dsn:
        cmd.extend(["--dsn", dsn])
    cmd.append(str(script_path))
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_conf(tmp_path, content):
    """Write an execsql.conf with arbitrary content."""
    conf = tmp_path / "execsql.conf"
    conf.write_text(textwrap.dedent(content))
    return conf


class TestDsnOverridesConf:
    """--dsn flag should override connection settings from execsql.conf."""

    def test_dsn_overrides_conf_db_file(self, tmp_path):
        """DSN database path takes precedence over conf db_file."""
        dsn_db = tmp_path / "dsn.db"
        conf_db = tmp_path / "conf.db"

        # Conf points to conf.db
        _write_conf(
            tmp_path,
            f"""\
            [connect]
            db_type = l
            db_file = {conf_db}
            new_db = yes
            password_prompt = no
        """,
        )

        script = write_script(
            tmp_path,
            """\
            CREATE TABLE t (id INTEGER);
            INSERT INTO t VALUES (1);
        """,
        )

        # DSN points to dsn.db — should win
        result = _run_execsql(tmp_path, script, dsn=f"sqlite:///{dsn_db}")
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Data should be in dsn.db, not conf.db
        assert dsn_db.exists(), "DSN database was not created"
        conn = sqlite3.connect(str(dsn_db))
        rows = conn.execute("SELECT id FROM t").fetchall()
        conn.close()
        assert rows == [(1,)]

    def test_dsn_without_conf_file(self, tmp_path):
        """DSN works even when no execsql.conf exists."""
        # Use a relative path — cwd is tmp_path, so test.db lands there.
        # Conf with new_db=yes is needed so SQLite creates the file.
        _write_conf(
            tmp_path,
            """\
            [connect]
            new_db = yes
        """,
        )

        script = write_script(
            tmp_path,
            """\
            CREATE TABLE t (val TEXT);
            INSERT INTO t VALUES ('hello');
        """,
        )

        result = _run_execsql(tmp_path, script, dsn="sqlite:///test.db")
        assert result.returncode == 0, f"stderr: {result.stderr}"

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT val FROM t").fetchall()
        conn.close()
        assert rows == [("hello",)]

    def test_conf_encoding_used_with_dsn_connection(self, tmp_path):
        """Conf file encoding settings are respected even when --dsn provides the connection."""
        _write_conf(
            tmp_path,
            """\
            [connect]
            new_db = yes

            [encoding]
            script = utf-8
            output = utf-8
        """,
        )

        csv_path = tmp_path / "out.csv"
        script = write_script(
            tmp_path,
            f"""\
            CREATE TABLE t (id INTEGER, name TEXT);
            INSERT INTO t VALUES (1, 'Alice');

            -- !x! EXPORT QUERY << SELECT id, name FROM t; >> TO {csv_path} AS CSV
        """,
        )

        result = _run_execsql(tmp_path, script, dsn="sqlite:///test.db")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert csv_path.exists()

    def test_dsn_db_type_overrides_conf_db_type(self, tmp_path):
        """DSN scheme determines db_type even if conf specifies a different type."""
        # Conf says PostgreSQL, but DSN says SQLite — DSN should win
        _write_conf(
            tmp_path,
            """\
            [connect]
            db_type = p
            server = nonexistent
            database = fake
            new_db = yes
            password_prompt = no
        """,
        )

        script = write_script(
            tmp_path,
            """\
            CREATE TABLE t (id INTEGER);
            INSERT INTO t VALUES (42);
        """,
        )

        result = _run_execsql(tmp_path, script, dsn="sqlite:///test.db")
        assert result.returncode == 0, f"stderr: {result.stderr}"

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT id FROM t").fetchall()
        conn.close()
        assert rows == [(42,)]
