"""Check execsql.conf files and report every problem with its file and line.

A run reads config files with :class:`~execsql.config.ConfigData`, which stops
at the first invalid value and silently ignores anything it does not
recognize — a misspelled key or section simply does nothing. This module
backs ``execsql config --validate``: it reads the same files in the same order
and reports all of it.

Values are checked by :meth:`ConfigData._apply_file`, the method a run uses,
applied to one option at a time on a fresh instance. Validation therefore
cannot accept a value a run rejects, or reject one a run accepts.
"""

from __future__ import annotations

import configparser
import difflib
import re
import sys
import warnings
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from execsql.config import ConfigData, describe_parse_error, validate_database_encoding
from execsql.exceptions import ConfigError

if TYPE_CHECKING:
    from execsql.config import _VariablePool

__all__ = ["ConfigProblem", "known_options", "validate_config"]

#: Sections whose keys are free-form: variable names, and numbered include files.
_FREE_SECTIONS = frozenset({"variables", "include_required", "include_optional", configparser.DEFAULTSECT})

_DATABASE_TYPE = (ConfigData._CONNECT_SECTION, "db_type")
_DATABASE_ENCODING = (ConfigData._ENCODING_SECTION, "database")


@dataclass(frozen=True)
class ConfigProblem:
    """One problem in one config file.

    Attributes:
        file: The config file.
        line: 1-based line number, or ``0`` when the problem has no single line.
        severity: ``"error"`` — a run fails on it — or ``"warning"`` — a run
            silently ignores it.
        message: What is wrong, and the likely fix when there is one.
    """

    file: str
    line: int
    severity: str
    message: str


def known_options() -> dict[str, set[str]]:
    """Every section execsql reads, and the keys it reads in each.

    Free-form sections (``[variables]`` and the include sections) map to an
    empty set: any key is accepted there.
    """
    probe = ConfigData.__new__(ConfigData)
    probe._set_defaults()
    probe._read_known_options(configparser.ConfigParser())  # fills ConfigData._option_keys
    known: dict[str, set[str]] = {}
    for section, key, _attr in ConfigData._option_keys:
        known.setdefault(section, set()).add(key)
    known.setdefault(ConfigData._CONFIG_SECTION, set()).update(ConfigData._CHAIN_KEYS)
    for section in _FREE_SECTIONS - {configparser.DEFAULTSECT}:
        known[section] = set()
    return known


def _line_numbers(text: str) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    """Where each section header and each key is, by 1-based line number.

    Keys are lower-cased, as :class:`configparser.ConfigParser` does.
    Continuation lines (indented) and comments are skipped.
    """
    sections: dict[str, int] = {}
    keys: dict[tuple[str, str], int] = {}
    current: str | None = None
    option_indent: int | None = None
    for number, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        indent = len(raw) - len(raw.lstrip())
        if option_indent is not None and indent > option_indent:
            continue  # ConfigParser treats this line as a continuation.
        header = configparser.ConfigParser.SECTCRE.match(line)
        if header:
            current = header.group("header")
            sections.setdefault(current, number)
            option_indent = None
            continue
        if current is None:
            continue
        option = re.match(r"([^=:]+?)\s*[=:]", line)
        if option:
            keys[(current, option.group(1).strip().lower())] = number
            option_indent = indent
    return sections, keys


def _suggest(word: str, candidates: Iterable[str]) -> str | None:
    match = difflib.get_close_matches(word, sorted(candidates), n=1, cutoff=0.7)
    return match[0] if match else None


def _check_value(
    section: str,
    key: str,
    value: str,
    variable_pool: _VariablePool,
    current_script: str,
) -> str | None:
    """Apply one option the way a run would; return why it fails, or ``None``."""
    single = configparser.ConfigParser()
    single.read_dict({section: {key: value.replace("%", "%%")}})
    probe = ConfigData.__new__(ConfigData)
    probe._set_defaults()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # enc_password's deprecation notice
            probe._apply_file(single, variable_pool, current_script)
    except ConfigError as exc:
        return str(exc)
    except ValueError as exc:
        if section in ("include_required", "include_optional"):
            return f"keys in [{section}] must be numbers, not {key!r}"
        return str(exc)
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def _check_rule_codes(value: str) -> str | None:
    """Rule codes in ``[lint] select`` / ``ignore``, checked as ``execsql lint`` checks them."""
    from execsql.cli.lint import resolve_selectors

    try:
        resolve_selectors([value])
    except ValueError as exc:
        return str(exc)
    return None


def _is_secret(key: str) -> bool:
    """Whether *key* holds a password (``password``, ``enc_password``, ``passwd``)."""
    return "passw" in key.lower()


