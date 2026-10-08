"""Completion: metacommands after ``-- !x!``, conditional tests inside a condition, variables after ``!!``.

Everything shown comes from :mod:`execsql.metacommands.reference` (syntax in
the docs' notation, never the dispatch regexes) and from the script's own
index.  A metacommand with several syntax lines offers one item per line, each
inserting a fill-in template.
"""

from __future__ import annotations

import re

from lsprotocol import types

from execsql.lsp.document import ScriptIndex
from execsql.metacommands import reference

__all__ = ["completions"]

_RX_KEYWORD = re.compile(r"^(?P<lead>\s*--\s*!x!\s*)(?P<partial>[A-Za-z_][A-Za-z_ ]*)?$", re.I)
_RX_VARIABLE = re.compile(r"""(?P<open>!(?P<q>['"]?)!|!\{)(?P<partial>[$&@~#+]?\w*)$""")
_RX_CONDITION = re.compile(
    r"(?:\b(?:IF|ELSEIF|ANDIF|ORIF|WHILE|UNTIL)\s*\(|\b(?:ASSERT|WAIT_UNTIL)\s+|\b(?:AND|OR|NOT)\s+|\()\s*(?P<partial>\w*)$",
    re.I,
)
_RX_EXPORT_FORMAT = re.compile(r"^\s*--\s*!x!\s*EXPORT\b.*\bAS\s+(?P<partial>\w*)$", re.I)
_RX_IS_METACOMMAND = re.compile(r"^\s*--\s*!x!", re.I)


def _range(line: int, start: int, end: int) -> types.Range:
    return types.Range(start=types.Position(line=line, character=start), end=types.Position(line=line, character=end))


def _markdown(text: str) -> types.MarkupContent:
    return types.MarkupContent(kind=types.MarkupKind.Markdown, value=text)


def _metacommand_doc(entry: reference.Metacommand) -> types.MarkupContent:
    forms = "\n".join(entry.forms)
    return _markdown(f"{entry.summary}\n\n```\n{forms}\n```\n\n[Reference]({entry.url})")


def _keyword_items(line: int, start: int, end: int, typed: str, snippets: bool) -> list[types.CompletionItem]:
    """One item per syntax line.  After a space, only keywords that continue what was typed."""
    items = []
    words = " ".join(typed.upper().split())
    for entry in reference.metacommands():
        if typed.endswith(" ") and not entry.keyword.startswith(words + " "):
            continue
        for n, form in enumerate(entry.forms):
            rest = form[len(entry.keyword) :].strip() if form.upper().startswith(entry.keyword) else form
            items.append(
                types.CompletionItem(
                    label=entry.keyword,
                    label_details=types.CompletionItemLabelDetails(detail=f" {rest}"[:70] if rest else None),
                    kind=types.CompletionItemKind.Keyword,
                    detail=form,
                    documentation=_metacommand_doc(entry),
                    filter_text=entry.keyword,
                    sort_text=f"{entry.keyword}\x00{n:03d}",
                    text_edit=types.TextEdit(
                        range=_range(line, start, end),
                        new_text=reference.to_snippet(form) if snippets else entry.keyword,
                    ),
                    insert_text_format=types.InsertTextFormat.Snippet if snippets else types.InsertTextFormat.PlainText,
                ),
            )
    return items


def _condition_items(line: int, start: int, end: int, snippets: bool) -> list[types.CompletionItem]:
    items = []
    for entry in reference.conditions():
        if entry.name in ("NOT", "OR"):
            continue
        items.append(
            types.CompletionItem(
                label=entry.name,
                kind=types.CompletionItemKind.Function,
                detail=entry.forms[0],
                documentation=_markdown(f"{entry.summary}\n\n```\n{entry.forms[0]}\n```\n\n[Reference]({entry.url})"),
                text_edit=types.TextEdit(
                    range=_range(line, start, end),
                    new_text=entry.snippet if snippets else entry.name,
                ),
                insert_text_format=types.InsertTextFormat.Snippet if snippets else types.InsertTextFormat.PlainText,
            ),
        )
    return items


