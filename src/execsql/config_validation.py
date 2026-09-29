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
import os
import re
import sys
import warnings
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from execsql.config import ConfigData
from execsql.exceptions import ConfigError

if TYPE_CHECKING:
    from execsql.config import _VariablePool

__all__ = ["ConfigProblem", "known_options", "validate_config"]

#: Sections whose keys are free-form: variable names, and numbered include files.
_FREE_SECTIONS = frozenset({"variables", "include_required", "include_optional", configparser.DEFAULTSECT})

#: Keys that chain to another config file, and the platform each applies on.
_CHAIN_KEYS = {
    "config_file": None,
    "linux_config_file": "linux",
    "macos_config_file": "darwin",
    "win_config_file": "win32",
}


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
    known.setdefault(ConfigData._CONFIG_SECTION, set()).update(_CHAIN_KEYS)
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
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        header = re.fullmatch(r"\[(.+)\]", line)
        if header:
            current = header.group(1)
            sections.setdefault(current, number)
            continue
        if raw[0].isspace() or current is None:
            continue
        option = re.match(r"([^=:]+?)\s*[=:]", line)
        if option:
            keys[(current, option.group(1).strip().lower())] = number
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


def _check_file(
    path: str,
    known: dict[str, set[str]],
    variable_pool: _VariablePool,
    current_script: str,
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
    except configparser.MissingSectionHeaderError as exc:
        problem(exc.lineno, "error", "a section header such as [connect] must come before the first option")
        return problems, []
    except configparser.ParsingError as exc:
        for err_line, err_text in exc.errors:
            problem(err_line, "error", f"cannot parse line: {err_text.strip()}")
        return problems, []
    except configparser.DuplicateOptionError as exc:
        problem(exc.lineno or 0, "error", f"{exc.option} is set twice in [{exc.section}]")
        return problems, []
    except configparser.DuplicateSectionError as exc:
        problem(exc.lineno or 0, "error", f"[{exc.section}] appears twice")
        return problems, []
    except configparser.Error as exc:
        problem(getattr(exc, "lineno", 0) or 0, "error", exc.message.split("\n")[0])
        return problems, []

    section_lines, key_lines = _line_numbers(text)

    for section in cp.sections():
        if section not in known:
            hint = _suggest(section, known)
            problem(
                section_lines.get(section, 0),
                "warning",
                f"unknown section [{section}]" + (f"; did you mean [{hint}]?" if hint else "; a run ignores it"),
            )

    chained: list[str] = []
    for (section, key), line in key_lines.items():
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
        if section == configparser.DEFAULTSECT:
            continue
        try:
            value = cp.get(section, key)
        except configparser.InterpolationSyntaxError:
            problem(line, "error", f"{key}: a literal % must be written %%")
            continue
        except configparser.Error as exc:
            problem(line, "error", f"{key}: {exc.message.splitlines()[0]}")
            continue
        if key in _CHAIN_KEYS:
            platform = _CHAIN_KEYS[key]
            if platform and not sys.platform.startswith(platform):
                continue  # another platform's file; a run here never reads it
            expand_home = os.name == "posix" if key == "config_file" else True
            target = ConfigData._chain_target(value, variable_pool, expand_home=expand_home)
            if Path(target).is_file():
                chained.append(target)
            else:
                problem(line, "warning", f"{key} = {value}: no such file; a run skips it")
            continue
        failure = _check_value(section, key, value, variable_pool, current_script)
        if failure is None and section == ConfigData._LINT_SECTION:
            failure = _check_rule_codes(value)
        if failure:
            problem(line, "error", f"{key} = {value}: {failure}")

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
    while queue and len(checked) < ConfigData._MAX_CONFIG_CHAIN:
        path = queue.popleft()
        if path in checked or not Path(path).is_file():
            continue
        checked.append(path)
        found, chained = _check_file(path, known, variable_pool, current_script)
        problems.extend(sorted(found, key=lambda p: p.line))
        for target in chained:
            queue.appendleft(target)
    return checked, problems
