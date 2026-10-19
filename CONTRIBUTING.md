# Contributing

## Development Setup

Requires [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/).

```bash
git clone https://github.com/geocoug/execsql
cd execsql
just sync
```

This creates a virtual environment at `.venv/` and installs every extra plus the `dev` dependency group (test, lint and docs tools). Without uv: `pip install -e ".[all]" --group dev` (pip 25.1 or later).

To install `just`:

```bash
brew install just          # macOS
cargo install just         # any platform with Rust
uv tool install rust-just  # via uv
```

## Available Recipes

Run `just` with no arguments to list all available recipes.

## Code Quality

Linting and formatting are handled by [ruff](https://docs.astral.sh/ruff/):

```bash
just lint
```

Static type checking is handled by [mypy](https://mypy.readthedocs.io/) and must pass with zero errors:

```bash
just typecheck
```

[pre-commit](https://pre-commit.com/) hooks enforce additional checks (gitleaks, uv-lock, mdformat, markdownlint, typos, validate-pyproject, mypy) on every commit. To run them manually against all files:

```bash
just pre-commit
```

CI rejects PRs that fail ruff lint/format, mypy type checking, the full pre-commit suite, docs build, or tests.

## Running Tests

```bash
just test       # active Python only
just test-all   # full 3.10–3.14 matrix in parallel
```

Tests are run with [pytest](https://pytest.org/) via [tox-uv](https://github.com/tox-dev/tox-uv). Coverage is reported automatically.

The scripts in `templates/` are tested against live PostgreSQL, MySQL, MariaDB and SQL Server (`tests/templates/`). The normal suite skips those tests when no server is running; CI's integration job runs them. To run them locally against throwaway containers:

```bash
just test-templates        # starts execsql-templates-* containers on ports 55440-55443, runs the tests
just test-templates-down   # removes the containers
```

SQL Server is included only when an ODBC driver for it is installed. A template bug the tests have found but not yet fixed is marked with `known_bug(...)`, a strict expected failure: the fix makes the test pass, which fails the run until the marker is removed with it.

### Script behavior corpus

`tests/corpus/` checks that whole scripts do under execsql2 what they did under upstream execsql 1.130.1: the same exit status, console output, files written and table contents. Each case is a directory in `tests/corpus/cases/` holding `script.sql` and the files it reads. Upstream's results are recorded in `tests/corpus/results/`, so the normal test run compares against them without upstream installed. A variable a case checks is `WRITE`n to a file, because upstream has no way to read variables after a run.

To add a case, create its directory, then record what upstream does (this installs execsql 1.130.1 from PyPI under Python 3.12 into `~/.cache/execsql-corpus/` on first use):

```bash
uv run python -m tests.corpus.record my_new_case
uv run pytest tests/corpus
```

Use only syntax upstream accepts; read `_execsql/execsql.py` when unsure. A case must not open a GUI dialog (`HALT "message"`, `PROMPT`) or loop forever under upstream: both hang the recording. Nor may it read a file it has just written (`FILE_EXISTS`, `ZIP`, `IMPORT` right after a `WRITE`): both programs write files in the background, so the result depends on timing; put such a file among the case's inputs instead. A difference from upstream fails the test unless `tests/corpus/changes.json` lists it with both values, a `status` (`accepted` for an upstream bug execsql2 fixed on purpose, `open` for one not yet decided) and the reason.

## Building the Docs

```bash
just docs-serve   # live-reloading local preview
just docs         # build static site to site/
```

Docs are built with [Zensical](https://zensical.dev/) (MkDocs + Material theme).

## Building a Distribution

```bash
uv build
```

Artifacts are written to `dist/`. The CI pipeline does this automatically on tagged releases.

## Releases

Releases are cut with `just bump-patch` / `bump-minor` / `bump-major` / `bump-pre <version>` and published by
`.github/workflows/ci-cd.yml` when the tag is pushed. [Release Process](docs/dev/releasing.md) is the one checklist:
what each bump does, what CI runs on a tag, where the release notes come from, and what to do when a step fails.
