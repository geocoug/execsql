"""
Tests for execsql.db.postgres — PostgresDatabase adapter.

These tests mock psycopg2 entirely so they can run without a PostgreSQL
server or the psycopg2 package installed.  They verify that the
connect_timeout parameter is correctly threaded through to psycopg2.connect().
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from execsql.db.postgres import DEFAULT_CONNECT_TIMEOUT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_psycopg2():
    """Return a mock psycopg2 module whose connect() returns a usable conn."""
    mock_mod = MagicMock()
    mock_conn = MagicMock()
    mock_conn.encoding = "UTF8"
    mock_mod.connect.return_value = mock_conn
    return mock_mod


# ---------------------------------------------------------------------------
# connect_timeout tests
# ---------------------------------------------------------------------------


class TestPostgresConnectTimeout:
    @patch.dict("sys.modules", {"psycopg2": _make_mock_psycopg2()})
    def test_default_connect_timeout(self):
        import sys

        mock_psycopg2 = sys.modules["psycopg2"]
        from execsql.db.postgres import PostgresDatabase

        db = PostgresDatabase(
            server_name="localhost",
            db_name="testdb",
            user_name="user",
            password="pass",
        )
        assert db.connect_timeout == DEFAULT_CONNECT_TIMEOUT
        # Verify psycopg2.connect was called with connect_timeout=30
        call_kwargs = mock_psycopg2.connect.call_args[1]
        assert call_kwargs["connect_timeout"] == DEFAULT_CONNECT_TIMEOUT

    @patch.dict("sys.modules", {"psycopg2": _make_mock_psycopg2()})
    def test_custom_connect_timeout(self):
        import sys

        mock_psycopg2 = sys.modules["psycopg2"]
        from execsql.db.postgres import PostgresDatabase

        db = PostgresDatabase(
            server_name="localhost",
            db_name="testdb",
            user_name="user",
            password="pass",
            connect_timeout=10,
        )
        assert db.connect_timeout == 10
        call_kwargs = mock_psycopg2.connect.call_args[1]
        assert call_kwargs["connect_timeout"] == 10

    @patch.dict("sys.modules", {"psycopg2": _make_mock_psycopg2()})
    def test_connect_timeout_without_credentials(self):
        import sys

        mock_psycopg2 = sys.modules["psycopg2"]
        from execsql.db.postgres import PostgresDatabase

        db = PostgresDatabase(
            server_name="localhost",
            db_name="testdb",
            user_name=None,
            connect_timeout=5,
        )
        assert db.connect_timeout == 5
        call_kwargs = mock_psycopg2.connect.call_args[1]
        assert call_kwargs["connect_timeout"] == 5
