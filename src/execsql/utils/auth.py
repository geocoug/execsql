from __future__ import annotations

"""
Authentication utilities for execsql.

Provides :func:`get_password`, which prompts the user for a database
password on the terminal (via :func:`getpass.getpass`) or through the
GUI console when running in GUI mode.  The last entered password is
cached in ``_state.upass`` so that re-prompting is suppressed when
the same password is needed again within the same session.

When the ``keyring`` package is installed, :func:`get_password` checks
the OS credential store first (macOS Keychain, Windows Credential
Manager, or Linux SecretService).  If a stored password is found it is
returned without prompting.  A password typed at the prompt is stored
only once the connection it was typed for succeeds: the adapter calls
:func:`remember_password` after connecting.

If a stored password is rejected by the server (after a password
change), callers check :func:`password_from_keyring` and
:func:`is_login_failure`, call :func:`clear_stored_password`, and
re-prompt with ``skip_keyring=True``.  Any other connection failure (a
timeout, a closed port, a missing database) leaves the stored password
alone and is raised.

Keyring service names follow the pattern
``execsql/<db_type>/<server>:<port>/<database>`` for server databases
and ``execsql/<db_type>/local/<database>`` otherwise.  An entry stored by
an earlier version, without the port, is read only for a connection on
the DBMS's default port, and is saved under the new name once it works.
"""

import getpass
from typing import Any, cast

import execsql.state as _state
from execsql.utils.fileio import register_secret

__all__ = [
    "clear_stored_password",
    "get_password",
    "is_login_failure",
    "is_plaintext_keyring",
    "password_from_keyring",
    "remember_password",
]

# Tracks whether the most recent get_password() call returned a keyring-stored value.
_last_from_keyring: bool = False

# (service, user, password) to store once the connection succeeds: a password
# typed at the prompt, or one read under the pre-port service name.
_pending_store: tuple[str, str, str] | None = None

# The port each server DBMS uses when none is given.  Part of the keyring
# service name, so two servers on one host do not share a stored password.
_DEFAULT_PORTS = {"PostgreSQL": 5432, "MySQL": 3306, "SQL Server": 1433, "Oracle": 1521, "Firebird": 3050}

# Tracks whether we've already warned about a plaintext keyring backend
# this process — keyring is a one-shot warning, not a per-call nag.
_plaintext_warned: bool = False


def is_plaintext_keyring() -> bool:
    """Return True if the active keyring backend stores secrets in cleartext.

    B20/F040: on headless Linux without a real Secret Service, the
    ``keyrings.alt.file.PlaintextKeyring`` (or
    ``EncryptedKeyring`` with a hard-coded passphrase) backend is
    used silently. Detect by inspecting the active backend's module
    path so callers can warn the user instead of pretending secrets
    are encrypted.
    """
    try:
        import keyring

        backend = keyring.get_keyring()
        module = type(backend).__module__
        return "keyrings.alt" in module or "fail" in module.lower()
    except Exception:
        return False


def _warn_if_plaintext_keyring() -> None:
    """Print a one-time warning if the active keyring backend is plaintext."""
    global _plaintext_warned
    if _plaintext_warned or not is_plaintext_keyring():
        return
    _plaintext_warned = True
    try:
        import keyring
        import sys

        backend_name = type(keyring.get_keyring()).__name__
        print(
            f"WARNING: active keyring backend ({backend_name}) stores secrets in "
            f"cleartext or with a hard-coded key. Stored passwords are not "
            f"meaningfully protected.",
            file=sys.stderr,
        )
    except Exception:
        pass


def _keyring_service(
    dbms_name: str,
    database_name: str,
    server_name: str | None,
    port: int | None = None,
) -> str:
    """Build a keyring service name from connection parameters; a server database's name includes the port."""
    server_part = server_name or "local"
    if server_name and dbms_name in _DEFAULT_PORTS:
        server_part = f"{server_name}:{port or _DEFAULT_PORTS[dbms_name]}"
    return f"execsql/{dbms_name}/{server_part}/{database_name}"


