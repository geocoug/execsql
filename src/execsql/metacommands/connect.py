from __future__ import annotations
from execsql.db.access import AccessDatabase

"""
Database connection metacommand handlers for execsql.

Implements all ``x_connect_*`` handler functions that open or switch
database connections at script runtime:

- ``x_connect_pg`` — ``CONNECT POSTGRESQL …``
- ``x_connect_mysql`` — ``CONNECT MYSQL …``
- ``x_connect_oracle`` — ``CONNECT ORACLE …``
- ``x_connect_sqlite`` — ``CONNECT SQLITE …``
- ``x_connect_duckdb`` — ``CONNECT DUCKDB …``
- ``x_connect_firebird`` — ``CONNECT FIREBIRD …``
- ``x_connect_sqlserver`` — ``CONNECT SQLSERVER …``
- ``x_connect_access`` — ``CONNECT ACCESS …``
- ``x_connect_dsn`` — ``CONNECT DSN …``
- ``x_use_db`` — ``USE DATABASE <alias>``
- ``x_close_db`` — ``CLOSE DATABASE <alias>``
"""

from pathlib import Path
from typing import Any

import execsql.state as _state
from execsql.db.dsn import DsnDatabase
from execsql.db.duckdb import DuckDBDatabase
from execsql.db.firebird import FirebirdDatabase
from execsql.db.mysql import MySQLDatabase
from execsql.db.oracle import OracleDatabase
from execsql.db.postgres import PostgresDatabase
from execsql.db.sqlite import SQLiteDatabase
from execsql.db.sqlserver import SqlServerDatabase
from execsql.exceptions import ErrInfo
from execsql.types import dbt_postgres
from execsql.utils.fileio import check_dir
from execsql.utils.strings import unquoted2


