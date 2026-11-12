#!/usr/bin/env python3
"""Measure substitution with small and large variable pools; emit JSON to stdout."""

from __future__ import annotations

import argparse
from functools import partial
import json
import platform
import statistics
import subprocess
import timeit

from execsql.script.variables import SubVarSet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--number", type=int, default=500, help="expansions per sample")
    parser.add_argument("--repeat", type=int, default=5, help="samples per workload")
    parser.add_argument("--baseline-ref", help="compare with variables.py at this local Git revision")
    args = parser.parse_args()
    if args.number < 1 or args.repeat < 1:
        parser.error("--number and --repeat must be positive")
    baseline_class = None
    if args.baseline_ref:
        source = subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:src/execsql/script/variables.py"],
            text=True,
        )
        namespace = {"__name__": "substitution_baseline"}
        exec(compile(source, "<substitution baseline>", "exec"), namespace)
        baseline_class = namespace["SubVarSet"]
    results = []
    for size in (10, 100, 1000):
        entries = [(f"unused_{index}", "unused") for index in range(size)]
        entries += [("group", "ABC"), ("n_abc_checks", "42")]
        variables = SubVarSet()
        variables.substitutions = entries
        baseline = baseline_class() if baseline_class else None
        if baseline is not None:
            baseline.substitutions = entries
        for name, text in (
            ("no_tokens", "SELECT 1;"),
            ("plain", "SELECT !!group!!;"),
            ("nested", "SELECT !!N_!!GROUP!!_CHECKS!!;"),
            ("quoted_control", "SELECT !'!N_!!GROUP!!_CHECKS!'!;"),
            ("nested_two_names", "SELECT !!N_!!GROUP!!_CHECKS!!, !!N_!!n_abc_checks!!_CHECKS!!;"),
            ("unresolved", "SELECT !!N_!!MISSING!!_CHECKS!!;"),
            ("long_unresolved", "SELECT " + "x " * 1000 + "!!MISSING!!;"),
        ):
            current_call = partial(variables.substitute_all, text)
            samples = []
            baseline_samples = []
            baseline_call = partial(baseline.substitute_all, text) if baseline is not None else None
            if baseline_call is not None:
                assert current_call() == baseline_call(), (size, name)
            for sample in range(args.repeat):
                # Alternate order to reduce bias from load and thermal changes.
                calls = [(current_call, samples)]
                if baseline_call is not None:
                    calls.append((baseline_call, baseline_samples))
                if sample % 2:
                    calls.reverse()
                for call, timings in calls:
                    timings.append(timeit.timeit(call, number=args.number) * 1e6 / args.number)
            result = {"variables": size, "workload": name, "microseconds": statistics.median(samples)}
            if baseline_samples:
                result["baseline_microseconds"] = statistics.median(baseline_samples)
                result["speedup"] = result["baseline_microseconds"] / result["microseconds"]
            results.append(result)
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "baseline_ref": args.baseline_ref,
                "number": args.number,
                "repeat": args.repeat,
                "results": results,
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