def _legacy_keyring_service(
    dbms_name: str,
    database_name: str,
    server_name: str | None,
    port: int | None,
) -> str | None:
    """The service name used before the port was part of it, if this connection may read it.

    Such an entry does not say which port it was stored for, so it is only
    offered to a connection on the DBMS's default port.
    """
    default = _DEFAULT_PORTS.get(dbms_name)
    if not server_name or default is None or (port or default) != default:
        return None
    return f"execsql/{dbms_name}/{server_name}/{database_name}"


def _keyring_get(service: str, username: str) -> str | None:
    """Try to retrieve a password from the OS keyring.  Returns None on failure."""
    try:
        import keyring

        return keyring.get_password(service, username)
    except Exception:
        return None


def _keyring_set(service: str, username: str, password: str) -> bool:
    """Try to store a password in the OS keyring.  Returns True on success."""
    # B20/F040: warn before storing into a plaintext backend so the user
    # knows their secret is not meaningfully protected at rest.
    _warn_if_plaintext_keyring()
    try:
        import keyring

        keyring.set_password(service, username, password)
        return True
    except Exception:
        return False


def _keyring_delete(service: str, username: str) -> bool:
    """Try to remove a password from the OS keyring.  Returns True on success."""
    try:
        import keyring

        keyring.delete_password(service, username)
        return True
    except Exception:
        return False


def password_from_keyring() -> bool:
    """Return True if the last :func:`get_password` call used a keyring-stored value."""
    return _last_from_keyring


def clear_stored_password(
    dbms_name: str,
    database_name: str,
    user_name: str,
    server_name: str | None = None,
    port: int | None = None,
) -> bool:
    """Remove a stored password from the OS keyring, under its current and pre-port names.  True if one was removed."""
    removed = _keyring_delete(_keyring_service(dbms_name, database_name, server_name, port), user_name)
    legacy = _legacy_keyring_service(dbms_name, database_name, server_name, port)
    if legacy is not None:
        removed = _keyring_delete(legacy, user_name) or removed
    return removed


def remember_password(
    dbms_name: str,
    database_name: str,
    user_name: str,
    server_name: str | None = None,
    port: int | None = None,
) -> None:
    """Store the password :func:`get_password` typed (or read under the pre-port name) for this connection, now that it works.

    A password typed for a connection that then failed is never stored,
    even if another connection succeeds afterwards.
    """
    global _pending_store
    pending, _pending_store = _pending_store, None
    if pending is not None and pending[:2] == (
        _keyring_service(dbms_name, database_name, server_name, port),
        user_name,
    ):
        _keyring_set(*pending)


# Login failures, by driver: what each reports when the server rejects the
# user name or password.  PostgreSQL gives no SQLSTATE for a failed
# connection, so its message is matched.  Anything else (a timeout, a closed
# port, a missing database) is not a login failure.
_LOGIN_FAILURE_TEXT = (
    "password authentication failed",  # PostgreSQL
    "no password supplied",  # PostgreSQL
    "ora-01017",  # Oracle: invalid username/password
    "your user name and password are not defined",  # Firebird
    "not a valid password",  # Access (DAO)
)
_MYSQL_ACCESS_DENIED = 1045
_ODBC_INVALID_AUTHORIZATION = "28000"
_ORACLE_INVALID_LOGON = 1017


