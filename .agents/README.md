# Shared agent setup

`AGENTS.md` holds the complete repository instructions. Codex reads it directly;
`CLAUDE.md` imports it with `@AGENTS.md`. Edit AGENTS.md when guidance changes.
The monolith map in `.agents/monolith_map.md` is reference material, loaded only
when needed. GitHub issues are the shared backlog; Claude's private persistent
memory is not copied or made available to Codex.

`.codex/config.toml` sets `project_doc_max_bytes = 262144` (256 KiB). This is a
ceiling for combined instruction files, not a target size. Project configuration
requires project trust. See the [Codex instruction documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## Skills and local adapters

Shared skills live in `.agents/skills/<name>/SKILL.md`, with `name` and
`description` frontmatter. Codex discovers that directory; Claude Code uses
`.claude/skills -> ../.agents/skills`.

- `merge-review` defines the fresh reviewer's scope, execsql checklist, and
  report contract. It can also be read directly when skill discovery is unavailable.

Personal Claude permissions and attribution stay in the ignored
`.claude/settings.local.json`. Optional Codex TOML personas in `.codex/agents/`
are local adapters, not shared skills; they are not published by this migration.
There is no tracked `.claude/agents/` or `.claude/commands/` inventory. Stage
shared files by name to avoid accidentally including local material.

## Merge review

`.agents/hooks/review-before-merge.sh` runs the Python hook beside it. Python 3,
Git, and an authenticated GitHub CLI are needed for merge checks. Claude Code
registers shell and edit tools in `.claude/settings.json`; Codex registers
`Bash` and `apply_patch` in `.codex/hooks.json`. Patches check every add, update,
move source/destination, and deletion. Relative edited paths use the payload's
session `cwd`. For repository discovery, `CLAUDE_PROJECT_DIR` takes precedence;
otherwise Git finds the root from that working directory. Codex's shell launcher
first walks up from its working directory to the nearest `.git` file or directory
to locate the shared wrapper, without running Git before the hook's timeouts apply.

The existing policy is preserved:

- Round 1 reviews the full pinned PR diff; rounds 2 and 3 review fixes. An
  unchanged patch after rebasing carries its review forward. Retargeting that
  changes the patch requires review of what the PR now brings.
- Reports start with exactly `Status: clean` or `Status: findings`. The launching
  agent triages findings. A clean report, or triaged findings before round 3,
  permits a merge pinned with `--match-head-commit <reviewed head>`.
- Findings at round 3 require the maintainer's direction and approval. Only
  the maintainer may write `.approved` files or reset round state, in their
  terminal (or with `!` in Claude Code). The agent must never do either.
- Commit, push, and merge still require the user's instruction. Passing this
  hook does not authorize them.

State remains under `<git common dir>/claude-review/pr-<number>/`: `state.json`,
reports, and head-specific `.approved` files. Legacy `state` files are read too.
Git refs retain `refs/claude-review/pr-<number>` so existing records survive.
The historical name is intentional. Worktrees share that common state.

Subprocess calls share a 90-second budget, with each call capped at 10 seconds
and root discovery capped at 5 seconds, below both registrations' 120-second
limit. Errors in sensitive operations block the tool. The wrapper also blocks
sensitive input when Python is unavailable or the Python hook crashes. These
are local execution hooks, not a server-side GitHub restriction.

## Claude automatic documentation updates

The existing `PostToolUse` agent handler remains installed in tracked
`.claude/settings.json`, extracted without personal configuration. It still
checks behavior changes and updates the affected documentation automatically;
its page paths and agent-directory skip list are current. Remove its local
duplicate when adopting the shared settings in an existing checkout.

Codex supports command and MCP handlers; its documented behavior skips `agent`
handlers. Consequently Codex has no equivalent automatic documentation handler
here. The shared docs-sync rule remains binding. Changing the automatic
behavior requires a separate proposal; a reminder is not a replacement.
See the [official hook documentation](https://learn.chatgpt.com/docs/hooks).

## Trust and verification

Start Codex interactively in this checkout, trust the project, and use `/hooks`
to review and trust the merge hook. New or changed definitions are skipped
until trusted. Do not bypass this step; a noninteractive invocation cannot
complete the interactive review for you. Claude imports are described in the
[Claude memory documentation](https://code.claude.com/docs/en/memory), and its
registrations follow the [Claude hook documentation](https://code.claude.com/docs/en/hooks).

Codex CLI 0.165.0 discovers linked-worktree hooks from the **original checkout's**
`.codex/` directory, even when instructions, skills, and project configuration
load from the worktree. If the migration exists only in a linked worktree,
`/hooks` can show zero installed hooks. Install the shared registrations in the
original checkout before reviewing them. For verification before integration,
temporarily copy only the two registration files there if neither already
exists, inspect and trust the hook yourself, then restore the original checkout
after the live check. Never overwrite existing local registrations. An empty
hook list does not verify installation.

Agent tooling stays outside the core software test suite. Check the hook
manually from the repository root without merging a PR or contacting GitHub:

```sh
# Ordinary commands pass (exit 0).
printf '%s\n' '{"tool_name":"Bash","tool_input":{"command":"git status --short"}}' |
  sh .agents/hooks/review-before-merge.sh

# Protected edits are denied (exit 2); this does not create or edit a file.
printf '%s\n' '{"tool_name":"Edit","tool_input":{"file_path":"/tmp/claude-review/pr-fixture/state.json"}}' |
  sh .agents/hooks/review-before-merge.sh
```

Use disposable fixtures for any additional checks. Never write approvals or
reset review rounds in the real repository to verify the guard.

Fresh-session checks remain interactive: in both tools, confirm the last
paragraph of AGENTS.md is available initially and `merge-review` is discovered;
verify the hook using disposable fixtures after trust, and confirm Claude's
automatic documentation handler is registered. Report checks that have not
been performed as pending.

### Verification on 2026-10-29

- Codex CLI 0.165.0 and Claude Code 2.1.308 both received the final AGENTS.md
  paragraph and discovered `merge-review` in fresh startup context. Claude's
  skill catalogue requires its Skill tool to be present; disabling every tool
  also removes that catalogue.
- Claude's automatic documentation handler remains registered exactly once.
- The maintainer reviewed and trusted the Codex hook. A fresh Codex session
  attempted one protected edit in a disposable fixture; the actual PreToolUse
  hook denied it and no fixture state file was created. No real PR merge or
  repository review-state edit was attempted.
- Disposable pre-integration checks covered both tools' registered shell
  commands from nested directories with spaces. Applicable pre-commit checks
  passed. The temporary original-checkout registrations used for the live
  check were removed; saved maintainer trust was preserved. Worktree-only
  discovery remains subject to the version-specific limitation above until
  the shared setup is installed in the original checkout.
