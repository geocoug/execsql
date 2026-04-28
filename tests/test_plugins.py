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
    discover_exporter_plugins,
    discover_importer_plugins,
    discover_metacommand_plugins,
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
