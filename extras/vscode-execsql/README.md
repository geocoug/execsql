# execsql for VS Code

For [execsql](https://execsql2.readthedocs.io/) scripts in `.sql` files:

- **Syntax highlighting** for metacommands and variable substitutions, layered on top of standard SQL highlighting.

- **Lint findings as you type**, completion of metacommands, conditional tests and variables, hover
    explanations, Go to Definition / Find All References / outline, quick fixes and Format Document, from
    the execsql language server (`execsql lsp`). This needs execsql with the `lsp` extra on your PATH:

    ```sh
    uv tool install "execsql2[lsp]"     # or: pipx install "execsql2[lsp]"
    ```

    If execsql is already installed with other extras, name them too, e.g.
    `uv tool install "execsql2[postgres,lsp]"` or `pipx install --force "execsql2[postgres,lsp]"`: the
    new list replaces the old one ([Adding an extra later](https://execsql2.readthedocs.io/en/stable/getting-started/installation/#adding-an-extra-later)).

    Without it, highlighting still works and VS Code shows a warning each time the server fails to start. See
    [Editor Support](https://execsql2.readthedocs.io/en/stable/guides/editors/) for what the server does.

## Settings

| Setting                   | Default   |                                                                                                                                                                                      |
| ------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `execsql.server.enabled`  | `true`    | Start the language server for SQL files. Turning it off stops the server; no reload is needed.                                                                                       |
| `execsql.server.path`     | `execsql` | The command to run as `<path> lsp`, if `execsql` is not on VS Code's PATH, e.g. `~/.local/bin/execsql`.                                                                              |
| `execsql.server.logLevel` | `info`    | How much the server writes to **Output → execsql**: `error`, `warning`, `info` (a startup record and each folder's config files) or `debug` (every message, scripts' text included). |
| `execsql.trace.server`    | `off`     | Trace the protocol messages in the same Output channel: `messages` or `verbose`.                                                                                                     |

After installing or upgrading execsql, run **execsql: Restart Language Server** from the Command Palette.

`execsql.server.path` is a command name looked up in PATH or an absolute path; a relative path is refused,
and the extension never runs an `execsql` found in the open folder. In a folder you have not trusted
([Workspace Trust](https://code.visualstudio.com/docs/editor/workspace-trust)) the language server does
not start; highlighting still works, and the server starts when you trust the folder.

## What gets highlighted

The grammar assigns TextMate scopes to all execsql syntax. The color customization config (see below)
applies custom colors to the most visually important elements; everything else inherits colors from
your theme.

**Custom colored:**

| Element             | Example                                                       |
| ------------------- | ------------------------------------------------------------- |
| Metacommand marker  | `-- !x!`                                                      |
| Variable delimiters | `!!` in any variable substitution                             |
| Variable names      | `!!var!!`, `!!$SYSVAR!!`, `!!#param!!`, `!!@col!!`, `!{var}!` |

Variable substitutions are highlighted everywhere in `.sql` files, not just on metacommand lines.

**Scoped by grammar, colored by theme:**

| Element             | Example                                       |
| ------------------- | --------------------------------------------- |
| Control flow        | `if`, `elseif`, `loop`, `halt`, `break`       |
| Block keywords      | `begin script`, `end batch`, `begin sql`      |
| Action keywords     | `sub`, `write`, `export`, `execute script`    |
| Directive keywords  | `config`, `on error_halt`, `timer`            |
| Prompt keywords     | `prompt ask`, `prompt file`, `console`        |
| Built-in functions  | `table_exists`, `hasrows`, `equal`, `is_null` |
| Export formats      | `csv`, `json`, `parquet`, `sqlite`            |
| Config option names | `make_export_dirs`, `write_warnings`, etc.    |
| String literals     | `"text"` inside metacommand lines             |

______________________________________________________________________

## Installation

### From a release

Each [GitHub release](https://github.com/geocoug/execsql/releases) has an `execsql-syntax.vsix` attached.
Download it, then:

```sh
code --install-extension execsql-syntax.vsix
```

or, in VS Code, **Extensions** → `…` menu → **Install from VSIX…**.

### From a clone (to work on the extension)

`just install-vscode` installs the extension's dependencies (`npm ci`, needs Node.js) and links the
folder into VS Code. By hand:

### Mac / Linux

Install the dependencies first: `cd extras/vscode-execsql && npm ci --ignore-scripts`.

Create a symlink from the VSCode extensions directory to this folder:

```sh
ln -s /path/to/execsql/extras/vscode-execsql ~/.vscode/extensions/execsql-syntax
```

For example, if you cloned the repo to `./execsql`:

```sh
ln -s "$(pwd)/execsql/extras/vscode-execsql" ~/.vscode/extensions/execsql-syntax
```

### Windows

Create a directory junction using Command Prompt (a junction, unlike a symbolic link, needs no Administrator rights):

```cmd
mklink /J "%USERPROFILE%\.vscode\extensions\execsql-syntax" "C:\path\to\execsql\extras\vscode-execsql"
```

Or using PowerShell:

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.vscode\extensions\execsql-syntax" -Target "C:\path\to\execsql\extras\vscode-execsql"
```

### After installing

Reload VSCode: open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) and run **Developer: Reload Window**.

To verify the extension loaded, go to **Extensions** (`Ctrl+Shift+X`) and search for "execsql" — it should appear in the list.

______________________________________________________________________

## Color customization (recommended)

The extension assigns token scopes but leaves colors up to your theme. Two themes are configured below. Add whichever applies (or both) to your VSCode user settings
(`Ctrl+Shift+P` → *Open User Settings (JSON)*):

```json
"editor.tokenColorCustomizations": {
  "[One Dark Pro]": {
    "textMateRules": [
      {
        "scope": "keyword.control.directive.marker.execsql",
        "settings": { "foreground": "#e5c07b", "fontStyle": "bold" }
      },
      {
        "scope": "punctuation.definition.variable.execsql",
        "settings": { "foreground": "#e5c07b", "fontStyle": "bold" }
      },
      {
        "scope": [
          "variable.language.execsql",
          "variable.parameter.execsql",
          "variable.other.member.execsql",
          "variable.other.local.execsql",
          "variable.other.execsql"
        ],
        "settings": { "foreground": "#e06c75" }
      }
    ]
  },
  "[GitHub Dark]": {
    "textMateRules": [
      {
        "scope": "keyword.control.directive.marker.execsql",
        "settings": { "foreground": "#85e89d", "fontStyle": "bold" }
      },
      {
        "scope": "punctuation.definition.variable.execsql",
        "settings": { "foreground": "#85e89d", "fontStyle": "bold" }
      },
      {
        "scope": [
          "variable.language.execsql",
          "variable.parameter.execsql",
          "variable.other.member.execsql",
          "variable.other.local.execsql",
          "variable.other.execsql"
        ],
        "settings": { "foreground": "#ffab70" }
      }
    ]
  }
}
```

For other themes, the extension will use whatever colors your theme assigns to standard TextMate scopes
(`keyword.control`, `support.function`, `variable.other`, etc.). To customize, add a block using your
theme name in brackets. To find your theme name: open `settings.json` and look for `"workbench.colorTheme"`.

______________________________________________________________________

## Troubleshooting

**Keywords not highlighted on a `-- !x!` line**

- Confirm the extension loaded (check the Extensions panel).
- Use **Developer: Inspect Editor Tokens and Scopes** (place cursor on a token) to see what scopes are assigned.
- The `-- !x!` marker itself should show scope `keyword.control.directive.marker.execsql`.

**Colors look wrong or still match regular SQL**

- The `tokenColorCustomizations` block in your user settings must use the exact theme name in brackets.
- Run **Developer: Reload Window** after changing color settings. The `execsql.server.*` settings take effect at once.

**No lint findings or completion**

- Run `execsql lsp --check` in a terminal. It says `execsql lsp is ready` when the server can start;
    otherwise it says what is missing. Add the extra with the extras you already have, e.g. `uv tool install "execsql2[postgres,lsp]"`
    ([Adding an extra later](https://execsql2.readthedocs.io/en/stable/getting-started/installation/#adding-an-extra-later)).
- If `execsql` works in a terminal but not in VS Code, set `execsql.server.path` to its full path
    (`which execsql`).
- **Output** panel → choose **execsql** to see the server's log, including why it did not start.
    It starts with the execsql version, the Python running it and whether the formatter is installed;
    include that when you [report a problem](https://execsql2.readthedocs.io/en/stable/guides/editors/#troubleshooting).

**Extension not showing in the Extensions panel**

- Check that the symlink/junction points to the folder containing `package.json`, not to a parent folder.
- On Windows, use a junction (`mklink /J`), not a symbolic link (`mklink /D`), which needs Administrator rights.
