# Install: brew install just  |  cargo install just  |  uv tool install rust-just
# Usage:   just <recipe>

set quiet
set unstable


[private]
default:
    @just --list --unsorted

# ── Dependencies ──────────────────────────────────────────────────────────────

# Sync dependencies from lockfile
[group('deps')]
sync:
    uv sync --all-extras

# Update pre-commit hooks
[group('deps')]
update-hooks:
    uv run pre-commit autoupdate


# ── Code Quality ──────────────────────────────────────────────────────────────

# Lint, spell-check, and test
[group('quality')]
check: format lint test

# Run linter
[group('quality')]
lint:
    uv run ruff check .

# Run formatter
[group('quality')]
format:
    uv run ruff format .

# Run pre-commit hooks on all files
[group('quality')]
pre-commit:
    uv run pre-commit run --all-files

# Run tests
[group('quality')]
test *ARGS:
    uv run tox -e py -- {{ ARGS }}

# Run tests across all supported Python versions
[group('quality')]
test-all:
    uv run tox run-parallel

# Run tests with coverage report printed to terminal
[group('quality')]
coverage:
    uv run pytest --cov-report=term-missing

# Clean up Python build artifacts and caches
[group('quality')]
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type d -name ".pytest_cache" -exec rm -rf {} +
    find . -type d -name "dist" -exec rm -rf {} +
    find . -type d -name "build" -exec rm -rf {} +
    find . -type d -name "*.egg-info" -exec rm -rf {} +
    find . -type d -name ".ruff_cache" -exec rm -rf {} +
    find . -type d -name "site" -exec rm -rf {} +
    find . -type f -name "*.pyc" -exec rm -f {} +
    find . -type f -name "*.pyo" -exec rm -f {} +
    find . -type f -name ".coverage" -exec rm -rf {} +
    find . -type f -name "coverage.xml" -exec rm -rf {} +
    find . -type f -name "execsql.log" -exec rm -f {} +


# ── VS Code Extension ────────────────────────────────────────────────────────

# Regenerate grammar and install VS Code extension via symlink
[group('vscode')]
install-vscode:
    uv run python scripts/generate_vscode_grammar.py
    ln -sfn "$(pwd)/extras/vscode-execsql" ~/.vscode/extensions/execsql-syntax
    @echo "Restart VS Code to activate the execsql extension."


# ── Documentation──────────────────────────────────────────────────────────────

# Copy CHANGELOG into docs source tree
[private]
_sync-changelog:
    cp CHANGELOG.md docs/about/change_log.md

# Build documentation
[group('docs')]
docs: _sync-changelog
    uv run zensical build

# Serve documentation locally
[group('docs')]
docs-serve: _sync-changelog
    uv run zensical serve


# ── Versioning ────────────────────────────────────────────────────────────────

# List the current version
[group('version')]
bump:
    uv run bump-my-version show-bump

# Bump patch version (e.g. 1.2.3 → 1.2.4)
[group('version')]
bump-patch:
    uv run bump-my-version bump patch

# Bump minor version (e.g. 1.2.3 → 1.3.0)
[group('version')]
bump-minor:
    uv run bump-my-version bump minor

# Bump major version (e.g. 1.2.3 → 2.0.0)
[group('version')]
bump-major:
    uv run bump-my-version bump major
