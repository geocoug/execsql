"""When execsql stores, reads and deletes a keyring password.

- The entry's name includes the server's port, so two servers on one host
  (a local database and an SSH tunnel to production) do not share it.
- A typed password is stored only once the connection it was typed for works.
- A stored password is deleted, and the user prompted again, only when the
  server rejects it; a timeout, a closed port or a missing database leaves it.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

import execsql.utils.auth as auth
from execsql.exceptions import ErrInfo


@pytest.fixture
def keyring(minimal_conf):
    store: dict[tuple[str, str], str] = {}
    mod = types.ModuleType("keyring")
    mod.get_password = MagicMock(side_effect=lambda svc, user: store.get((svc, user)))
    mod.set_password = MagicMock(side_effect=lambda svc, user, pw: store.__setitem__((svc, user), pw))
    mod.delete_password = MagicMock(side_effect=lambda svc, user: store.pop((svc, user)))
    mod.store = store
    minimal_conf.use_keyring = True
    minimal_conf.gui_level = 0
    with patch.dict("sys.modules", {"keyring": mod}):
        yield mod


# ---------------------------------------------------------------------------
# Login failures, by driver
# ---------------------------------------------------------------------------


class _Exc(Exception):
    pass


class _OracleError:
    def __init__(self, code):
        self.code = code


def _wrapped(exc: BaseException) -> ErrInfo:
    """What the adapters raise: an ErrInfo raised from the driver's error."""
    try:
        try:
            raise exc
        except BaseException as inner:
            raise ErrInfo("exception", other_msg="Failed to open database") from inner
    except ErrInfo as err:
        return err


@pytest.mark.parametrize(
    "exc",
    [
        _Exc(
            'connection to server at "127.0.0.1", port 5432 failed: FATAL:  password authentication failed for user "u"',
        ),
        _Exc("fe_sendauth: no password supplied"),
        _Exc(1045, "Access denied for user 'u'@'localhost' (using password: YES)"),
        _Exc("28000", "[28000] [Microsoft][ODBC Driver 17 for SQL Server]Login failed for user 'u'. (18456)"),
        _Exc(_OracleError(1017)),
        _Exc("ORA-01017: invalid username/password; logon denied"),
        _Exc("Your user name and password are not defined. Ask your database administrator"),
    ],
    ids=["postgres", "postgres-no-password", "mysql", "odbc", "oracle-object", "oracle-text", "firebird"],
)
def test_a_rejected_login_is_recognised_directly_and_behind_errinfo(exc):
    assert auth.is_login_failure(exc)
    assert auth.is_login_failure(_wrapped(exc))


@pytest.mark.parametrize(
    "exc",
    [
        _Exc('connection to server at "127.0.0.1", port 55499 failed: Connection refused'),
        _Exc('connection to server at "127.0.0.1", port 5432 failed: FATAL:  database "nope" does not exist'),
        _Exc("timeout expired"),
        _Exc(2003, "Can't connect to MySQL server on 'db' (timed out)"),
        _Exc("08001", "[08001] TCP Provider: Error code 0x2749"),
        _Exc("IM002", "[IM002] Data source name not found and no default driver specified"),
        _Exc(_OracleError(12541)),
    ],
    ids=[
        "refused",
        "missing-db",
        "timeout",
        "mysql-unreachable",
        "odbc-unreachable",
        "odbc-no-driver",
        "oracle-no-listener",
    ],
)
def test_other_connection_failures_are_not_login_failures(exc):
    assert not auth.is_login_failure(exc)
    assert not auth.is_login_failure(_wrapped(exc))


# ---------------------------------------------------------------------------
# Entry names, the pre-port name, and storing only after success
# ---------------------------------------------------------------------------


def test_two_ports_on_one_host_do_not_share_a_password(keyring):
    keyring.store[("execsql/PostgreSQL/localhost:5432/db", "u")] = "dev-secret"
    with patch("execsql.utils.auth.getpass.getpass", return_value="prod-secret") as prompt:
        assert auth.get_password("PostgreSQL", "db", "u", server_name="localhost", port=15432) == "prod-secret"
    prompt.assert_called_once()


def test_a_pre_port_entry_is_used_on_the_default_port_and_saved_under_the_new_name(keyring):
    keyring.store[("execsql/PostgreSQL/localhost/db", "u")] = "old-secret"
    assert auth.get_password("PostgreSQL", "db", "u", server_name="localhost") == "old-secret"
    assert auth.password_from_keyring()
    auth.remember_password("PostgreSQL", "db", "u", "localhost")
    assert keyring.store[("execsql/PostgreSQL/localhost:5432/db", "u")] == "old-secret"


