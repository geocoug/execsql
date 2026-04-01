"""Comprehensive pytest tests for execsql.metacommands.connect.

Covers all handler functions in connect.py with mocked database constructors
and mocked _state singletons so no real database connections are required.

Handlers under test
-------------------
- x_connect_pg
- x_connect_user_pg
- x_connect_ssvr
- x_connect_user_ssvr
- x_connect_mysql
- x_connect_user_mysql
- x_connect_access
- x_connect_fb
- x_connect_user_fb
- x_connect_ora
- x_connect_user_ora
- x_connect_duckdb
- x_connect_sqlite
- x_connect_dsn
- x_use
- x_disconnect
- x_autocommit_on
- x_autocommit_off
- x_pg_vacuum
- x_daoflushdelay
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import execsql.state as _state
from execsql.exceptions import ErrInfo


# ---------------------------------------------------------------------------
# Shared state-setup helpers
# ---------------------------------------------------------------------------


def _make_mock_dbs(aliases=None, current_alias="initial"):
    """Return a MagicMock DatabasePool installed on _state.dbs."""
    mock_dbs = MagicMock()
    mock_dbs.aliases.return_value = aliases if aliases is not None else ["initial", "mydb"]
    mock_dbs.current_alias.return_value = current_alias
    _state.dbs = mock_dbs
    return mock_dbs


def _make_mock_exec_log():
    """Return a MagicMock Logger installed on _state.exec_log."""
    mock_log = MagicMock()
    _state.exec_log = mock_log
    return mock_log


def _make_mock_status(uses_db=False):
    """Return a MagicMock StatObj installed on _state.status."""
    mock_status = MagicMock()
    mock_status.batch.uses_db.return_value = uses_db
    _state.status = mock_status
    return mock_status


def _make_mock_subvars():
    """Return a MagicMock SubVarSet installed on _state.subvars."""
    mock_sv = MagicMock()
    _state.subvars = mock_sv
    return mock_sv


def _make_current_db(user="testuser", server_name="srv", db_name="dbname", dbms_id="postgresql"):
    """Return a MagicMock db instance and install it as current on _state.dbs."""
    mock_dbs = _make_mock_dbs()
    mock_db = MagicMock()
    mock_db.user = user
    mock_db.server_name = server_name
    mock_db.name.return_value = db_name
    mock_db.type = MagicMock()
    mock_db.type.dbms_id = dbms_id
    mock_dbs.current.return_value = mock_db
    mock_dbs.aliased_as.return_value = mock_db
    return mock_dbs, mock_db


# ---------------------------------------------------------------------------
# x_connect_pg
# ---------------------------------------------------------------------------


class TestXConnectPg:
    """Handler for CONNECT POSTGRESQL."""

    def test_minimal_args_no_encoding(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_pg

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            mock_inst = MagicMock()
            MockPg.return_value = mock_inst
            x_connect_pg(
                server="host1",
                db_name="db1",
                user="alice",
                db_alias="PG1",
                need_pwd=None,
                port=None,
                new=None,
                password=None,
                encoding=None,
            )
            MockPg.assert_called_once_with(
                "host1",
                "db1",
                "alice",
                need_passwd=None,
                port=None,
                new_db=False,
                password=None,
            )
            mock_dbs.add.assert_called_once_with("pg1", mock_inst)

    def test_alias_lowercased(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_pg

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.PostgresDatabase"):
            x_connect_pg(
                server="h",
                db_name="d",
                user=None,
                db_alias="MyPG",
                need_pwd=None,
                port=None,
                new=None,
                password=None,
                encoding=None,
            )
            alias_used = mock_dbs.add.call_args[0][0]
            assert alias_used == "mypg"

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_pg

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_pg(
                server="host",
                db_name="db",
                user="bob",
                db_alias="pgenc",
                need_pwd="true",
                port="5432",
                new="NEW",
                password="secret",
                encoding="latin1",
            )
            MockPg.assert_called_once_with(
                "host",
                "db",
                "bob",
                need_passwd=True,
                port=5432,
                new_db=True,
                encoding="latin1",
                password="secret",
            )

    def test_need_pwd_false_string(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_pg

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_pg(
                server="host",
                db_name="db",
                user="bob",
                db_alias="pg3",
                need_pwd="false",
                port=None,
                new=None,
                password=None,
                encoding=None,
            )
            _, kwargs = MockPg.call_args
            assert kwargs["need_passwd"] is False

    def test_new_not_new_keyword_is_false(self, minimal_conf):
        """Any value other than 'new' (case-insensitive) means new_db=False."""
        from execsql.metacommands.connect import x_connect_pg

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_pg(
                server="host",
                db_name="db",
                user=None,
                db_alias="pg4",
                need_pwd=None,
                port=None,
                new="existing",
                password=None,
                encoding=None,
            )
            _, kwargs = MockPg.call_args
            assert kwargs["new_db"] is False

    def test_quoted_server_and_db_stripped(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_pg

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_pg(
                server='"my server"',
                db_name='"my db"',
                user=None,
                db_alias="pg5",
                need_pwd=None,
                port=None,
                new=None,
                password=None,
                encoding=None,
            )
            pos_args = MockPg.call_args[0]
            assert pos_args[0] == "my server"
            assert pos_args[1] == "my db"

    def test_port_parsed_as_int(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_pg

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_pg(
                server="h",
                db_name="d",
                user=None,
                db_alias="pg6",
                need_pwd=None,
                port="5433",
                new=None,
                password=None,
                encoding=None,
            )
            _, kwargs = MockPg.call_args
            assert kwargs["port"] == 5433
            assert isinstance(kwargs["port"], int)

    def test_user_none_stays_none(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_pg

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_pg(
                server="h",
                db_name="d",
                user=None,
                db_alias="pg7",
                need_pwd=None,
                port=None,
                new=None,
                password=None,
                encoding=None,
            )
            pos_args = MockPg.call_args[0]
            assert pos_args[2] is None


# ---------------------------------------------------------------------------
# x_connect_user_pg
# ---------------------------------------------------------------------------


class TestXConnectUserPg:
    """Handler for CONNECT POSTGRESQL using current connection credentials."""

    def test_inherits_user_and_password_from_current_db(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_pg

        mock_dbs, mock_db = _make_current_db(user="pguser")
        _state.upass = "supersecret"

        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_user_pg(
                server="pghost",
                db_name="pgdb",
                db_alias="upg",
                port=None,
                encoding=None,
            )
            pos_args = MockPg.call_args[0]
            assert pos_args[2] == "pguser"
            _, kwargs = MockPg.call_args
            assert kwargs["password"] == "supersecret"
            assert kwargs["need_passwd"] is True
            mock_dbs.add.assert_called_once_with("upg", MockPg.return_value)

    def test_no_current_user_becomes_none(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_pg

        mock_dbs, mock_db = _make_current_db(user=None)
        _state.upass = None

        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_user_pg(
                server="h",
                db_name="d",
                db_alias="upg2",
                port=None,
                encoding=None,
            )
            pos_args = MockPg.call_args[0]
            assert pos_args[2] is None
            _, kwargs = MockPg.call_args
            assert kwargs["need_passwd"] is False

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_pg

        _make_current_db(user="u")
        _state.upass = "pw"

        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_user_pg(
                server="h",
                db_name="d",
                db_alias="upg3",
                port="5432",
                encoding="utf8",
            )
            _, kwargs = MockPg.call_args
            assert kwargs["encoding"] == "utf8"
            assert kwargs["port"] == 5432

    def test_without_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_pg

        _make_current_db(user="u")
        _state.upass = None

        with patch("execsql.metacommands.connect.PostgresDatabase") as MockPg:
            x_connect_user_pg(
                server="h",
                db_name="d",
                db_alias="upg4",
                port=None,
                encoding=None,
            )
            _, kwargs = MockPg.call_args
            assert "encoding" not in kwargs


# ---------------------------------------------------------------------------
# x_connect_ssvr
# ---------------------------------------------------------------------------


class TestXConnectSsvr:
    """Handler for CONNECT SQLSERVER."""

    def test_basic_sqlserver_connection(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_ssvr

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.SqlServerDatabase") as MockSS:
            x_connect_ssvr(
                server="sshost",
                db_name="ssdb",
                user="ssuser",
                db_alias="SSDB",
                need_pwd=None,
                port=None,
                encoding=None,
                password=None,
            )
            MockSS.assert_called_once_with(
                "sshost",
                "ssdb",
                user_name="ssuser",
                need_passwd=None,
                port=None,
                encoding=None,
                password=None,
            )
            mock_dbs.add.assert_called_once_with("ssdb", MockSS.return_value)

    def test_password_unquoted(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_ssvr

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.SqlServerDatabase") as MockSS:
            x_connect_ssvr(
                server="h",
                db_name="d",
                user=None,
                db_alias="ss2",
                need_pwd="true",
                port="1433",
                encoding="latin1",
                password='"my pw"',
            )
            _, kwargs = MockSS.call_args
            assert kwargs["password"] == "my pw"
            assert kwargs["need_passwd"] is True
            assert kwargs["port"] == 1433
            assert kwargs["encoding"] == "latin1"

    def test_user_none_stays_none(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_ssvr

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.SqlServerDatabase") as MockSS:
            x_connect_ssvr(
                server="h",
                db_name="d",
                user=None,
                db_alias="ss3",
                need_pwd=None,
                port=None,
                encoding=None,
                password=None,
            )
            _, kwargs = MockSS.call_args
            assert kwargs["user_name"] is None

    def test_alias_lowercased(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_ssvr

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.SqlServerDatabase"):
            x_connect_ssvr(
                server="h",
                db_name="d",
                user=None,
                db_alias="MYSS",
                need_pwd=None,
                port=None,
                encoding=None,
                password=None,
            )
            alias = mock_dbs.add.call_args[0][0]
            assert alias == "myss"


# ---------------------------------------------------------------------------
# x_connect_user_ssvr
# ---------------------------------------------------------------------------


class TestXConnectUserSsvr:
    """Handler for CONNECT SQLSERVER using current connection credentials."""

    def test_inherits_user_and_password(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_ssvr

        mock_dbs, mock_db = _make_current_db(user="ssuser")
        _state.upass = "pw123"

        with patch("execsql.metacommands.connect.SqlServerDatabase") as MockSS:
            x_connect_user_ssvr(
                server="sshost",
                db_name="ssdb",
                db_alias="uss",
                port=None,
                encoding=None,
            )
            pos_args = MockSS.call_args[0]
            assert pos_args[0] == "sshost"
            assert pos_args[1] == "ssdb"
            _, kwargs = MockSS.call_args
            assert kwargs["need_passwd"] is True
            mock_dbs.add.assert_called_once_with("uss", MockSS.return_value)

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_ssvr

        _make_current_db(user="u")
        _state.upass = "pw"

        with patch("execsql.metacommands.connect.SqlServerDatabase") as MockSS:
            x_connect_user_ssvr(
                server="h",
                db_name="d",
                db_alias="uss2",
                port="1433",
                encoding="utf8",
            )
            _, kwargs = MockSS.call_args
            assert kwargs["encoding"] == "utf8"

    def test_without_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_ssvr

        # user=None means current().user is falsy -> user variable will be None
        _make_current_db(user=None)
        _state.upass = None

        with patch("execsql.metacommands.connect.SqlServerDatabase") as MockSS:
            x_connect_user_ssvr(
                server="h",
                db_name="d",
                db_alias="uss3",
                port=None,
                encoding=None,
            )
            _, kwargs = MockSS.call_args
            assert kwargs["user_name"] is None
            assert kwargs["need_passwd"] is False


# ---------------------------------------------------------------------------
# x_connect_mysql
# ---------------------------------------------------------------------------


class TestXConnectMysql:
    """Handler for CONNECT MYSQL."""

    def test_basic_mysql_connection_no_encoding(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_mysql

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.MySQLDatabase") as MockMySQL:
            x_connect_mysql(
                server="mysqlhost",
                db_name="mysqldb",
                user="myuser",
                db_alias="MDB",
                need_pwd=None,
                port=None,
                encoding=None,
                password=None,
            )
            MockMySQL.assert_called_once_with(
                "mysqlhost",
                "mysqldb",
                "myuser",
                need_passwd=None,
                port=None,
                password=None,
            )
            mock_dbs.add.assert_called_once_with("mdb", MockMySQL.return_value)

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_mysql

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.MySQLDatabase") as MockMySQL:
            x_connect_mysql(
                server="h",
                db_name="d",
                user="u",
                db_alias="mdb2",
                need_pwd="true",
                port="3306",
                encoding="utf8",
                password='"mypassword"',
            )
            MockMySQL.assert_called_once_with(
                "h",
                "d",
                "u",
                need_passwd=True,
                port=3306,
                encoding="utf8",
                password="mypassword",
            )

    def test_need_pwd_false(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_mysql

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.MySQLDatabase") as MockMySQL:
            x_connect_mysql(
                server="h",
                db_name="d",
                user=None,
                db_alias="mdb3",
                need_pwd="false",
                port=None,
                encoding=None,
                password=None,
            )
            _, kwargs = MockMySQL.call_args
            assert kwargs["need_passwd"] is False

    def test_user_none_stays_none(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_mysql

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.MySQLDatabase") as MockMySQL:
            x_connect_mysql(
                server="h",
                db_name="d",
                user=None,
                db_alias="mdb4",
                need_pwd=None,
                port=None,
                encoding=None,
                password=None,
            )
            pos_args = MockMySQL.call_args[0]
            assert pos_args[2] is None


# ---------------------------------------------------------------------------
# x_connect_user_mysql
# ---------------------------------------------------------------------------


class TestXConnectUserMysql:
    """Handler for CONNECT MYSQL using current connection credentials."""

    def test_inherits_credentials(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_mysql

        mock_dbs, mock_db = _make_current_db(user="muser")
        _state.upass = "mpass"

        with patch("execsql.metacommands.connect.MySQLDatabase") as MockMySQL:
            x_connect_user_mysql(
                server="mhost",
                db_name="mdb",
                db_alias="umdb",
                port=None,
                encoding=None,
            )
            pos_args = MockMySQL.call_args[0]
            assert pos_args[2] == "muser"
            _, kwargs = MockMySQL.call_args
            assert kwargs["need_passwd"] is True
            assert kwargs["password"] == "mpass"
            mock_dbs.add.assert_called_once_with("umdb", MockMySQL.return_value)

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_mysql

        _make_current_db(user="u")
        _state.upass = "pw"

        with patch("execsql.metacommands.connect.MySQLDatabase") as MockMySQL:
            x_connect_user_mysql(
                server="h",
                db_name="d",
                db_alias="umdb2",
                port="3306",
                encoding="latin1",
            )
            _, kwargs = MockMySQL.call_args
            assert kwargs["encoding"] == "latin1"
            assert kwargs["port"] == 3306

    def test_no_password_need_passwd_false(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_mysql

        _make_current_db(user=None)
        _state.upass = None

        with patch("execsql.metacommands.connect.MySQLDatabase") as MockMySQL:
            x_connect_user_mysql(
                server="h",
                db_name="d",
                db_alias="umdb3",
                port=None,
                encoding=None,
            )
            _, kwargs = MockMySQL.call_args
            assert kwargs["need_passwd"] is False


# ---------------------------------------------------------------------------
# x_connect_access
# ---------------------------------------------------------------------------


class TestXConnectAccess:
    """Handler for CONNECT ACCESS."""

    def test_basic_access_connection(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_access

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.AccessDatabase") as MockAccess:
            x_connect_access(
                filename="myfile.mdb",
                db_alias="ACB",
                need_pwd=None,
                encoding=None,
                password=None,
            )
            MockAccess.assert_called_once_with(
                "myfile.mdb",
                need_passwd=None,
                encoding=None,
                password=None,
            )
            mock_dbs.add.assert_called_once_with("acb", MockAccess.return_value)

    def test_with_encoding_and_password(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_access

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.AccessDatabase") as MockAccess:
            x_connect_access(
                filename='"my file.mdb"',
                db_alias="acb2",
                need_pwd="true",
                encoding="latin1",
                password='"dbpass"',
            )
            MockAccess.assert_called_once_with(
                "my file.mdb",
                need_passwd=True,
                encoding="latin1",
                password="dbpass",
            )

    def test_need_pwd_false(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_access

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.AccessDatabase") as MockAccess:
            x_connect_access(
                filename="f.mdb",
                db_alias="acb3",
                need_pwd="false",
                encoding=None,
                password=None,
            )
            _, kwargs = MockAccess.call_args
            assert kwargs["need_passwd"] is False

    def test_alias_lowercased(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_access

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.AccessDatabase"):
            x_connect_access(
                filename="f.mdb",
                db_alias="MyACCESS",
                need_pwd=None,
                encoding=None,
                password=None,
            )
            assert mock_dbs.add.call_args[0][0] == "myaccess"


# ---------------------------------------------------------------------------
# x_connect_fb (Firebird)
# ---------------------------------------------------------------------------


class TestXConnectFb:
    """Handler for CONNECT FIREBIRD."""

    def test_basic_firebird_no_encoding(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_fb

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.FirebirdDatabase") as MockFb:
            x_connect_fb(
                server="fbhost",
                db_name="fbdb",
                user="fbuser",
                db_alias="FBD",
                need_pwd=None,
                port=None,
                encoding=None,
            )
            MockFb.assert_called_once_with("fbhost", "fbdb", "fbuser", need_passwd=None, port=None)
            mock_dbs.add.assert_called_once_with("fbd", MockFb.return_value)

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_fb

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.FirebirdDatabase") as MockFb:
            x_connect_fb(
                server="fbhost",
                db_name="fbdb",
                user="fbuser",
                db_alias="fbd2",
                need_pwd="true",
                port="3050",
                encoding="utf8",
            )
            MockFb.assert_called_once_with(
                "fbhost",
                "fbdb",
                "fbuser",
                need_passwd=True,
                port=3050,
                encoding="utf8",
            )

    def test_need_pwd_false(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_fb

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.FirebirdDatabase") as MockFb:
            x_connect_fb(
                server="h",
                db_name="d",
                user=None,
                db_alias="fbd3",
                need_pwd="false",
                port=None,
                encoding=None,
            )
            _, kwargs = MockFb.call_args
            assert kwargs["need_passwd"] is False

    def test_user_none_stays_none(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_fb

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.FirebirdDatabase") as MockFb:
            x_connect_fb(
                server="h",
                db_name="d",
                user=None,
                db_alias="fbd4",
                need_pwd=None,
                port=None,
                encoding=None,
            )
            pos_args = MockFb.call_args[0]
            assert pos_args[2] is None


# ---------------------------------------------------------------------------
# x_connect_user_fb
# ---------------------------------------------------------------------------


class TestXConnectUserFb:
    """Handler for CONNECT FIREBIRD using current connection credentials."""

    def test_inherits_credentials(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_fb

        mock_dbs, mock_db = _make_current_db(user="fbuser")
        _state.upass = "fbpw"

        with patch("execsql.metacommands.connect.FirebirdDatabase") as MockFb:
            x_connect_user_fb(
                server="fbhost",
                db_name="fbdb",
                db_alias="ufb",
                port=None,
                encoding=None,
            )
            pos_args = MockFb.call_args[0]
            assert pos_args[2] == "fbuser"
            _, kwargs = MockFb.call_args
            assert kwargs["need_passwd"] is True
            mock_dbs.add.assert_called_once_with("ufb", MockFb.return_value)

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_fb

        _make_current_db(user="u")
        _state.upass = "pw"

        with patch("execsql.metacommands.connect.FirebirdDatabase") as MockFb:
            x_connect_user_fb(
                server="h",
                db_name="d",
                db_alias="ufb2",
                port="3050",
                encoding="utf8",
            )
            _, kwargs = MockFb.call_args
            assert kwargs["encoding"] == "utf8"
            assert kwargs["port"] == 3050

    def test_no_password_need_passwd_false(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_fb

        _make_current_db(user=None)
        _state.upass = None

        with patch("execsql.metacommands.connect.FirebirdDatabase") as MockFb:
            x_connect_user_fb(
                server="h",
                db_name="d",
                db_alias="ufb3",
                port=None,
                encoding=None,
            )
            _, kwargs = MockFb.call_args
            assert kwargs["need_passwd"] is False


# ---------------------------------------------------------------------------
# x_connect_ora (Oracle)
# ---------------------------------------------------------------------------


class TestXConnectOra:
    """Handler for CONNECT ORACLE."""

    def test_basic_oracle_no_encoding(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_ora

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.OracleDatabase") as MockOra:
            x_connect_ora(
                server="orahost",
                db_name="oradb",
                user="orauser",
                db_alias="ORA",
                need_pwd=None,
                port=None,
                encoding=None,
                password=None,
            )
            MockOra.assert_called_once_with(
                "orahost",
                "oradb",
                "orauser",
                need_passwd=None,
                port=None,
                password=None,
            )
            mock_dbs.add.assert_called_once_with("ora", MockOra.return_value)

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_ora

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.OracleDatabase") as MockOra:
            x_connect_ora(
                server="orahost",
                db_name="oradb",
                user="orauser",
                db_alias="ora2",
                need_pwd="true",
                port="1521",
                encoding="al32utf8",
                password='"orapw"',
            )
            MockOra.assert_called_once_with(
                "orahost",
                "oradb",
                "orauser",
                need_passwd=True,
                port=1521,
                encoding="al32utf8",
                password="orapw",
            )

    def test_need_pwd_false(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_ora

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.OracleDatabase") as MockOra:
            x_connect_ora(
                server="h",
                db_name="d",
                user=None,
                db_alias="ora3",
                need_pwd="false",
                port=None,
                encoding=None,
                password=None,
            )
            _, kwargs = MockOra.call_args
            assert kwargs["need_passwd"] is False

    def test_user_none_stays_none(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_ora

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.OracleDatabase") as MockOra:
            x_connect_ora(
                server="h",
                db_name="d",
                user=None,
                db_alias="ora4",
                need_pwd=None,
                port=None,
                encoding=None,
                password=None,
            )
            pos_args = MockOra.call_args[0]
            assert pos_args[2] is None

    def test_alias_lowercased(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_ora

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.OracleDatabase"):
            x_connect_ora(
                server="h",
                db_name="d",
                user=None,
                db_alias="MYORA",
                need_pwd=None,
                port=None,
                encoding=None,
                password=None,
            )
            assert mock_dbs.add.call_args[0][0] == "myora"


# ---------------------------------------------------------------------------
# x_connect_user_ora
# ---------------------------------------------------------------------------


class TestXConnectUserOra:
    """Handler for CONNECT ORACLE using current connection credentials."""

    def test_inherits_credentials(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_ora

        mock_dbs, mock_db = _make_current_db(user="orauser")
        _state.upass = "orapw"

        with patch("execsql.metacommands.connect.OracleDatabase") as MockOra:
            x_connect_user_ora(
                server="orahost",
                db_name="oradb",
                db_alias="uora",
                port=None,
                encoding=None,
            )
            pos_args = MockOra.call_args[0]
            assert pos_args[2] == "orauser"
            _, kwargs = MockOra.call_args
            assert kwargs["need_passwd"] is True
            assert kwargs["password"] == "orapw"
            mock_dbs.add.assert_called_once_with("uora", MockOra.return_value)

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_ora

        _make_current_db(user="u")
        _state.upass = "pw"

        with patch("execsql.metacommands.connect.OracleDatabase") as MockOra:
            x_connect_user_ora(
                server="h",
                db_name="d",
                db_alias="uora2",
                port="1521",
                encoding="al32utf8",
            )
            _, kwargs = MockOra.call_args
            assert kwargs["encoding"] == "al32utf8"
            assert kwargs["port"] == 1521

    def test_no_password_need_passwd_false(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_user_ora

        _make_current_db(user=None)
        _state.upass = None

        with patch("execsql.metacommands.connect.OracleDatabase") as MockOra:
            x_connect_user_ora(
                server="h",
                db_name="d",
                db_alias="uora3",
                port=None,
                encoding=None,
            )
            _, kwargs = MockOra.call_args
            assert kwargs["need_passwd"] is False


# ---------------------------------------------------------------------------
# x_connect_duckdb
# ---------------------------------------------------------------------------


class TestXConnectDuckdb:
    """Handler for CONNECT DUCKDB."""

    def test_new_db_created_when_new_keyword_given(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_duckdb

        mock_dbs = _make_mock_dbs()
        db_path = str(tmp_path / "test.duckdb")

        with patch("execsql.metacommands.connect.DuckDBDatabase") as MockDuck:
            x_connect_duckdb(
                filename=db_path,
                db_alias="DKB",
                new="NEW",
                metacommandline="CONNECT DUCKDB ...",
            )
            MockDuck.assert_called_once_with(db_path)
            mock_dbs.add.assert_called_once_with("dkb", MockDuck.return_value)

    def test_existing_file_connects_without_new(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_duckdb

        db_path = tmp_path / "existing.duckdb"
        db_path.write_bytes(b"")
        mock_dbs = _make_mock_dbs()

        with patch("execsql.metacommands.connect.DuckDBDatabase") as MockDuck:
            x_connect_duckdb(
                filename=str(db_path),
                db_alias="dkb2",
                new=None,
                metacommandline="CONNECT DUCKDB ...",
            )
            MockDuck.assert_called_once_with(str(db_path))
            mock_dbs.add.assert_called_once_with("dkb2", MockDuck.return_value)

    def test_missing_file_no_new_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_duckdb

        _make_mock_dbs()
        with pytest.raises(ErrInfo):
            x_connect_duckdb(
                filename=str(tmp_path / "gone.duckdb"),
                db_alias="dkb3",
                new=None,
                metacommandline="CONNECT DUCKDB ...",
            )

    def test_new_deletes_existing_file(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_duckdb

        db_path = tmp_path / "old.duckdb"
        db_path.write_bytes(b"old data")
        _make_mock_dbs()

        with patch("execsql.metacommands.connect.DuckDBDatabase"):
            x_connect_duckdb(
                filename=str(db_path),
                db_alias="dkb4",
                new="new",
                metacommandline="CONNECT DUCKDB ...",
            )
        assert not db_path.exists()

    def test_new_case_insensitive(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_duckdb

        db_path = str(tmp_path / "ci.duckdb")
        _make_mock_dbs()

        with patch("execsql.metacommands.connect.DuckDBDatabase") as MockDuck:
            x_connect_duckdb(
                filename=db_path,
                db_alias="dkb5",
                new="New",
                metacommandline="CONNECT DUCKDB ...",
            )
            MockDuck.assert_called_once_with(db_path)


# ---------------------------------------------------------------------------
# x_connect_sqlite
# ---------------------------------------------------------------------------


class TestXConnectSqlite:
    """Handler for CONNECT SQLITE."""

    def test_new_db_created_when_new_keyword_given(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_sqlite

        db_path = str(tmp_path / "new.db")
        mock_dbs = _make_mock_dbs()

        with patch("execsql.metacommands.connect.SQLiteDatabase") as MockSQLite:
            x_connect_sqlite(
                filename=db_path,
                db_alias="SDB",
                new="NEW",
                metacommandline="CONNECT SQLITE ...",
            )
            MockSQLite.assert_called_once_with(db_path)
            mock_dbs.add.assert_called_once_with("sdb", MockSQLite.return_value)

    def test_existing_file_connects_without_new(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_sqlite

        db_path = tmp_path / "existing.db"
        db_path.write_bytes(b"")
        mock_dbs = _make_mock_dbs()

        with patch("execsql.metacommands.connect.SQLiteDatabase") as MockSQLite:
            x_connect_sqlite(
                filename=str(db_path),
                db_alias="sdb2",
                new=None,
                metacommandline="CONNECT SQLITE ...",
            )
            MockSQLite.assert_called_once_with(str(db_path))
            mock_dbs.add.assert_called_once_with("sdb2", MockSQLite.return_value)

    def test_missing_file_no_new_raises(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_sqlite

        _make_mock_dbs()
        with pytest.raises(ErrInfo):
            x_connect_sqlite(
                filename=str(tmp_path / "nosuchfile.db"),
                db_alias="sdb3",
                new=None,
                metacommandline="CONNECT SQLITE ...",
            )

    def test_new_deletes_existing_file(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_sqlite

        db_path = tmp_path / "old.db"
        db_path.write_bytes(b"old data")
        _make_mock_dbs()

        with patch("execsql.metacommands.connect.SQLiteDatabase"):
            x_connect_sqlite(
                filename=str(db_path),
                db_alias="sdb4",
                new="new",
                metacommandline="CONNECT SQLITE ...",
            )
        assert not db_path.exists()

    def test_errinfo_contains_command_text(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_sqlite

        _make_mock_dbs()
        cmd_text = "CONNECT SQLITE /missing/path.db AS sdb5"
        with pytest.raises(ErrInfo) as exc_info:
            x_connect_sqlite(
                filename=str(tmp_path / "absent.db"),
                db_alias="sdb5",
                new=None,
                metacommandline=cmd_text,
            )
        # ErrInfo stores command_text as .command attribute
        assert exc_info.value.command == cmd_text

    def test_alias_lowercased(self, minimal_conf, tmp_path):
        from execsql.metacommands.connect import x_connect_sqlite

        db_path = str(tmp_path / "lc.db")
        mock_dbs = _make_mock_dbs()

        with patch("execsql.metacommands.connect.SQLiteDatabase"):
            x_connect_sqlite(
                filename=db_path,
                db_alias="MySQLite",
                new="NEW",
                metacommandline="...",
            )
            assert mock_dbs.add.call_args[0][0] == "mysqlite"


# ---------------------------------------------------------------------------
# x_connect_dsn
# ---------------------------------------------------------------------------


class TestXConnectDsn:
    """Handler for CONNECT DSN."""

    def test_basic_dsn_no_encoding(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_dsn

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.DsnDatabase") as MockDsn:
            x_connect_dsn(
                dsn="mydsn",
                user="dsnuser",
                db_alias="DSN1",
                need_pwd=None,
                encoding=None,
                password=None,
            )
            MockDsn.assert_called_once_with(
                "mydsn",
                "dsnuser",
                need_passwd=None,
                password=None,
            )
            mock_dbs.add.assert_called_once_with("dsn1", MockDsn.return_value)

    def test_with_encoding_branch(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_dsn

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.DsnDatabase") as MockDsn:
            x_connect_dsn(
                dsn="mydsn",
                user="u",
                db_alias="dsn2",
                need_pwd="true",
                encoding="latin1",
                password="pw",
            )
            MockDsn.assert_called_once_with(
                "mydsn",
                "u",
                need_passwd=True,
                encoding="latin1",
                password="pw",
            )

    def test_need_pwd_false(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_dsn

        _make_mock_dbs()
        with patch("execsql.metacommands.connect.DsnDatabase") as MockDsn:
            x_connect_dsn(
                dsn="d",
                user=None,
                db_alias="dsn3",
                need_pwd="false",
                encoding=None,
                password=None,
            )
            _, kwargs = MockDsn.call_args
            assert kwargs["need_passwd"] is False

    def test_alias_lowercased(self, minimal_conf):
        from execsql.metacommands.connect import x_connect_dsn

        mock_dbs = _make_mock_dbs()
        with patch("execsql.metacommands.connect.DsnDatabase"):
            x_connect_dsn(
                dsn="d",
                user=None,
                db_alias="MyDSN",
                need_pwd=None,
                encoding=None,
                password=None,
            )
            assert mock_dbs.add.call_args[0][0] == "mydsn"


# ---------------------------------------------------------------------------
# x_use
# ---------------------------------------------------------------------------


class TestXUse:
    """Handler for USE DATABASE."""

    def test_switches_current_db_and_sets_subvars(self, minimal_conf):
        from execsql.metacommands.connect import x_use

        mock_dbs, mock_db = _make_current_db(dbms_id="postgresql", db_name="thedb", server_name="theserver")
        mock_dbs.aliases.return_value = ["initial", "myalias"]
        mock_log = _make_mock_exec_log()
        mock_sv = _make_mock_subvars()

        x_use(db_alias="myalias", metacommandline="USE DATABASE myalias")

        mock_dbs.make_current.assert_called_once_with("myalias")
        mock_log.log_db_connect.assert_called_once_with(mock_dbs.current())
        assert mock_sv.add_substitution.call_count == 3

    def test_sets_current_dbms_substitution_var(self, minimal_conf):
        from execsql.metacommands.connect import x_use

        mock_dbs, mock_db = _make_current_db(dbms_id="sqlite")
        mock_dbs.aliases.return_value = ["initial", "lite"]
        _make_mock_exec_log()
        mock_sv = _make_mock_subvars()

        x_use(db_alias="lite", metacommandline="USE DATABASE lite")

        calls = [str(c) for c in mock_sv.add_substitution.call_args_list]
        assert any("$CURRENT_DBMS" in c for c in calls)

    def test_unknown_alias_raises_errinfo(self, minimal_conf):
        from execsql.metacommands.connect import x_use

        mock_dbs = _make_mock_dbs()
        mock_dbs.aliases.return_value = ["initial"]
        _make_mock_exec_log()
        _make_mock_subvars()

        with pytest.raises(ErrInfo):
            x_use(db_alias="nosuch", metacommandline="USE DATABASE nosuch")

    def test_alias_lowercased_before_lookup(self, minimal_conf):
        from execsql.metacommands.connect import x_use

        mock_dbs, mock_db = _make_current_db()
        mock_dbs.aliases.return_value = ["initial", "mydb"]
        _make_mock_exec_log()
        _make_mock_subvars()

        x_use(db_alias="MYDB", metacommandline="USE DATABASE MYDB")

        mock_dbs.make_current.assert_called_once_with("mydb")

    def test_use_sets_db_server_substitution_var(self, minimal_conf):
        from execsql.metacommands.connect import x_use

        mock_dbs, mock_db = _make_current_db(server_name="dbserver.example.com")
        mock_dbs.aliases.return_value = ["initial", "remotedb"]
        _make_mock_exec_log()
        mock_sv = _make_mock_subvars()

        x_use(db_alias="remotedb", metacommandline="USE DATABASE remotedb")

        subvar_calls = [c[0] for c in mock_sv.add_substitution.call_args_list]
        subvar_names = [c[0] for c in subvar_calls]
        assert "$DB_SERVER" in subvar_names


# ---------------------------------------------------------------------------
# x_disconnect
# ---------------------------------------------------------------------------


class TestXDisconnect:
    """Handler for CLOSE DATABASE."""

    def test_disconnect_named_alias(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        mock_dbs = _make_mock_dbs()
        _make_mock_exec_log()
        _make_mock_status()

        x_disconnect(alias="mydb")

        mock_dbs.disconnect.assert_called_once_with("mydb")

    def test_disconnect_none_uses_current_alias(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        mock_dbs = _make_mock_dbs(current_alias="mydb")
        _make_mock_exec_log()
        _make_mock_status()

        x_disconnect(alias=None)

        mock_dbs.disconnect.assert_called_once_with("mydb")

    def test_disconnect_initial_raises_errinfo(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        _make_mock_dbs()
        _make_mock_exec_log()
        _make_mock_status()

        with pytest.raises(ErrInfo) as exc_info:
            x_disconnect(alias="initial")
        assert "initial" in str(exc_info.value).lower()

    def test_disconnect_db_in_batch_raises_errinfo(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        _make_mock_dbs()
        _make_mock_exec_log()
        _make_mock_status(uses_db=True)

        with pytest.raises(ErrInfo) as exc_info:
            x_disconnect(alias="mydb")
        assert "batch" in str(exc_info.value).lower()

    def test_disconnect_current_db_resets_to_initial(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        mock_dbs = _make_mock_dbs(current_alias="mydb")
        _make_mock_exec_log()
        _make_mock_status()

        x_disconnect(alias="mydb")

        mock_dbs.make_current.assert_called_once_with("initial")
        mock_dbs.disconnect.assert_called_once_with("mydb")

    def test_disconnect_non_current_db_does_not_change_current(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        mock_dbs = _make_mock_dbs(current_alias="initial")
        _make_mock_exec_log()
        _make_mock_status()

        x_disconnect(alias="mydb")

        mock_dbs.make_current.assert_not_called()
        mock_dbs.disconnect.assert_called_once_with("mydb")

    def test_disconnect_logs_status_info(self, minimal_conf):
        from execsql.metacommands.connect import x_disconnect

        _make_mock_dbs()
        mock_log = _make_mock_exec_log()
        _make_mock_status()

        x_disconnect(alias="mydb")

        mock_log.log_status_info.assert_called_once()
        logged_msg = mock_log.log_status_info.call_args[0][0]
        assert "mydb" in logged_msg


# ---------------------------------------------------------------------------
# x_autocommit_on
# ---------------------------------------------------------------------------


class TestXAutocommitOn:
    """Handler for AUTOCOMMIT ON."""

    def test_autocommit_on_no_action(self, minimal_conf):
        from execsql.metacommands.connect import x_autocommit_on

        mock_db = MagicMock()
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_autocommit_on(action=None)

        mock_db.autocommit_on.assert_called_once()
        mock_db.commit.assert_not_called()
        mock_db.rollback.assert_not_called()

    def test_autocommit_on_with_commit_action(self, minimal_conf):
        from execsql.metacommands.connect import x_autocommit_on

        mock_db = MagicMock()
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_autocommit_on(action="COMMIT")

        mock_db.autocommit_on.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()

    def test_autocommit_on_with_rollback_action(self, minimal_conf):
        from execsql.metacommands.connect import x_autocommit_on

        mock_db = MagicMock()
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_autocommit_on(action="ROLLBACK")

        mock_db.autocommit_on.assert_called_once()
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_autocommit_on_action_case_insensitive(self, minimal_conf):
        from execsql.metacommands.connect import x_autocommit_on

        mock_db = MagicMock()
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_autocommit_on(action="Commit")

        mock_db.commit.assert_called_once()

    def test_autocommit_on_unknown_action_calls_rollback(self, minimal_conf):
        from execsql.metacommands.connect import x_autocommit_on

        mock_db = MagicMock()
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_autocommit_on(action="UNKNOWN_ACTION")

        mock_db.autocommit_on.assert_called_once()
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# x_autocommit_off
# ---------------------------------------------------------------------------


class TestXAutocommitOff:
    """Handler for AUTOCOMMIT OFF."""

    def test_autocommit_off_calls_db_method(self, minimal_conf):
        from execsql.metacommands.connect import x_autocommit_off

        mock_db = MagicMock()
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_autocommit_off()

        mock_db.autocommit_off.assert_called_once()

    def test_autocommit_off_uses_current_db(self, minimal_conf):
        from execsql.metacommands.connect import x_autocommit_off

        mock_db = MagicMock()
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_autocommit_off()

        mock_dbs.current.assert_called_once()


# ---------------------------------------------------------------------------
# x_pg_vacuum
# ---------------------------------------------------------------------------


class TestXPgVacuum:
    """Handler for PostgreSQL VACUUM."""

    def test_vacuum_called_on_postgres_db(self, minimal_conf):
        from execsql.metacommands.connect import x_pg_vacuum
        from execsql.types import dbt_postgres

        mock_db = MagicMock()
        mock_db.type = dbt_postgres
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_pg_vacuum(vacuum_args="FULL ANALYZE")

        mock_db.vacuum.assert_called_once_with("FULL ANALYZE")

    def test_vacuum_not_called_on_non_postgres_db(self, minimal_conf):
        from execsql.metacommands.connect import x_pg_vacuum
        from execsql.types import dbt_sqlite

        mock_db = MagicMock()
        mock_db.type = dbt_sqlite
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_pg_vacuum(vacuum_args="FULL")

        mock_db.vacuum.assert_not_called()

    def test_vacuum_none_args_forwarded(self, minimal_conf):
        from execsql.metacommands.connect import x_pg_vacuum
        from execsql.types import dbt_postgres

        mock_db = MagicMock()
        mock_db.type = dbt_postgres
        mock_dbs = _make_mock_dbs()
        mock_dbs.current.return_value = mock_db

        x_pg_vacuum(vacuum_args=None)

        mock_db.vacuum.assert_called_once_with(None)


# ---------------------------------------------------------------------------
# x_daoflushdelay
# ---------------------------------------------------------------------------


class TestXDaoFlushDelay:
    """Handler for DAO FLUSH DELAY."""

    @pytest.mark.parametrize(
        "secs,expected",
        [
            ("5.0", 5.0),
            ("10.0", 10.0),
            ("100.5", 100.5),
            ("5", 5.0),
        ],
    )
    def test_valid_delay_stored_on_conf(self, minimal_conf, secs, expected):
        from execsql.metacommands.connect import x_daoflushdelay

        x_daoflushdelay(secs=secs)
        assert minimal_conf.dao_flush_delay_secs == expected

    @pytest.mark.parametrize("secs", ["0", "1.0", "4.99", "-1"])
    def test_delay_below_minimum_raises_errinfo(self, minimal_conf, secs):
        from execsql.metacommands.connect import x_daoflushdelay

        with pytest.raises(ErrInfo) as exc_info:
            x_daoflushdelay(secs=secs)
        assert "5.0" in str(exc_info.value)

    def test_error_message_includes_bad_value(self, minimal_conf):
        from execsql.metacommands.connect import x_daoflushdelay

        with pytest.raises(ErrInfo) as exc_info:
            x_daoflushdelay(secs="3.14")
        assert "3.14" in str(exc_info.value)

    def test_exactly_five_is_valid(self, minimal_conf):
        from execsql.metacommands.connect import x_daoflushdelay

        x_daoflushdelay(secs="5.0")
        assert minimal_conf.dao_flush_delay_secs == 5.0


# ---------------------------------------------------------------------------
# Parametrized cross-handler checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "handler_name,db_class_path,kwargs",
    [
        (
            "x_connect_pg",
            "execsql.metacommands.connect.PostgresDatabase",
            {
                "server": "h",
                "db_name": "d",
                "user": None,
                "db_alias": "alias",
                "need_pwd": None,
                "port": None,
                "new": None,
                "password": None,
                "encoding": None,
            },
        ),
        (
            "x_connect_ssvr",
            "execsql.metacommands.connect.SqlServerDatabase",
            {
                "server": "h",
                "db_name": "d",
                "user": None,
                "db_alias": "alias",
                "need_pwd": None,
                "port": None,
                "encoding": None,
                "password": None,
            },
        ),
        (
            "x_connect_mysql",
            "execsql.metacommands.connect.MySQLDatabase",
            {
                "server": "h",
                "db_name": "d",
                "user": None,
                "db_alias": "alias",
                "need_pwd": None,
                "port": None,
                "encoding": None,
                "password": None,
            },
        ),
        (
            "x_connect_fb",
            "execsql.metacommands.connect.FirebirdDatabase",
            {
                "server": "h",
                "db_name": "d",
                "user": None,
                "db_alias": "alias",
                "need_pwd": None,
                "port": None,
                "encoding": None,
            },
        ),
        (
            "x_connect_ora",
            "execsql.metacommands.connect.OracleDatabase",
            {
                "server": "h",
                "db_name": "d",
                "user": None,
                "db_alias": "alias",
                "need_pwd": None,
                "port": None,
                "encoding": None,
                "password": None,
            },
        ),
        (
            "x_connect_access",
            "execsql.metacommands.connect.AccessDatabase",
            {"filename": "f.mdb", "db_alias": "alias", "need_pwd": None, "encoding": None, "password": None},
        ),
        (
            "x_connect_dsn",
            "execsql.metacommands.connect.DsnDatabase",
            {"dsn": "d", "user": None, "db_alias": "alias", "need_pwd": None, "encoding": None, "password": None},
        ),
    ],
)
def test_handler_registers_db_with_pool(minimal_conf, handler_name, db_class_path, kwargs):
    """Every connect handler must call _state.dbs.add(alias, db_instance)."""
    import importlib

    module = importlib.import_module("execsql.metacommands.connect")
    handler = getattr(module, handler_name)

    mock_dbs = _make_mock_dbs()
    with patch(db_class_path) as MockDB:
        mock_inst = MagicMock()
        MockDB.return_value = mock_inst
        handler(**kwargs)
        mock_dbs.add.assert_called_once()
        # First argument to .add() must be the lowercased alias
        assert mock_dbs.add.call_args[0][0] == "alias"
        # Second argument must be the db instance returned by the constructor
        assert mock_dbs.add.call_args[0][1] is mock_inst
