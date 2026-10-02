"""``execsql lint`` against the script fixtures in ``tests/data/lint/``.

Each fixture is a script, and a comment ``-- expect: CODE[, CODE ...]`` says
the line right below it is reported with exactly those rule codes.  A fixture
without annotations must lint clean.  The fixtures are linted through the CLI,
so this covers the same path a user runs.

Two fixtures double as an inventory: ``every_metacommand.sql`` must use every
metacommand handler in the dispatch table and ``conditions_and_blocks.sql``
every conditional test, so registering one fails here until a fixture line
shows it — and lint is then checked against it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from execsql.cli import app
from execsql.cli.lint import _conditional_table, _dispatch_table, _extract_var_definition
from execsql.parser import CondAstNode, CondParser

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "lint"
VALID = ("every_metacommand.sql", "conditions_and_blocks.sql")

_EXPECT = re.compile(r"^\s*--\s*expect:\s*(?P<codes>.+?)\s*$")
_METACOMMAND = re.compile(r"^\s*--\s*!x!\s*(?P<command>.+?)\s*$", re.I)
# Block keywords only the script parser knows; the dispatch table has no entry for them.
_PARSER_ONLY = re.compile(r"^(?:(?:BEGIN|CREATE)\s+SCRIPT|END\s+SCRIPT|END\s*LOOP|BEGIN\s+SQL|END\s+SQL)\b", re.I)
# Named groups in which a metacommand's pattern captures a condition.
_CONDITION_GROUPS = ("condtest", "condition", "loopcond")

runner = CliRunner()


def _expected(source: str) -> list[tuple[int, str]]:
    found = []
    for line_no, line in enumerate(source.splitlines(), 1):
        m = _EXPECT.match(line)
        if m:
            found += [(line_no + 1, code.strip()) for code in m.group("codes").split(",")]
    return sorted(found)


def _reported(path: Path) -> list[tuple[int, str]]:
    result = runner.invoke(app, ["lint", str(path), "--output-format", "json"])
    assert result.exit_code in (0, 1), result.output
    return sorted((issue["line"], issue["code"]) for issue in json.loads(result.output))


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("*.sql")))
def test_lint_reports_exactly_the_annotated_issues(name):
    path = FIXTURES / name
    assert _reported(path) == _expected(path.read_text(encoding="utf-8"))


def test_the_valid_fixtures_have_no_annotations():
    for name in VALID:
        assert _expected((FIXTURES / name).read_text(encoding="utf-8")) == [], name


def _matches():
    """``(command, MetaCommand, re.Match)`` for every metacommand line in the valid fixtures.

    IF, ELSE, LOOP, BEGIN BATCH and the like are in the dispatch table too, so
    they count; a one-line IF's ``{ command }`` is matched as well.
    The valid fixtures keep no metacommand inside a block comment or BEGIN SQL.
    """
    table = _dispatch_table()
    for name in VALID:
        for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines():
            m = _METACOMMAND.match(line)
            if not m or _PARSER_ONLY.match(m.group("command")):
                continue
            commands = [m.group("command")]
            while commands:
                command = commands.pop()
                match = table.get_match(command)
                assert match is not None, command
                yield command, match[0], match[1]
                if match[1].groupdict().get("condcmd"):
                    commands.append(match[1].group("condcmd"))


def _conditions():
    for _command, _mc, match in _matches():
        yield from (v for g, v in match.groupdict().items() if g in _CONDITION_GROUPS and v)


def _tests_in(node, found: set[str]) -> None:
    if node.type == CondAstNode.CONDITIONAL:
        found.add(node.left[0].exec_fn.__name__)
        return
    _tests_in(node.left, found)
    if node.right is not None:
        _tests_in(node.right, found)


def test_every_metacommand_has_a_fixture_line():
    handlers = {mc.exec_fn.__name__ for mc in _dispatch_table()}
    used = {mc.exec_fn.__name__ for _command, mc, _match in _matches()}
    missing = sorted(handlers - used)
    assert not missing, f"add a line to tests/data/lint/every_metacommand.sql for: {missing}"


def test_every_conditional_test_has_a_fixture_use():
    tests = {mc.exec_fn.__name__ for mc in _conditional_table()}
    used: set[str] = set()
    for condition in _conditions():
        _tests_in(CondParser(condition, _conditional_table()).parse(), used)
    missing = sorted(tests - used)
    assert not missing, f"add a use to tests/data/lint/conditions_and_blocks.sql for: {missing}"


# The groups that name a variable the metacommand defines, and the handlers
# whose groups of those names do something else (RM_SUB removes the variable).
_DEFINING_GROUPS = ("match", "match_str", "fn_match", "path_match", "ext_match", "fnbase_match")
_NOT_DEFINING = {"x_rm_sub"}


def _defined_by(mc, match) -> set[str]:
    """The variables a matched metacommand defines, read from its own pattern's groups."""
    groups = match.groupdict()
    name = mc.exec_fn.__name__
    if name == "x_prompt_credentials":
        names = [groups["user"], groups["pw"]]
    elif name == "x_sub_querystring":
        from urllib.parse import parse_qsl

        names = [key for key, _value in parse_qsl(groups["qstr"])]
    elif name in _NOT_DEFINING:
        names = []
    else:
        names = [groups[g] for g in _DEFINING_GROUPS if groups.get(g)]
    return {n.lstrip("+~").upper() for n in names}


def test_lint_knows_every_variable_a_metacommand_defines():
    """V001 / V002 depend on lint recognising each defining metacommand; its own patterns must agree with dispatch."""
    checked = set()
    for command, mc, match in _matches():
        expected = _defined_by(mc, match)
        found: set[str] = set()
        _extract_var_definition(command, None, found)
        assert found == expected, command
        if expected:
            checked.add(mc.exec_fn.__name__)
    defining = {
        mc.exec_fn.__name__
        for mc in _dispatch_table()
        if mc.exec_fn.__name__ not in _NOT_DEFINING
        and (
            mc.exec_fn.__name__ in ("x_prompt_credentials", "x_sub_querystring")
            or any(g in re.compile(mc.pattern).groupindex for g in _DEFINING_GROUPS)
        )
    }
    assert checked == defining
