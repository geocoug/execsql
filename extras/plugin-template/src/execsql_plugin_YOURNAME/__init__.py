"""execsql plugin template.

Rename this package from ``execsql_plugin_YOURNAME`` to your plugin name,
update ``pyproject.toml``, and implement your handlers.

Quick start:
    1. Copy this directory and rename everything marked YOURNAME
    2. Implement your handler functions below
    3. Install with: pip install -e .
    4. Verify with:  execsql --list-plugins
    5. Use in scripts: -- !x! YOUR_COMMAND arg1 arg2
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Metacommand plugin
# ---------------------------------------------------------------------------


def register_metacommands(mcl: Any) -> None:
    """Register custom metacommands.

    This function is called by execsql at startup. ``mcl`` is a
    MetaCommandList — call ``mcl.add()`` to register your commands.

    Each registration needs:
        - regex: Pattern to match (use named groups for arguments)
        - handler: Function receiving regex groups as **kwargs
        - description: Name for --dump-keywords output
        - category: "action", "control", "config", "prompt", or "block"
    """
    mcl.add(
        r"^\s*YOUR_COMMAND\s+(?P<arg>.+)\s*$",
        _your_command_handler,
        description="YOUR_COMMAND",
        category="action",
    )


def _your_command_handler(**kwargs: Any) -> None:
    """Handle: -- !x! YOUR_COMMAND <arg>"""
    import execsql.state as _state

    arg = kwargs["arg"]
    _state.output.write(f"YOUR_COMMAND received: {arg}\n")


# ---------------------------------------------------------------------------
# Exporter plugin (uncomment to use)
# ---------------------------------------------------------------------------

# def register_exporters(registry):
#     """Register custom export formats.
#
#     ``registry`` is an ExporterRegistry — call ``registry.add()`` to
#     register your format.
#     """
#     registry.add(
#         format_name="YOURFORMAT",
#         query_fn=_export_yourformat,
#         description="Your custom format",
#         plugin_name="execsql-plugin-YOURNAME",
#     )
#
#
# def _export_yourformat(outfile, headers, rows, **kwargs):
#     """Write query results to your custom format."""
#     with open(outfile, "w") as f:
#         f.write("your format here\n")


# ---------------------------------------------------------------------------
# Importer plugin (uncomment to use)
# ---------------------------------------------------------------------------

# def register_importers(registry):
#     """Register custom import formats.
#
#     ``registry`` is an ImporterRegistry — call ``registry.add()`` to
#     register your format.
#     """
#     registry.add(
#         format_name="YOURFORMAT",
#         import_fn=_import_yourformat,
#         description="Your custom format",
#         plugin_name="execsql-plugin-YOURNAME",
#     )
#
#
# def _import_yourformat(db, schema, table, is_new, filename, **kwargs):
#     """Read data from your custom format into a table."""
#     pass
