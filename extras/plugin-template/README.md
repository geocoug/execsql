# execsql Plugin Template

Use this template to create a custom execsql plugin.

## Setup

1. Copy this directory and rename `YOURNAME` everywhere:

    ```bash
    cp -r extras/plugin-template my-plugin
    cd my-plugin
    # Rename in pyproject.toml, directory names, and source files
    ```

1. Implement your handler functions in `src/execsql_plugin_YOURNAME/__init__.py`

1. Install in development mode:

    ```bash
    pip install -e .
    ```

1. Verify execsql discovers it:

    ```bash
    execsql --list-plugins
    ```

1. Use in a script:

    ```sql
    -- !x! YOUR_COMMAND hello world
    ```

## Plugin types

- **Metacommands**: Add new `-- !x! COMMAND` syntax. Uncomment and edit `register_metacommands()`.
- **Exporters**: Add new `EXPORT TO YOURFORMAT` support. Uncomment and edit `register_exporters()`.
- **Importers**: Add new `IMPORT FROM YOURFORMAT` support. Uncomment and edit `register_importers()`.

## Publishing

Package and publish to PyPI so others can install with `pip install execsql-plugin-YOURNAME`.
