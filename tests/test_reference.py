"""The readable syntax registry agrees with the dispatch table, the conditional tests and the docs.

``execsql.metacommands.reference`` is what editors and ``execsql list
metacommands`` show.  These tests fail when a metacommand or condition is
added without an entry, when an entry links to a docs section that does not
exist, or when a syntax line describes something the dispatch table would
reject.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from execsql.metacommands import reference

ROOT = Path(__file__).resolve().parent.parent
METACOMMANDS_MD = ROOT / "docs" / "reference" / "metacommands.md"
SUBVARS_MD = ROOT / "docs" / "reference" / "substitution_vars.md"


def _keywords() -> dict:
    from execsql.cli.help import _keywords_data

    return _keywords_data()


def _heading_anchors(path: Path) -> set[str]:
    """Anchors the docs site gives the headings of *path*: an explicit ``{ #id }``, or the slugged title."""
    anchors = set()
    for m in re.finditer(r"^#{1,6} (.+?)(?:\s*\{ #([\w-]+) \})?\s*$", path.read_text(encoding="utf-8"), re.M):
        if m.group(2):
            anchors.add(m.group(2))
        else:
            title = re.sub(r"[*`]", "", m.group(1)).strip().lower()
            anchors.add(re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", title)))
    return anchors


# ---------------------------------------------------------------------------
# Coverage: one entry per keyword, condition and documented system variable
# ---------------------------------------------------------------------------


def test_every_metacommand_keyword_has_one_entry():
    keywords = {k for words in _keywords()["metacommands"].values() for k in words}
    entries = [m.keyword for m in reference.metacommands()]
    assert len(entries) == len(set(entries)), "duplicate keyword entries"
    assert keywords - set(entries) == set(), "keywords without an entry"
    assert set(entries) - keywords == set(), "entries for keywords the dispatch table does not have"


def test_categories_match_the_dispatch_table():
    for category, words in _keywords()["metacommands"].items():
        for word in words:
            assert reference.metacommand(word).category == category, word


def test_every_condition_has_one_entry():
    names = set(_keywords()["conditions"])
    entries = [c.name for c in reference.conditions()]
    assert len(entries) == len(set(entries))
    assert set(entries) == names


def _documented_system_variables() -> set[str]:
    text = SUBVARS_MD.read_text(encoding="utf-8")
    section = text[text.index("## System Variables") : text.index("## Data Variables")]
    names = set(re.findall(r"^(\$\w+)\s*\n:   ", section, re.M))
    md = METACOMMANDS_MD.read_text(encoding="utf-8")
    pg = md[md.index("### Substitution variables", md.index("## PG_UPSERT")) :]
    pg = pg[: pg.index("\n### ", 5)]
    return names | set(re.findall(r"^\| `(\$PG_UPSERT_\w+)` \|", pg, re.M))


def test_every_documented_system_variable_has_one_entry():
    entries = [v.name for v in reference.system_variables()]
    assert len(entries) == len(set(entries))
    assert set(entries) == _documented_system_variables()


# ---------------------------------------------------------------------------
# Links and text
# ---------------------------------------------------------------------------


def test_every_link_points_at_a_docs_heading():
    meta_anchors = _heading_anchors(METACOMMANDS_MD)
    for entry in (*reference.metacommands(), *reference.conditions()):
        assert entry.anchor in meta_anchors, f"{entry}: no heading #{entry.anchor} in metacommands.md"
    pages = {"metacommands.md": meta_anchors, "substitution_vars.md": _heading_anchors(SUBVARS_MD)}
    for var in reference.system_variables():
        page, _, anchor = var.doc.partition("#")
        assert anchor in pages[page], f"{var.name}: no heading #{anchor} in {page}"


@pytest.mark.parametrize(
    "entry",
    [*reference.metacommands(), *reference.conditions(), *reference.system_variables()],
    ids=lambda e: getattr(e, "keyword", None) or e.name,
)
def test_summaries_are_one_short_plain_sentence(entry):
    s = entry.summary
    assert s and len(s) <= 120, f"{len(s)} characters"
    assert s.endswith((".", "?")), "ends a sentence"
    assert not re.search(r"\]\(|\*|\\<", s), "no markdown"


@pytest.mark.parametrize(
    "entry",
    [*reference.metacommands(), *reference.conditions()],
    ids=lambda e: getattr(e, "keyword", None) or e.name,
)
def test_syntax_lines_are_well_formed(entry):
    for form in entry.forms:
        assert form.count("<") == form.count(">"), form
        assert form.count("[") == form.count("]"), form


# ---------------------------------------------------------------------------
# Each syntax line describes a command the dispatch table accepts
# ---------------------------------------------------------------------------

_SAMPLES = (
    (r"_var$|match_string|variable", "x1"),
    (r"expression|lines|chars|width|height|seconds", "1"),
    (r"sql_statement", "select 1;"),
    (r"file|path|template", "out.csv"),
    (r"director", "outdir"),
    (r"format", "CSV"),
    (r"^(n|integer|number|value_n|counter_no|count|maxint|integer_value)$", "1"),
    (r"query|sql", "select 1"),
    (r"alias", "db2"),
    (r"url", "https://example.invalid"),
    (r"address", "a@example.invalid"),
)


def _sample(name: str) -> str:
    for pattern, value in _SAMPLES:
        if re.search(pattern, name, re.I):
            return value
    return "x1"


def _filled(form: str) -> str:
    """A concrete command for *form*: optional parts dropped, first choice taken, values filled in."""
    text = form
    while True:
        stripped = re.sub(r"\s*\[[^\[\]]*\]", "", text)
        if stripped == text:
            break
        text = stripped
    text = re.sub(r"<<([^<>]+)>>", "\0QUERY\0", text)
    text = re.sub(r"<([^<>]+)>(?:\|\S+)?", lambda m: _sample(m.group(1)), text)
    text = text.replace("\0QUERY\0", "<<select 1;>>")
    return re.sub(r"\b([A-Z_]+)(?:\|[A-Z_]+)+\b", r"\1", text)


def _handlers_for(keyword: str) -> set:
    from execsql.metacommands import DISPATCH_TABLE

    return {mc.exec_fn for mc in DISPATCH_TABLE._commands if mc.description == keyword}


# Keywords the script parser handles itself; they never reach the dispatch table.
_PARSER_KEYWORDS = {"BEGIN SCRIPT", "END SCRIPT", "BEGIN SQL", "END SQL"}

# Documented forms the dispatch table does not accept, with the reason.  Each
# one is a real gap between the docs and execsql, to be fixed in one or the other.
_KNOWN_GAPS = {}


@pytest.mark.parametrize("entry", reference.metacommands(), ids=lambda e: e.keyword)
def test_every_syntax_line_is_accepted_by_the_dispatch_table(entry):
    from execsql.metacommands import DISPATCH_TABLE

    if entry.keyword in _PARSER_KEYWORDS:
        pytest.skip("handled by the script parser, not the dispatch table")
    handlers = _handlers_for(entry.keyword)
    for form in entry.forms:
        if form.startswith("IF(") and "<SQL" in form:
            continue  # the one-line IF form documents a statement after the condition
        if form in _KNOWN_GAPS:
            continue
        command = _filled(form)
        match = DISPATCH_TABLE.get_match(command)
        assert match is not None, f"{form!r} -> {command!r} matches no metacommand"
        # The line names this keyword, or runs this keyword's handler
        # (PROMPT MAP is written PROMPT MESSAGE ... MAP).
        names_it = re.match(rf"{re.escape(entry.keyword)}S?\b", command, re.I) is not None
        assert names_it or match[0].exec_fn in handlers, f"{command!r} runs {match[0].exec_fn.__name__}"


# ---------------------------------------------------------------------------
# Lookups and snippets
# ---------------------------------------------------------------------------


def test_lookups_ignore_case_and_spacing():
    assert reference.metacommand("export  query").keyword == "EXPORT QUERY"
    assert reference.condition("hasrows").name == "HASROWS"
    assert reference.system_variable("current_date").name == "$CURRENT_DATE"
    assert reference.system_variable("$ARG_3").name == "$ARG_x"
    assert reference.metacommand("FROBNICATE") is None


@pytest.mark.parametrize(
    ("form", "snippet"),
    [
        (
            'EXPORT <table_or_view> [TEE] [APPEND] TO <filename>|stdout AS <format> [DESCRIPTION "<description>"]',
            "EXPORT ${1:table_or_view} TO ${2:filename} AS ${3:format}",
        ),
        ("CANCEL_HALT ON|OFF", "CANCEL_HALT ${1|ON,OFF|}"),
        ("ROW_COUNT_GT(<table_name>, <N>)", "ROW_COUNT_GT(${1:table_name}, ${2:N})"),
        ('WRITE "<text>" [TO <output>]', 'WRITE "${1:text}"'),
        ("SUB $x <v>", "SUB \\$x ${1:v}"),
        ("EXPORT QUERY <<query>> TO <file>", "EXPORT QUERY <<${1:query}>> TO ${2:file}"),
    ],
)
def test_snippets(form, snippet):
    assert reference.to_snippet(form) == snippet
