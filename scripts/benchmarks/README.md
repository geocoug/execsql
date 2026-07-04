# execsql benchmark harness

Reproducible measurements of how execsql scales across data sizes, export
formats, and configuration options. The goal is to show **which of execsql's
own choices matter** — not to compare execsql against dedicated bulk loaders.

## Quick start

```sh
# From the repository root
uv run python scripts/benchmarks/run_benchmarks.py --quick --execsql "uv run execsql"
```

## Full suite

```sh
uv run python scripts/benchmarks/run_benchmarks.py --execsql "uv run execsql"
```

The full suite includes 1 M-row import and export runs and takes 15–25 minutes
depending on hardware.

## Options

| Flag            | Default                       | Description                                           |
| --------------- | ----------------------------- | ----------------------------------------------------- |
| `--execsql CMD` | `execsql`                     | execsql command to use, e.g. `"uv run execsql"`       |
| `--quick`       | off                           | Use small sizes only (1 k / 10 k / 100 k rows), 1 rep |
| `--reps N`      | `3`                           | Repetitions per benchmark; median is reported         |
| `--outdir PATH` | `scripts/benchmarks/results/` | Directory for `results.json` and `results.md`         |

## What is measured

| Group            | What                                                                          |
| ---------------- | ----------------------------------------------------------------------------- |
| **startup**      | Empty script — pure subprocess + interpreter launch cost                      |
| **import**       | `IMPORT TO REPLACEMENT … FROM data.csv` across row counts                     |
| **export**       | `EXPORT … TO out.{ext} AS {fmt}` by format on the largest table               |
| **config**       | Same import job with `scan_lines`, `-z` (buffer), and `trim_strings` variants |
| **metacommands** | Two WHILE loop sizes; delta isolates per-dispatch overhead                    |

XLSX and ODS *export* benchmarks are included. XLSX and ODS *import* is not
benchmarked: execsql's `IMPORT` metacommand reads tabular text (CSV, TSV, etc.),
not binary spreadsheet files. These benchmarks are silently skipped when the
`formats` extra is absent.

## Methodology

- Data: deterministic mixed-type CSV (seed 20260703): integer id, float amount,
    text label, date event_date, sparse text note.
- Database: SQLite in a temporary directory (discarded after the run).
- Timing: `time.perf_counter()` wall time around the `execsql` subprocess call;
    median of `--reps` repetitions.
- Startup cost (~1 s) is included in every measurement. Import/export numbers
    at small row counts are dominated by this cost, not I/O throughput. The
    **startup** benchmark isolates the baseline.

## Output

Results are written to `scripts/benchmarks/results/`:

- `results.json` — machine-readable, includes environment metadata.
- `results.md` — ready-to-paste Markdown tables.

Committed results represent one canonical run; re-run locally to get
environment-specific numbers.
