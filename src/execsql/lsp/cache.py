"""What the server keeps between requests, so each one reparses only what changed.

Every feature request indexes the current document together with every file
it ``INCLUDE``s.  Without this, a script with fifty large includes rereads and
reparses all of them on each completion, hover or definition request.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from execsql.lsp.document import FileFacts, file_facts, read_included, same_file_key

__all__ = ["IndexCache"]

# Characters of file text held at most (included files' text plus the texts facts were taken from).
MAX_CACHED_CHARS = 64 * 1024 * 1024


class IndexCache:
    """Included files' text, by path and the file's size and modification time, and each text's :class:`FileFacts`."""

    def __init__(self, max_chars: int = MAX_CACHED_CHARS) -> None:
        self.max_chars = max_chars
        self._texts: OrderedDict[tuple[str, int, int], str | None] = OrderedDict()
        self._facts: OrderedDict[tuple[str | None, str | None, str], FileFacts] = OrderedDict()
        self._chars = 0

    def text(self, path: Path) -> str | None:
        """:func:`read_included` of *path*, read again only when the file's size or modification time changed."""
        try:
            stat = path.stat()
        except (OSError, ValueError):  # missing, unreadable, or a name the OS rejects
            return None
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key in self._texts:
            self._texts.move_to_end(key)
            return self._texts[key]
        text = read_included(path)
        self._texts[key] = text
        self._grow(len(text or ""))
        return text

    def facts(self, source: str, path: str | None, base_dir: str | None = None) -> FileFacts:
        """:func:`file_facts` of *source*, taken again only when its text or paths differ, or it reads an INI file."""
        key = (path, base_dir, source)
        found = self._facts.get(key)
        if found is not None and not found.reads_ini:
            self._facts.move_to_end(key)
            return found
        found = file_facts(source, path, base_dir)
        if key not in self._facts:
            self._grow(len(source))
        self._facts[key] = found
        return found

    def forget(self, path: str) -> None:
        """Drop what was read from the file at *path*: the client says it changed."""
        changed = same_file_key(path)
        for key in [k for k in self._texts if same_file_key(k[0]) == changed]:
            self._chars -= len(self._texts.pop(key) or "")

    def _grow(self, chars: int) -> None:
        self._chars += chars
        while self._chars > self.max_chars and (self._texts or self._facts):
            # From the kind holding more entries, least recently used first.
            if self._texts and (not self._facts or len(self._texts) >= len(self._facts)):
                _, text = self._texts.popitem(last=False)
                self._chars -= len(text or "")
            else:
                (_, _, source), _ = self._facts.popitem(last=False)
                self._chars -= len(source)
