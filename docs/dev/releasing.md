# Release Process

This page documents the release workflow for `execsql2`. The release is
fully automated — the version-bump commit (plus its companion tag) is
the trigger; `.github/workflows/ci-cd.yml` does the rest.

## Prerequisites

- Working tree clean on `main` (or whatever branch you are releasing
    from).
- Local tests green: `just check`.
- `CHANGELOG.md` `[Unreleased]` section reviewed and tightened to the
    Keep-a-Changelog voice rule (one idea per bullet, user-facing tone,
    no internal-only refactor notes). See `CLAUDE.md` for the full rule.
- `docs/about/divergence.md` updated for any new feature, changed
    behavior, security fix, or removed functionality that diverges from
    upstream `execsql` v1.130.1.
- You have `gh` authenticated against the `geocoug/execsql` repository
    (`gh auth status` shows you're logged in).

## Choose the bump level

| Recipe                   | Use when                                                                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `just bump-patch`        | Bug fixes, doc fixes, dependency hygiene, anything user-invisible. Most releases.                                                              |
| `just bump-minor`        | New features, new metacommands / flags / formats, backwards-compatible behavior changes.                                                       |
| `just bump-major`        | Breaking changes. Public-API signature changes, removed metacommands, dropped Python versions.                                                 |
| `just bump-pre 2.20.0a1` | Cut an explicit pre-release (alpha / beta / rc). Doesn't fire the publish workflow unless `--allow-dirty` and a tag-style argument trigger it. |

What each one does (per `[tool.bumpversion]` in `pyproject.toml`):

1. Rewrites the version in `pyproject.toml`, `CHANGELOG.md` (turns
    `[Unreleased]` into the new dated section), `README.md`'s pre-commit
    `rev:` snippet, and `docs/guides/formatter.md`'s pre-commit `rev:`
    snippet.
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

| Job                    | Gating?                            | Purpose                                                          |
| ---------------------- | ---------------------------------- | ---------------------------------------------------------------- |
| `lint`                 | yes                                | ruff check + ruff format check                                   |
| `tests` (matrix)       | yes                                | py3.10–3.14 × {ubuntu, macos, windows}                           |
| `integration-tests`    | yes                                | PostgreSQL, MySQL, MSSQL service containers                      |
| `access-tests-windows` | yes (when Access install succeeds) | Real Access driver on `windows-latest`                           |
| `build`                | yes                                | `python -m build` produces sdist + wheel                         |
| `publish`              | yes (tag-gated)                    | OIDC trusted-publisher PyPI upload                               |
| `generate-release`     | yes (tag-gated)                    | Creates the GitHub release with auto-extracted CHANGELOG section |

Build / publish / generate-release run only on tag refs
(`if: startsWith(github.ref, 'refs/tags/v')`), so a non-bump push to
`main` doesn't publish.

## When something goes wrong

### A test failed after the tag push (PyPI not yet published)

The `build` job won't run if any earlier job is red, so `publish` won't
fire. Fix:

1. Identify the failure: `gh run view <RUN_ID> --log-failed`.
1. Fix it on `main`.
1. Re-bump: `just bump-patch` (this creates a *new* tag at the next patch
    level; do NOT delete the old tag and retag the new commit — once a
    tag has been visible publicly, treat it as immutable).
1. Push and re-watch.

### `publish` failed but the tag is live

This is the worst case: PyPI is unaware, GitHub thinks the release
happened. Fix:

1. `gh run view <RUN_ID> --log-failed` and read the publish job log.
1. Common cause: OIDC trust-policy drift, transient PyPI 5xx, or a name
    collision with the pre-release tag.
1. If transient: `gh run rerun --failed <RUN_ID>` and watch again.
1. If structural (trust policy changed, package name conflict): delete
    the GitHub release **but not the tag**, fix the cause, and re-trigger
    the workflow manually via the Actions UI. The tag is the source of
    truth for the version; don't reassign it.

### `generate-release` succeeded but the CHANGELOG section is wrong

The release-notes step in the workflow extracts the CHANGELOG section
matching `## [<version>]`. Edit the GitHub release body directly through
the UI or `gh release edit v2.X.Y --notes-file <path>`. Then fix the
voice in `CHANGELOG.md` on `main` so future releases don't repeat the
mistake.

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
    matches what's on `main`.
- `git pull` locally to retrieve the bump commit (you already had it
    locally if you bumped yourself, but other contributors will sync).
