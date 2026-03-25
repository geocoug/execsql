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
returned without prompting.  After a successful interactive prompt the
password is offered for storage in the keyring for future use (console
mode only; GUI mode stores silently).

Keyring service names follow the pattern
``execsql/<db_type>/<server_or_file>/<database>``.
"""

import getpass

import execsql.state as _state


def _keyring_service(dbms_name: str, database_name: str, server_name: str | None) -> str:
    """Build a keyring service name from connection parameters."""
    server_part = server_name or "local"
    return f"execsql/{dbms_name}/{server_part}/{database_name}"


def _keyring_get(service: str, username: str) -> str | None:
    """Try to retrieve a password from the OS keyring.  Returns None on failure."""
    try:
        import keyring

        return keyring.get_password(service, username)
    except Exception:
        return None


def _keyring_set(service: str, username: str, password: str) -> bool:
    """Try to store a password in the OS keyring.  Returns True on success."""
    try:
        import keyring

        keyring.set_password(service, username, password)
        return True
    except Exception:
        return False


def get_password(
    dbms_name: str,
    database_name: str,
    user_name: str,
    server_name: str | None = None,
    other_msg: str | None = None,
) -> str:
    """Prompt the user for a database password, using the GUI if available.

    When ``keyring`` is installed the OS credential store is checked first.
    If a stored credential is found it is returned immediately.
    """
    # Deferred imports to avoid circular dependencies at import time.
    from execsql.utils.errors import exit_now

    # --- Keyring lookup (before any prompting) ---
    conf = _state.conf
    use_keyring = conf is None or getattr(conf, "use_keyring", True)
    service = _keyring_service(dbms_name, database_name, server_name)
    if use_keyring:
        stored = _keyring_get(service, user_name)
        if stored is not None:
            _state.upass = stored
            return stored

    script_name = ""
    prompt = f"The execsql script {script_name} wants the {dbms_name} password for"
    if server_name is not None:
        prompt = f"{prompt}\nServer: {server_name}"
    prompt = f"{prompt}\nDatabase: {database_name}\nUser: {user_name}"
    if other_msg is not None:
        prompt = f"{prompt}\n{other_msg}"

    # Try GUI path if a GUI manager thread is running.
    use_gui = False
    try:
        import queue

        gui_manager_thread = getattr(_state, "gui_manager_thread", None)
        gui_manager_queue = getattr(_state, "gui_manager_queue", None)
        if gui_manager_thread:
            return_queue = queue.Queue()
            from execsql.utils.gui import GuiSpec, QUERY_CONSOLE

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
            gui_manager_queue.put(GuiSpec(GUI_DISPLAY, gui_args, return_queue))
            user_response = return_queue.get(block=True)
            btn = user_response["button"]
            passwd = user_response["return_value"]
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

    # --- Offer to store in keyring after interactive prompt ---
    if use_keyring and passwd:
        _keyring_set(service, user_name, passwd)

    return passwd
