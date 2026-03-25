"""Connection-string (DSN URL) parser for the execsql CLI."""

from __future__ import annotations

from execsql.exceptions import ConfigError

#: Mapping from URL scheme to execsql db_type code.
_SCHEME_TO_DBTYPE: dict[str, str] = {
    "postgresql": "p",
    "postgres": "p",
    "mysql": "m",
    "mariadb": "m",
    "mssql": "s",
    "sqlserver": "s",
    "oracle": "o",
    "oracle+cx_oracle": "o",
    "firebird": "f",
    "sqlite": "l",
    "duckdb": "k",
}


def _parse_connection_string(dsn: str) -> dict:
    """Parse a database URL into a dict of connection parameters.

    Supports the common form::

        scheme://[user[:password]@][host[:port]]/database

    For file-based databases (SQLite, DuckDB) the path after ``//`` is
    treated as the database file path::

        sqlite:///path/to/file.db   -> db_file = /path/to/file.db
        duckdb:///path/to/file.db   -> db_file = /path/to/file.db

    Returns a dict with keys: ``db_type``, ``server``, ``db``, ``db_file``,
    ``user``, ``password``, ``port``.  Absent components are ``None``.

    Raises :class:`~execsql.exceptions.ConfigError` for an unrecognised
    URL scheme or a completely un-parseable string.
    """
    from urllib.parse import urlparse

    parsed = urlparse(dsn)
    scheme = parsed.scheme.lower()
    if not scheme:
        raise ConfigError(f"Cannot parse connection string (no scheme): {dsn!r}")
    if scheme not in _SCHEME_TO_DBTYPE:
        raise ConfigError(
            f"Unrecognised connection-string scheme {scheme!r}. "
            f"Supported schemes: {', '.join(sorted(_SCHEME_TO_DBTYPE))}",
        )

    db_type = _SCHEME_TO_DBTYPE[scheme]
    port: int | None = parsed.port
    server: str | None = parsed.hostname or None
    user: str | None = parsed.username or None
    password: str | None = parsed.password or None

    # Database / file path
    # urlparse puts the path in parsed.path.  For three-slash URIs like
    # sqlite:///foo.db the path starts with "/"; strip exactly one leading
    # slash for relative paths (sqlite:///foo.db -> foo.db) and leave
    # absolute paths intact (sqlite:////abs/path -> /abs/path).
    raw_path = parsed.path
    if db_type in ("l", "k", "a"):
        # File-based: no server component
        if raw_path.startswith("/") and not raw_path.startswith("//"):
            db_file: str | None = raw_path[1:] or None
        else:
            db_file = raw_path or None
        db: str | None = None
    else:
        db_file = None
        # Remove leading "/"
        db = raw_path.lstrip("/") or None

    return {
        "db_type": db_type,
        "server": server,
        "db": db,
        "db_file": db_file,
        "user": user,
        "password": password,
        "port": port,
    }
