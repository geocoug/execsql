# VS Code

The Python package supplies the language server. A separately downloaded VSIX supplies VS Code syntax highlighting and starts that server. Installing one does not install the other.

## Install

1. [Install and verify the language server](../editors.md#install): `uv tool install "execsql2[lsp]"`, then `execsql lsp --check`. Retain any other extras you use in the same install command.
1. Download **execsql-syntax.vsix** from the [current GitHub release](https://github.com/geocoug/execsql/releases/latest). Save the actual file to a known location, such as Downloads. It is a release asset, not a Marketplace extension ID.
1. In VS Code open **Extensions → … → Install from VSIX…**, select the downloaded file and follow any reload prompt.

If the `code` command is on PATH, you can download and install from a terminal instead:

```sh
curl -fL --output execsql-syntax.vsix \
  https://github.com/geocoug/execsql/releases/latest/download/execsql-syntax.vsix
code --install-extension ./execsql-syntax.vsix
```

Run both commands in the same directory. If the file was downloaded elsewhere, pass its actual path instead, for example `code --install-extension ~/Downloads/execsql-syntax.vsix`. On Windows, use the browser/UI route above or supply the downloaded Windows path.

## Verify

Open a `.sql` file in a trusted workspace. Metacommand markers and variable substitutions should receive syntax highlighting. Add this temporary misspelling:

```sql
-- !x! EXPROT orders TO out.csv AS CSV
```

A diagnostic for an unknown/malformed metacommand confirms the language server is running. No database is needed and the script is not executed. If your workspace ignores [P003](../../reference/lint.md#p003), this line will not produce a diagnostic. Check **View → Output → execsql** for the `[extension] starting … lsp` startup message instead, or temporarily enable the rule. Correct or remove the demonstration line afterward. Highlighting alone does not establish that the server works.

## Settings

| Setting                   | Default   |                                                                                                                                                                                      |
| ------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `execsql.server.enabled`  | `true`    | Start the language server for SQL files. Turning it off stops the server; no reload is needed.                                                                                       |
| `execsql.server.path`     | `execsql` | The command to run as `<path> lsp`, if `execsql` is not on VS Code's PATH, e.g. `~/.local/bin/execsql`.                                                                              |
| `execsql.server.logLevel` | `info`    | How much the server writes to **Output → execsql**: `error`, `warning`, `info` (a startup record and each folder's config files) or `debug` (every message, scripts' text included). |
| `execsql.trace.server`    | `off`     | Trace the protocol messages in the same Output channel: `messages` or `verbose`.                                                                                                     |

If `execsql` is not on VS Code's PATH, set **execsql.server.path** to its full
path (`which execsql`); a leading `~` is expanded, e.g. `~/.local/bin/execsql`.
The setting is a command name looked up in PATH or an absolute path; a relative
path is refused. The extension never looks for `execsql` in the open folder,
and starts the server from your home directory.
After upgrading execsql, run **execsql: Restart Language Server** from the
Command Palette. The server's log is in **View → Output → execsql**
([Troubleshooting](#troubleshooting)). The extension also highlights execsql syntax; that works
without the server.

In a folder you have not marked as trusted
([Workspace Trust](https://code.visualstudio.com/docs/editor/workspace-trust)),
the extension does not start the language server: it reads the scripts, the
files they `INCLUDE` and the folder's `execsql.conf`, which a cloned repository
chooses. Syntax highlighting still works. The server starts as soon as you trust
the folder. VS Code also ignores an untrusted folder's own
`.vscode/settings.json` value of **execsql.server.path**, so a cloned repository
cannot choose the program the extension runs.

In any folder, trusted or not, the server never follows an `INCLUDE`,
`SUB_INI` or config chain written as a network path (`\\host\share\…`): on
Windows, merely checking it would send your login to that host
([Network paths](../../reference/security.md#network_paths)).

## Troubleshooting

| Symptom                                | Action                                                                                                              |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `ENOENT` installing the extension      | Download the VSIX first; check its saved filename and pass its actual path. The install command reads a local file. |
| `code` is not found                    | Use **Install from VSIX…** in VS Code.                                                                              |
| Highlighting works, diagnostics do not | Run `execsql lsp --check`; check workspace trust and `execsql.server.enabled`.                                      |
| Server executable not found            | Set `execsql.server.path` to an absolute path or make execsql available on VS Code's PATH.                          |
| Server stopped after an upgrade        | Run **execsql: Restart Language Server** from the Command Palette.                                                  |

For startup logs, open **View → Output → execsql**. See [server logging](../../reference/cli/lsp.md#logging) before attaching diagnostics to an issue; debug/trace output can contain script text.

For extension development, local clone installation and color customization, see the [extension README](https://github.com/geocoug/execsql/tree/main/extras/vscode-execsql#readme).
