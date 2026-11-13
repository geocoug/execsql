# Commands

The package is named `execsql2`; the executable is **execsql**. Run `execsql --help` to list commands and `execsql COMMAND --help` for that command's options.

| Command                                | Use it to                                                                | Database needed?     |
| -------------------------------------- | ------------------------------------------------------------------------ | -------------------- |
| [run](../../getting-started/syntax.md) | Execute a SQL script with metacommands.                                  | Yes                  |
| [format](../../guides/formatter.md)    | Normalize SQL/metacommand layout; check formatting in CI.                | No                   |
| [lint](../lint.md)                     | Find script structure, variable and target problems before execution.    | No                   |
| [config](config.md)                    | Inspect configuration sources, generate a template or validate settings. | No                   |
| [list](list.md)                        | Discover metacommands, encodings, plugins and keywords.                  | No                   |
| [init](init.md)                        | Create project configuration, a script and pre-commit hooks.             | No                   |
| [lsp](lsp.md)                          | Provide language features to your editor.                                | No                   |
| [inspect](inspect.md)                  | Inspect database structure or importable files before execution.         | Database scopes only |

## First workflow

Start with [your first script](../../getting-started/first-script.md), which supplies all input files and expected output. To set up a new project with SQL formatting:

```sh
uv tool install "execsql2[formatter]"
execsql init checks --script validate
cd checks
execsql format --check validate.sql
execsql lint --strict validate.sql
execsql config --validate
```

Retain any other extras you use when installing `formatter`; see [adding an extra later](../../getting-started/installation.md#adding-an-extra-later).

The `format` and `lint` commands accept files, directories or `-` for stdin. Once you have a `scripts/` directory:

```sh
execsql format --check scripts/
execsql lint scripts/
```

Use `execsql run SCRIPT.sql ...` for execution. The bare `execsql SCRIPT.sql ...` form is deprecated and will be removed in execsql2 3.0. See [migration notes](../../about/divergence.md) and the [exit-status reference](../../getting-started/syntax.md#exit_codes).
