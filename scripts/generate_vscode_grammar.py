#!/usr/bin/env python3
"""Generate the VS Code tmLanguage grammar from execsql's --dump-keywords output.

Usage:
    uv run python scripts/generate_vscode_grammar.py

The script calls ``execsql --dump-keywords`` to introspect the dispatch table,
then writes ``extras/vscode-execsql/syntaxes/execsql.tmLanguage.json``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "extras" / "vscode-execsql" / "syntaxes" / "execsql.tmLanguage.json"

# ---------------------------------------------------------------------------
# Static data not available from --dump-keywords
# ---------------------------------------------------------------------------

# Secondary operators / modifier keywords (these aren't metacommands)
SECONDARY_OPERATORS = [
    "WITH TEMPLATE",
    "IN ZIPFILE",
    "ATTACH_FILE",
    "CONTINUE",
    "COMPARE",
    "DISPLAY",
    "MESSAGE",
    "SUBJECT",
    "APPEND",
    "AFTER",
    "FROM",
    "TEE",
    "WITH",
    "KEY",
    "AS",
    "TO",
]

# Additional config option names from the old grammar not in the dispatch table
EXTRA_CONFIG_OPTIONS = [
    "CONSOLE_WAIT_WHEN_ERROR_HALT",
    "IMPORT_COMMON_COLUMNS_ONLY",
    "ACCESS_USE_NUMERIC",
    "OUTFILE_OPEN_TIMEOUT",
    "TEMPLATE_PROCESSOR",
    "CONSOLE_HEIGHT",
    "PASSWORD_PROMPT",
    "USER_LOGFILE",
    "CSS_STYLE",
    "CSS_FILE",
    "DB_FILE",
    "DB_TYPE",
    "DB",
    "SERVER",
    "PORT",
    "USERNAME",
    "NEW_DB",
    "ACCESS_USERNAME",
    "CONSOLE_WIDTH",
    "LOG_WRITE_MESSAGES",
    "SHOW_PROGRESS",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_pattern(keywords: list[str]) -> str:
    """Build a TextMate match regex from a keyword list.

    - Sorts longest-first to avoid prefix shadowing.
    - Replaces spaces with ``\\s+`` for multi-word keywords.
    - Wraps in ``(?i)\\b(...)\\b``.
    """
    sorted_kw = sorted(keywords, key=lambda k: (-len(k), k))
    escaped = [kw.replace(" ", "\\s+").lower() for kw in sorted_kw]
    alternation = "|".join(escaped)
    return f"(?i)\\b({alternation})\\b"


def _var_sub_pattern(comment: str, prefix_pattern: str, scope_name: str) -> dict:
    """Build a substitution-variable pattern matching all three delimiter forms.

    Produces a rule that matches ``!!name!!``, ``!'!name!'!``, and ``!"!name!"!``
    via a backreference on the optional quote character, mirroring
    ``SubVarSet._TOKEN_RX`` in ``src/execsql/script/variables.py``.

    Captures:
        1 — opening delimiter (``!!``, ``!'!``, or ``!"!``)
        2 — the quote character or empty (used by the backreference)
        3 — the variable name (with any scope prefix)
        4 — closing delimiter (matches capture 1's quote)
    """
    return {
        "comment": comment,
        "match": rf"(!(['\"]?)!)({prefix_pattern}[A-Za-z_][A-Za-z0-9_]*)(!\2!)",
        "captures": {
            "1": {"name": "punctuation.definition.variable.execsql"},
            "3": {"name": scope_name},
            "4": {"name": "punctuation.definition.variable.execsql"},
        },
    }


def _build_grammar(data: dict) -> dict:
    """Build the complete tmLanguage grammar dict."""
    mc = data["metacommands"]
    conditions = data["conditions"]
    config_options = data["config_options"] + EXTRA_CONFIG_OPTIONS
    export_formats = data["export_formats"]["all"]
    # Add JSON variants
    export_formats = sorted(set(export_formats + data["export_formats"]["json_variants"]))

    # Deduplicate config options
    config_options = sorted(set(config_options))

    return {
        "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
        "name": "execsql injection",
        "scopeName": "injection.execsql",
        "injectionSelector": "L:source.sql",
        "patterns": [
            {"include": "#commented-out-metacommand"},
            {"include": "#metacommand-line"},
            {"include": "#variable-substitution"},
        ],
        "repository": {
            "commented-out-metacommand": {
                "comment": "A metacommand line preceded by an extra -- or wrapped in /* */. "
                "Consumes the entire line so keyword/variable patterns are suppressed.",
                "patterns": [
                    {
                        "comment": "Line-commented metacommand: -- ... -- !x! ...",
                        "match": r"^\s*--.*--\s*!x!.*$",
                        "name": "comment.line.double-dash.sql",
                    },
                    {
                        "comment": "Block-commented metacommand (single line): /* ... -- !x! ... */",
                        "match": r"^\s*/\*.*--\s*!x!.*\*/\s*$",
                        "name": "comment.block.sql",
                    },
                    {
                        "comment": "Multi-line block comment /* ... */. Suppresses metacommand highlighting inside.",
                        "begin": r"/\*",
                        "end": r"\*/",
                        "name": "comment.block.sql",
                    },
                ],
            },
            "metacommand-line": {
                "comment": "Matches an entire -- !x! metacommand line",
                "begin": r"^\s*(--\s*!x!\s*)",
                "end": "$",
                "beginCaptures": {
                    "1": {"name": "keyword.control.directive.marker.execsql"},
                },
                "patterns": [
                    {"include": "#block-keywords"},
                    {"include": "#control-keywords"},
                    {"include": "#prompt-keywords"},
                    {"include": "#config-event-keywords"},
                    {"include": "#action-keywords"},
                    {"include": "#builtin-functions"},
                    {"include": "#config-option-names"},
                    {"include": "#export-formats"},
                    {"include": "#secondary-operators"},
                    {"include": "#variable-substitution"},
                    {"include": "#string-double"},
                ],
            },
            "control-keywords": {
                "comment": "if/else/loop/halt etc.",
                "match": _build_pattern(mc["control"] + ["END LOOP", "ENDLOOP"]),
                "name": "keyword.control.execsql",
            },
            "block-keywords": {
                "comment": "begin/end script/batch/sql/rollback",
                "match": _build_pattern(mc["block"] + ["ROLLBACK"]),
                "name": "keyword.control.block.execsql",
            },
            "action-keywords": {
                "comment": "sub, write, execute script, export, etc.",
                "match": _build_pattern(mc["action"]),
                "name": "keyword.other.execsql",
            },
            "config-event-keywords": {
                "comment": "config, on error_halt, on cancel_halt, on, timer",
                "match": _build_pattern(mc["config"] + ["ERROR_HALT", "METACOMMAND_ERROR_HALT", "ON"]),
                "name": "keyword.other.directive.execsql",
            },
            "prompt-keywords": {
                "comment": "prompt subcommands and console",
                "match": _build_pattern(mc["prompt"]),
                "name": "keyword.other.prompt.execsql",
            },
            "builtin-functions": {
                "comment": "Conditional test functions used in if/elseif",
                "match": _build_pattern(conditions),
                "name": "support.function.execsql",
            },
            "config-option-names": {
                "comment": "Config option names used after the config keyword",
                "match": _build_pattern(config_options),
                "name": "support.constant.config.execsql",
            },
            "export-formats": {
                "comment": "Export/import format names",
                "match": _build_pattern(export_formats),
                "name": "support.constant.execsql",
            },
            "secondary-operators": {
                "comment": "Modifier keywords used as arguments/options",
                "match": _build_pattern(SECONDARY_OPERATORS),
                "name": "keyword.operator.execsql",
            },
            "variable-substitution": {
                "comment": "Variable substitution patterns — apply everywhere in .sql files. "
                "Each prefix-specific rule matches all three delimiter forms: "
                "bare !!name!!, single-quoted !'!name!'!, and double-quoted !\"!name!\"!.",
                "patterns": [
                    _var_sub_pattern(
                        "System variable (!!$name!!, !'!$name!'!, !\"!$name!\"!)",
                        r"\$",
                        "variable.language.execsql",
                    ),
                    _var_sub_pattern(
                        "Environment variable (!!&name!!, !'!&name!'!, !\"!&name!\"!)",
                        r"&",
                        "variable.language.execsql",
                    ),
                    _var_sub_pattern(
                        "Parameter variable (!!#name!!, !'!#name!'!, !\"!#name!\"!)",
                        r"#",
                        "variable.parameter.execsql",
                    ),
                    _var_sub_pattern(
                        "Column/data variable (!!@name!!, !'!@name!'!, !\"!@name!\"!)",
                        r"@",
                        "variable.other.member.execsql",
                    ),
                    _var_sub_pattern(
                        "Local variable (!!~name!! / !!+name!! and quoted variants)",
                        r"[~+]",
                        "variable.other.local.execsql",
                    ),
                    _var_sub_pattern(
                        "Regular variable (!!name!!, !'!name!'!, !\"!name!\"!)",
                        r"",
                        "variable.other.execsql",
                    ),
                    {
                        "comment": "Deferred substitution !{name}!",
                        "match": r"!\{[A-Za-z_~+$@&#][A-Za-z0-9_]*\}!",
                        "name": "variable.other.execsql",
                    },
                    {
                        "comment": "Bare variable delimiters !!",
                        "match": "!!",
                        "name": "punctuation.definition.variable.execsql",
                    },
                ],
            },
            "string-double": {
                "comment": "Double-quoted string literals inside metacommand lines",
                "match": r'"[^"]*"',
                "name": "string.quoted.double.execsql",
            },
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Get keyword data from execsql --dump-keywords
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "--dump-keywords"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error running execsql --dump-keywords:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(result.stdout)
    grammar = _build_grammar(data)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(grammar, indent=2) + "\n")
    print(f"Generated {OUTPUT}")


if __name__ == "__main__":
    main()
