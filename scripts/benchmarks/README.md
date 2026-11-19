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

XLSX and ODS export benchmarks are included and need the `formats` extra. The
harness also attempts spreadsheet imports, but currently uses the plain delimited
IMPORT form for those files instead of `FROM EXCEL … SHEET …` (XLSX) or
`FROM … SHEET …` (ODS). Those failed attempts are printed as skips; they are not
valid spreadsheet-import measurements. Missing optional dependencies can also
cause printed skips. Use only the completed measurements when comparing runs.

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

## Control-flow profiling (E1)

Measure the three E1 targets: named-script body copying, per-command path/system
variables, and `EQUAL()` conversion attempts. This uses isolated SQLite memory
databases and synthetic scripts; it never changes execsql's runtime implementation.

```sh
# Check the workloads/guards and profile output, not performance:
uv run python scripts/benchmarks/control_flow.py --iterations 3 --number 3 --repeat 1

# Five paired timing samples, plus separate profiles:
uv run python scripts/benchmarks/control_flow.py --baseline-ref v2.41.0
```

`--baseline-ref` executes the full `src/execsql` package from a **trusted local Git
revision**. It does not fetch code. The baseline is archived into a temporary
directory; each baseline/current sample runs in a separate process using the same
Python interpreter, installed dependencies and fixture directory. The benchmark
verifies the imported package path and hashes both source trees before and after
measurement. It never installs the baseline over the working copy.

| Workload                                                              | Purpose                                                                                                                                       |
| --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Small body, inline/relative/absolute script                           | Whole API runs with two commands per iteration; separate path/parse controls.                                                                 |
| Large body                                                            | Thirty-two commands per iteration; profiles quantify body copying and dispatch rather than attributing the entire size difference to copying. |
| Matching, fixed-unequal, changing-unequal and numeric `EQUAL()` loops | Measure comparisons inside actual execution, including one changing pair per iteration.                                                       |
| SQLite INSERT loop                                                    | Include real statement/commit work and a final row-count assertion. This is not a server/database-throughput benchmark.                       |
| Direct comparison pairs                                               | Separate comparison costs for text, integers, decimals, Booleans, dates, timestamps, offsets, Unicode and quotes.                             |

Every worker checks a self-extending script's snapshot behavior, path variables
across `CD`, `INCLUDE` and a named script, and a Cartesian comparison matrix.
All timed/profiled outputs and command counts must agree with the baseline.
In particular, the existing relative-source path variables can change after `CD`
inside an included script; caching them solely by source name would change behavior.
The guards complement, rather than replace, the script corpus and behavior tests.
Python `-O` is refused because it would disable the assertions.

Options: `--iterations` (default 1,000 script iterations), `--number` (1,000 direct
comparisons per sample), `--repeat` (5 paired samples), and `--outdir` (a new output
directory). Existing output directories are refused. Without `--outdir`, each run
gets a timestamped directory under ignored `scripts/benchmarks/results/`.

Results include `results.json` (raw wall/CPU samples, medians, MAD, environment,
source identities and correctness outcomes), `results.md` (summary), `profiles.json`
(function statistics), and `profiles/{baseline,current}/*.prof`. Inspect a profile
with the same Python version used to produce it:

```sh
uv run python -c 'import pstats, sys; pstats.Stats(sys.argv[1]).sort_stats("cumulative").print_stats(25)' \
  /path/to/results/profiles/current/api_large_relative.prof
```

Interpreter startup, imports, semantic guards and a complete workload warmup are
outside timing samples. API timings include each run's parsing, setup and cleanup;
inline script text is already in memory. Samples alternate baseline/current order
to reduce thermal/load bias. Wall and process CPU time are both retained. Profiles
are collected separately, after timing: instrumentation inflates their times and
cumulative function costs overlap, so do not add them or subtract them from
uninstrumented measurements.

Before proposing an optimization, require at least five samples and identify the
hotspot in a representative API workload, not just a direct-call microbenchmark.
A follow-up change should demonstrate at least a 10% median whole-workload gain in
two independent runs, with MAD at or below 5%, and preserve the semantic guards
and relevant behavior/corpus coverage. These are decision criteria, not CI timing
assertions. If runtime source hashes match, timing ratios measure noise, not speedup.

## Nested substitution

Measure expansion with 10, 100 and 1,000 unrelated variables, including nested
names, unresolved tokens and ordinary-token controls:

```sh
uv run --python 3.13 python scripts/benchmarks/substitution.py --baseline-ref v2.40.0 \
    > scripts/benchmarks/results/substitution.json
```

`--baseline-ref` loads `script/variables.py` from a **trusted local Git revision**
for comparison with the working tree. Omit it to measure only the working tree.
The benchmark asserts equal output and alternates the timing order of the two
implementations. JSON reports median microseconds per expansion and the ratio of
baseline time to current time. `--number` (default 500) controls expansions per
sample; `--repeat` (default 5) controls the sample count. These are in-process
substitution measurements, not end-to-end script speedups.
