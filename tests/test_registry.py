"""Tests to ensure keyword consistency across the dispatch table, grammar, and CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GRAMMAR_PATH = ROOT / "extras" / "vscode-execsql" / "syntaxes" / "execsql.tmLanguage.json"


# ---------------------------------------------------------------------------
# --dump-keywords sanity
# ---------------------------------------------------------------------------


def test_dump_keywords_produces_valid_json():
    """``execsql --dump-keywords`` exits 0 and returns valid JSON with expected keys."""
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "--dump-keywords"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "metacommands" in data
    assert "conditions" in data
    assert "config_options" in data
    assert "export_formats" in data
    assert "database_types" in data
    assert "variable_patterns" in data


def test_dump_keywords_metacommand_categories():
    """All expected metacommand categories are present and non-empty."""
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "--dump-keywords"],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    mc = data["metacommands"]
    for cat in ("control", "block", "action", "config", "prompt"):
        assert cat in mc, f"Missing category: {cat}"
        assert len(mc[cat]) > 0, f"Empty category: {cat}"


# ---------------------------------------------------------------------------
# Dispatch table introspection
# ---------------------------------------------------------------------------


def test_dispatch_table_keywords_by_category():
    """Every mcl.add() with a description also has a category."""
    from execsql.metacommands import DISPATCH_TABLE

    uncategorized = []
    for mc in DISPATCH_TABLE:
        if mc.description and not mc.category:
            uncategorized.append(mc.description)

    # Deduplicate (many regex variants for same command won't have category)
    # This is expected — only first variant needs category
    # The test just checks there are no UNIQUE descriptions without a category
    kw = DISPATCH_TABLE.keywords_by_category()
    all_categorized = set()
    for cat_kws in kw.values():
        all_categorized.update(cat_kws)

    all_described = set()
    for mc in DISPATCH_TABLE:
        if mc.description:
            all_described.add(mc.description)

    # Every described keyword should appear in at least one category
    # (this will fail if someone adds a description but forgets category)
    missing = all_described - all_categorized
    if missing:
        pytest.fail(
            f"Keywords with description but no category: {missing}. "
            f"Add category= to the first mcl.add() call for these.",
        )


def test_conditional_table_keywords():
    """All conditional functions have a keyword name and category."""
    from execsql.metacommands.conditions import CONDITIONAL_TABLE

    kw = CONDITIONAL_TABLE.keywords_by_category()
    conditions = kw.get("condition", [])
    assert len(conditions) >= 25, f"Expected at least 25 conditions, got {len(conditions)}"


# ---------------------------------------------------------------------------
# Export format coverage
# ---------------------------------------------------------------------------


def test_export_format_constants():
    """Format constants are consistent and non-empty."""
    from execsql.metacommands import (
        ALL_EXPORT_FORMATS,
        QUERY_EXPORT_FORMATS,
        SERVE_FORMATS,
        TABLE_EXPORT_FORMATS,
    )

    assert len(QUERY_EXPORT_FORMATS) >= 15
    assert len(TABLE_EXPORT_FORMATS) >= 15
    assert len(SERVE_FORMATS) >= 5
    assert set(QUERY_EXPORT_FORMATS).issubset(set(ALL_EXPORT_FORMATS) | {"PARQUET"})
    assert set(TABLE_EXPORT_FORMATS).issubset(set(ALL_EXPORT_FORMATS) | {"PARQUET"})


# ---------------------------------------------------------------------------
# Grammar consistency
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not GRAMMAR_PATH.exists(), reason="Grammar file not generated yet")
def test_grammar_is_valid_json():
    """The checked-in tmLanguage.json is valid JSON."""
    data = json.loads(GRAMMAR_PATH.read_text())
    assert data["scopeName"] == "injection.execsql"
    assert "repository" in data


@pytest.mark.skipif(not GRAMMAR_PATH.exists(), reason="Grammar file not generated yet")
def test_grammar_matches_dump_keywords():
    """Keywords in the grammar match what --dump-keywords produces.

    If this fails, run ``just generate-vscode-grammar`` to regenerate.
    """
    # Get keywords from CLI
    result = subprocess.run(
        [sys.executable, "-m", "execsql", "--dump-keywords"],
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)

    # Regenerate grammar in memory
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_vscode_grammar import _build_grammar

    expected = _build_grammar(data)

    # Load checked-in grammar
    actual = json.loads(GRAMMAR_PATH.read_text())

    # Compare keyword patterns (the dynamic parts)
    for key in [
        "control-keywords",
        "block-keywords",
        "action-keywords",
        "config-event-keywords",
        "prompt-keywords",
        "builtin-functions",
        "config-option-names",
        "export-formats",
    ]:
        expected_match = expected["repository"][key]["match"]
        actual_match = actual["repository"][key]["match"]
        assert expected_match == actual_match, (
            f"{key} mismatch. Run `just generate-vscode-grammar` to update.\n"
            f"  expected: {expected_match[:80]}...\n"
            f"  actual:   {actual_match[:80]}..."
        )
