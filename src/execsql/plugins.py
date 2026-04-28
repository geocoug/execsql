"""Plugin discovery and registration for execsql.

Discovers and loads plugins via Python `entry_points`_.  Plugins can
provide custom metacommands, export formats, and import formats.

Entry point groups:

- ``execsql.metacommands`` — custom metacommand handlers
- ``execsql.exporters`` — custom export formats
- ``execsql.importers`` — custom import formats

Each entry point should reference a **registration function** that
receives the appropriate registry and adds its entries.

Metacommand plugin example
--------------------------

In the plugin package's ``pyproject.toml``::

    [project.entry-points."execsql.metacommands"]
    my_plugin = "my_package.execsql_plugin:register"

The registration function receives a
:class:`~execsql.script.engine.MetaCommandList` and adds entries::

    def register(mcl):
        mcl.add(
            r"^\\s*MY_COMMAND\\s+(?P<arg>.+)\\s*$",
            my_handler,
            description="MY_COMMAND",
            category="action",
        )

    def my_handler(**kwargs):
        import execsql.state as _state
        arg = kwargs["arg"]
        # ... do work ...

Exporter plugin example
-----------------------

In ``pyproject.toml``::

    [project.entry-points."execsql.exporters"]
    my_format = "my_package.execsql_export:register"

The registration function receives an :class:`ExporterRegistry` and
adds entries::

    def register(registry):
        registry.add(
            format_name="myformat",
            query_fn=my_query_exporter,
            table_fn=my_table_exporter,  # optional
            description="My custom format",
        )

.. _entry_points: https://packaging.python.org/en/latest/specifications/entry-points/
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

__all__ = [
    "ExporterEntry",
    "ExporterRegistry",
    "ImporterEntry",
    "ImporterRegistry",
    "discover_metacommand_plugins",
    "discover_exporter_plugins",
    "discover_importer_plugins",
    "discover_all_plugins",
    "get_exporter_registry",
    "get_importer_registry",
]

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entry point group names
# ---------------------------------------------------------------------------

METACOMMAND_GROUP = "execsql.metacommands"
EXPORTER_GROUP = "execsql.exporters"
IMPORTER_GROUP = "execsql.importers"


# ---------------------------------------------------------------------------
# Exporter registry
# ---------------------------------------------------------------------------


class ExporterEntry:
    """A registered export format.

    Attributes:
        format_name: The format keyword (e.g. ``"csv"``, ``"myformat"``).
        query_fn: Function for exporting query results.
        table_fn: Function for exporting full tables (optional).
        description: Human-readable description.
        plugin_name: Name of the plugin that registered this entry, or
            ``"built-in"`` for formats shipped with execsql.
    """

    __slots__ = ("format_name", "query_fn", "table_fn", "description", "plugin_name")

    def __init__(
        self,
        format_name: str,
        query_fn: Callable | None = None,
        table_fn: Callable | None = None,
        description: str = "",
        plugin_name: str = "built-in",
    ) -> None:
        self.format_name = format_name.upper()
        self.query_fn = query_fn
        self.table_fn = table_fn
        self.description = description
        self.plugin_name = plugin_name

    def __repr__(self) -> str:
        return f"ExporterEntry({self.format_name!r}, plugin={self.plugin_name!r})"


class ExporterRegistry:
    """Registry of available export formats.

    Built-in formats are registered during initialization.  Plugins add
    their formats via :meth:`add`.
    """

    def __init__(self) -> None:
        self._entries: dict[str, ExporterEntry] = {}

    def add(
        self,
        format_name: str,
        query_fn: Callable | None = None,
        table_fn: Callable | None = None,
        description: str = "",
        plugin_name: str = "built-in",
    ) -> None:
        """Register an export format.

        If a format with the same name already exists, the new entry
        overwrites it (plugins can override built-in formats).
        """
        key = format_name.upper()
        if key in self._entries and self._entries[key].plugin_name != plugin_name:
            _log.info(
                "Plugin %r overrides export format %r (was %r)",
                plugin_name,
                key,
                self._entries[key].plugin_name,
            )
        self._entries[key] = ExporterEntry(
            format_name=key,
            query_fn=query_fn,
            table_fn=table_fn,
            description=description,
            plugin_name=plugin_name,
        )

    def get(self, format_name: str) -> ExporterEntry | None:
        """Look up an export format by name (case-insensitive)."""
        return self._entries.get(format_name.upper())

    def formats(self) -> list[str]:
        """Return sorted list of registered format names."""
        return sorted(self._entries)

    def entries(self) -> list[ExporterEntry]:
        """Return all registered entries."""
        return list(self._entries.values())

    def __contains__(self, format_name: str) -> bool:
        return format_name.upper() in self._entries

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Importer registry
# ---------------------------------------------------------------------------


class ImporterEntry:
    """A registered import format.

    Attributes:
        format_name: The format keyword (e.g. ``"csv"``, ``"json"``).
        import_fn: Function for importing data.
        description: Human-readable description.
        plugin_name: Name of the plugin that registered this entry.
    """

    __slots__ = ("format_name", "import_fn", "description", "plugin_name")

    def __init__(
        self,
        format_name: str,
        import_fn: Callable | None = None,
        description: str = "",
        plugin_name: str = "built-in",
    ) -> None:
        self.format_name = format_name.upper()
        self.import_fn = import_fn
        self.description = description
        self.plugin_name = plugin_name

    def __repr__(self) -> str:
        return f"ImporterEntry({self.format_name!r}, plugin={self.plugin_name!r})"


class ImporterRegistry:
    """Registry of available import formats."""

    def __init__(self) -> None:
        self._entries: dict[str, ImporterEntry] = {}

    def add(
        self,
        format_name: str,
        import_fn: Callable | None = None,
        description: str = "",
        plugin_name: str = "built-in",
    ) -> None:
        """Register an import format."""
        key = format_name.upper()
        if key in self._entries and self._entries[key].plugin_name != plugin_name:
            _log.info(
                "Plugin %r overrides import format %r (was %r)",
                plugin_name,
                key,
                self._entries[key].plugin_name,
            )
        self._entries[key] = ImporterEntry(
            format_name=key,
            import_fn=import_fn,
            description=description,
            plugin_name=plugin_name,
        )

    def get(self, format_name: str) -> ImporterEntry | None:
        return self._entries.get(format_name.upper())

    def formats(self) -> list[str]:
        return sorted(self._entries)

    def entries(self) -> list[ImporterEntry]:
        return list(self._entries.values())

    def __contains__(self, format_name: str) -> bool:
        return format_name.upper() in self._entries

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_exporter_registry: ExporterRegistry | None = None
_importer_registry: ImporterRegistry | None = None


def get_exporter_registry() -> ExporterRegistry:
    """Return the global exporter registry, creating it on first access."""
    global _exporter_registry
    if _exporter_registry is None:
        _exporter_registry = ExporterRegistry()
    return _exporter_registry


def get_importer_registry() -> ImporterRegistry:
    """Return the global importer registry, creating it on first access."""
    global _importer_registry
    if _importer_registry is None:
        _importer_registry = ImporterRegistry()
    return _importer_registry


# ---------------------------------------------------------------------------
# Discovery functions
# ---------------------------------------------------------------------------


def _load_entry_points(group: str) -> list[tuple[str, Any]]:
    """Load all entry points for a group, returning (name, loaded_object) pairs.

    Errors during loading are logged and skipped — a broken plugin should
    not prevent execsql from starting.
    """
    results = []
    try:
        eps = entry_points(group=group)
    except Exception:
        _log.warning("Failed to query entry points for group %r", group, exc_info=True)
        return results

    for ep in eps:
        try:
            obj = ep.load()
            results.append((ep.name, obj))
        except Exception:
            _log.warning(
                "Failed to load plugin %r from group %r: %s",
                ep.name,
                group,
                ep.value,
                exc_info=True,
            )
    return results


def discover_metacommand_plugins(mcl: Any) -> int:
    """Discover and register metacommand plugins.

    Each entry point should be a callable that receives a
    :class:`~execsql.script.engine.MetaCommandList` and calls ``mcl.add()``
    to register its commands.

    Args:
        mcl: The metacommand dispatch table to register into.

    Returns:
        Number of plugins successfully loaded.
    """
    loaded = 0
    for name, register_fn in _load_entry_points(METACOMMAND_GROUP):
        try:
            register_fn(mcl)
            _log.info("Loaded metacommand plugin: %s", name)
            loaded += 1
        except Exception:
            _log.warning("Metacommand plugin %r failed during registration", name, exc_info=True)
    return loaded


def discover_exporter_plugins(registry: ExporterRegistry | None = None) -> int:
    """Discover and register exporter plugins.

    Each entry point should be a callable that receives an
    :class:`ExporterRegistry` and calls ``registry.add()`` to register
    its formats.

    Args:
        registry: The exporter registry.  Defaults to the global singleton.

    Returns:
        Number of plugins successfully loaded.
    """
    if registry is None:
        registry = get_exporter_registry()
    loaded = 0
    for name, register_fn in _load_entry_points(EXPORTER_GROUP):
        try:
            register_fn(registry)
            _log.info("Loaded exporter plugin: %s", name)
            loaded += 1
        except Exception:
            _log.warning("Exporter plugin %r failed during registration", name, exc_info=True)
    return loaded


def discover_importer_plugins(registry: ImporterRegistry | None = None) -> int:
    """Discover and register importer plugins.

    Each entry point should be a callable that receives an
    :class:`ImporterRegistry` and calls ``registry.add()`` to register
    its formats.

    Args:
        registry: The importer registry.  Defaults to the global singleton.

    Returns:
        Number of plugins successfully loaded.
    """
    if registry is None:
        registry = get_importer_registry()
    loaded = 0
    for name, register_fn in _load_entry_points(IMPORTER_GROUP):
        try:
            register_fn(registry)
            _log.info("Loaded importer plugin: %s", name)
            loaded += 1
        except Exception:
            _log.warning("Importer plugin %r failed during registration", name, exc_info=True)
    return loaded


def discover_all_plugins(mcl: Any = None) -> dict[str, int]:
    """Discover and load all plugin types.

    Args:
        mcl: The metacommand dispatch table.  If ``None``, metacommand
            plugins are skipped.

    Returns:
        Dict of ``{group_name: count}`` for each plugin type loaded.
    """
    results = {}
    if mcl is not None:
        results[METACOMMAND_GROUP] = discover_metacommand_plugins(mcl)
    results[EXPORTER_GROUP] = discover_exporter_plugins()
    results[IMPORTER_GROUP] = discover_importer_plugins()
    return results
