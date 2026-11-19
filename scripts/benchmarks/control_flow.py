#!/usr/bin/env python3
"""Measure E1 control-flow costs against a trusted local Git revision, without patching runtime code."""

from __future__ import annotations

import argparse
import cProfile
import datetime
import hashlib
import importlib.metadata
import json
import locale
import os
from pathlib import Path
import platform
import pstats
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VALUES = [
    "",
    "alpha",
    "ALPHA",
    "beta",
    "1",
    "01",
    "2",
    "1.0",
    "1.25",
    "nan",
    "true",
    "t",
    "false",
    "2020-01-02",
    "Jan 2, 2020",
]
PAIRS = {
    "text_same": ("Alpha", "alpha"),
    "text_different": ("alpha", "beta"),
    "integer_same": ("01", "1"),
    "integer_different": ("1", "2"),
    "decimal_same": ("1.25", "1.250"),
    "decimal_different": ("1.25", "1.5"),
    "boolean_same": ("true", "t"),
    "boolean_different": ("true", "false"),
    "boolean_numeric": ("true", "1"),
    "date_same": ("2020-01-02", "Jan 2, 2020"),
    "date_different": ("2020-01-02", "2020-01-03"),
    "timestamp_different": ("2020-01-02 03:00:00", "2020-01-02 04:00:00"),
    "offset_same_instant": ("2020-01-02 03:00:00+01:00", "2020-01-02 02:00:00+00:00"),
    "unicode_same": ("ÉCOLE", "e\u0301cole"),
    "quoted_same": ('"Alpha"', '"ALPHA"'),
}


def loop(iterations: int, *, padding: int = 0, comparison: str | None = None, sql: bool = False) -> str:
    lines = ["-- !x! SUB i 0", f"-- !x! SUB total {iterations}"]
    if sql:
        lines.append("CREATE TABLE sink(value INTEGER);")
    lines += ["-- !x! BEGIN SCRIPT work", "-- !x! SUB_ADD i 1", "-- !x! SUB label item_!!i!!"]
    lines += [f"-- !x! SUB padding_{index} unchanged" for index in range(padding)]
    if comparison:
        condition = {
            "same": 'EQUAL("alpha", "ALPHA")',
            "fixed": 'EQUAL("alpha", "beta")',
            "changing": 'EQUAL("alpha_!!i!!", "beta_!!i!!")',
            "numeric": "EQUAL(!!i!!, !!total!!)",
        }[comparison]
        lines += [f"-- !x! IF ({condition})", "-- !x! SUB matched yes", "-- !x! ENDIF"]
    if sql:
        lines.append("INSERT INTO sink VALUES (!!i!!);")
    lines += ["-- !x! END SCRIPT", "-- !x! EXECUTE SCRIPT work WHILE(IS_GT(!!total!!, !!i!!))"]
    if sql:
        lines.append(f"-- !x! ASSERT ROW_COUNT_EQ(sink, {iterations})")
    return "\n".join(lines) + "\n"


def fixtures(directory: Path, iterations: int) -> None:
    for name, text in {
        "small": loop(iterations),
        "large": loop(iterations, padding=30),
        "comparison": loop(iterations, comparison="fixed"),
        "same": loop(iterations, comparison="same"),
        "changing": loop(iterations, comparison="changing"),
        "numeric": loop(iterations, comparison="numeric"),
        "sql": loop(iterations, sql=True),
    }.items():
        (directory / f"{name}.sql").write_text(text, encoding="utf-8")
    for name in ("sub", "other"):
        (directory / name).mkdir()
    (directory / "sub/part.sql").write_text(
        '-- !x! SUB included_before "!!$CURRENT_SCRIPT_PATH!!"\n'
        '-- !x! CD ../other\n-- !x! SUB included_after "!!$CURRENT_SCRIPT_PATH!!"\n-- !x! CD ../sub\n',
        encoding="utf-8",
    )
    (directory / "paths.sql").write_text(
        '-- !x! SUB start_seen "!!$CURRENT_SCRIPT_PATH!!"\n-- !x! CD sub\n'
        '-- !x! SUB after_cd "!!$CURRENT_SCRIPT_PATH!!"\n-- !x! INCLUDE part.sql\n'
        '-- !x! BEGIN SCRIPT probe\n-- !x! SUB inline_seen "!!$CURRENT_SCRIPT_PATH!!"\n'
        "-- !x! END SCRIPT\n-- !x! EXECUTE SCRIPT probe\n-- !x! CD ..\n"
        '-- !x! SUB after_return "!!$CURRENT_SCRIPT_PATH!!"\n',
        encoding="utf-8",
    )


