# File inspection

Inspect a local importable file without running a script, connecting to a database
or changing the source:

```sh
execsql inspect file results.csv
execsql inspect file results.csv --output-format json
execsql inspect file results.xlsx
execsql inspect file results.xlsx --sheet Data
execsql inspect file results.parquet --sample-rows 1000
```

Text is the default. A successful scan reports the format, text encoding and its
source where applicable, delimiter/quote settings for delimited text, data rows
examined, column names, inferred types and observed NULL counts. Parquet/Feather
also show their stored types. Actual row values are not included in the report.
Output treats paths, headers and worksheet names literally, escaping terminal
control characters.

## Formats and selection

| Input                      | Format selection and reader                                                                                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| CSV, TSV, TAB, TXT         | Extension selects the delimited reader; delimiter and quoting are diagnosed using the same `CsvFile` reader as `IMPORT`. The extension does not force the delimiter.           |
| JSON, JSONL, NDJSON        | The JSON reader detects an array or an object-per-line stream from content. It uses IMPORT's nested-object flattening, missing-key alignment and exact scalar decimal parsing. |
| XLS, XLSX, ODS             | List worksheets by default. `--sheet NAME` selects a worksheet; a positive numeric selector is a 1-based sheet index, as in `IMPORT`.                                          |
| Parquet, Feather/Arrow IPC | Use the same Polars readers as IMPORT. Stored types are shown alongside IMPORT's inferred types, which may differ. Feather uses the existing Arrow IPC reader.                 |

The filename extension is a format hint, not a general file-signature detector.
Use `--format` for a missing or misleading extension. Available values are `csv`,
`tsv`, `text`, `json`, `jsonl`, `xls`, `xlsx`, `ods`, `parquet` and `feather`.
JSON's final `format` is detected from content regardless of its extension.

Spreadsheet and columnar formats require their existing optional readers:

```sh
uv tool install 'execsql2[formats]'
```

A missing or broken optional dependency produces a structured `dependency_error`
and an installation hint. Inspection retains the XLSX archive checks and ODS
archive/expansion limits used by imports. Sampling does not bypass those limits.
Readers that parse the whole source can report parser errors outside the inference
sample. Delimited-text sampling stops after the sample and one lookahead row, so
parser errors in later rows can remain undiscovered.

## Full scans and sampling

The default is a **full scan**, using the same `DataTable` inference as
`IMPORT TO NEW`/`REPLACEMENT`. Inferred types are logical execsql types, such as
`integer`, `character(3)`, `varchar(12)` or `decimal(8,3)`. Each database maps these
to its own SQL declarations; inspection does not choose a database dialect or
guarantee that a destination can represent every value.

Matching an import requires matching the format, selected sheet, skipped prefix
and configuration. An import into an **existing** table instead converts by that
table's destination types; this report does not validate that conversion.

`--sample-rows N` limits inference to at most N data rows. The reader may look at
one additional row to determine whether the sample reached the end. An incomplete
scan is labeled **provisional**: later rows can change types, lengths, precision
or scale. A sample that reaches EOF has `complete: true`.

Sampling is **not an I/O or memory budget**. CSV streams rows, but delimiter
diagnosis reads its configured prefix, and identifying trailing blank rows can
read beyond the inference limit. The existing JSON, spreadsheet and columnar
readers materialize their data; sampling limits the subsequent inference. Text
output explicitly reports full materialization for sampled inputs, and JSON
exposes `source_materialized`.

`rows_examined` counts rows delivered to inference after reader-specific handling,
excluding the header and the skipped prefix. `total_rows` is known after a
complete scan or when the reader materialized the full source; otherwise it is
`null`. Blank-row and empty-string behavior follows the import reader/settings.

## Options and configuration