def _variable_items(
    index: ScriptIndex,
    line: int,
    start: int,
    end: int,
    closing: str,
    partial: str,
    snippets: bool,
) -> list[types.CompletionItem]:
    items: list[types.CompletionItem] = []

    def add(name: str, detail: str, doc: str, kind: types.CompletionItemKind, snippet: str | None = None) -> None:
        use_snippet = snippets and snippet is not None
        items.append(
            types.CompletionItem(
                label=name,
                kind=kind,
                detail=detail,
                documentation=_markdown(doc) if doc else None,
                text_edit=types.TextEdit(
                    range=_range(line, start, end),
                    new_text=(snippet if use_snippet and snippet is not None else name) + closing,
                ),
                insert_text_format=types.InsertTextFormat.Snippet if use_snippet else types.InsertTextFormat.PlainText,
            ),
        )

    sigil = partial[:1] if partial[:1] in "$&@#~+" else ""
    if sigil in ("", "~", "+"):
        for key, locations in sorted(index.definitions.items()):
            first = locations[0]
            where = f"line {first.line + 1}" if first.path == index.path else f"{first.path}, line {first.line + 1}"
            add(sigil + index.spellings[key], f"defined at {where}", "", types.CompletionItemKind.Variable)
    if sigil in ("", "#"):
        for script, params in sorted(index.script_params.items()):
            for param in params:
                add(f"#{param}", f"parameter of SCRIPT {script}", "", types.CompletionItemKind.Variable)
    if sigil in ("", "$"):
        for var in reference.system_variables():
            name = var.name
            snippet = None
            if name.endswith("_x"):  # $ARG_x, $COUNTER_x: the number is filled in
                snippet = name[:-1].replace("$", "\\$") + "${1:1}"
                name = name[:-1] + "n"
            add(
                name,
                "system variable",
                f"{var.summary}\n\n[Reference]({var.url})",
                types.CompletionItemKind.Constant,
                snippet,
            )
    return items


def completions(
    index: ScriptIndex,
    source: str,
    line: int,
    character: int,
    snippets: bool = True,
) -> types.CompletionList:
    """What to offer at (*line*, *character*) of *source*, zero-based."""
    lines = source.splitlines()
    text = lines[line] if 0 <= line < len(lines) else ""
    before, after = text[:character], text[character:]
    empty = types.CompletionList(is_incomplete=False, items=[])

    m = _RX_VARIABLE.search(before)
    if m:
        closing = {"!!": "!!", "!'!": "!'!", '!"!': '!"!', "!{": "}!"}[m.group("open")]
        rest = re.match(r"[$&@~#+]?\w*", after)
        tail = after[rest.end() :] if rest else after
        if tail.startswith(closing):
            closing = ""
        end = character + (rest.end() if rest else 0)
        items = _variable_items(index, line, m.start("partial"), end, closing, m.group("partial"), snippets)
        return types.CompletionList(is_incomplete=False, items=items)

    if not _RX_IS_METACOMMAND.match(before):
        return empty

    m = _RX_EXPORT_FORMAT.match(before)
    if m:
        from execsql.metacommands import ALL_EXPORT_FORMATS

        start = m.start("partial")
        return types.CompletionList(
            is_incomplete=False,
            items=[
                types.CompletionItem(
                    label=fmt.upper(),
                    kind=types.CompletionItemKind.EnumMember,
                    detail="export format",
                    text_edit=types.TextEdit(range=_range(line, start, character), new_text=fmt.upper()),
                )
                for fmt in sorted(ALL_EXPORT_FORMATS)
            ],
        )

    m = _RX_CONDITION.search(before)
    if m:
        return types.CompletionList(
            is_incomplete=False,
            items=_condition_items(line, m.start("partial"), character, snippets),
        )

    m = _RX_KEYWORD.match(before)
    if m:
        start = m.end("lead")
        items = _keyword_items(line, start, character, m.group("partial") or "", snippets)
        return types.CompletionList(is_incomplete=False, items=items)
    return empty
