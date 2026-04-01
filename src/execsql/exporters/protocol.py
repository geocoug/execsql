"""
Exporter Protocol definitions for execsql.

Defines two ``@runtime_checkable`` Protocols that describe the two main
exporter calling conventions used throughout the ``exporters`` package:

- :class:`QueryExporter` — functions that accept a SQL SELECT statement
  and a database connection, execute the query, and write the results.
- :class:`RowsetExporter` — functions that accept pre-fetched column
  headers and rows and write them to an output destination.

These Protocols capture the *most common* parameter signature.  Several
concrete exporters have additional keyword arguments (``tablename``,
``sheetname``, ``template_file``, ``write_types``, ``and_val``, etc.)
that extend the base contract.  Such functions remain structurally
compatible: they satisfy the Protocol when called with the base
arguments, and the extra parameters have defaults or are supplied by
the dispatch layer.

.. note::

   The ``io_export.py`` dispatch chain is **not** refactored here.
   These Protocols exist as a documentation and static-type-checking
   layer that formalises the implicit interface already present in the
   codebase.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["QueryExporter", "RowsetExporter"]


@runtime_checkable
class QueryExporter(Protocol):
    """Protocol for exporters that execute a query and write output.

    The canonical signature is::

        def __call__(
            self,
            select_stmt: str,
            db: Any,
            outfile: str,
            append: bool = False,
            desc: str | None = None,
            zipfile: str | None = None,
        ) -> None: ...

    Conforming functions
    --------------------
    - ``write_query_to_json``
    - ``write_query_to_html``
    - ``write_query_to_cgi_html``
    - ``write_query_to_latex``
    - ``write_query_to_values``
    - ``prettyprint_query`` (adds ``and_val``)

    Functions with extended signatures
    ----------------------------------
    - ``write_query_to_xml`` (adds ``tablename``)
    - ``write_query_to_json_ts`` (adds ``write_types``)
    - ``write_query_to_ods`` (adds ``sheetname``, no ``zipfile``)
    - ``write_query_to_hdf5`` (adds ``table_name``, no ``zipfile``)
    - ``write_query_to_duckdb`` (adds ``tablename``, no ``desc``/``zipfile``)
    - ``write_query_to_sqlite`` (adds ``tablename``, no ``desc``/``zipfile``)
    - ``report_query`` (adds ``template_file``)
    - ``write_queries_to_ods`` (``table_list`` instead of ``select_stmt``)
    """

    def __call__(
        self,
        select_stmt: str,
        db: Any,
        outfile: str,
        append: bool = False,
        desc: str | None = None,
        zipfile: str | None = None,
    ) -> None: ...


@runtime_checkable
class RowsetExporter(Protocol):
    """Protocol for exporters that accept pre-fetched headers and rows.

    The canonical signature is::

        def __call__(
            self,
            outfile: str,
            hdrs: list[str],
            rows: Any,
            append: bool = False,
            desc: str | None = None,
            zipfile: str | None = None,
        ) -> None: ...

    Conforming functions
    --------------------
    - ``export_values``

    Functions with extended signatures
    ----------------------------------
    - ``export_html`` (adds ``querytext``)
    - ``export_cgi_html`` (adds ``querytext``)
    - ``export_latex`` (adds ``querytext``)
    - ``export_ods`` (adds ``querytext``, ``sheetname``, no ``zipfile``)
    - ``prettyprint_rowset`` (uses ``colhdrs``/``output_dest``, adds ``and_val``)
    - ``export_duckdb`` (adds ``tablename``, no ``desc``/``zipfile``)
    - ``export_sqlite`` (adds ``tablename``, no ``desc``/``zipfile``)
    - ``write_query_to_feather`` (minimal: ``outfile``, ``headers``, ``rows`` only)
    - ``write_query_to_parquet`` (minimal: ``outfile``, ``headers``, ``rows`` only)
    - ``write_query_raw`` (uses ``rowsource`` + ``db_encoding``)
    - ``write_query_b64`` (uses ``rowsource`` only)
    - ``write_delimited_file`` (uses ``filefmt``, ``column_headers``, ``rowsource``,
      ``file_encoding``)
    """

    def __call__(
        self,
        outfile: str,
        hdrs: list[str],
        rows: Any,
        append: bool = False,
        desc: str | None = None,
        zipfile: str | None = None,
    ) -> None: ...
