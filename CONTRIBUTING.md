# Contributing

## Development Setup

Requires [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/).

```bash
git clone https://github.com/geocoug/execsql
cd execsql
just sync
```

This creates a virtual environment at `.venv/` and installs all dependencies including dev extras.

To install `just`:

```bash
brew install just          # macOS
cargo install just         # any platform with Rust
uv tool install rust-just  # via uv
```

## Available Recipes

Run `just` with no arguments to list all available recipes.

```
just sync          # Sync dependencies from lockfile
just update-hooks  # Update pre-commit hooks to latest versions

just lint          # Run ruff linter + formatter
just pre-commit    # Run all pre-commit hooks against every file
just test          # Run tests against the active Python version
just test-all      # Run tests across all supported Python versions (3.10–3.13)
just clean         # Remove build artifacts and caches

just docs          # Build the documentation site
just docs-serve    # Serve docs locally at http://127.0.0.1:8000

just bump          # Show available version bumps from current version
just bump-patch    # Bump patch version  (e.g. 2.0.0 → 2.0.1)
just bump-minor    # Bump minor version  (e.g. 2.0.0 → 2.1.0)
just bump-major    # Bump major version  (e.g. 2.0.0 → 3.0.0)
just bump-pre 2.0.0a1  # Tag a specific pre-release version
```

## Code Quality

Linting and formatting are handled by [ruff](https://docs.astral.sh/ruff/):

```bash
just lint
```

[pre-commit](https://pre-commit.com/) hooks enforce additional checks (gitleaks, uv-lock, mdformat, markdownlint, typos, validate-pyproject) on every commit. To run them manually against all files:

```bash
just pre-commit
```

CI rejects PRs that fail linting or any pre-commit check.

## Running Tests

```bash
just test       # active Python only
just test-all   # full 3.10–3.13 matrix in parallel
```

Tests are run with [pytest](https://pytest.org/) via [tox-uv](https://github.com/tox-dev/tox-uv). Coverage is reported automatically.

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

Releases are managed with [bump-my-version](https://callowayproject.github.io/bump-my-version/) and published automatically by the `ci-cd.yml` workflow when a version tag is pushed.

### Stable releases

```bash
just bump-patch   # or bump-minor / bump-major
git push origin main --follow-tags
```

`bump-my-version` commits the version change and creates the tag in one step.

### Pre-releases (alpha, beta, RC)

Use `just bump-pre` with a full [PEP 440](https://peps.python.org/pep-0440/) version string:

```bash
just bump-pre 2.0.0a1   # alpha
just bump-pre 2.0.0b1   # beta
just bump-pre 2.0.0rc1  # release candidate
git push origin <branch> --follow-tags
```

Pre-releases are published to PyPI but are not installed by default — `pip install execsql2` will not pick them up unless `--pre` is passed.

### CI/CD pipeline (`ci-cd.yml`)

Triggered on pushes to `main`, any `v*.*.*` tag, and pull requests.

| Job                | Trigger            | What it does                                    |
| ------------------ | ------------------ | ----------------------------------------------- |
| `tests`            | all events         | Runs the test matrix (3 OS × 4 Python versions) |
| `build`            | `v*.*.*` tags only | Builds sdist + wheel, checks with twine         |
| `publish`          | `v*.*.*` tags only | Publishes to PyPI via OIDC trusted publishing   |
| `generate-release` | `v*.*.*` tags only | Creates a GitHub Release with dist artifacts    |

### PyPI trusted publishing setup

The `publish` job uses OIDC trusted publishing — no API token is required. To configure it on PyPI, add a trusted publisher with these settings:

| Field       | Value       |
| ----------- | ----------- |
| Owner       | `geocoug`   |
| Repository  | `execsql`   |
| Workflow    | `ci-cd.yml` |
| Environment | `pypi`      |
