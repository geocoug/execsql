from __future__ import annotations

"""
Exporter package for execsql.

Each sub-module implements one or more export formats.  All exporter
functions are re-exported through :mod:`execsql.state` so that metacommand
handlers can access them via ``_state.write_query_to_csv`` etc. without
importing directly from here.

Sub-modules: ``base``, ``delimited``, ``json``, ``xml``, ``html``,
``latex``, ``ods``, ``xls``, ``zip``, ``raw``, ``pretty``, ``values``,
``templates``, ``feather``, ``parquet``, ``duckdb``, ``sqlite``.
"""