def x_connect_pg(**kwargs: Any) -> None:
    need_pwd = kwargs["need_pwd"]
    if need_pwd:
        need_pwd = unquoted2(need_pwd).lower() == "true"
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = kwargs["user"]
    if user:
        user = unquoted2(user)
    mk_new = kwargs["new"]
    mk_new = unquoted2(mk_new).lower() == "new" if mk_new else False
    pw = kwargs["password"]
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
        new_db = PostgresDatabase(
            server,
            db_name,
            user,
            need_passwd=need_pwd,
            port=portno,
            new_db=mk_new,
            encoding=enc,
            password=pw,
        )
    else:
        new_db = PostgresDatabase(
            server,
            db_name,
            user,
            need_passwd=need_pwd,
            port=portno,
            new_db=mk_new,
            password=pw,
        )
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_user_pg(**kwargs: Any) -> None:
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = _state.dbs.current().user if _state.dbs.current().user else None
    pw = _state.upass
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
        new_db = PostgresDatabase(
            server,
            db_name,
            user,
            need_passwd=pw is not None,
            port=portno,
            new_db=False,
            encoding=enc,
            password=pw,
        )
    else:
        new_db = PostgresDatabase(
            server,
            db_name,
            user,
            need_passwd=pw is not None,
            port=portno,
            new_db=False,
            password=pw,
        )
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_ssvr(**kwargs: Any) -> None:
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = kwargs["user"]
    if user:
        user = unquoted2(user)
    need_pwd = kwargs["need_pwd"]
    pw = kwargs["password"]
    if pw is not None:
        pw = unquoted2(pw)
    if need_pwd:
        need_pwd = unquoted2(need_pwd).lower() == "true"
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    encoding = kwargs["encoding"]
    if encoding:
        encoding = unquoted2(encoding)
    new_db = SqlServerDatabase(
        server,
        db_name,
        user_name=user,
        need_passwd=need_pwd,
        port=portno,
        encoding=encoding,
        password=pw,
    )
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_user_ssvr(**kwargs: Any) -> None:
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = _state.dbs.current().user if _state.dbs.current().user else None
    pw = _state.upass
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
        new_db = SqlServerDatabase(
            server,
            db_name,
            user,
            need_passwd=pw is not None,
            port=portno,
            encoding=enc,
            password=pw,
        )
    else:
        new_db = SqlServerDatabase(
            server,
            db_name,
            user_name=user,
            need_passwd=pw is not None,
            port=portno,
            encoding=enc,
            password=pw,
        )
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_mysql(**kwargs: Any) -> None:
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = kwargs["user"]
    if user:
        user = unquoted2(user)
    need_pwd = kwargs["need_pwd"]
    if need_pwd:
        need_pwd = unquoted2(need_pwd).lower() == "true"
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    pw = kwargs["password"]
    if pw:
        pw = unquoted2(pw)
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
        new_db = MySQLDatabase(
            server,
            db_name,
            user,
            need_passwd=need_pwd,
            port=portno,
            encoding=enc,
            password=pw,
        )
    else:
        new_db = MySQLDatabase(
            server,
            db_name,
            user,
            need_passwd=need_pwd,
            port=portno,
            password=pw,
        )
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_user_mysql(**kwargs: Any) -> None:
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = _state.dbs.current().user if _state.dbs.current().user else None
    pw = _state.upass
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
        new_db = MySQLDatabase(
            server,
            db_name,
            user,
            need_passwd=pw is not None,
            port=portno,
            encoding=enc,
            password=pw,
        )
    else:
        new_db = MySQLDatabase(
            server,
            db_name,
            user,
            need_passwd=pw is not None,
            port=portno,
            password=pw,
        )
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_access(**kwargs: Any) -> None:
    db_file = unquoted2(kwargs["filename"])
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
    need_pwd = kwargs["need_pwd"]
    password = kwargs["password"]
    if password:
        password = unquoted2(password)
    if need_pwd:
        need_pwd = unquoted2(need_pwd).lower() == "true"
    new_db = AccessDatabase(db_file, need_passwd=need_pwd, encoding=enc, password=password)
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_fb(**kwargs: Any) -> None:
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = kwargs["user"]
    if user:
        user = unquoted2(user)
    need_pwd = kwargs["need_pwd"]
    if need_pwd:
        need_pwd = unquoted2(need_pwd).lower() == "true"
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
        new_db = FirebirdDatabase(server, db_name, user, need_passwd=need_pwd, port=portno, encoding=enc)
    else:
        new_db = FirebirdDatabase(server, db_name, user, need_passwd=need_pwd, port=portno)
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_user_fb(**kwargs: Any) -> None:
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = _state.dbs.current().user if _state.dbs.current().user else None
    pw = _state.upass
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
        new_db = FirebirdDatabase(server, db_name, user, need_passwd=pw is not None, port=portno, encoding=enc)
    else:
        new_db = FirebirdDatabase(server, db_name, user, need_passwd=pw is not None, port=portno)
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_ora(**kwargs: Any) -> None:
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = kwargs["user"]
    if user:
        user = unquoted2(user)
    need_pwd = kwargs["need_pwd"]
    if need_pwd:
        need_pwd = unquoted2(need_pwd).lower() == "true"
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    pw = kwargs["password"]
    if pw:
        pw = unquoted2(pw)
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
        new_db = OracleDatabase(
            server,
            db_name,
            user,
            need_passwd=need_pwd,
            port=portno,
            encoding=enc,
            password=pw,
        )
    else:
        new_db = OracleDatabase(server, db_name, user, need_passwd=need_pwd, port=portno, password=pw)
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_user_ora(**kwargs: Any) -> None:
    portno = kwargs["port"]
    if portno:
        portno = int(unquoted2(portno))
    server = unquoted2(kwargs["server"])
    db_name = unquoted2(kwargs["db_name"])
    user = _state.dbs.current().user if _state.dbs.current().user else None
    pw = _state.upass
    enc = kwargs["encoding"]
    if enc:
        enc = unquoted2(enc)
        new_db = OracleDatabase(
            server,
            db_name,
            user,
            need_passwd=pw is not None,
            port=portno,
            encoding=enc,
            password=pw,
        )
    else:
        new_db = OracleDatabase(
            server,
            db_name,
            user,
            need_passwd=pw is not None,
            port=portno,
            password=pw,
        )
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_duckdb(**kwargs: Any) -> None:
    import os

    db_file = unquoted2(kwargs["filename"])
    mk_new = kwargs["new"]
    mk_new = unquoted2(mk_new).lower() == "new" if mk_new else False
    if not mk_new and not Path(db_file).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="DuckDB file does not exist.",
        )
    if mk_new:
        check_dir(db_file)
        if Path(db_file).exists():
            os.unlink(db_file)
    new_db = DuckDBDatabase(db_file)
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_sqlite(**kwargs: Any) -> None:
    import os

    db_file = unquoted2(kwargs["filename"])
    mk_new = kwargs["new"]
    mk_new = unquoted2(mk_new).lower() == "new" if mk_new else False
    if not mk_new and not Path(db_file).exists():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg="SQLite file does not exist.",
        )
    if mk_new:
        check_dir(db_file)
        if Path(db_file).exists():
            os.unlink(db_file)
    new_db = SQLiteDatabase(db_file)
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_connect_dsn(**kwargs: Any) -> None:
    need_pwd = kwargs["need_pwd"]
    if need_pwd:
        need_pwd = need_pwd.lower() == "true"
    pw = kwargs["password"]
    enc = kwargs["encoding"]
    if enc:
        new_db = DsnDatabase(kwargs["dsn"], kwargs["user"], need_passwd=need_pwd, encoding=enc, password=pw)
    else:
        new_db = DsnDatabase(kwargs["dsn"], kwargs["user"], need_passwd=need_pwd, password=pw)
    _state.dbs.add(kwargs["db_alias"].lower(), new_db)
    return None


