# E1 control-flow baseline — execsql2 2.41.0

Measured 2026-11-19 on an Apple M1 Max (10 logical CPUs), macOS 27.0.1 arm64,
Python 3.13.7 and python-dateutil 3.0.0. This is the approved measurement phase of
[E1](../../ROADMAP.md), tracked in [#214](https://github.com/geocoug/execsql/issues/214).

## Decision

The first follow-up worth evaluating is a normalized-string equality fast path
in `xf_equals`: after the existing NFC normalization, lowercasing and quote
stripping, return `True` immediately if the two strings are identical. For
different strings, retain the existing conversion chain, order and fallback.
This proposal has not been implemented or measured as an optimization here.

Ordinary matching text currently takes about 77 µs per direct comparison even
though normalization already makes it identical. The matching-label execution
workload spends 26.5% of its **instrumented** time in `xf_equals`. That gives a
concrete small change to evaluate against the recorded 332 µs/iteration API
baseline. Instrumented shares are ranking evidence, not speedup predictions.

The largest measured group is per-command system-variable work. Caching resolved
paths has a wider correctness surface: working directories, includes, named
scripts and filesystem changes matter. Script bodies remain mutable, so removing
their deep copy is not justified by these measurements.

## Reproduce and identify the run

```sh
uv run python scripts/benchmarks/control_flow.py \
  --baseline-ref v2.41.0 --iterations 1000 --number 1000 --repeat 7
```

- Baseline: `v2.41.0`, commit `0e4ec110b0811320158b4c3c2b874a1fa9c132d0`.
- Benchmark implementation: commit `9a45435a15068feba2031589f5ca6c3c2813a828`.
- Benchmark script SHA-256: `9dd84c1c58b11cbc28d70dab9023417370b09be218403c5af90416115c1040b4`.
- Both runtime source trees SHA-256: `2694b93c6f6c9aa652358fb1a8e8fb5e1ad7ece2d60013c864c7ea3b7f693e6c`.
- Seven paired samples per implementation; 1,000 iterations or comparisons per sample.
- Maximum working-tree median absolute deviation (MAD): 2.74%.
- Baseline/current timing ratios: 0.975–1.018. The runtime bytes match; these
    differences describe measurement noise.

[Raw samples and correctness outcomes](baselines/control-flow-2.41.0.json) and
[compact profile statistics](baselines/control-flow-2.41.0-profiles.json) are
committed alongside this report. Full function statistics and binary profiles
remain in the producing checkout's ignored
`scripts/benchmarks/results/e1-2.41.0-2026-11-19-configured/`; the command above regenerates
them in a new timestamped directory. See the [harness guide](README.md#control-flow-profiling-e1)
for options and profile inspection.

## Whole API execution

The wall times include API parsing, configuration/connection setup, execution and
cleanup. Process startup, imports and a complete workload warmup are excluded.
Each run uses a fresh SQLite memory database, the same fixtures and default library
configuration. No system/user configuration or customer scripts are read.

| Workload                                                | Median µs/iteration | MAD % |
| ------------------------------------------------------- | ------------------: | ----: |
| Two-command body, inline SQL                            |              123.73 |  0.35 |
| Two-command body, relative script                       |              125.16 |  0.52 |
| Two-command body, absolute script                       |              117.66 |  0.75 |
| Thirty-two-command body, relative script                |             1575.53 |  1.59 |
| Fixed unequal text `EQUAL()` loop                       |              284.01 |  0.78 |
| Matching text `EQUAL()` loop                            |              332.17 |  1.20 |
| Changing unequal text `EQUAL()` loop                    |              292.65 |  2.09 |
| Changing numeric `EQUAL()` loop                         |              284.15 |  1.16 |
| SQLite INSERT loop, including final row-count assertion |              199.63 |  2.74 |

Body-size, path-mode and condition workloads execute different work; their timing
differences cannot be attributed wholly to one function. The SQLite case includes
real statement/commit work but does not predict network database throughput.

## Where the profiles spend time

These percentages use each separate cProfile run's wall duration. Profiling made
the API runs about 2.6–3.6 times slower, so these are instrumented cost shares.
The path resolver is inside the system-variable group: columns overlap and must
not be added. Profiles trace the worker's main thread.

| API workload                 | Body copy | System-variable updates | Path resolution | `xf_equals` |
| ---------------------------- | --------: | ----------------------: | --------------: | ----------: |
| Small relative script        |     18.9% |                   37.8% |           18.2% |           — |
| Large relative script        |     22.3% |                   48.7% |           23.3% |           — |
| Unequal fixed labels         |     18.2% |                   25.2% |           12.6% |       29.7% |
| Matching labels              |     15.6% |                   29.4% |           14.2% |       26.5% |
| Changing unequal labels      |     17.3% |                   24.9% |           12.1% |       29.7% |
| Changing numeric comparisons |     17.8% |                   26.0% |           12.7% |       28.5% |
| SQLite INSERT loop           |     18.9% |                   38.5% |           18.3% |           — |

Body-copy figures use the `_run_body → copy.deepcopy` caller edge, excluding
unrelated copies. Each workload made 1,000 such root calls. The large body made
32,004 `_set_command_vars` calls; the small body made 2,004. This explains why
system-variable work remains significant as the script grows.

For fixed/changing unequal labels, the profile records 17,000 `_strptime` calls
for 1,000 comparisons. These attempts account for about 81% of `xf_equals`'s
instrumented cumulative time. Direct text comparisons show about 83% in this
date-format parsing path. Unequal integers and decimals also traverse it.

## Direct comparison costs and semantics

| Pair                                 | Result | Median µs/comparison |
| ------------------------------------ | ------ | -------------------: |
| `Alpha`, `alpha`                     | True   |                77.09 |
| `alpha`, `beta`                      | False  |                76.24 |
| `01`, `1`                            | True   |                 0.85 |
| `1`, `2`                             | False  |                75.68 |
| `1.25`, `1.250`                      | True   |                 1.34 |
| `1.25`, `1.5`                        | False  |                74.92 |
| `true`, `t`                          | True   |                75.87 |
| `true`, `1`                          | True   |                74.62 |
| `2020-01-02`, `Jan 2, 2020`          | True   |                 2.88 |
| Same date, different timestamp hours | False  |                76.73 |

The Cartesian guard compares 225 outcomes, including blank strings, case,
numeric spellings, Boolean spellings, dates and NaN text. Separate workloads cover
UTC offsets, Unicode normalization and quotes. A normalized-string fast path
must leave tolerant matches between different strings intact. Returning `False`
as soon as one conversion finds different values would change the algorithm and
is outside the proposed change.

The snapshot guard extends a script while it runs: newly appended commands take
effect on later calls, with observed totals 0, 1 and 3. The path guard changes
directories within both the main file and an include and invokes a named script.
All guards, timed/profiled outputs and command counts matched the baseline.

## Follow-up acceptance criteria

Evaluate the normalized-string fast path separately, with direct tests for
normalization, quotes, empty strings, NaN text, typed matches and error cases.
Keep the existing conversion order for unequal normalized strings. Require all
guards and relevant condition/corpus tests to pass, and at least a 10% median
gain in the matching-label API workload in two independent runs with MAD at or
below 5%. Check unequal and numeric controls for regressions. A direct-call
microbenchmark improvement alone is insufficient.

The unequal-comparison hotspot remains a separate candidate. A conversion cache
would need bounds and context/invalidation rules and must also help changing-value
workloads. Path caching needs additional coverage for source identity, `CD`,
includes, symlink changes and clock-variable rollovers. Deep-copy work needs
mutation coverage before any narrower immutable-object sharing experiment.
