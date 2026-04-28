# execsql Plugin Template

A starting point for creating execsql plugins. Copy this directory, rename
everything marked `YOURNAME`, and implement your handlers.

## For users of a published plugin

```bash
pip install execsql-plugin-YOURNAME
execsql --list-plugins  # verify it's detected
```

That's it — execsql discovers installed plugins automatically via Python
entry points. No configuration needed.

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
    execsql --list-plugins
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

Example tests are in `tests/test_plugin.py` with two approaches:

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
- **Exporters**: Add new `EXPORT TO YOURFORMAT` support. Uncomment `register_exporters()`.
- **Importers**: Add new `IMPORT FROM YOURFORMAT` support. Uncomment `register_importers()`.
