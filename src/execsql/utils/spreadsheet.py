"""Allocation budgets for imported spreadsheet data."""

from __future__ import annotations

from typing import Any

from execsql.exceptions import ErrInfo

INPUT_LIMIT_DEFAULTS = {
    "ods_max_xml_mb": 100,
    "ods_max_compression_ratio": 100,
    "import_max_rows": 1_048_576,
    "import_max_columns": 16_384,
    "import_max_cells": 10_000_000,
    "import_max_cell_chars": 1_048_576,
    "import_max_text_chars": 268_435_456,
}


class SheetBudget:
    """Count materialized cells, including headers/padding, before allocating them.

    Limits come from the run configuration; zero disables a limit. The generic
    import_max_* names allow other spreadsheet readers to share the contract.
    """

    def __init__(self, conf: Any, filename: str, sheet: Any) -> None:
        self.limits = {name: getattr(conf, name, default) for name, default in INPUT_LIMIT_DEFAULTS.items()}
        self.filename = filename
        self.sheet = sheet
        self.rows = 0
        self.columns = 0
        self.text_chars = 0

    def check(self, setting: str, count: int, unit: str) -> None:
        limit = self.limits[setting]
        if limit and count > limit:
            raise ErrInfo(
                type="error",
                other_msg=(
                    f"Refusing to import sheet {self.sheet} of {self.filename}: "
                    f"{count:,} {unit} exceeds limit {limit:,} set by {setting}."
                ),
            )

    def check_row(self, width: int, repeat: int, pending: int) -> None:
        rows = self.rows + pending + repeat
        columns = max(self.columns, width)
        self.check("import_max_rows", rows, "rows")
        self.check("import_max_columns", columns, "columns")
        self.check("import_max_cells", rows * columns, "cells")

    def add_row(self, values: list, repeat: int, pending: int) -> None:
        self.check_row(len(values), repeat, pending)
        text_chars = self.text_chars + sum(len(value) for value in values if value is not None) * repeat
        self.check("import_max_text_chars", text_chars, "text characters")
        self.rows += pending + repeat
        self.columns = max(self.columns, len(values))
        self.text_chars = text_chars


class CellTextBudget:
    """Count a cell's text before expansion, with all materialized copies."""

    def __init__(self, sheet: SheetBudget, prior: int, copies: int) -> None:
        self.sheet = sheet
        self.prior = prior
        self.copies = copies
        self.characters = 0

    def add(self, count: int) -> None:
        self.characters += count
        self.sheet.check("import_max_cell_chars", self.characters, "characters in one cell")
        self.sheet.check("import_max_text_chars", self.prior + self.characters * self.copies, "text characters")