def test_a_pre_port_entry_is_never_sent_to_another_port(keyring):
    keyring.store[("execsql/PostgreSQL/localhost/db", "u")] = "dev-secret"
    with patch("execsql.utils.auth.getpass.getpass", return_value="tunnel-secret"):
        assert auth.get_password("PostgreSQL", "db", "u", server_name="localhost", port=15432) == "tunnel-secret"


def test_a_password_typed_for_a_failed_connection_is_never_stored(keyring):
    with patch("execsql.utils.auth.getpass.getpass", return_value="typo"):
        auth.get_password("PostgreSQL", "db", "u", server_name="localhost")
    # That connection failed; a different one then succeeds.
    auth.remember_password("PostgreSQL", "other_db", "u", "localhost")
    keyring.set_password.assert_not_called()


# ---------------------------------------------------------------------------
# The adapters: PostgreSQL (one driver call) and SQL Server (a driver loop)
# ---------------------------------------------------------------------------


def _pg(**kw):
    from execsql.db.postgres import PostgresDatabase

    with patch.object(PostgresDatabase, "open_db"):
        db = PostgresDatabase("localhost", "db", "u", need_passwd=True, port=5432, **kw)
    return db


class TestPostgresStoredPassword:
    pytestmark = pytest.mark.skipif(pytest.importorskip("psycopg") is None, reason="psycopg")

    def test_a_server_that_is_down_keeps_the_stored_password_and_does_not_prompt(self, keyring):
        keyring.store[("execsql/PostgreSQL/localhost:5432/db", "u")] = "good"
        db = _pg()
        refused = Exception('connection to server at "localhost", port 5432 failed: Connection refused')
        with (
            patch("psycopg.connect", side_effect=refused),
            patch("execsql.utils.auth.getpass.getpass") as prompt,
            pytest.raises(ErrInfo),
        ):
            db.open_db()
        prompt.assert_not_called()
        keyring.delete_password.assert_not_called()
        assert keyring.store[("execsql/PostgreSQL/localhost:5432/db", "u")] == "good"

    def test_a_rejected_stored_password_is_replaced_by_the_one_typed(self, keyring):
        keyring.store[("execsql/PostgreSQL/localhost:5432/db", "u")] = "stale"
        db = _pg()
        rejected = Exception(
            'connection to server at "localhost", port 5432 failed: FATAL:  password authentication failed for user "u"',
        )
        with (
            patch("psycopg.connect", side_effect=[rejected, MagicMock(info=MagicMock(encoding="UTF8"))]),
            patch("execsql.utils.auth.getpass.getpass", return_value="current"),
        ):
            db.open_db()
        assert keyring.store == {("execsql/PostgreSQL/localhost:5432/db", "u"): "current"}

    def test_a_mistyped_password_is_not_stored(self, keyring):
        db = _pg()
        rejected = Exception('FATAL:  password authentication failed for user "u"')
        with (
            patch("psycopg.connect", side_effect=rejected),
            patch("execsql.utils.auth.getpass.getpass", return_value="typo"),
            pytest.raises(ErrInfo),
        ):
            db.open_db()
        keyring.set_password.assert_not_called()


class TestSqlServerStoredPassword:
    def _db(self):
        pytest.importorskip("pyodbc")
        from execsql.db.sqlserver import SqlServerDatabase

        with patch.object(SqlServerDatabase, "open_db"):
            return SqlServerDatabase("sql01", "Lab", "u", need_passwd=True)

    def test_a_driver_that_cannot_reach_the_server_keeps_the_stored_password(self, keyring):
        keyring.store[("execsql/SQL Server/sql01:1433/Lab", "u")] = "good"
        db = self._db()
        with (
            patch("pyodbc.connect", side_effect=Exception("08001", "[08001] TCP Provider: timeout")),
            patch("execsql.utils.auth.getpass.getpass") as prompt,
            pytest.raises(ErrInfo),
        ):
            db.open_db()
        prompt.assert_not_called()
        keyring.delete_password.assert_not_called()

    def test_a_login_failure_from_one_driver_replaces_the_stored_password(self, keyring):
        keyring.store[("execsql/SQL Server/sql01:1433/Lab", "u")] = "stale"
        db = self._db()
        login_failed = Exception("28000", "[28000] Login failed for user 'u'. (18456)")
        no_driver = Exception("IM002", "[IM002] Data source name not found")
        attempts = [login_failed] + [no_driver] * 7 + [MagicMock()]
        with (
            patch("pyodbc.connect", side_effect=attempts),
            patch("execsql.utils.auth.getpass.getpass", return_value="current"),
        ):
            db.open_db()
        assert keyring.store == {("execsql/SQL Server/sql01:1433/Lab", "u"): "current"}