def x_use(**kwargs: Any) -> None:
    db_alias = kwargs["db_alias"].lower()
    if db_alias not in _state.dbs.aliases():
        raise ErrInfo(
            type="cmd",
            command_text=kwargs["metacommandline"],
            other_msg=f"Unrecognized database alias: {db_alias}.",
        )
    _state.dbs.make_current(db_alias)
    _state.exec_log.log_db_connect(_state.dbs.current())
    _state.subvars.add_substitution("$CURRENT_DBMS", _state.dbs.aliased_as(db_alias).type.dbms_id)
    _state.subvars.add_substitution("$CURRENT_DATABASE", _state.dbs.aliased_as(db_alias).name())
    _state.subvars.add_substitution("$DB_SERVER", _state.dbs.aliased_as(db_alias).server_name)
    return None


def x_disconnect(**kwargs: Any) -> None:
    alias = kwargs["alias"]
    current_alias = _state.dbs.current_alias()
    if alias is None:
        alias = _state.dbs.current_alias()
    if alias.lower() == "initial":
        raise ErrInfo(type="error", other_msg="You may not disconnect from the initial database used.")
    if _state.status.batch.uses_db(alias):
        raise ErrInfo(
            type="error",
            other_msg="You may not disconnect from a database that is currently used in a batch.",
        )
    _state.exec_log.log_status_info(f"Disconnecting from database with alias '{alias}'")
    if alias == current_alias:
        _state.dbs.make_current("initial")
    _state.dbs.disconnect(alias)


def x_autocommit_on(**kwargs: Any) -> None:
    action = kwargs["action"]
    if action is not None:
        action = action.lower()
    db = _state.dbs.current()
    db.autocommit_on()
    if action is not None:
        if action == "commit":
            db.commit()
        else:
            db.rollback()


def x_autocommit_off(**kwargs: Any) -> None:
    db = _state.dbs.current()
    db.autocommit_off()


def x_pg_vacuum(**kwargs: Any) -> None:
    db = _state.dbs.current()
    if db.type == dbt_postgres:
        args = kwargs["vacuum_args"]
        db.vacuum(args)


def x_daoflushdelay(**kwargs: Any) -> None:
    delay = float(kwargs["secs"])
    if delay < 5.0:
        raise ErrInfo(type="error", other_msg=f"Invalid DAO flush delay: {delay}; must be >= 5.0.")
    _state.conf.dao_flush_delay_secs = delay
