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

# Lint, type-check, and test
[group('quality')]
check: format lint typecheck test

# Run linter
[group('quality')]
lint:
    uv run ruff check .

# Run formatter
[group('quality')]
format:
    uv run ruff format .

# Run mypy type checker
[group('quality')]
typecheck:
    uv run mypy src/execsql/

# Run pre-commit hooks on all files
[group('quality')]
pre-commit:
    uv run pre-commit run --all-files

# Run tests
[group('quality')]
test *ARGS:
    uv run tox -e py -- {{ ARGS }}

# Run tests across all supported Python versions. The versions run at once, so
# each gets two pytest workers instead of one per CPU.
[group('quality')]
test-all:
    uv run tox run-parallel -- -n 2

# Run tests with coverage report printed to terminal
[group('quality')]
coverage:
    uv run pytest --cov-report=term-missing

# Run the templates/ tests against throwaway database containers, started if
# needed: PostgreSQL, MySQL and MariaDB always; SQL Server only when an ODBC
# driver for it is installed (the tests skip it otherwise). The containers are
# named execsql-templates-* and published on 5544x, so no other database on the
# machine is touched. Remove them with `just test-templates-down`.
[group('quality')]
test-templates *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    start() {  # name, port, image, container port, docker run args...
        local name="execsql-templates-$1" port=$2 image=$3 inner=$4; shift 4
        if [ -z "$(docker ps -q -f "name=^${name}$")" ]; then
            docker rm -f "$name" > /dev/null 2>&1 || true
            docker run -d --name "$name" -p "127.0.0.1:${port}:${inner}" "$@" "$image" > /dev/null
            echo "started $name on 127.0.0.1:$port"
        fi
    }
    start postgres 55440 postgres:17 5432 -e POSTGRES_USER=execsql -e POSTGRES_PASSWORD=execsql -e POSTGRES_DB=execsql_test
    start mysql 55441 mysql:8 3306 -e MYSQL_ROOT_PASSWORD=root
    start mariadb 55442 mariadb:11 3306 -e MARIADB_ROOT_PASSWORD=root
    sqlserver=""
    if uv run python -c "import pyodbc, sys; sys.exit(not any('SQL Server' in d for d in pyodbc.drivers()))" 2> /dev/null; then
        # An x86 image: on Apple Silicon, Docker Desktop needs Rosetta emulation
        # (Settings > General, Apple Virtualization framework); QEMU crashes it.
        start sqlserver 55443 mcr.microsoft.com/mssql/server:2022-latest 1433 \
            --platform linux/amd64 -e ACCEPT_EULA=Y -e "MSSQL_SA_PASSWORD=ExecSql_Test123!"
        sqlserver=yes
    fi
    # Homebrew's ODBC Driver 18 loads OpenSSL from /opt/homebrew/opt/openssl,
    # which Homebrew now points at OpenSSL 4; the driver needs 3. Only the
    # processes started here see this.
    if [ -d /opt/homebrew/opt/openssl@3/lib ]; then
        export DYLD_LIBRARY_PATH="/opt/homebrew/opt/openssl@3/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
    fi
    export EXECSQL_PG_HOST=127.0.0.1 EXECSQL_PG_PORT=55440
    export EXECSQL_MYSQL_HOST=127.0.0.1 EXECSQL_MYSQL_PORT=55441
    export EXECSQL_MARIADB_HOST=127.0.0.1 EXECSQL_MARIADB_PORT=55442
    export EXECSQL_MSSQL_HOST=127.0.0.1 EXECSQL_MSSQL_PORT=55443
    echo "waiting for the servers to accept logins..."
    for _ in $(seq 1 90); do
        if docker exec execsql-templates-postgres pg_isready -q -U execsql 2> /dev/null \
            && docker exec execsql-templates-mysql mysqladmin ping -uroot -proot --silent 2> /dev/null \
            && docker exec execsql-templates-mariadb healthcheck.sh --connect 2> /dev/null \
            && { [ -z "$sqlserver" ] || docker exec execsql-templates-sqlserver /opt/mssql-tools18/bin/sqlcmd \
                -S localhost -U sa -P 'ExecSql_Test123!' -No -Q 'select 1' > /dev/null 2>&1; }; then
            break
        fi
        sleep 2
    done
    # The venv's Python directly: `uv run` drops DYLD_LIBRARY_PATH. The venv
    # needs the driver extras (`uv sync --all-extras`).
    .venv/bin/python -m pytest tests/templates --no-cov -q {{ ARGS }}

# Remove the containers `just test-templates` started
[group('quality')]
test-templates-down:
    @docker rm -f execsql-templates-postgres execsql-templates-mysql execsql-templates-mariadb execsql-templates-sqlserver > /dev/null 2>&1 || true
    @echo "removed the execsql-templates-* containers"

# Run the formatter corpus checks over every .sql file in the repo
[group('quality')]
corpus:
    uv run pytest tests/test_format.py -k corpus --no-cov -q

# Run the corpus checks over an external library of real SQL as well.
# CORPUS must be a read-only copy — never the original library.
# Refresh one with:
#   rsync -a --delete --include='*/' --include='*.sql' --exclude='*' \
#       <library>/ ~/.cache/execsql-format-corpus/
[group('quality')]
corpus-external CORPUS='~/.cache/execsql-format-corpus':
    EXECSQL_FORMAT_CORPUS={{ CORPUS }} uv run pytest tests/test_format.py -k corpus --no-cov -q

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
    cd extras/vscode-execsql && npm ci --ignore-scripts --no-audit --no-fund
    ln -sfn "$(pwd)/extras/vscode-execsql" ~/.vscode/extensions/execsql-syntax
    @echo "Restart VS Code to activate the execsql extension."

# Build the VS Code extension into a .vsix (needs Node.js; vsce comes from package-lock.json)
package-vscode:
    uv run python scripts/generate_vscode_grammar.py
    cd extras/vscode-execsql && npm ci --ignore-scripts --no-audit --no-fund
    cd extras/vscode-execsql && ./node_modules/.bin/vsce package --out execsql-syntax.vsix
    @echo "Built extras/vscode-execsql/execsql-syntax.vsix — install with:"
    @echo "  code --install-extension extras/vscode-execsql/execsql-syntax.vsix"


# ── Documentation──────────────────────────────────────────────────────────────

# Copy CHANGELOG into docs source tree
[private]
_sync-changelog:
    cp CHANGELOG.md docs/about/change_log.md

# Build documentation; a warning (such as a link to a missing #anchor) fails it
[group('docs')]
docs: _sync-changelog
    uv run zensical build --strict

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

# Bump to an explicit pre-release version (e.g. 2.0.0a1, 2.0.0b1, 2.0.0rc1)
[group('version')]
bump-pre version:
    uv run bump-my-version bump --new-version {{ version }} patch