def _check_file(
    path: str,
    known: dict[str, set[str]],
    variable_pool: _VariablePool,
    current_script: str,
    database_settings: dict[tuple[str, str], tuple[str, int, str]],
) -> tuple[list[ConfigProblem], list[str]]:
    """Every problem in one file, and the config files it chains to (in queue order)."""
    problems: list[ConfigProblem] = []

    def problem(line: int, severity: str, message: str) -> None:
        problems.append(ConfigProblem(path, line, severity, message))

    try:
        with open(path) as f:  # the encoding ConfigParser.read uses
            text = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        problem(0, "error", f"cannot read: {exc}")
        return problems, []

    cp = configparser.ConfigParser()
    try:
        cp.read_string(text, source=path)
    except configparser.ParsingError as exc:
        if isinstance(exc, configparser.MissingSectionHeaderError):
            line, text = describe_parse_error(exc)
            problem(line, "error", text)
        else:  # every unparsable line, not only the first
            for err_line, err_text in exc.errors:
                problem(err_line, "error", f"cannot parse line: {err_text.strip()}")
        return problems, []
    except configparser.Error as exc:
        line, text = describe_parse_error(exc)
        problem(line, "error", text)
        return problems, []

    section_lines, key_lines = _line_numbers(text)
    inherited_options = (
        *((ConfigData._ENCODING_SECTION, key) for key in ConfigData._FILE_ENCODING_KEYS),
        _DATABASE_TYPE,
        _DATABASE_ENCODING,
    )
    for section, key in inherited_options:
        default_line = key_lines.get((configparser.DEFAULTSECT, key))
        if default_line is not None and cp.has_section(section):
            key_lines.setdefault((section, key), default_line)

    for section in cp.sections():
        if section not in known:
            hint = _suggest(section, known)
            problem(
                section_lines.get(section, 0),
                "warning",
                f"unknown section [{section}]" + (f"; did you mean [{hint}]?" if hint else "; a run ignores it"),
            )

    # Resolve links with the variables from preceding files. The runtime
    # installs this file's [variables] only after resolving its links.
    chain_section = ConfigData._CONFIG_SECTION
    chained: list[str] = []
    for key in ConfigData._active_chain_keys(cp):
        line = key_lines.get((chain_section, key), key_lines.get((configparser.DEFAULTSECT, key), 0))
        try:
            value, target = ConfigData._read_chain_option(cp, key, variable_pool)
        except configparser.Error as exc:
            problem(line, "error", describe_parse_error(exc)[1])
            continue
        if Path(target).is_file():
            chained.append(target)
        else:
            problem(line, "warning", f"{key} = {value}: no such file; a run skips it")

    # ConfigParser yields inherited variables before local variables.
    # Nested substitutions in subsequent links depend on that order.
    variable_section = ConfigData._VARIABLES_SECTION
    option_lines = {option: line for option, line in key_lines.items() if option[0] != variable_section}
    if cp.has_section(variable_section):
        for key, _ in cp.items(variable_section, raw=True):
            option = (variable_section, key)
            option_lines[option] = key_lines.get(option, key_lines.get((configparser.DEFAULTSECT, key), 0))

    for (section, key), line in option_lines.items():
        if section not in known and section != configparser.DEFAULTSECT:
            continue  # reported once, as an unknown section
        if section not in _FREE_SECTIONS and key not in known[section]:
            elsewhere = sorted(s for s, keys in known.items() if key in keys)
            if elsewhere:
                message = f"{key} belongs in [{elsewhere[0]}], not [{section}]"
            else:
                hint = _suggest(key, known[section])
                message = f"unknown key {key!r} in [{section}]" + (
                    f"; did you mean {hint!r}?" if hint else "; a run ignores it"
                )
            problem(line, "warning", message)
            continue
        if section == configparser.DEFAULTSECT or (section == chain_section and key in ConfigData._CHAIN_KEYS):
            continue
        try:
            value = cp.get(section, key)
        except configparser.Error as exc:
            problem(line, "error", describe_parse_error(exc)[1])
            continue
        failure = _check_value(section, key, value, variable_pool, current_script)
        if failure is None and section == ConfigData._LINT_SECTION:
            failure = _check_rule_codes(value)
        if failure:
            if _is_secret(key):
                # Never echo a password, even an obfuscated one, into logs.
                failure = failure.replace(value, "***") if value else failure
                value = "***"
            problem(line, "error", f"{key} = {value}: {failure}")
        elif (section, key) in (_DATABASE_TYPE, _DATABASE_ENCODING):
            database_settings[section, key] = path, line, value

    return problems, chained


def validate_config(
    script_path: str,
    variable_pool: _VariablePool,
    config_file: str | None = None,
) -> tuple[list[str], list[ConfigProblem]]:
    """Check every config file a run from *script_path* would read.

    Args:
        script_path: Directory of the script a run would execute; its
            ``execsql.conf`` is included, as for a run.
        variable_pool: Substitution variables for expanding chained file paths
            and checking ``[variables]`` names.
        config_file: The file ``--config`` names, read last.

    Returns:
        The files checked, in the order a run reads them, and every problem
        found, in file order and then line order.
    """
    known = known_options()
    current_script = str(Path(sys.argv[0]).resolve())
    queue: deque[str] = deque(ConfigData._search_paths(script_path, config_file))
    checked: list[str] = []
    problems: list[ConfigProblem] = []
    database_settings: dict[tuple[str, str], tuple[str, int, str]] = {}
    while queue and len(checked) < ConfigData._MAX_CONFIG_CHAIN:
        path = queue.popleft()
        if path in checked or not Path(path).is_file():
            continue
        checked.append(path)
        found, chained = _check_file(path, known, variable_pool, current_script, database_settings)
        problems.extend(found)
        for target in chained:
            queue.appendleft(target)

    if _DATABASE_TYPE in database_settings and _DATABASE_ENCODING in database_settings:
        _, _, db_type = database_settings[_DATABASE_TYPE]
        path, line, encoding = database_settings[_DATABASE_ENCODING]
        try:
            validate_database_encoding(db_type, encoding)
        except ConfigError as exc:
            problems.append(ConfigProblem(path, line, "error", str(exc)))

    problems.sort(key=lambda p: (checked.index(p.file), p.line))
    return checked, problems
