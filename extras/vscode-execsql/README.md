# execsql Syntax Highlighting for VSCode

Adds syntax highlighting for [execsql](https://execsql.readthedocs.io/) metacommands in `.sql` files.
Standard SQL highlighting is preserved — execsql `-- !x!` lines and variable substitutions get
distinct custom colors layered on top.

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

### Mac / Linux

Create a symlink from the VSCode extensions directory to this folder:

```sh
ln -s /path/to/data-management/vscode-execsql ~/.vscode/extensions/execsql-syntax
```

For example, if you cloned the repo to `~/GitHub/gsi/data-management`:

```sh
ln -s ~/GitHub/gsi/data-management/vscode-execsql ~/.vscode/extensions/execsql-syntax
```

### Windows

Create a directory junction using Command Prompt **as Administrator**:

```cmd
mklink /J "%USERPROFILE%\.vscode\extensions\execsql-syntax" "C:\path\to\data-management\vscode-execsql"
```

Or using PowerShell **as Administrator**:

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.vscode\extensions\execsql-syntax" -Target "C:\path\to\data-management\vscode-execsql"
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
- Run **Developer: Reload Window** after changing settings.

**Extension not showing in the Extensions panel**

- Check that the symlink/junction points to the folder containing `package.json`, not to a parent folder.
- On Windows, the junction must be created with Administrator privileges.
