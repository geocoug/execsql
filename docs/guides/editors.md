# Editor Support { #editors }

Use execsql in your editor to see lint diagnostics, complete metacommands and variables, navigate scripts, apply quick fixes and format documents. The server reads scripts and configuration; it does not run SQL or connect to a database.

## Set up your editor { #install }

Choose the instructions for your editor:

| Editor                          | Setup                                                              |
| ------------------------------- | ------------------------------------------------------------------ |
| <a id="vscode"></a>VS Code      | [Download/install the extension and verify it](editors/vscode.md). |
| <a id="neovim"></a>Neovim       | [Neovim configuration](editors/other-editors.md#neovim).           |
| <a id="helix"></a>Helix         | [Helix configuration](editors/other-editors.md#helix).             |
| <a id="other"></a>Other editors | [LSP client, Geany and Vim setup](editors/other-editors.md).       |

The server needs the `lsp` extra, which includes the `formatter` extra:

```sh
uv tool install "execsql2[lsp]"     # or: pipx install "execsql2[lsp]"
```

If execsql is already installed with other extras, name them in the same
command, or they are removed: the new list replaces the old one.

```sh
uv tool install "execsql2[postgres,lsp]"
pipx install --force "execsql2[postgres,lsp]"
```

See [Adding an extra later](../getting-started/installation.md#adding-an-extra-later).
Install it as a tool like this, in its own environment, not into a project's virtual environment: the extra pins sqlglot to one release (see [sqlglot version](formatter.md#sqlglot-version)).
Check it with `execsql lsp --check`: it prints `execsql lsp is ready (pygls 2.x.y)` and exits 0 when the server can start, and otherwise says what is
missing and exits 1.

## Verify the server { #verify }

```sh
execsql lsp --check
```

A ready message and exit status 0 mean the server can start in that environment. Exit status 1 explains a missing or incompatible dependency. Your editor must resolve the same executable. After configuration, open a SQL file and check that a misspelled metacommand produces a diagnostic; the [VS Code walkthrough](editors/vscode.md#verify) supplies a safe example.

## Features

The [language-server reference](../reference/language-server.md) explains capabilities and their limits:

- [Lint diagnostics and rule-code links](../reference/language-server.md#diagnostics).
- <a id="completion"></a>[Completion](../reference/language-server.md#completion) of metacommands, conditions, variables and export formats.
- <a id="hover"></a>[Hover](../reference/language-server.md#hover) descriptions and source definitions.
- <a id="navigation"></a>[Definitions, references and outline](../reference/language-server.md#navigation).
- <a id="rename"></a>[Variable rename](../reference/language-server.md#rename) and its workspace limits.
- <a id="folding"></a>[Folding](../reference/language-server.md#folding), <a id="quick-fixes"></a>[quick fixes](../reference/language-server.md#quick-fixes) and <a id="formatting"></a>[document formatting](../reference/language-server.md#formatting).

## Configuration { #settings }

The server uses the same `[lint]` and `[format]` configuration as the CLI. See [workspace configuration and file watching](../reference/language-server.md#settings) for multi-root behavior and client-specific refresh limits. [VS Code settings](editors/vscode.md#settings) control executable path, startup and tracing. [execsql lsp](../reference/cli/lsp.md) documents server launch options.

## Troubleshooting { #troubleshooting }

Start with `execsql lsp --check`, then the editor's server log. [VS Code troubleshooting](editors/vscode.md#troubleshooting) covers the missing-VSIX error, executable paths and workspace trust. [Server logging](../reference/cli/lsp.md#logging) explains log levels, files and the details useful in a bug report.
