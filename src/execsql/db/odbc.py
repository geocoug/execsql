"""
ODBC connection strings for the SQL Server and Access adapters.

An ODBC connection string is a ``;``-separated list of ``KEY=value``
attributes, so a value containing ``;`` (a password, a file path, a name
taken from a substitution variable) would end its attribute early and
start another.  :func:`odbc_value` brace-quotes such values;
:func:`connection_string` joins the attributes, and :func:`loggable`
gives the same string with the password masked for the log.
"""

from __future__ import annotations

__all__ = ["connection_string", "loggable", "odbc_value"]

_SECRET_KEYS = frozenset({"pwd", "password"})


def odbc_value(value: object) -> str:
    """Return *value* as an ODBC attribute value, brace-quoted when it needs it.

    A ``;`` ends an attribute and a leading ``{`` opens a quoted value, so a
    value with either is wrapped in ``{…}`` with each ``}`` doubled.  Other
    values are written as they are, because older drivers do not all accept
    braces around every attribute.
    """
    text = str(value)
    if ";" in text or text.startswith("{"):
        return "{" + text.replace("}", "}}") + "}"
    return text


def connection_string(driver: str, attributes: list[tuple[str, object]]) -> str:
    """Return ``DRIVER={driver};KEY=value;…`` with every value quoted as needed."""
    parts = [f"DRIVER={{{driver}}}"]
    parts.extend(f"{key}={odbc_value(value)}" for key, value in attributes)
    return ";".join(parts) + ";"


def loggable(driver: str, attributes: list[tuple[str, object]]) -> str:
    """Return the connection string with the password replaced by ``***``."""
    return connection_string(
        driver,
        [(key, "***" if key.lower() in _SECRET_KEYS else value) for key, value in attributes],
    )
