# execsql Plugin Template

A starting point for creating execsql plugins. Copy this directory, rename
everything marked `YOURNAME`, and implement your handlers.

## For users of a published plugin

```bash
pip install execsql-plugin-YOURNAME
execsql list plugins  # verify it's detected
```

Install the plugin in the same environment as execsql. For a uv tool installation use `uv tool install execsql2 --with execsql-plugin-YOURNAME`, retaining any extras in the execsql2 package specification. For pipx use `pipx inject execsql2 execsql-plugin-YOURNAME`; for a project environment use the pip command above. Verify the plugin’s documented script invocation as well as its presence in the listing. Only metacommand registration runs automatically; see the [plugin lifecycle](https://execsql2.readthedocs.io/en/stable/dev/architecture/#plugin-system).

## For plugin developers

1. Copy this directory and rename `YOURNAME` everywhere:

    ```bash
    cp -r extras/plugin-template execsql-plugin-mycommand
    cd execsql-plugin-mycommand
    # Rename in pyproject.toml, directory names, and source files
    ```

1. Implement your handler functions in `src/execsql_plugin_YOURNAME/__init__.py`

1. Install in development mode (changes take effect immediately):

    ```bash
    pip install -e .
    ```

1. Verify execsql discovers it:

    ```bash
    execsql list plugins
    ```

1. Test in a script:

    ```sql
    -- !x! YOUR_COMMAND hello world
    ```

1. Publish to PyPI when ready:

    ```bash
    python -m build
    twine upload dist/*
    ```

## Testing

Example tests are in `tests/test_plugin.py.example` with two approaches:

- **Unit tests**: Mock `execsql.state`, call your handler function directly.
    Fast, no database needed.
- **Integration tests**: Run a real script via `subprocess` with the plugin
    installed. Verifies regex matching and full dispatch pipeline.

```bash
pip install -e .   # install plugin in dev mode
pytest tests/      # run tests
```

## Plugin types

- **Metacommands**: Add new `-- !x! COMMAND` syntax. Edit `register_metacommands()`.
- **Exporters/importers**: The template's `execsql.exporters` and `execsql.importers` entry-point blocks are commented out in `pyproject.toml`. Uncomment the relevant block to expose a name in `execsql list plugins`. Their `register_exporters()` / `register_importers()` callbacks are not invoked automatically. To execute a custom format, register a metacommand that calls the writer/reader, or follow the in-tree [exporter](https://execsql2.readthedocs.io/en/stable/dev/adding_exporters/) or [importer](https://execsql2.readthedocs.io/en/stable/dev/adding_importers/) guide.