def worker(
    source: Path,
    directory: Path,
    iterations: int,
    number: int,
    profile_dir: Path | None,
    selected: list[str] | None,
) -> dict:
    if sys.pycache_prefix is None or Path(sys.pycache_prefix).resolve() != directory.parent / "bytecode":
        raise RuntimeError("Worker requires the measurement's private bytecode cache.")
    sys.path.insert(0, str(source))
    import execsql
    from execsql.api import _LibraryConfig
    from execsql.state import RuntimeContext, active_context

    if not Path(execsql.__file__).resolve().is_relative_to(source.resolve()):
        raise RuntimeError("Benchmark imported the wrong source tree.")
    context = RuntimeContext()
    context.conf = _LibraryConfig()
    with active_context(context):
        return _measure_worker(source, directory, iterations, number, profile_dir, selected)


def _measure_worker(
    source: Path,
    directory: Path,
    iterations: int,
    number: int,
    profile_dir: Path | None,
    selected: list[str] | None,
) -> dict:
    import execsql
    from execsql.metacommands.conditions import xf_equals

    os.chdir(directory)

    def execute(**kwargs: Any) -> Any:
        result = execsql.run(dsn="sqlite:///:memory:", **kwargs)
        if not result.success:
            raise RuntimeError(str(result.errors))
        return result

    execute(sql="-- !x! ASSERT EQUAL(true, t)\n-- !x! ASSERT EQUAL(true, 1)\n")
    boolean_checks = [xf_equals(string1="true", string2=value) for value in ("t", "1")]
    assert boolean_checks == [True, True], "Direct comparisons must use the API's default Boolean configuration."
    snapshot = execute(
        sql="""-- !x! SUB calls 0
-- !x! SUB seen 0
-- !x! BEGIN SCRIPT grow
-- !x! SUB_ADD calls 1
-- !x! EXTEND SCRIPT grow WITH METACOMMAND SUB_ADD seen 1
-- !x! END SCRIPT
-- !x! EXECUTE SCRIPT grow
-- !x! ASSERT IDENTICAL(!!seen!!, 0)
-- !x! EXECUTE SCRIPT grow
-- !x! ASSERT IDENTICAL(!!seen!!, 1)
-- !x! EXECUTE SCRIPT grow
-- !x! ASSERT IDENTICAL(!!seen!!, 3)
""",
    )
    assert snapshot.variables["calls"] == "3"
    paths = execute(script="paths.sql")
    expected_paths = {
        "start_seen": directory,
        "after_cd": directory / "sub",
        "included_before": directory / "sub",
        "included_after": directory / "other",
        "inline_seen": directory / "sub",
        "after_return": directory,
    }
    for name, path in expected_paths.items():
        assert paths.variables[name] == f'"{path.resolve()}{os.sep}"', (name, paths.variables[name])
    guards = {
        "default_booleans": boolean_checks,
        "extension_calls": snapshot.variables["calls"],
        "extension_seen": snapshot.variables["seen"],
        "paths": {name: paths.variables[name].replace(str(directory), "<fixture>") for name in expected_paths},
        "comparison_matrix": [xf_equals(string1=a, string2=b) for a in VALUES for b in VALUES],
    }
    texts = {
        name: (directory / f"{name}.sql").read_text(encoding="utf-8")
        for name in ("small", "large", "comparison", "same", "changing", "numeric", "sql")
    }

    def api_case(name: str, mode: str = "relative") -> dict:
        path = directory / f"{name}.sql"
        kwargs = (
            {"sql": texts[name]} if mode == "inline" else {"script": str(path) if mode == "absolute" else path.name}
        )
        result = execute(**kwargs)
        assert result.variables["i"] == str(iterations)
        assert result.variables["label"] == f"item_{iterations}"
        assert result.variables.get("matched") == ("yes" if name in ("same", "numeric") else None)
        return {
            "commands": result.commands_run,
            "i": result.variables["i"],
            "label": result.variables["label"],
            "matched": result.variables.get("matched"),
        }

    def compare(pair: tuple[str, str]) -> bool:
        outcome = False
        for _ in range(number):
            outcome = xf_equals(string1=pair[0], string2=pair[1])
        return outcome

    cases = {
        "api_small_inline": (lambda: api_case("small", "inline"), iterations),
        "api_small_relative": (lambda: api_case("small"), iterations),
        "api_small_absolute": (lambda: api_case("small", "absolute"), iterations),
        "api_large_relative": (lambda: api_case("large"), iterations),
        "api_comparison_loop": (lambda: api_case("comparison"), iterations),
        "api_same_comparison_loop": (lambda: api_case("same"), iterations),
        "api_changing_comparison_loop": (lambda: api_case("changing"), iterations),
        "api_numeric_comparison_loop": (lambda: api_case("numeric"), iterations),
        "api_sql_loop": (lambda: api_case("sql"), iterations),
    }
    for label, pair in PAIRS.items():
        cases[f"equal_{label}"] = (lambda pair=pair: compare(pair), number)
    results = {}
    if profile_dir:
        profile_dir.mkdir(parents=True)
    if selected:
        unknown = set(selected) - cases.keys()
        if unknown:
            raise ValueError(f"Unknown workload(s): {', '.join(sorted(unknown))}")
        cases = {name: case for name, case in cases.items() if name in selected}
    for name, (call, operations) in cases.items():
        expected = call()  # Imports, caches and all workload paths warm before timing.
        profiler = cProfile.Profile() if profile_dir else None
        cpu_start, start = time.process_time(), time.perf_counter()
        observed = profiler.runcall(call) if profiler else call()
        elapsed, cpu = time.perf_counter() - start, time.process_time() - cpu_start
        assert observed == expected, name
        result = {"seconds": elapsed, "cpu_seconds": cpu, "operations": operations, "signature": observed}
        if profiler:
            profiler.dump_stats(str(profile_dir / f"{name}.prof"))
            stats = pstats.Stats(profiler)
            functions = []
            for (filename, line, function), (primitive, total, own, cumulative, _) in stats.stats.items():
                if filename.startswith(str(source)):
                    filename = str(Path(filename).relative_to(source))
                functions.append(
                    {
                        "file": filename,
                        "line": line,
                        "function": function,
                        "primitive_calls": primitive,
                        "total_calls": total,
                        "self_seconds": own,
                        "cumulative_seconds": cumulative,
                    },
                )
            result["functions"] = sorted(functions, key=lambda item: item["cumulative_seconds"], reverse=True)
        results[name] = result
    return {"guards": guards, "results": results}


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def source_hash(source: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(str(path.relative_to(source)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1000, help="Iterations per API script workload.")
    parser.add_argument("--number", type=int, default=1000, help="Comparisons per EQUAL microbenchmark sample.")
    parser.add_argument(
        "--repeat",
        type=int,
        default=5,
        help="Paired timing samples, alternating implementation order.",
    )
    parser.add_argument("--baseline-ref", default="v2.41.0", help="Trusted local Git revision to execute in isolation.")
    parser.add_argument("--outdir", type=Path, help="New output directory; must not already exist.")
    parser.add_argument("--case", action="append", help="Measure only this workload name; repeat to select several.")
    parser.add_argument("--worker-source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--workdir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--profile-dir", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run without -O; the benchmark requires its correctness assertions.")
    if min(args.iterations, args.number, args.repeat) < 1:
        parser.error("--iterations, --number and --repeat must be positive")
    if args.worker_source:
        if not args.workdir:
            parser.error("worker requires --workdir")
        print(
            json.dumps(
                worker(args.worker_source, args.workdir, args.iterations, args.number, args.profile_dir, args.case),
            ),
        )
        return
    baseline = git("rev-parse", "--verify", "--end-of-options", args.baseline_ref + "^{commit}")
    outdir = (
        args.outdir
        or ROOT / "scripts/benchmarks/results" / datetime.datetime.now().strftime("control-flow-%Y%m%d-%H%M%S-%f")
    ).resolve()
    try:
        outdir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("Output directory exists; select a new directory to preserve prior results.")
    samples: dict[str, list] = {"baseline": [], "current": []}
    profiles = {}
    with tempfile.TemporaryDirectory(prefix="execsql-control-flow-") as temporary:
        directory = Path(temporary).resolve()
        archive = directory / "baseline.tar"
        subprocess.run(
            ["git", "-C", str(ROOT), "archive", "--format=tar", f"--output={archive}", baseline, "src/execsql"],
            check=True,
        )
        baseline_dir = directory / "baseline"
        with tarfile.open(archive) as contents:
            for member in contents:
                if member.isdir():
                    continue
                target = baseline_dir / member.name
                if not member.isfile() or not target.resolve().is_relative_to(baseline_dir.resolve()):
                    raise RuntimeError("Baseline source archive contains an unsupported entry.")
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = contents.extractfile(member)
                assert stream is not None
                with stream:
                    target.write_bytes(stream.read())
        sources = {"baseline": baseline_dir / "src", "current": ROOT / "src"}
        hashes = {label: source_hash(path / "execsql") for label, path in sources.items()}
        workdir = directory / "fixtures"
        workdir.mkdir()
        fixtures(workdir, args.iterations)
        guards = None

        def invoke(label: str, *, profile: bool = False) -> dict:
            command = [
                sys.executable,
                "-X",
                f"pycache_prefix={directory / 'bytecode'}",
                str(Path(__file__).resolve()),
                "--worker-source",
                str(sources[label]),
                "--workdir",
                str(workdir),
                "--iterations",
                str(args.iterations),
                "--number",
                str(args.number),
            ]
            if profile:
                command += ["--profile-dir", str(outdir / "profiles" / label)]
            for name in args.case or []:
                command += ["--case", name]
            completed = subprocess.run(command, cwd=workdir, capture_output=True, text=True, timeout=600)
            if completed.returncode:
                raise RuntimeError(f"{label} worker failed:\n{completed.stdout}\n{completed.stderr}")
            return json.loads(completed.stdout)

        for repeat in range(args.repeat):
            for label in ("baseline", "current") if repeat % 2 == 0 else ("current", "baseline"):
                print(f"Timing {label}, sample {repeat + 1}/{args.repeat}", flush=True)
                sample = invoke(label)
                if guards is None:
                    guards = sample["guards"]
                assert sample["guards"] == guards, f"{label}: semantic guards differ"
                samples[label].append(sample["results"])
        for label in sources:
            print(f"Profiling {label} (separate from timing samples)", flush=True)
            profiled = invoke(label, profile=True)
            assert profiled["guards"] == guards
            profiles[label] = profiled["results"]
        assert hashes == {label: source_hash(path / "execsql") for label, path in sources.items()}, (
            "Source changed during measurement"
        )
    rows = []
    for name in samples["current"][0]:
        row = {"name": name}
        signature = samples["baseline"][0][name]["signature"]
        for label in sources:
            timings = [sample[name] for sample in samples[label]]
            assert all(sample["signature"] == signature for sample in timings), name
            assert profiles[label][name]["signature"] == signature, name
            values = [sample["seconds"] for sample in timings]
            median = statistics.median(values)
            row[label] = {
                "samples": timings,
                "median_seconds": median,
                "mad_percent": statistics.median(abs(value - median) for value in values) / median * 100,
                "microseconds_per_operation": median * 1e6 / timings[0]["operations"],
            }
        row["baseline_over_current"] = row["baseline"]["median_seconds"] / row["current"]["median_seconds"]
        rows.append(row)
    payload = {
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "locale": locale.getlocale(locale.LC_TIME),
            "dateutil": importlib.metadata.version("python-dateutil"),
            "perf_counter_resolution": time.get_clock_info("perf_counter").resolution,
        },
        "measured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "baseline_ref": args.baseline_ref,
        "baseline_commit": baseline,
        "current_commit": git("rev-parse", "HEAD"),
        "runtime_dirty": bool(git("status", "--porcelain", "--untracked-files=all", "--", "src/execsql")),
        "source_sha256": hashes,
        "iterations": args.iterations,
        "number": args.number,
        "repeat": args.repeat,
        "selected_cases": args.case,
        "guards": guards,
        "results": rows,
    }
    (outdir / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (outdir / "profiles.json").write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")
    markdown = [
        "# E1 control-flow measurements",
        "",
        f"Baseline `{baseline}`; current `{payload['current_commit']}`.",
        f"Runtime source identical: {hashes['baseline'] == hashes['current']}. Repeats: {args.repeat}.",
        "",
        "API rows: microseconds per script iteration, including run setup/parse/cleanup. EQUAL rows: microseconds per direct comparison.",
        "",
        "| Workload | Baseline µs/op | Current µs/op | Baseline/current | Current MAD % |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        markdown.append(
            f"| {row['name']} | {row['baseline']['microseconds_per_operation']:.2f} | {row['current']['microseconds_per_operation']:.2f} | {row['baseline_over_current']:.3f} | {row['current']['mad_percent']:.2f} |",
        )
    markdown += [
        "",
        "Timing ratios between identical sources measure noise, not improvements.",
        "Profiles are instrumented separately; cumulative function times overlap and must not be added together.",
        "",
    ]
    (outdir / "results.md").write_text("\n".join(markdown), encoding="utf-8")
    print(f"Results and profiles: {outdir}")


if __name__ == "__main__":
    main()