| Option                       | Meaning                                                                                                                                          |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--format FORMAT`            | Select a built-in reader explicitly; otherwise use the extension hint.                                                                           |
| `--sheet NAME`               | Select a workbook worksheet or 1-based index. Omit to list worksheets without column inference.                                                  |
| `--sample-rows N`            | Positive inference-row limit; omitted means full scan.                                                                                           |
| `--encoding NAME`            | Override configured text encoding, or the legacy XLS reader's encoding. Other binary formats use internal encoding.                              |
| `--delimiter CHAR`           | Explicit delimiter character, or `TAB`, `US`, `SPACE` (case-insensitive). Only delimited text. Sets double quote as the default quote character. |
| `--quote CHAR`               | Override that quote character, or use `none`; requires `--delimiter`.                                                                            |
| `--skip-rows N`              | Non-negative physical text lines or worksheet rows before the header. Only delimited text and spreadsheets.                                      |
| `--config FILE`              | Read an explicit execsql configuration in addition to normal tool configuration.                                                                 |
| `--output-format text\|json` | Human-readable text (default), or the shared JSON contract.                                                                                      |

CSV's existing BOM detection takes precedence over its configured/explicit
encoding. Without a BOM it uses the explicit encoding, `[encoding] import`, or
the default UTF-8; it does not guess a legacy encoding. JSON uses its existing
configured/explicit decoding, including `utf-8-sig` when needed for a UTF-8 BOM.

The command and Python API read the same tool configuration as `format`/`lint`:
system, user and working-directory files, then `--config`, including local config
chains. The data file's directory is not an additional configuration search root.
Startup SQL/includes are never executed. Reports include `config_files` and a
whitelist of effective import/inference settings, including header handling,
Boolean/decimal rules, string normalization, integer threshold, dialect scan
length and spreadsheet budgets. Unrelated configuration and variable values are
not included. Command-line parsing controls are reported separately.

## Python and JSON contract

```python
from execsql import inspect_file

report = inspect_file("results.csv", sample_rows=1000)
if not report["success"]:
    raise RuntimeError(report["error"]["message"])
for column in report["columns"]:
    print(column["name"], column["inferred_type"])
```

Python accepts `file_format=`, `sheet=`, `sample_rows=`, `encoding=`, `delimiter=`,
`quote=`, `skip_rows=` and `config_file=` with the same meaning as the CLI options.
It returns exactly the dictionary printed by `--output-format json`. Invalid
arguments raise `ValueError`; file/configuration/parser failures return
`success: false`. Keyboard interrupts and plain process exits propagate after
reader cleanup and restoration of the caller's runtime context.

The contract has `schema_version: 1`. Check this and `success` before consuming
metadata. New optional fields can be added within version 1; consumers should
ignore unknown fields. Removing/renaming fields or changing their meaning/type
requires a new contract version, independent of the package version.

| Field                                  | Meaning                                                                                                                                                                                                                            |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `file`, `format`, `format_source`      | Input path, canonical reader format, and `extension`/`explicit`/`detected` provenance. Delimited formats share `format: "delimited"`.                                                                                              |
| `encoding`                             | `{name, source}` or `null` for an internal/unreported binary encoding. Source is `default`, `config`, `explicit` or CSV `bom`.                                                                                                     |
| `delimiter`, `quote`, `dialect_source` | Effective delimited-text dialect, or `null` where inapplicable. A `null` quote means no quoting.                                                                                                                                   |
| `sheet`, `worksheets`, `skip_rows`     | Selected worksheet, available names (or `null` for other formats), and skipped prefix length. Numeric selectors report the resolved name when valid.                                                                               |
| `scan`                                 | `{mode, row_limit, rows_examined, complete, total_rows, source_materialized}`, or `null` for worksheet listing or a failed scan.                                                                                                   |
| `columns`                              | Ordered `{name, inferred_type, source_type, null_count}` entries. Stored `source_type` strings come from Polars for Parquet/Feather; other readers report `null`. NULL counts describe examined rows, not destination constraints. |
| `settings`, `config_files`             | Effective import settings and loaded config paths.                                                                                                                                                                                 |
| `error`                                | `null` on success; otherwise `{code, message}`. Failed scans clear `columns` and `scan`; available format metadata may remain.                                                                                                     |

Success exits **0**, operational failure **1**, and invalid CLI arguments **2**.
JSON operational errors go to stdout as one JSON object; text errors go to stderr.
Error codes are `file_error`, `unsupported_format`, `configuration_error`,
`dependency_error` and `read_error`. Do not merge stderr into JSON stdout.
