# Release Process

This page is the release checklist for `execsql2`; CONTRIBUTING and the
project notes link here rather than repeating it. The release is fully
automated: the version-bump commit and its tag are the trigger, and
`.github/workflows/ci-cd.yml` does the rest.

## Prerequisites

- Working tree clean on `main` (or whatever branch you are releasing
    from).
- Local tests green: `just check`.
- `CHANGELOG.md` `[Unreleased]` section reviewed and tightened to the
    Keep-a-Changelog voice rule (one idea per bullet, user-facing tone,
    no internal-only refactor notes). It becomes the GitHub Release text
    word for word, so read it as the release announcement.
- `docs/about/divergence.md` updated for any new feature, changed
    behavior, security fix, or removed functionality that diverges from
    upstream `execsql` v1.130.1.
- You have `gh` authenticated against the `geocoug/execsql` repository
    (`gh auth status` shows you're logged in).

## Choose the bump level

| Recipe                   | Use when                                                                                                                                                                                |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `just bump-patch`        | Bug fixes, doc fixes, dependency hygiene, anything user-invisible. Most releases.                                                                                                       |
| `just bump-minor`        | New features, new metacommands / flags / formats, backwards-compatible behavior changes.                                                                                                |
| `just bump-major`        | Breaking changes. Public-API signature changes, removed metacommands, dropped Python versions.                                                                                          |
| `just bump-pre 2.20.0a1` | Cut an explicit pre-release (alpha / beta / rc). The tag publishes to PyPI like any release; pip and uv skip it unless `--pre` is passed, and the GitHub Release is marked pre-release. |

What each one does (per `[tool.bumpversion]` in `pyproject.toml`):

1. Rewrites the version in `pyproject.toml`, `CHANGELOG.md` (turns
    `[Unreleased]` into the new dated section), `README.md`'s pre-commit
    `rev:` snippet, `docs/guides/formatter.md`'s pre-commit `rev:`
    snippet, and the VS Code extension's version in
    `extras/vscode-execsql/package.json` and `package-lock.json` (a
    pre-release in VS Code's form: `2.31.0rc1` is `2.31.0-rc.1`).
1. Runs `uv lock` (refreshes the lockfile against the new version) and
    `git add uv.lock`.
1. Creates a commit `Bump version: 2.X.Y → 2.X.Y+1`.
1. Creates an annotated tag `v2.X.Y+1` on that commit.

The working tree is now clean.

## Push and watch CI

```bash
git push && git push --tags     # commit AND tag, both required
gh run list --limit 1            # confirm the workflow fired
gh run watch <RUN_ID> --exit-status   # block until it finishes (red on failure)
```

`gh run watch --exit-status` returns non-zero if any job in the workflow
fails. Stay on the command until it exits.

### What runs on a tag push

Every push to `main`, every pull request and every `v*.*.*` tag runs the
checks; only a tag runs the last two jobs.

| Job                                     | Gates `build`? | Purpose                                                                                                         |
| --------------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------- |
| `lint`                                  | yes            | `ruff check` and `ruff format --check`, at the ruff `rev` in `.pre-commit-config.yaml`                          |
| `typecheck`                             | yes            | `mypy src/execsql/` against the packages in `uv.lock` (a stale lock fails)                                      |
| `pre-commit`                            | yes            | every pre-commit hook on every file (mypy is left to `typecheck`)                                               |
| `typer-floor`                           | yes            | the CLI tests against the lowest Typer `pyproject.toml` allows                                                  |
| `docs`                                  | yes            | `zensical build --strict`: a broken link or anchor fails it                                                     |
| `tests` (`test-<os>-py<version>`)       | yes            | Python 3.10–3.14 on Ubuntu, macOS and Windows                                                                   |
| `integration-tests` (`tier1-live-db-…`) | yes            | PostgreSQL, MySQL, MariaDB and SQL Server containers (including the `templates/` tests); 86% coverage floor     |
| `vscode-extension`                      | yes            | packages `extras/vscode-execsql` as `execsql-syntax.vsix`                                                       |
| `access-tests-windows`                  | no             | the real MS Access driver on Windows; informational                                                             |
| `build`                                 | —              | on a tag: checks the tag equals `project.version` and that `CHANGELOG.md` has its section; builds sdist + wheel |
| `publish`                               | tag only       | uploads to PyPI by OIDC trusted publishing                                                                      |
| `generate-release`                      | tag only       | creates the GitHub Release: body = the version's `CHANGELOG.md` section; attaches sdist, wheel and `.vsix`      |

They run in the order `build → publish → generate-release`, so no GitHub
Release goes out unless the PyPI upload succeeded. A version already on
PyPI fails the upload rather than being skipped.

### Release notes

The Release text is the `## [X.Y.Z]` section of `CHANGELOG.md`, printed by
`python scripts/release_notes.py X.Y.Z` (try it before tagging). GitHub's
generated list of commits is not used: the CHANGELOG says what changed for
the person upgrading.

### Pre-releases

`just bump-pre 2.31.0rc1` (or `a1`, `b1`) cuts a [PEP 440](https://peps.python.org/pep-0440/)
pre-release. It publishes to PyPI like any release; `pip` and `uv` skip it
unless `--pre` is passed, and the GitHub Release is marked pre-release.
Promote it with the final version string (`just bump-pre 2.31.0`); `just bump-patch` from `2.31.0rc1` would skip to `2.31.1`. Preview first:
`uv run bump-my-version bump --new-version 2.31.0rc1 patch --dry-run -v`.

### PyPI trusted publishing

`publish` needs no token. PyPI's trusted publisher for `execsql2` is:
owner `geocoug`, repository `execsql`, workflow `ci-cd.yml`, environment
`pypi`.

## When something goes wrong

### A test failed after the tag push (PyPI not yet published)

The `build` job won't run if any earlier job is red, so `publish` won't
fire. Fix:

1. Identify the failure: `gh run view <RUN_ID> --log-failed`.
1. Fix it on `main`.
1. Move the unpublished version's `CHANGELOG.md` section back under
    `[Unreleased]` (drop its heading and separator), so the next release's
    notes carry those changes.
1. Re-bump: `just bump-patch` (this creates a *new* tag at the next patch
    level; do NOT delete the old tag and retag the new commit — once a
    tag has been visible publicly, treat it as immutable).
1. Push and re-watch.

### `build` failed: tag does not match the package version

The tag name (minus `v`) must equal `project.version` in `pyproject.toml`
on the tagged commit. A mismatch means the tag was made by hand or points
at the wrong commit; `just bump-*` always creates matching pairs. Nothing
was published. Bump again from `main` with `just bump-patch` rather than
moving the tag.

### `publish` failed but the tag is live

PyPI does not have the version, and the GitHub release was not created
(it waits for `publish`). Fix:

1. `gh run view <RUN_ID> --log-failed` and read the publish job log.
1. Common cause: OIDC trust-policy drift, transient PyPI 5xx, or a name
    collision with the pre-release tag.
1. If transient, or once a cause outside the repository is fixed (the
    trusted-publisher settings on PyPI): `gh run rerun --failed <RUN_ID>`
    and watch again. This re-runs `publish` and `generate-release` after it.
1. If the fix needs a code change: fix it on `main` and re-bump. The tag
    is the source of truth for the version; don't reassign it.

### `build` failed: CHANGELOG.md has no section for the tag

Nothing was published. The bump turns `[Unreleased]` into the dated
section, so this means the section is empty or the tag was made by hand.
Add the notes on `main` and bump again.

### The Release text needs a correction

Fix `CHANGELOG.md` on `main`, then replace the published text with it:
`python scripts/release_notes.py 2.X.Y > notes.md && gh release edit v2.X.Y --notes-file notes.md`.

### `uv lock` produced an unrelated diff

`bump-my-version` runs `uv lock` as a pre-commit hook to refresh the
lockfile. If unrelated packages also moved (because they updated since
your last sync), that's expected — `uv` is doing the right thing. If the
diff is large enough to be worrying, abort the bump (`git restore .`),
run `uv lock` manually, review, commit the lock update on its own, then
re-bump.

## Post-release sanity check

After `gh run watch` exits green:

- `pip install execsql2==2.X.Y` in a throwaway venv — confirms the
    wheel landed on PyPI.
- Browse the new GitHub release page; check the CHANGELOG section
    matches what's on `main` and that `execsql-syntax.vsix` is attached.
- `git pull` locally to retrieve the bump commit (you already had it
    locally if you bumped yourself, but other contributors will sync).
