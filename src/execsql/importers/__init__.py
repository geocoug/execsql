from __future__ import annotations

"""
Importer package for execsql.

Each sub-module reads a specific file format and loads data into a target
database table via the active :class:`~execsql.db.base.Database` connection.
Sub-modules: ``base``, ``csv``, ``ods``, ``xls``, ``feather``.
"""
