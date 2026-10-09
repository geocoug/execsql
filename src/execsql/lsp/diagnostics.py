"""``execsql lint`` findings as LSP diagnostics."""

from __future__ import annotations

from lsprotocol import types

from execsql.cli.lint import Issue, filter_issues, lint_source

__all__ = ["LINT_DOCS_URL", "diagnostics", "to_diagnostic", "too_deep_diagnostic"]

LINT_DOCS_URL = "https://execsql2.readthedocs.io/en/latest/reference/lint/"

_SEVERITY = {
    "error": types.DiagnosticSeverity.Error,
    "warning": types.DiagnosticSeverity.Warning,
}


def to_diagnostic(issue: Issue, lines: list[str]) -> types.Diagnostic:
    """One lint issue as a diagnostic that underlines its line.

    Lint reports lines, not columns: the range covers the line's text from
    its first non-blank character.  An issue with no single line (line 0)
    is placed at the top of the document.
    """
    row = max(issue.line - 1, 0)
    text = lines[row] if row < len(lines) else ""
    start = len(text) - len(text.lstrip())
    return types.Diagnostic(
        range=types.Range(
            start=types.Position(line=row, character=start),
            end=types.Position(line=row, character=len(text.rstrip("\r\n"))),
        ),
        message=issue.message,
        severity=_SEVERITY.get(issue.severity, types.DiagnosticSeverity.Warning),
        code=issue.code,
        code_description=types.CodeDescription(href=f"{LINT_DOCS_URL}#{issue.code.lower()}"),
        source="execsql",
    )


def diagnostics(
    source: str,
    path: str | None,
    select: tuple[str, ...] = (),
    ignore: tuple[str, ...] = (),
) -> list[types.Diagnostic]:
    """Lint *source* (the editor's current text of the file at *path*).

    *path* lets lint resolve ``INCLUDE`` targets relative to the file;
    *select* and *ignore* are rule-code prefixes, as ``execsql lint`` takes
    them from ``--select`` / ``--ignore`` or a config file's ``[lint]``.
    """
    issues = filter_issues(lint_source(source, path or "<untitled>", path), select, ignore)
    lines = source.splitlines()
    return [to_diagnostic(issue, lines) for issue in sorted(issues, key=lambda i: (i.line, i.code))]


def too_deep_diagnostic() -> types.Diagnostic:
    """Stands in for lint's findings on a script nested too deeply to parse."""
    return types.Diagnostic(
        range=types.Range(start=types.Position(line=0, character=0), end=types.Position(line=0, character=0)),
        message="The script nests blocks or conditions too deeply to check.",
        severity=types.DiagnosticSeverity.Error,
        source="execsql",
    )
