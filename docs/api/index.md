# API Reference

The pages in this section are auto-generated from the source docstrings and show the full Python interface of the `execsql` package.

If you want to **extend** execsql — add a new exporter format, support a new database, or add an importer for a file type — start with the Contributing guides, which give you step-by-step walkthroughs and copy-paste skeletons. The API pages here serve as the detailed reference those guides link to.

For a high-level overview of how all the pieces fit together, start with the [Architecture & Design Guide](../dev/architecture.md).

| Extension type       | Guide                                                    | API reference                   |
| -------------------- | -------------------------------------------------------- | ------------------------------- |
| New export format    | [Adding Exporters](../dev/adding_exporters.md)           | [Exporters](exporters.md)       |
| New database adapter | [Adding Database Adapters](../dev/adding_db_adapters.md) | [Databases](db.md)              |
| New import format    | [Adding Importers](../dev/adding_importers.md)           | [Importers](importers.md)       |
| New metacommand      | [Adding Metacommands](../dev/adding_metacommands.md)     | [Metacommands](metacommands.md) |

## Modules

| Module                          | Description                                           |
| ------------------------------- | ----------------------------------------------------- |
| [CLI](cli.md)                   | Entry-point functions and argument parsing            |
| [Databases](db.md)              | `Database` ABC and `DatabasePool`                     |
| [Exporters](exporters.md)       | Export metadata, write specs, and format writers      |
| [Importers](importers.md)       | Data-import back-end used by all importer sub-modules |
| [Metacommands](metacommands.md) | Dispatch table and metacommand handler modules        |
