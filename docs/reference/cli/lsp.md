# execsql lsp

```text
execsql lsp [--check] [--log-level error|warning|info|debug] [--log-file PATH]
```

An editor starts this command for SQL files and exchanges Language Server Protocol messages over standard input/output. Running it manually without `--check` waits for protocol input; it is not a terminal editing session. There is no network listener or database connection.

Install the `lsp` extra and follow [editor setup](../../guides/editors.md). The extra includes SQL formatting. [Language-server features](../language-server.md) covers completions, navigation, lint diagnostics and formatting.

## Options

| Option              | Behavior                                                                                                 |
| ------------------- | -------------------------------------------------------------------------------------------------------- |
| `--check`           | Print readiness and exit: 0 when dependencies can load, 1 otherwise. Does not start a persistent server. |
| `--log-level LEVEL` | `error`, `warning` (default), `info` or `debug`; may also be set by `EXECSQL_LSP_LOG_LEVEL`.             |
| `--log-file PATH`   | Append the server log to this file instead of stderr.                                                    |

`--stdio` is accepted for clients that pass it explicitly; stdio is already the only transport. stdout is reserved for protocol messages.

## Logging { #logging }

**Where the server's log is.** The server writes its log to stderr, which the
editor keeps:

| Editor  | Where                                                                                 |
| ------- | ------------------------------------------------------------------------------------- |
| VS Code | **View → Output**, then choose **execsql** in the list. Start failures are there too. |
| Neovim  | `:LspLog` (`~/.local/state/nvim/lsp.log`)                                             |
| Helix   | `:log-open`                                                                           |

**How much it logs.** `execsql lsp --log-level` (or the `EXECSQL_LSP_LOG_LEVEL`
environment variable) takes `error`, `warning` (the default), `info` or `debug`:

- `info` adds a startup record and each workspace folder's settings, which is
    what a bug report needs:

    ```text
    INFO execsql.lsp.server: execsql lsp 2.x.y; Python 3.12.7 at /home/me/.local/share/uv/tools/execsql2/bin/python; pygls 2.x.y; formatter available
    INFO execsql.lsp.server: workspace folders: /home/me/etl
    INFO execsql.lsp.server: settings for /home/me/etl: config files /home/me/etl/execsql.conf; lint select all, ignore V; format {...}
    ```

- `debug` adds every message between the editor and the server, including the
    scripts' text.

The VS Code extension logs at `info` (setting **execsql.server.logLevel**). In
another editor, add the option to the server command, e.g. in Neovim
`cmd = { "execsql", "lsp", "--log-level", "info" }`. An editor that does not
keep the server's stderr can use `--log-file PATH` to append the log to a file.

**Tracing the protocol in VS Code.** Set **execsql.trace.server** to `messages`
(or `verbose`, which adds each message's content); the trace appears in the same
Output channel.

**Reporting a problem.** [Open an issue](https://github.com/geocoug/execsql/issues)
with:

1. The output of `execsql --version` and `execsql lsp --check`.
1. The server log at `info`, from start-up to the problem.
1. A small script that shows it, if you can share one.
