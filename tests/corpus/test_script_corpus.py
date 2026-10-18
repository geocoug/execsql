"""Whole scripts run under execsql2 do what they did under upstream execsql 1.130.1.

Each case in ``tests/corpus/cases/`` is run with ``python -m execsql run``
and what the script compatibility contract covers (exit status, console
output, files written, table contents) is compared with what upstream did,
recorded in ``tests/corpus/results/<case>.json`` by ``tests/corpus/record.py``.

A difference fails the test unless ``tests/corpus/changes.json`` lists it:
``{case: {part: {"status": …, "upstream": …, "execsql2": …, "why": …}}}``,
where *part* is ``exit``, ``stdout``, ``stderr``, ``files/<name>`` or
``tables/<name>``.  Each entry names the value upstream produced and the
value execsql2 produces, so an entry goes stale, and fails, when either side
changes.  *status* is ``accepted`` for an upstream bug that execsql2 fixed on
purpose, or ``open`` for a difference not yet decided: fixed to match
upstream, or accepted and added to ``docs/about/divergence.md``.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import pytest

from tests.corpus.runner import CORPUS, RESULTS, case_names, run_case

_CHANGES = json.loads((CORPUS / "changes.json").read_text("utf-8"))


def _parts(result: dict[str, Any]) -> dict[str, Any]:
    """The compared parts of a result, keyed as changes.json keys them."""
    parts: dict[str, Any] = {key: result[key] for key in ("exit", "stdout", "stderr")}
    for kind in ("files", "tables"):
        for name, value in result[kind].items():
            parts[f"{kind}/{name}"] = value
    return parts


def test_every_case_has_recorded_results():
    recorded = {p.stem for p in RESULTS.glob("*.json")}
    assert recorded == set(case_names()), "record the new or renamed cases with: uv run python -m tests.corpus.record"


def test_changes_name_only_real_cases():
    assert set(_CHANGES) <= set(case_names())


def test_every_change_says_whether_it_is_decided_and_why():
    for case, parts in _CHANGES.items():
        for part, entry in parts.items():
            assert entry.get("status") in ("accepted", "open"), f"{case} {part}: status"
            assert entry.get("why"), f"{case} {part}: why"


@pytest.mark.parametrize("case", case_names())
def test_script_does_what_upstream_did(case, tmp_path):
    upstream = _parts(json.loads((RESULTS / f"{case}.json").read_text("utf-8")))
    ours = _parts(run_case(case, [sys.executable, "-m", "execsql", "run"], tmp_path / "work"))
    accepted = _CHANGES.get(case, {})

    problems = []
    for part in sorted(set(upstream) | set(ours) | set(accepted)):
        before = upstream.get(part, None)
        now = ours.get(part, None)
        if part in accepted:
            entry = accepted[part]
            if entry["upstream"] != before:
                problems.append(f"{part}: changes.json has a stale 'upstream' value")
            elif entry["execsql2"] != now:
                problems.append(f"{part}: changes.json expects {entry['execsql2']!r}, execsql2 gave {now!r}")
        elif before != now:
            problems.append(f"{part}: upstream {before!r}\n{' ' * len(part)}  execsql2 {now!r}")
    assert not problems, f"{case} differs from upstream:\n" + "\n".join(problems)
