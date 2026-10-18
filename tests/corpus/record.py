"""Record what upstream execsql 1.130.1 does for each corpus case.

    uv run python -m tests.corpus.record            # every case
    uv run python -m tests.corpus.record sub_basic  # named cases

Upstream is installed from PyPI once, into a virtual environment under
``~/.cache/execsql-corpus/upstream-1.130.1`` (``EXECSQL_CORPUS_UPSTREAM``
overrides the location), with Python 3.12: the 1.130.1 monolith does not run
on 3.13 or later.  Each case's results are written to
``tests/corpus/results/<case>.json``; CI compares against those files and
never needs upstream installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.corpus.runner import RESULTS, case_names, run_case

UPSTREAM_VERSION = "1.130.1"
_MAIN = "import sys; sys.argv[0] = 'execsql'; from execsql.execsql import main; main()"


def upstream_python() -> Path:
    """The Python of a virtual environment with upstream execsql installed; created on first use."""
    default = Path.home() / ".cache" / "execsql-corpus" / f"upstream-{UPSTREAM_VERSION}"
    venv = Path(os.environ.get("EXECSQL_CORPUS_UPSTREAM", default))
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        subprocess.run(["uv", "venv", "--python", "3.12", str(venv)], check=True)
        subprocess.run(["uv", "pip", "install", "--python", str(python), f"execsql=={UPSTREAM_VERSION}"], check=True)
    return python


def main(names: list[str]) -> None:
    command = [str(upstream_python()), "-c", _MAIN]
    RESULTS.mkdir(exist_ok=True)
    for case in names or case_names():
        with tempfile.TemporaryDirectory() as tmp:
            result = run_case(case, command, Path(tmp) / "work")
        result["recorded_with"] = f"execsql {UPSTREAM_VERSION}"
        path = RESULTS / f"{case}.json"
        path.write_text(json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
        print(f"{case}: exit {result['exit']}, {len(result['files'])} files, {len(result['tables'])} tables")


if __name__ == "__main__":
    main(sys.argv[1:])
