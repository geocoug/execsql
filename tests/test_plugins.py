"""Tests for the plugin discovery and registration system."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from execsql.plugins import (
    METACOMMAND_GROUP,
    ExporterEntry,
    ExporterRegistry,
    ImporterEntry,
    ImporterRegistry,
    _load_entry_points,
    discover_all_plugins,
    discover_exporter_plugins,
    discover_importer_plugins,
    discover_metacommand_plugins,
    get_exporter_registry,
    get_importer_registry,
)


# ---------------------------------------------------------------------------
# ExporterRegistry
# ---------------------------------------------------------------------------


class TestExporterRegistry:
    def test_empty(self):
        reg = ExporterRegistry()
        assert len(reg) == 0
        assert reg.formats() == []

    def test_add_and_get(self):
        reg = ExporterRegistry()
        reg.add("myformat", query_fn=lambda: None, description="My format")
        assert "MYFORMAT" in reg
        entry = reg.get("myformat")
        assert entry is not None
        assert entry.format_name == "MYFORMAT"
        assert entry.description == "My format"
        assert entry.plugin_name == "built-in"

    def test_case_insensitive(self):
        reg = ExporterRegistry()
        reg.add("MyFormat", query_fn=lambda: None)
        assert reg.get("myformat") is not None
        assert reg.get("MYFORMAT") is not None

    def test_override(self):
        reg = ExporterRegistry()
        reg.add("csv", query_fn=lambda: "old", plugin_name="built-in")
        reg.add("csv", query_fn=lambda: "new", plugin_name="my_plugin")
        entry = reg.get("csv")
        assert entry.plugin_name == "my_plugin"

    def test_formats_sorted(self):
        reg = ExporterRegistry()
        reg.add("zebra", query_fn=lambda: None)
        reg.add("alpha", query_fn=lambda: None)
        assert reg.formats() == ["ALPHA", "ZEBRA"]

    def test_entries(self):
        reg = ExporterRegistry()
        reg.add("a", query_fn=lambda: None)
        reg.add("b", query_fn=lambda: None)
        assert len(reg.entries()) == 2

    def test_repr(self):
        entry = ExporterEntry("csv", plugin_name="built-in")
        assert "CSV" in repr(entry)


# ---------------------------------------------------------------------------
# ImporterRegistry
# ---------------------------------------------------------------------------


class TestImporterRegistry:
    def test_empty(self):
        reg = ImporterRegistry()
        assert len(reg) == 0

    def test_add_and_get(self):
        reg = ImporterRegistry()
        reg.add("json", import_fn=lambda: None, description="JSON importer")
        assert "JSON" in reg
        entry = reg.get("json")
        assert entry is not None
        assert entry.format_name == "JSON"

    def test_override(self):
        reg = ImporterRegistry()
        reg.add("csv", import_fn=lambda: "old", plugin_name="built-in")
        reg.add("csv", import_fn=lambda: "new", plugin_name="my_plugin")
        assert reg.get("csv").plugin_name == "my_plugin"

    def test_repr(self):
        entry = ImporterEntry("json", plugin_name="built-in")
        assert "JSON" in repr(entry)


# ---------------------------------------------------------------------------
# Entry point discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_no_plugins_returns_empty(self):
        with patch("execsql.plugins.entry_points", return_value=[]):
            result = _load_entry_points(METACOMMAND_GROUP)
            assert result == []

    def test_broken_plugin_skipped(self):
        mock_ep = MagicMock()
        mock_ep.name = "broken_plugin"
        mock_ep.value = "broken.module:register"
        mock_ep.load.side_effect = ImportError("no such module")

        with patch("execsql.plugins.entry_points", return_value=[mock_ep]):
            result = _load_entry_points(METACOMMAND_GROUP)
            assert result == []

    def test_working_plugin_loaded(self):
        mock_fn = MagicMock()
        mock_ep = MagicMock()
        mock_ep.name = "good_plugin"
        mock_ep.load.return_value = mock_fn

        with patch("execsql.plugins.entry_points", return_value=[mock_ep]):
            result = _load_entry_points(METACOMMAND_GROUP)
            assert len(result) == 1
            assert result[0] == ("good_plugin", mock_fn)

    def test_discover_metacommand_plugins(self):
        mock_register = MagicMock()
        mock_ep = MagicMock()
        mock_ep.name = "test_mc"
        mock_ep.load.return_value = mock_register

        mock_mcl = MagicMock()
        with patch("execsql.plugins.entry_points", return_value=[mock_ep]):
            count = discover_metacommand_plugins(mock_mcl)
            assert count == 1
            mock_register.assert_called_once_with(mock_mcl)

    def test_discover_metacommand_plugin_error_handled(self):
        mock_register = MagicMock(side_effect=TypeError("bad register"))
        mock_ep = MagicMock()
        mock_ep.name = "bad_mc"
        mock_ep.load.return_value = mock_register

        mock_mcl = MagicMock()
        with patch("execsql.plugins.entry_points", return_value=[mock_ep]):
            count = discover_metacommand_plugins(mock_mcl)
            assert count == 0

    def test_discover_exporter_plugins(self):
        def fake_register(registry):
            registry.add("custom_fmt", query_fn=lambda: None, plugin_name="test")

        mock_ep = MagicMock()
        mock_ep.name = "test_exp"
        mock_ep.load.return_value = fake_register

        reg = ExporterRegistry()
        with patch("execsql.plugins.entry_points", return_value=[mock_ep]):
            count = discover_exporter_plugins(reg)
            assert count == 1
            assert "CUSTOM_FMT" in reg

    def test_discover_importer_plugins(self):
        def fake_register(registry):
            registry.add("custom_fmt", import_fn=lambda: None, plugin_name="test")

        mock_ep = MagicMock()
        mock_ep.name = "test_imp"
        mock_ep.load.return_value = fake_register

        reg = ImporterRegistry()
        with patch("execsql.plugins.entry_points", return_value=[mock_ep]):
            count = discover_importer_plugins(reg)
            assert count == 1
            assert "CUSTOM_FMT" in reg


# ---------------------------------------------------------------------------
# CLI --list-plugins
# ---------------------------------------------------------------------------


class TestListPluginsCli:
    def test_list_plugins_no_plugins(self):
        from typer.testing import CliRunner

        from execsql.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["--list-plugins"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "No plugins found" in result.output

    def test_list_plugins_with_metacommand_plugin(self):
        from typer.testing import CliRunner

        from execsql.cli import app

        mock_ep = MagicMock()
        mock_ep.name = "my_awesome_plugin"
        mock_ep.load.return_value = lambda mcl: None

        runner = CliRunner()
        with patch("execsql.plugins.entry_points", return_value=[mock_ep]):
            result = runner.invoke(app, ["--list-plugins"], catch_exceptions=False)
            assert result.exit_code == 0
            assert "my_awesome_plugin" in result.output


# ---------------------------------------------------------------------------
# ImporterRegistry — untested methods
# ---------------------------------------------------------------------------


class TestImporterRegistryMethods:
    def test_formats_returns_sorted_uppercase(self):
        reg = ImporterRegistry()
        reg.add("zebra", import_fn=lambda: None)
        reg.add("alpha", import_fn=lambda: None)
        assert reg.formats() == ["ALPHA", "ZEBRA"]

    def test_entries_returns_all(self):
        reg = ImporterRegistry()
        reg.add("a", import_fn=lambda: None)
        reg.add("b", import_fn=lambda: None)
        assert len(reg.entries()) == 2


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------


class TestRegistrySingletons:
    def test_get_exporter_registry_returns_instance(self):
        import execsql.plugins as _plugins

        # Reset global to ensure we exercise the None-branch.
        original = _plugins._exporter_registry
        _plugins._exporter_registry = None
        try:
            reg = get_exporter_registry()
            assert isinstance(reg, ExporterRegistry)
            # Second call returns the same singleton.
            assert get_exporter_registry() is reg
        finally:
            _plugins._exporter_registry = original

    def test_get_importer_registry_returns_instance(self):
        import execsql.plugins as _plugins

        original = _plugins._importer_registry
        _plugins._importer_registry = None
        try:
            reg = get_importer_registry()
            assert isinstance(reg, ImporterRegistry)
            assert get_importer_registry() is reg
        finally:
            _plugins._importer_registry = original


# ---------------------------------------------------------------------------
# _load_entry_points — error branch when entry_points() itself raises
# ---------------------------------------------------------------------------


class TestLoadEntryPointsError:
    def test_entry_points_query_failure_returns_empty(self):
        """If entry_points() raises, _load_entry_points should return []."""
        with patch("execsql.plugins.entry_points", side_effect=RuntimeError("registry broken")):
            result = _load_entry_points(METACOMMAND_GROUP)
            assert result == []


# ---------------------------------------------------------------------------
# discover_all_plugins
# ---------------------------------------------------------------------------


class TestDiscoverAllPlugins:
    def test_discover_all_plugins_without_mcl_skips_metacommands(self):
        """When mcl is None, metacommand plugins are not attempted."""
        with patch("execsql.plugins.entry_points", return_value=[]):
            result = discover_all_plugins(mcl=None)
        # Key for metacommand group must be absent since mcl is None.
        from execsql.plugins import METACOMMAND_GROUP

        assert METACOMMAND_GROUP not in result
        # Exporter and importer counts are present.
        from execsql.plugins import EXPORTER_GROUP, IMPORTER_GROUP

        assert EXPORTER_GROUP in result
        assert IMPORTER_GROUP in result

    def test_discover_all_plugins_with_mcl_includes_metacommands(self):
        """When mcl is provided, all three plugin types are discovered."""
        mock_mcl = MagicMock()
        with patch("execsql.plugins.entry_points", return_value=[]):
            result = discover_all_plugins(mcl=mock_mcl)
        from execsql.plugins import EXPORTER_GROUP, IMPORTER_GROUP, METACOMMAND_GROUP

        assert METACOMMAND_GROUP in result
        assert EXPORTER_GROUP in result
        assert IMPORTER_GROUP in result

    def test_discover_exporter_plugin_registration_error_handled(self):
        """A plugin whose register function raises does not crash discover_exporter_plugins."""
        mock_register = MagicMock(side_effect=ValueError("bad exporter"))
        mock_ep = MagicMock()
        mock_ep.name = "broken_exp"
        mock_ep.load.return_value = mock_register

        with patch("execsql.plugins.entry_points", return_value=[mock_ep]):
            count = discover_exporter_plugins()
        assert count == 0

    def test_discover_importer_plugin_registration_error_handled(self):
        """A plugin whose register function raises does not crash discover_importer_plugins."""
        mock_register = MagicMock(side_effect=ValueError("bad importer"))
        mock_ep = MagicMock()
        mock_ep.name = "broken_imp"
        mock_ep.load.return_value = mock_register

        with patch("execsql.plugins.entry_points", return_value=[mock_ep]):
            count = discover_importer_plugins()
        assert count == 0
