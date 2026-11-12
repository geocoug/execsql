# Contributing

## Development Setup

Use **Python 3.13** for development, as selected by `.python-version`. The development and docs tools require **Python 3.11 or later**. Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/).

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

Tests are run with [pytest](https://pytest.org/) via [tox-uv](https://github.com/tox-dev/tox-uv). Coverage is reported automatically. Tox and CI install the unpublished `test` dependency group inside each test environment, so the full Python 3.10–3.14 matrix does not need development/docs tools on Python 3.10.

To make a separate Python 3.10 test environment with uv, run:

```bash
UV_PROJECT_ENVIRONMENT=.tox/uv-py310 uv sync --python 3.10 --no-dev --group test --all-extras
UV_PROJECT_ENVIRONMENT=.tox/uv-py310 uv run --python 3.10 --no-dev --group test pytest
```

The separate path keeps your Python 3.13 development environment intact. With pip in an existing Python 3.10 virtual environment, use `pip install -e ".[all]" --group test` instead of `--group dev`.

pytest runs the tests in parallel, one worker per CPU ([pytest-xdist](https://pytest-xdist.readthedocs.io/)), so each test must stand alone: use `tmp_path` for files, and never rely on another test having run first. Pass `-n 0` to run in one process, for example under a debugger (`uv run pytest -n 0 --pdb tests/test_x.py`) or to see live log output. Tests that run against a live database server share its database, so they are kept on one worker per server: a test parametrized with `postgres`, `mysql`, `mariadb` or `sqlserver` is grouped by `tests/conftest.py`, a module that tests one server throughout sets `pytestmark = pytest.mark.xdist_group("live-<server>")`, and a test that opens a server by name (`open_backend("postgres", tmp_path)`) carries `@pytest.mark.xdist_group("live-postgres")` itself.

The scripts in `templates/` are tested against live PostgreSQL, MySQL, MariaDB and SQL Server (`tests/templates/`). The normal suite skips those tests when no server is running; CI's integration job runs them. To run them locally against throwaway containers:

```bash
just test-templates        # starts execsql-templates-* containers on ports 55440-55443, runs the tests
just test-templates-down   # removes the containers
```

CI sets `EXECSQL_REQUIRED_BACKENDS=postgres,mysql,mariadb,sqlserver` for the in-process integration suite. A missing driver, failed connection or unavailable import prerequisite for one of those backends fails the run instead of skipping its checks. The selected names appear in pytest's report header. To require a locally provisioned server, run:

```bash
EXECSQL_REQUIRED_BACKENDS=postgres uv run pytest
```

The comma-separated list accepts `postgres`, `mysql`, `mariadb`, `sqlserver`, `sqlite` and `duckdb`; unknown names are configuration errors. With the variable unset, unavailable optional servers retain their cached local skips. Exporter table-creation and seed errors after a successful connection always fail, including locally.

SQL Server is included only when an ODBC driver for it is installed. A template bug the tests have found but not yet fixed is marked with `known_bug(...)`, a strict expected failure: the fix makes the test pass, which fails the run until the marker is removed with it.

### Transaction rules: generated scripts

`tests/test_transaction_model.py` checks the transaction rules (batches, `BREAK`, failed commits, `AUTOCOMMIT`, `ERROR_HALT`, an `ON ERROR_HALT` script, and interrupts: `KeyboardInterrupt` or a plain `SystemExit` after a statement, inside a metacommand, or before or after a commit) against scripts [Hypothesis](https://hypothesis.readthedocs.io/) generates: a small model of one SQLite connection predicts the rows stored, the rows left pending on the caller's connection, the errors reported and `SQL_ERROR()`, and a mismatch is shrunk to the shortest script that still differs. Each run, CI included, tries 700 new scripts (about 7 s); `EXECSQL_MODEL_EXAMPLES=5000` tries more (about a minute). A failure of this test, in CI too, is a bug in execsql or in the model: add the script it prints as an `@example` and fix one or the other, rather than rerunning. When you change a transaction rule, change the model with it; a combination that matters but is rarely generated goes in an `@example`.

The **Transaction model** workflow runs 5,000 generated scripts every Monday at 07:23 UTC and can be started manually from GitHub Actions. It runs on SQLite, without the full-suite coverage floor, and saves a JUnit report containing any failing example. Run the same check locally with:

```bash
EXECSQL_MODEL_EXAMPLES=5000 uv run pytest tests/test_transaction_model.py -n 0 --no-cov
```

Keep focused regressions for multiple databases, driver behavior, error messages and BREAKPOINT input: the single-connection model does not replace them. Duplicate single-case checks have been consolidated into permanent `@example` cases.

Whole-script CLI tests allow 120 seconds on Windows, where durable SQLite commits on shared runners have approached or exceeded a 30-second limit. Other platforms keep their 30-second defaults (60 seconds for standalone script fixtures). Explicit short timeout regressions keep their own limits. CI points temporary files at `runner.temp`; SQLite's normal durability and transaction settings remain in effect. Timed-out CLI processes report watchdog stacks, and slow successful processes report them as pytest warnings without changing the script's stdout/stderr or output files.

### Script behavior corpus

`tests/corpus/` checks that whole scripts do under execsql2 what they did under upstream execsql 1.130.1: the same exit status, console output, files written and table contents. Each case is a directory in `tests/corpus/cases/` holding `script.sql` and the files it reads. Upstream's results are recorded in `tests/corpus/results/`, so the normal test run compares against them without upstream installed. A variable a case checks is `WRITE`n to a file, because upstream has no way to read variables after a run.

To add a case, create its directory, then record what upstream does (this installs execsql 1.130.1 from PyPI under Python 3.12 into `~/.cache/execsql-corpus/` on first use):

```bash
uv run python -m tests.corpus.record my_new_case
uv run pytest tests/corpus
```

Firebird transaction regressions run against a disposable database when `EXECSQL_FIREBIRD_DATABASE` is set. Install the `[firebird]` extra and the native Firebird client library, then set these variables for a server you own:

```sh
export EXECSQL_FIREBIRD_DATABASE=/var/lib/firebird/data/execsql.fdb
export EXECSQL_FIREBIRD_HOST=localhost
export EXECSQL_FIREBIRD_PORT=3050
export EXECSQL_FIREBIRD_USER=SYSDBA
export EXECSQL_FIREBIRD_PASSWORD=your-test-password
uv run pytest tests/db/test_firebird_live.py tests/corpus -k firebird
```

The tests create and drop tables, exceptions and transaction triggers: use only a disposable database. The official [Firebird Docker image](https://github.com/FirebirdSQL/firebird-docker) can provide one; the fix for #138 was verified with Firebird 5.0.4. This opt-in suite does not change Firebird's best-effort support tier.

A corpus case with a `requires-firebird` marker starts with Firebird instead of SQLite and exports observations to files. Its test skips when the database variable is absent; recording all cases skips it too, while explicitly recording it requires a configured server. To re-record it, install `fdb` into the upstream environment as well as the native client library, then run `uv run python -m tests.corpus.record firebird_catalog_holds`. Credentials are passed through the driver's environment variables and are never recorded. The live tests and native corpus cases share an xdist group so their transaction triggers cannot interfere.

Use only syntax upstream accepts; read `_execsql/execsql.py` when unsure. A case must not open a GUI dialog (`HALT "message"`, `PROMPT`) or loop forever under upstream: both hang the recording. Nor may it read a file it has just written (`FILE_EXISTS`, `ZIP`, `IMPORT` right after a `WRITE`): both programs write files in the background, so the result depends on timing; put such a file among the case's inputs instead. A difference from upstream fails the test unless `tests/corpus/changes.json` lists it with both values, a `status` (`accepted` for an upstream bug execsql2 fixed on purpose, `open` for one not yet decided) and the reason.

## Building the Docs

```bash
just docs-serve   # live-reloading local preview
just docs         # build static site to site/
```

Docs are built with [Zensical](https://zensical.org/), using MkDocs-compatible configuration and Markdown extensions. `zensical.toml` owns navigation and theme settings. `just docs` builds in strict mode; a warning fails the build.

The `docs` group pins Zensical 0.0.74 and requires Python 3.11+. The `dev` group includes docs and test tools, so it has the same minimum; Python 3.13 is the recommended working environment. This does not change execsql2’s Python 3.10 runtime support.

Use native anchor redirects in `[project.plugins.redirects.redirect_maps]` when moving published sections. Keep a usable old-page link as a fallback. The `llmstxt` configuration exports selected public pages as Markdown and enables **Copy as Markdown**; update its sections when adding a major documentation area. The canonical site URL includes Read the Docs’ `/en/stable/` prefix so generated sitemaps and Markdown links resolve to the published site.

## Building a Distribution

```bash
uv build
```

Artifacts are written to `dist/`. The CI pipeline does this automatically on tagged releases.

## Releases

Releases are cut with `just bump-patch` / `bump-minor` / `bump-major` / `bump-pre <version>` and published by
`.github/workflows/ci-cd.yml` when the tag is pushed. [Release Process](docs/dev/releasing.md) is the one checklist:
what each bump does, what CI runs on a tag, where the release notes come from, and what to do when a step fails.