def is_login_failure(exc: BaseException) -> bool:
    """True if *exc*, or an exception it was raised from, is the server rejecting the credentials."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        first = current.args[0] if getattr(current, "args", None) else None
        if first == _MYSQL_ACCESS_DENIED:  # pymysql: (errno, message)
            return True
        if first == _ODBC_INVALID_AUTHORIZATION:  # pyodbc: (SQLSTATE, message)
            return True
        if getattr(first, "code", None) == _ORACLE_INVALID_LOGON:  # oracledb / cx_Oracle error object
            return True
        if any(text in str(current).lower() for text in _LOGIN_FAILURE_TEXT):
            return True
        current = current.__cause__ or current.__context__
    return False


def get_password(
    dbms_name: str,
    database_name: str,
    user_name: str,
    server_name: str | None = None,
    other_msg: str | None = None,
    skip_keyring: bool = False,
    port: int | None = None,
) -> str:
    """Prompt the user for a database password, using the GUI if available.

    When ``keyring`` is installed the OS credential store is checked first.
    If a stored credential is found it is returned immediately.

    Parameters
    ----------
    skip_keyring:
        If True, bypass the keyring lookup and always prompt interactively.
        Useful when a previously stored password is known to be invalid.
    port:
        The server's port, part of the keyring entry's name.

    A typed password is not stored here: :func:`remember_password` stores
    it once the connection succeeds.
    """
    global _last_from_keyring, _pending_store
    # Deferred imports to avoid circular dependencies at import time.
    from execsql.utils.errors import exit_now

    _last_from_keyring = False
    _pending_store = None

    # --- Keyring lookup (before any prompting) ---
    conf = _state.conf
    use_keyring = conf is None or getattr(conf, "use_keyring", True)
    service = _keyring_service(dbms_name, database_name, server_name, port)
    if use_keyring and not skip_keyring:
        stored = _keyring_get(service, user_name)
        if stored is None:
            legacy = _legacy_keyring_service(dbms_name, database_name, server_name, port)
            if legacy is not None:
                stored = _keyring_get(legacy, user_name)
                if stored is not None:
                    _pending_store = (service, user_name, stored)
        if stored is not None:
            _last_from_keyring = True
            _state.upass = stored
            register_secret(stored)
            return stored

    script_name = ""
    prompt = f"The execsql script {script_name} wants the {dbms_name} password for"
    if server_name is not None:
        prompt = f"{prompt}\nServer: {server_name}"
    prompt = f"{prompt}\nDatabase: {database_name}\nUser: {user_name}"
    if other_msg is not None:
        prompt = f"{prompt}\n{other_msg}"

    passwd = ""
    # Try GUI path if a GUI manager thread is running.
    use_gui = False
    try:
        import queue

        gui_manager_thread = getattr(_state, "gui_manager_thread", None)
        gui_manager_queue = getattr(_state, "gui_manager_queue", None)
        if gui_manager_thread:
            return_queue: queue.Queue[Any] = queue.Queue()
            from execsql.utils.gui import GuiSpec, QUERY_CONSOLE

            assert gui_manager_queue is not None
            gui_manager_queue.put(GuiSpec(QUERY_CONSOLE, {}, return_queue))
            user_response = return_queue.get(block=True)
            use_gui = user_response["console_running"]
    except Exception:
        pass  # GUI query failed; fall back to non-GUI password prompt.

    conf = _state.conf
    if use_gui or (conf is not None and conf.gui_level > 0):
        import queue as _queue

        try:
            from execsql.utils.gui import enable_gui, GuiSpec, GUI_DISPLAY

            enable_gui()
            return_queue = _queue.Queue()
            gui_args = {
                "title": f"Password for {dbms_name} database {database_name}",
                "message": prompt,
                "button_list": [("Continue", 1, "<Return>")],
                "textentry": True,
                "hidetext": True,
            }
            gui_manager_queue = getattr(_state, "gui_manager_queue", None)
            assert gui_manager_queue is not None
            gui_manager_queue.put(GuiSpec(GUI_DISPLAY, gui_args, return_queue))
            user_response = return_queue.get(block=True)
            btn = user_response["button"]
            passwd = cast(str, user_response["return_value"])
            if not btn and _state.status and _state.status.cancel_halt:
                if _state.exec_log:
                    _state.exec_log.log_exit_halt(
                        script_name,
                        0,
                        f"Canceled on password prompt for {dbms_name} database {database_name}, user {user_name}",
                    )
                exit_now(2, None)
        except Exception:
            prompt_text = prompt.replace("\n", " ", 1).replace("\n", ", ") + " >"
            passwd = getpass.getpass(str(prompt_text))
    else:
        prompt_text = prompt.replace("\n", " ", 1).replace("\n", ", ") + " >"
        passwd = getpass.getpass(str(prompt_text))

    _state.upass = passwd
    register_secret(passwd)

    # --- Stored once the connection succeeds (remember_password) ---
    if use_keyring and passwd:
        _pending_store = (service, user_name, passwd)

    return passwd
