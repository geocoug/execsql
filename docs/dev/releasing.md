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

<a id="a-test-failed-after-the-tag-push-pypi-not-yet-published"></a>

### A test failed after the tag push

Check the individual `build`, `publish` and `generate-release` outcomes before choosing recovery:

```sh
gh run view <RUN_ID>
gh run view <RUN_ID> --log-failed
gh release view <TAG> --json tagName,assets,url
```

Only jobs in `build.needs` gate the build. The conditional Windows Access job is not in that list: its failure can coexist with a successfully published version. A red workflow or a nonzero `gh run watch` result is not proof that PyPI has no distribution.

If publication was attempted, inspect that version's PyPI files as well as the GitHub release assets. A failed upload can leave some distributions published. Treat any publicly visible version/tag as immutable.

Once you have verified that the version was **not published**, fix the gating failure on `main`, move that unpublished version's notes back under `[Unreleased]` (remove its empty dated heading and separator), and bump a new patch version. Push and watch the new tag. Do not delete/reassign the old public tag.

If the version **was published**, keep its dated changelog section. Fix the problem and release a new version, or use the artifact/release-only recovery below when no package change is needed.

### `build` failed: tag does not match the package version

The tag name (minus `v`) must equal `project.version` in `pyproject.toml`
on the tagged commit. A mismatch means the tag was made by hand or points
at the wrong commit; `just bump-*` always creates matching pairs. Nothing
was published. Bump again from `main` with `just bump-patch` rather than
moving the tag.

### `publish` failed but the tag is live

Do not infer package absence from a failed publish job. Read its log and inspect the version's actual PyPI files first; a partial upload or a failed retry can leave a published distribution. Inspect `generate-release` and GitHub assets separately.

1. Read `gh run view <RUN_ID> --log-failed` and identify the failure and remote artifact state.
1. For an external/transient failure with no uploaded distributions, fix the trust/availability issue and use `gh run rerun --failed <RUN_ID>`, then watch it.
1. If any distributions already exist, do not blindly re-upload the same version or move its changelog notes. Resolve missing release assets using the state-specific procedure below, or make a code fix on `main` and bump a new version.
1. Preserve the public tag in every case; never reassign it to another commit.

### `build` failed: CHANGELOG.md has no section for the tag

Nothing was published. The bump turns `[Unreleased]` into the dated
section, so this means the section is empty or the tag was made by hand.
Add the notes on `main` and bump again.

### GitHub release generation failed or assets are missing

When PyPI already has the version, recover the GitHub release without re-uploading the package or changing its tag. First check that `publish` succeeded and the original run still has the wheel, sdist and `vscode-extension` artifacts.

Find the **Generate GitHub Release** job's `databaseId` and rerun that job, rather than the publish job or the whole workflow:

```sh
gh run view <RUN_ID> --json jobs --jq '.jobs[] | {name, databaseId, conclusion}'
gh run rerun <RUN_ID> --job <GENERATE_RELEASE_DATABASE_ID>
gh run watch <RUN_ID> --exit-status
gh release view <TAG> --json tagName,assets,url
```

Use the `databaseId` from the JSON, not the number in a browser job URL. Inspect the individual job and remote release again even if an unrelated job leaves the run red.

If the job cannot be rerun but its original artifacts remain available, use a fresh local `recovery/` directory:

```sh
gh run download <RUN_ID> --name execsql --dir recovery/dist
gh run download <RUN_ID> --name vscode-extension --dir recovery/dist
python scripts/release_notes.py <TAG> > recovery/release-notes.md
```

Run the notes command from a checkout whose CHANGELOG has the reviewed section for that exact tag. Check the downloaded wheel/sdist versions and the VSIX version against the tag before attaching anything. If the release does not exist, create it from the existing tag:

```sh
gh release create <TAG> --verify-tag --notes-file recovery/release-notes.md recovery/dist/*
```

For an alpha, beta or release-candidate tag, add `--prerelease`. If a release already exists, upload only the missing original assets with `gh release upload <TAG> recovery/dist/<MISSING_ASSET>`; do not overwrite existing assets blindly. Confirm that the wheel, sdist and `execsql-syntax.vsix` are all attached. These commands do not publish to PyPI.

If the original artifacts have expired or do not match the tag, stop this recovery path. Do not substitute a new local build for the published distributions; recover the exact originals from a trusted source or publish a new version using the normal checklist.

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
