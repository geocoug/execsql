#!/usr/bin/env python3
"""Reproducible execsql benchmark harness.

Measures how execsql scales — import and export across formats and data
sizes, the effect of performance-relevant configuration options, and
per-metacommand dispatch overhead. Results are written as JSON and a
ready-to-paste Markdown fragment.

This is NOT a comparison against dedicated bulk loaders. The point is to
show how execsql behaves and which of its own choices matter.

Usage:
    python benchmarks/run_benchmarks.py --quick          # small sizes, fast
    python benchmarks/run_benchmarks.py                  # full suite
    python benchmarks/run_benchmarks.py --execsql "uv run execsql"

Requirements: execsql on PATH (or --execsql), plus the `formats` extra
for the XLSX/ODS/Parquet/Feather benchmarks (they are skipped when the
underlying packages are missing).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import platform
import random
import shlex
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Row counts for the scaling series. XLSX and ODS are capped separately —
# spreadsheet formats are dramatically slower and 1M-row spreadsheets are
# not a realistic workload.
FULL_SIZES = [1_000, 10_000, 100_000, 1_000_000]
QUICK_SIZES = [1_000, 10_000, 100_000]
XLSX_CAP = 100_000
ODS_CAP = 10_000

EXPORT_FORMATS = ["CSV", "TSV", "JSON", "XLSX", "ODS", "PARQUET", "FEATHER"]

WORDS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]


def make_csv(path: Path, rows: int) -> None:
    """Write a deterministic mixed-type CSV: int, float, text, date, sparse text."""
    rng = random.Random(20260703)
    start = datetime.date(2020, 1, 1)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "amount", "label", "event_date", "note"])
        for i in range(rows):
            w.writerow(
                [
                    i,
                    round(rng.uniform(0, 10_000), 2),
                    f"{rng.choice(WORDS)}_{rng.randint(0, 999)}",
                    (start + datetime.timedelta(days=rng.randint(0, 1800))).isoformat(),
                    "" if rng.random() < 0.2 else rng.choice(WORDS) * rng.randint(1, 4),
                ],
            )


class Runner:
    def __init__(self, execsql_cmd: str, workdir: Path, reps: int) -> None:
        self.cmd = shlex.split(execsql_cmd)
        self.workdir = workdir
        self.reps = reps
        self.results: list[dict] = []

    def run_script(self, script: str, extra_args: list[str] | None = None) -> float:
        """Run one script through the execsql CLI; return wall seconds."""
        sf = self.workdir / "bench_script.sql"
        sf.write_text(script)
        db = self.workdir / "bench.sqlite"
        argv = [*self.cmd, *(extra_args or []), "-tl", "-n", str(sf), str(db)]
        t0 = time.perf_counter()
        proc = subprocess.run(argv, cwd=self.workdir, capture_output=True, text=True)
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"execsql failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
        return elapsed

    def bench(
        self,
        group: str,
        name: str,
        script: str,
        extra_args: list[str] | None = None,
        rows: int | None = None,
        reps: int | None = None,
    ) -> float:
        """Run a benchmark `reps` times and record the median wall time."""
        n = reps if reps is not None else self.reps
        times = [self.run_script(script, extra_args) for _ in range(n)]
        med = statistics.median(times)
        self.results.append(
            {
                "group": group,
                "name": name,
                "rows": rows,
                "reps": n,
                "seconds": round(med, 3),
                "rows_per_sec": round(rows / med) if rows else None,
            },
        )
        print(f"  {name:<42s} {med:>9.3f} s" + (f"  ({rows / med:,.0f} rows/s)" if rows else ""), flush=True)
        return med


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execsql", default="execsql", help='execsql command (e.g. "uv run execsql")')
    ap.add_argument("--quick", action="store_true", help="small sizes only, 1 rep")
    ap.add_argument("--reps", type=int, default=3, help="repetitions per benchmark (median reported)")
    ap.add_argument("--outdir", default=None, help="results directory (default: scripts/benchmarks/results)")
    args = ap.parse_args()

    sizes = QUICK_SIZES if args.quick else FULL_SIZES
    reps = 1 if args.quick else args.reps
    outdir = Path(args.outdir) if args.outdir else Path(__file__).parent / "results"
    outdir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="execsql_bench_") as td:
        workdir = Path(td)
        r = Runner(args.execsql, workdir, reps)

        version_output = subprocess.run([*r.cmd, "--version"], capture_output=True, text=True).stdout.strip()
        # "execsql 2.x.y" → "2.x.y"
        version = version_output.split()[-1] if " " in version_output else version_output
        print(f"execsql: {version}")
        print(f"sizes: {sizes}  reps: {reps}\n", flush=True)

        print("generating data files...")
        for n in sizes:
            make_csv(workdir / f"data_{n}.csv", n)

        # ------------------------------------------------------------------
        print("\n[startup] CLI baseline (connect, parse, no work)")
        r.bench("startup", "empty script", "-- !x! WRITE ''\n")

        # ------------------------------------------------------------------
        print("\n[import] CSV -> SQLite, IMPORT TO REPLACEMENT")
        for n in sizes:
            # Full-suite 1M-row runs are long; median of 1 is acceptable there.
            r.bench(
                "import",
                f"IMPORT CSV ({n:,} rows)",
                f"-- !x! IMPORT TO REPLACEMENT t_data FROM data_{n}.csv\n",
                rows=n,
                reps=1 if n >= 1_000_000 else None,
            )

        # Spreadsheet import files are produced by execsql itself (EXPORT),
        # then imported back.
        xlsx_n = min(max(sizes), XLSX_CAP)
        ods_n = min(max(sizes), ODS_CAP)
        prep = (
            f"-- !x! IMPORT TO REPLACEMENT t_data FROM data_{xlsx_n}.csv\n"
            f"-- !x! EXPORT t_data TO data_{xlsx_n}.xlsx AS XLSX\n"
        )
        prep_ods = (
            f"-- !x! IMPORT TO REPLACEMENT t_small FROM data_{ods_n}.csv\n"
            f"-- !x! EXPORT t_small TO data_{ods_n}.ods AS ODS\n"
        )
        try:
            r.run_script(prep)
            r.bench(
                "import",
                f"IMPORT XLSX ({xlsx_n:,} rows)",
                f"-- !x! IMPORT TO REPLACEMENT t_x FROM data_{xlsx_n}.xlsx\n",
                rows=xlsx_n,
            )
        except RuntimeError as e:
            print(f"  IMPORT XLSX skipped: {str(e).splitlines()[-1][:80]}")
        try:
            r.run_script(prep_ods)
            r.bench(
                "import",
                f"IMPORT ODS ({ods_n:,} rows)",
                f"-- !x! IMPORT TO REPLACEMENT t_o FROM data_{ods_n}.ods\n",
                rows=ods_n,
            )
        except RuntimeError as e:
            print(f"  IMPORT ODS skipped: {str(e).splitlines()[-1][:80]}")

        # ------------------------------------------------------------------
        print("\n[export] SQLite table -> file, by format")
        big = max(sizes)
        r.run_script(f"-- !x! IMPORT TO REPLACEMENT t_big FROM data_{big}.csv\n")
        db_keep = workdir / "bench.sqlite"  # reused by subsequent runs  # noqa: F841
        for fmt in EXPORT_FORMATS:
            n = big
            table = "t_big"
            if fmt == "XLSX" and big > XLSX_CAP:
                n, table = XLSX_CAP, "t_x100k"
            if fmt == "ODS" and big > ODS_CAP:
                n, table = ODS_CAP, "t_o10k"
            if table != "t_big":
                r.run_script(f"-- !x! IMPORT TO REPLACEMENT {table} FROM data_{n}.csv\n")
            ext = fmt.lower()
            try:
                r.bench(
                    "export",
                    f"EXPORT {fmt} ({n:,} rows)",
                    f"-- !x! EXPORT {table} TO out.{ext} AS {fmt}\n",
                    rows=n,
                    reps=1 if n >= 1_000_000 else None,
                )
            except RuntimeError as e:
                print(f"  EXPORT {fmt} skipped: {str(e).splitlines()[-1][:80]}")

        # ------------------------------------------------------------------
        print("\n[config] import knobs on the largest CSV (defaults vs tuned)")
        imp = f"-- !x! IMPORT TO REPLACEMENT t_cfg FROM data_{big}.csv\n"
        knob_reps = 1 if big >= 1_000_000 else None
        r.bench("config", f"scan_lines=100 (default, {big:,} rows)", imp, rows=big, reps=knob_reps)
        r.bench(
            "config",
            f"scan_lines=0 (scan whole file, {big:,} rows)",
            imp,
            extra_args=["-s", "0"],
            rows=big,
            reps=knob_reps,
        )
        r.bench(
            "config",
            f"import_buffer=1024KB (-z, {big:,} rows)",
            imp,
            extra_args=["-z", "1024"],
            rows=big,
            reps=knob_reps,
        )
        conf = workdir / "trim.conf"
        conf.write_text("[input]\ntrim_strings=Yes\n")
        r.bench(
            "config",
            f"trim_strings=Yes ({big:,} rows)",
            imp,
            extra_args=["--config", str(conf)],
            rows=big,
            reps=knob_reps,
        )

        # ------------------------------------------------------------------
        print("\n[metacommands] dispatch + substitution overhead")

        # Two loop sizes; the delta isolates per-iteration cost from startup.
        # Uses EXECUTE SCRIPT … WHILE (iterative, no Python recursion) and
        # SUB_ADD (avoids the counter auto-increment-on-reference quirk).
        def loop_script(n: int) -> str:
            return (
                f"-- !x! SUB total {n}\n"
                "-- !x! SUB i 0\n"
                "-- !x! BEGIN SCRIPT looper\n"
                "-- !x! SUB_ADD i 1\n"
                "-- !x! SUB label item_!!i!!\n"
                "-- !x! END SCRIPT looper\n"
                f"-- !x! EXECUTE SCRIPT looper WHILE(IS_GT(!!total!!, !!i!!))\n"
            )

        t1 = r.bench("metacommands", "WHILE loop, 500 iterations", loop_script(500))
        t2 = r.bench("metacommands", "WHILE loop, 2000 iterations", loop_script(2000))
        per_cmd_us = (t2 - t1) / (1500 * 2) * 1e6  # 2 metacommands per loop body iteration
        r.results.append(
            {
                "group": "metacommands",
                "name": "per-metacommand overhead",
                "rows": None,
                "reps": reps,
                "seconds": None,
                "rows_per_sec": None,
                "per_command_us": round(per_cmd_us, 1),
            },
        )
        print(f"  {'per-metacommand overhead':<42s} {per_cmd_us:>9.1f} µs")

        # ------------------------------------------------------------------
        env = {
            "execsql": version,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "date": datetime.date.today().isoformat(),
            "sizes": sizes,
            "reps": reps,
        }
        payload = {"environment": env, "results": r.results}
        (outdir / "results.json").write_text(json.dumps(payload, indent=2) + "\n")

        md = ["<!-- generated by benchmarks/run_benchmarks.py -->", ""]
        md.append(f"Measured with execsql {version}, Python {env['python']}, {env['platform']} ({env['date']}).")
        for group in ("startup", "import", "export", "config", "metacommands"):
            rows = [x for x in r.results if x["group"] == group]
            if not rows:
                continue
            md += ["", f"**{group.capitalize()}**", "", "| Benchmark | Time (s) | Rows/s |", "| --- | ---: | ---: |"]
            for x in rows:
                if x.get("per_command_us") is not None:
                    md.append(f"| {x['name']} | — | {x['per_command_us']} µs/metacommand |")
                else:
                    rps = f"{x['rows_per_sec']:,}" if x["rows_per_sec"] else "—"
                    md.append(f"| {x['name']} | {x['seconds']} | {rps} |")
        (outdir / "results.md").write_text("\n".join(md) + "\n")

        print(f"\nresults written to {outdir}/results.json and {outdir}/results.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
