#!/usr/bin/env python3
"""PreToolUse hook: no pull request merges until a fresh-context sub-agent has reviewed it.

Run by review-before-merge.sh for the Bash, Write and Edit tools, with the tool call's JSON on stdin. Exit 0 lets the
call run; exit 2 blocks it and shows stderr to the agent. Codex apply_patch is also supported.

For `gh pr merge` (and `gh api .../pulls/<n>/merge`): the merge is blocked until a sub-agent has followed the shared merge-review skill on
the PR and written `<git common dir>/claude-review/pr-<n>/<head sha>.md`, whose first line is exactly `Status: clean`
or `Status: findings`. Round 1 reviews the whole PR (the diff from the merge base to the head, pinned to that head);
when fixes are pushed, rounds 2 and 3 review only the fixes. A head whose diff is unchanged (a stacked PR rebased onto
its base) counts as already reviewed. A merge passes when the head's report is clean, or has findings and fewer than
3 rounds have run (the agent triaged them), and the command pins that head with `--match-head-commit <sha>`, so nothing
pushed after the review can merge. After round 3 with findings, only the user can let it through, by writing
`<head sha>.approved` themselves; this hook blocks agents from writing approvals or the round count.

Only real merge commands count: text in quotes, here-document bodies and comments don't. Commands it can't read, a
merge whose PR it can't name, and any failure of its own block the merge rather than let it through.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from hook_paths import edited_paths, project_dir

MAX_ROUNDS = 3
STALE_DAYS = 30
CHECK_BUDGET = 90
SUBPROCESS_TIMEOUT = 10
_deadline = None


def block(msg: str) -> None:
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(2)


def run(args, cwd, stdin=None):
    # Share one budget across all calls; individual timeouts alone can exceed the outer 120 seconds.
    remaining = CHECK_BUDGET if _deadline is None else _deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("merge review exceeded its 90-second subprocess budget")
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        input=stdin,
        timeout=min(SUBPROCESS_TIMEOUT, remaining),
    )


# ---------------------------------------------------------------------------------------------------------------------
# Reading the command


def flatten(text: str) -> str:
    """The command with here-document bodies and comments taken out and each unquoted newline turned into `;`.
    Quotes are tracked across lines, so a quoted message that spans lines stays one word."""
    out, pending, i, n, q = [], [], 0, len(text), None
    while i < n:
        c = text[i]
        if q:
            out.append(c)
            if q == "'" and c == "'":
                q = None
            elif q == '"':
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                if c == '"':
                    q = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            if text[i + 1] == "\n":  # a line continuation
                i += 2
                continue
            out += [c, text[i + 1]]
            i += 2
            continue
        if c in "'\"":
            q = c
            out.append(c)
            i += 1
            continue
        if c == "#" and (i == 0 or text[i - 1] in " \t\n;&|()"):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("<<<", i):  # a here-string: no body to skip
            out.append("<<<")
            i += 3
            continue
        if text.startswith("$((", i):  # arithmetic, where << is a shift
            j = text.find("))", i)
            j = n if j < 0 else j + 2
            out.append(text[i:j])
            i = j
            continue
        if text.startswith("<<", i):
            m = re.match(r"<<(-?)[ \t]*\\?(['\"]?)([A-Za-z_][\w.-]*)\2", text[i:])
            if m:
                pending.append((m.group(3), m.group(1) == "-", bool(m.group(2) or "\\" in m.group(0))))
                out.append(" ")
                i += m.end()
                continue
        if c == "\n":
            out.append(" ; ")
            i += 1
            for delim, tabs, quoted in pending:
                while i < n:
                    j = text.find("\n", i)
                    line = text[i:] if j < 0 else text[i:j]
                    i = n if j < 0 else j + 1
                    if (line.lstrip("\t") if tabs else line) == delim:
                        break
                    if not quoted and re.search(r"\$\(|`", line):
                        raise ValueError(
                            "command substitutions in expandable heredocs cannot be checked; "
                            "quote the delimiter for literal text, or run the command separately",
                        )
            pending = []
            continue
        out.append(c)
        i += 1
    return "".join(out)


def substitutions(text: str) -> list:
    """The insides of `$(...)` and backticks outside single quotes: each runs as a command of its own."""
    found, i, n, q = [], 0, len(text), None
    while i < n:
        c = text[i]
        if q == "'":
            if c == "'":
                q = None
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if c == "'" and q is None:
            q = "'"
        elif c == '"':
            q = None if q == '"' else '"'
        elif text.startswith("$(", i) and not text.startswith("$((", i):
            depth, j = 1, i + 2
            while j < n and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            found.append(text[i + 2 : j - 1])
            i = j
            continue
        elif c == "`":
            j = text.find("`", i + 1)
            j = n if j < 0 else j
            found.append(text[i + 1 : j])
            i = j + 1
            continue
        i += 1
    return found


OPS = set(";&|()")


def simple_commands(text: str) -> list:
    """Every simple command in `text` as a list of words, including those in command substitutions and in the
    script of `bash -c`, `sh -c` and `eval`. Raises ValueError when the quoting doesn't close."""
    flat = flatten(text)
    found = []
    for sub in substitutions(flat):
        found += simple_commands(sub)
    cmds = []
    lex = shlex.shlex(flat, posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    lex.commenters = ""
    cur = []
    for tok in lex:
        if tok and set(tok) <= OPS:
            if cur:
                cmds.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        cmds.append(cur)
    out = found
    for words in cmds:
        words, via_xargs = strip_prefix(words)
        if not words:
            continue
        base = os.path.basename(words[0])
        if base in ("bash", "sh", "zsh", "dash", "ksh"):
            for k, w in enumerate(words[1:], 1):
                if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", w) and k + 1 < len(words):
                    out += simple_commands(words[k + 1])
                    break
            continue
        if base == "eval":
            out += simple_commands(" ".join(words[1:]))
            continue
        out.append((words, via_xargs))
    return out


KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "time", "{", "}", "!", "function", "in"}
# Commands that run another command, with their options that take a value.
WRAPPERS = {
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "command": set(),
    "builtin": set(),
    "exec": {"-a"},
    "nohup": set(),
    "time": set(),
    "nice": {"-n", "--adjustment"},
    "sudo": {"-u", "-g", "-h", "-p", "-U", "-C", "-D", "-r", "-t", "-T"},
    "doas": {"-u", "-C"},
    "timeout": {"-k", "--kill-after", "-s", "--signal"},
    "xargs": {
        "-n",
        "-I",
        "-i",
        "-L",
        "-l",
        "-P",
        "-d",
        "-E",
        "-e",
        "-s",
        "-a",
        "-J",
        "-R",
        "--max-args",
        "--replace",
        "--max-lines",
        "--max-procs",
        "--delimiter",
        "--eof",
        "--max-chars",
        "--arg-file",
    },
    "stdbuf": {"-i", "-o", "-e"},
    "caffeinate": {"-t", "-w"},
    "chronic": set(),
}


def strip_prefix(words: list):
    """The words of the command a simple command runs, past keywords, variable assignments and wrappers such as
    `env`, `timeout 60` or `xargs -n1`; and whether `xargs` adds arguments the hook can't see."""
    i, via_xargs = 0, False
    while i < len(words):
        w = words[i]
        if w in KEYWORDS or re.match(r"^[A-Za-z_]\w*=", w):
            i += 1
            continue
        base = os.path.basename(w)
        if base not in WRAPPERS:
            break
        via_xargs |= base == "xargs"
        takes, i = WRAPPERS[base], i + 1
        while i < len(words) and words[i].startswith("-") and words[i] != "-":
            flag = words[i]
            i += 1
            if flag == "--":
                break
            if flag in takes:
                i += 1
        if base == "timeout" and i < len(words):
            i += 1  # the duration
    return words[i:], via_xargs


MERGE_VALUE_FLAGS = {
    "-t",
    "--subject",
    "-b",
    "--body",
    "-F",
    "--body-file",
    "--match-head-commit",
    "-A",
    "--author-email",
    "-R",
    "--repo",
}


def merge_of(words: list, via_xargs: bool):
    """What a simple command merges: None when it merges nothing, else a dict with the PR as named ("sel", None for
    the current branch's), the `--match-head-commit` value, the `--repo` value, and whether the PR can be told at all
    ("unknown", for `gh api`, xargs and variables)."""
    if not words:
        return None
    if os.path.basename(words[0]) != "gh":
        # A merge run through a command the hook doesn't unwrap (`find -exec`, `watch`, a function): it can't be
        # checked, so it can't run. Commands that only print or search text are left alone.
        if os.path.basename(words[0]) not in (
            "echo",
            "printf",
            "grep",
            "rg",
            "git",
            "cat",
            "less",
            "head",
            "tail",
        ) and any(a == "pr" and b == "merge" for a, b in zip(words, words[1:])):
            return {"sel": None, "match": None, "repo": None, "unknown": True}
        return None
    repo, i = None, 1

    def flags(i, repo):
        while i < len(words) and words[i].startswith("-"):
            w = words[i]
            if w in ("-R", "--repo"):
                repo, i = (words[i + 1] if i + 1 < len(words) else None), i + 2
            elif w.startswith("--repo="):
                repo, i = w.split("=", 1)[1], i + 1
            elif w.startswith("-R") and len(w) > 2:
                repo, i = w[2:], i + 1
            else:
                i += 1
        return i, repo

    i, repo = flags(i, repo)
    if i < len(words) and words[i] == "api":
        rest = " ".join(words[i + 1 :])
        if re.search(r"pulls/[^/\s]+/merge\b|mergePullRequest|enablePullRequestAutoMerge", rest):
            return {"api": True}
        return None
    if i >= len(words) or words[i] != "pr":
        return None
    i, repo = flags(i + 1, repo)
    if i >= len(words) or words[i] != "merge":
        return None
    args = words[i + 1 :]
    sel, match, j, only_positional = None, None, 0, False
    while j < len(args):
        a = args[j]
        if only_positional or not a.startswith("-") or a == "-":
            sel = a if sel is None else sel
            j += 1
            continue
        if a == "--":
            only_positional, j = True, j + 1
            continue
        if a in ("-h", "--help", "--disable-auto"):  # as a flag, not as another flag's value (`-b -h`)
            return None
        name, eq, val = a.partition("=")
        if eq and name.startswith("--"):
            match = val if name == "--match-head-commit" else match
            repo = val if name == "--repo" else repo
            j += 1
            continue
        if a in MERGE_VALUE_FLAGS:
            val = args[j + 1] if j + 1 < len(args) else None
            match = val if a == "--match-head-commit" else match
            repo = val if a in ("-R", "--repo") else repo
            j += 2
            continue
        if re.match(r"^-[tbFAR].", a):  # a short flag with its value attached: -b"text"
            repo = a[2:] if a[1] == "R" else repo
        j += 1
    unknown = via_xargs or (sel is not None and re.search(r"[$`*?]", sel) is not None)
    return {"sel": sel, "match": match, "repo": repo, "unknown": unknown}


# ---------------------------------------------------------------------------------------------------------------------
# Guards on the hook's own records


WRITES = re.compile(
    r"\b(tee|cp|mv|rm|rmdir|unlink|touch|truncate|install|ln|dd|rsync|ditto|find|perl|ruby|node)\b|"
    r"\bsed\s+(-\w*\s+)*-i|\bpython3?\b(?!\s+-m\s+json\.tool)",
)


def guard_records(tool: str, ti: dict, payload: dict) -> None:
    """Only the user approves a merge or resets the round count: block agents writing `.approved` files or `state`."""
    msg = (
        "Blocked: only the user can approve a merge or reset its review rounds. Ask them to type the command "
        "themselves in their terminal (or with `!` in Claude Code)."
    )
    if tool == "Bash":
        cmd = ti.get("command") or ""
        cwd = Path(payload.get("cwd") or Path.cwd()).resolve()
        # Here-document bodies are data; a redirect into one of the files stays outside them. Each command is judged on
        # its own, so reading the state and writing elsewhere in the same line isn't caught.
        for seg in re.split(r"&&|\|\||(?<!>)\||[;&\n]", flatten(cmd)):  # `>|` is a redirect, not a pipe
            # A relative write from inside the records must not evade the literal-path checks below.
            # Keep report-writing shell commands outside this directory, using absolute .md paths.
            if "claude-review" in cwd.parts and (">" in seg or WRITES.search(seg)):
                block(msg + " Run report-writing shell commands from the repository root with absolute .md paths.")
            if re.match(r"\s*cd\s", seg):
                words = shlex.split(seg)
                args = words[1:]
                if args[:1] == ["--"]:
                    args = args[1:]
                if len(args) == 1:
                    cwd = (cwd / args[0]).resolve()
            # Any path under claude-review other than a report (.md): approvals, the state, a pr-<n> folder, the lot.
            paths = [t.strip("'\";)") for t in re.findall(r"\S*claude-review\S*", seg)]
            protected = [p for p in paths if not p.endswith(".md")]
            if re.search(r">[>|]?\s*['\"]?\S*claude-review(?!\S*\.md\b)", seg):
                block(msg)
            if protected and re.match(r"\s*(git|gh)\s", seg) is None and WRITES.search(seg):
                block(msg)
    else:
        for path in edited_paths(payload):
            # Resolve '..' and symlinks, including moves out of the review records. Reports stay writable.
            if "claude-review" in path.parts and path.suffix != ".md":
                block(msg)


# ---------------------------------------------------------------------------------------------------------------------
# The review state


def report_status(path: str):
    """'clean' or 'findings' from a report's first line; None when the report is missing or its first line is
    neither (still being written, or malformed)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            first = f.readline().rstrip("\r\n").strip()
    except OSError:
        return None
    return {"Status: clean": "clean", "Status: findings": "findings"}.get(first)


def load_state(d: str) -> dict:
    path = os.path.join(d, "state.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError) as e:
            block(
                f"Merge blocked: the review state {path} can't be read ({e}). Ask the user to look at it, or to reset "
                f"this PR's reviews in their terminal with `rm -r {shlex.quote(d)}`.",
            )
    st = {"rounds": 0, "reviewed": [], "requested": None}
    old = os.path.join(d, "state")  # the first version's format: "<done> <base> <req>\n<heads>"
    try:
        with open(old) as f:
            first, _, rest = f.read().partition("\n")
        _, _, req = (first.split() + ["-", "-", "-"])[:3]
        for h in rest.split():
            status = report_status(os.path.join(d, h + ".md"))
            if status:  # a head whose report is gone or unfinished counts as never reviewed
                st["reviewed"].append({"head": h, "base": None, "patch": None, "status": status})
        st["rounds"] = len(st["reviewed"])
        if req != "-":
            st["requested"] = {"head": req, "base": None, "patch": None}
    except OSError:
        pass
    return st


def save_state(d: str, st: dict) -> None:
    tmp = os.path.join(d, "state.json.tmp")
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, os.path.join(d, "state.json"))  # all or nothing, so a kill can't leave half a file
    try:
        os.remove(os.path.join(d, "state"))
    except OSError:
        pass


def clean_up(root: str, keep: str) -> None:
    """Forget reviews untouched for a month: whole pr-<n> folders (never `keep`, the PR being merged), and the old
    commit hook's loose files."""
    cutoff = time.time() - STALE_DAYS * 86400
    try:
        names = os.listdir(root)
    except OSError:
        return
    for name in names:
        p = os.path.join(root, name)
        try:
            if os.path.isdir(p) and name.startswith("pr-") and name != keep:
                files = [os.path.join(p, f) for f in os.listdir(p)]
                if max([os.path.getmtime(p)] + [os.path.getmtime(f) for f in files]) < cutoff:
                    for f in files:
                        os.remove(f)
                    os.rmdir(p)
            elif os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass


# ---------------------------------------------------------------------------------------------------------------------
# The merge gate

SRC = re.compile(r"^(src/execsql|tests)/")
RISKY = re.compile(
    r"^(src/execsql/(db|importers|exporters|script|metacommands)/|"
    r"src/execsql/(api|types|models|state)\.py$|tests/corpus/|\.agents/hooks/)",
)
SKILL = ".agents/skills/merge-review/SKILL.md"
RULES = (
    "Read AGENTS.md in full: check data integrity in IMPORT/EXPORT/COPY, transaction/batch and interrupt "
    "behavior, CLI/metacommand compatibility, Python 3.10 support, accepted corpus divergences, and "
    "documentation/changelog requirements. Preserve maintainer decisions and approval rules."
)


def gate(m: dict, cwd: str) -> None:
    if m.get("api"):
        block(
            "Merge blocked: merge pull requests with `gh pr merge <number>`, so the review hook can check them, not "
            "through `gh api`.",
        )
    if m["unknown"]:
        block(
            "Merge blocked: the review hook can't tell which PR this merges (it comes from xargs, a variable or a "
            "pattern). Merge one PR per command, named by its number: `gh pr merge <number> ...`.",
        )

    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd)
    if common.returncode:
        block("Merge blocked: the review hook couldn't find this repository's git folder:\n" + common.stderr)
    root = os.path.join(common.stdout.strip(), "claude-review")

    fields = "number,headRefOid,headRefName,baseRefName,state,url"
    view = run(
        ["gh", "pr", "view"]
        + ([m["sel"]] if m["sel"] else [])
        + (["-R", m["repo"]] if m["repo"] else [])
        + ["--json", fields],
        cwd,
    )
    if view.returncode:
        block(
            f"Merge blocked: the review hook couldn't look up the pull request{' ' + m['sel'] if m['sel'] else ''} "
            f"with `gh pr view`. Its error:\n{view.stderr.strip()}\nIf gh isn't signed in or is offline, fix that and "
            f"retry; otherwise name the PR by its number.",
        )
    pr = json.loads(view.stdout)
    repo_view = run(["gh", "repo", "view", "--json", "url", "-q", ".url"], cwd)
    here = repo_view.stdout.strip()
    if not here or not pr["url"].startswith(here.rstrip("/") + "/pull/"):
        block(
            f"Merge blocked: {pr['url']} isn't a pull request of this repository ({here or repo_view.stderr.strip()}), "
            f"so the review hook can't track it. Ask the user.",
        )
    if pr["state"] != "OPEN":
        sys.exit(0)  # gh refuses it anyway
    n, head, head_ref, base_ref = pr["number"], pr["headRefOid"], pr["headRefName"], pr["baseRefName"]

    d = os.path.join(root, f"pr-{n}")
    clean_up(root, keep=f"pr-{n}")
    os.makedirs(d, exist_ok=True)

    # The PR's commits and its base branch, as they are on GitHub now.
    fetch = run(
        [
            "git",
            "fetch",
            "-q",
            "origin",
            f"+refs/pull/{n}/head:refs/claude-review/pr-{n}",
            f"+refs/heads/{base_ref}:refs/remotes/origin/{base_ref}",
        ],
        cwd,
    )
    if fetch.returncode or run(["git", "cat-file", "-e", head + "^{commit}"], cwd).returncode:
        block(
            f"Merge blocked: the review hook couldn't fetch PR #{n}'s head ({head}) and its base ({base_ref}). Its "
            f"error:\n{fetch.stderr.strip()}",
        )
    mb = run(["git", "merge-base", f"origin/{base_ref}", head], cwd)
    if mb.returncode:
        block(f"Merge blocked: PR #{n}'s head has no common history with origin/{base_ref}.")
    base = mb.stdout.strip()
    # What the merge would change in the base branch, as one patch id. It changes when the PR's base is retargeted (a
    # stacked PR pointed at main would bring its parents' commits too), and stays the same when the PR is only rebased
    # onto its base. --verbatim counts whitespace, so an indentation-only fix isn't taken for no change.
    merged = run(["git", "merge-tree", "--write-tree", f"origin/{base_ref}", head], cwd)
    tree = merged.stdout.split()[0] if merged.returncode == 0 and merged.stdout.split() else None
    diff = run(["git", "diff", f"origin/{base_ref}", tree] if tree else ["git", "diff", base, head], cwd)
    if diff.returncode:
        block(f"Merge blocked: the review hook couldn't diff PR #{n}. Its error:\n{diff.stderr.strip()}")
    patch_result = run(["git", "patch-id", "--verbatim"], cwd, stdin=diff.stdout)
    if patch_result.returncode:
        block("Merge blocked: the review hook couldn't compute patch identity:\n" + patch_result.stderr)
    patch = patch_result.stdout.split()[:1]
    patch = patch[0] if patch else "empty"

    st = load_state(d)
    req = st.get("requested")
    if req:
        req_path = os.path.join(d, req.get("report") or req["head"] + ".md")
        status = report_status(req_path)
        if status:
            st["rounds"] += 1
            st["reviewed"].append(dict(req, status=status))
            st["requested"] = None
        elif os.path.exists(req_path) and req["head"] == head:
            save_state(d, st)
            block(
                f"Merge blocked: the review report {req_path} isn't finished or is malformed: its "
                f"first line must be exactly `Status: clean` or `Status: findings`. Wait for the reviewer, or have it "
                f"rewrite the report.",
            )

    # A review from before patch ids were kept was of the PR as it stands against its base now (nothing was retargeted
    # since): record that, so a later change of base shows.
    for e in st["reviewed"]:
        if e.get("patch") is None and e["head"] == head:
            e["patch"] = patch
    # Reviewed: the last review of this exact change (same head against the same base, or a rebase that left the
    # change as it was). A head reviewed against a different base needs a review of what it now brings.
    last = st["reviewed"][-1] if st["reviewed"] else None
    entry = last if last and last.get("patch") == patch else None
    if entry and entry["head"] != head:
        entry = dict(entry, head=head, base=base, carried=True)
        st["reviewed"].append(entry)
    approved = os.path.exists(os.path.join(d, head + ".approved"))
    save_state(d, st)

    if approved or (entry and (entry["status"] == "clean" or st["rounds"] < MAX_ROUNDS)):
        if m["match"] != head:
            block(
                f"Merge blocked: PR #{n}'s head {head} is reviewed{' and approved' if approved else ''}; pin it so "
                f"nothing pushed since can merge. Add `--match-head-commit {head}` to the same merge command and "
                f"retry.",
            )
        sys.exit(0)

    def reports():
        return "\n".join(f"   - {os.path.join(d, e['head'] + '.md')}" for e in st["reviewed"] if not e.get("carried"))

    def step_back() -> str:
        return f"""Reviews that keep finding problems usually mean the approach is wrong, not the details. Step back:
   a. Read every report side by side:
{reports()}
      Look for what the findings share: the same function or area failing again, fixes that caused the next round's findings, or one design choice behind several of them.
   b. Reconsider the approach against what the PR is meant to do. Would a different or simpler design avoid that whole class of problem? Is the PR trying to do too much at once?
   c. Judge how significant the open issues are, then do one of these:
      - Minor (nothing open beyond low-severity edge cases or style, and no fix caused a new finding): fix what is clearly in scope, tell the user what was fixed, what is still open and why it is safe to leave, and ask whether to merge.
      - Significant (any high-severity finding in the last round, fixes that introduced new bugs, the same area failing in more than one round, or a better approach found in b): do not fix, merge or start a redesign. Tell the user the recurring problem, its likely cause, and two or three ways forward (keep the approach and fix what is open, change the approach, or narrow the PR), with your recommendation, then wait for their direction.
   Merge only when the user says so. You can't approve it yourself: ask them to run in their terminal, in their own words, `echo "<what they said>" > {shlex.quote(os.path.join(d, head + ".approved"))}` (that's the PR's head now; if you push again, retry the merge for the new one). If they pick a new approach, ask them to reset the rounds in their terminal with `rm -r {shlex.quote(d)}` once it's pushed, so it gets a full review from round 1."""

    if entry:  # reviewed, with findings, at the last round
        block(
            f"Merge blocked: review round {MAX_ROUNDS} of PR #{n}, the last, found problems. Do not launch another "
            f"review.\n\n{step_back()}",
        )
    rnd = st["rounds"] + 1
    if rnd > MAX_ROUNDS:
        block(
            f"Merge blocked: PR #{n} changed after review round {MAX_ROUNDS}, the last one. Do not launch another "
            f"review.\n\n{step_back()}",
        )

    last = next((e for e in reversed(st["reviewed"]) if not e.get("carried")), None) if st["reviewed"] else None
    retargeted = last is not None and last["head"] == head  # same commits, but they now bring something else
    if rnd == 1 or last is None or retargeted:
        rng = f"git diff {base} {head}"
        stats = run(["git", "diff", "--numstat", base, head], cwd)
    elif last.get("base") in (None, base):
        rng = f"git diff {last['head']} {head}"
        stats = run(["git", "diff", "--numstat", last["head"], head], cwd)
    else:  # rebased since: compare the PR's commits before and after
        rng = f"git range-diff {last['base']}..{last['head']} {base}..{head}"
        stats = run(["git", "diff", "--numstat", base, head], cwd)
    if stats.returncode:
        block("Merge blocked: the review hook could not summarize the diff:\n" + stats.stderr)
    numstat = stats.stdout
    rows = [r.split("\t") for r in numstat.splitlines() if r.count("\t") >= 2]
    src = [r for r in rows if SRC.match(r[2])]
    src_lines = sum(int(a) + int(b) for a, b, _ in src if a.isdigit() and b.isdigit())
    risky = [r[2] for r in rows if RISKY.search(r[2])]
    level = "high" if (rnd == 1 and (src_lines > 150 or len(src) > 3)) or risky else "medium"

    # A head reviewed before (against another base) gets a report of its own, so the old one isn't taken for it.
    name = head + ".md" if not os.path.exists(os.path.join(d, head + ".md")) else f"{head}-{patch[:12]}.md"
    report_path = os.path.join(d, name)
    st["requested"] = {"head": head, "base": base, "patch": patch, "report": name}
    save_state(d, st)

    report = (
        f"Write your report to {report_path} (the only file you may write) once the review is done: its first "
        f"line exactly `Status: clean` or `Status: findings`, then every finding with file:line, severity, and a "
        f"concrete failure scenario. Return the same report."
    )
    pinned = (
        f"Review only the pinned scope above, not the local working tree or upstream branch. To run tests, "
        f"use a scratch worktree at {head}; never switch the main checkout. The report is the only file you may write."
    )
    if retargeted:
        what = f"PR #{n}'s base changed since it was reviewed (review round {rnd} of {MAX_ROUNDS})"
        intent = (
            "what this PR is meant to do and why (its description, `gh pr view " + str(n) + "`, and its linked "
            "issue), and that its base branch changed since the last review, so it now brings more or other "
            "changes into its base. The earlier reports:\n" + reports()
        )
        scope = (
            f"Review pull request #{n} ({head_ref} into {base_ref}) at head {head}: `{rng}` is everything it "
            f"would merge now. Report any bug in it, including changes that came with the new base."
        )
    elif rnd == 1:
        what = f"PR #{n} has not been reviewed"
        intent = (
            "what this PR is meant to do and why (its description, `gh pr view " + str(n) + "`, and its linked "
            "issue, `gh issue view`), the approach taken, and anything deliberately left out of scope."
        )
        scope = (
            f"Review pull request #{n} ({head_ref} into {base_ref}) at head {head}: `{rng}` is the whole change. "
            f"Treat the INTENT as a claim to verify: report where the PR does not achieve it, and any bug it "
            f"introduces."
        )
    else:
        what = f"PR #{n} changed since review round {rnd - 1} (review round {rnd} of {MAX_ROUNDS}"
        what += ", the last)" if rnd == MAX_ROUNDS else ")"
        intent = (
            "what the whole PR is meant to do, then each finding from the earlier rounds and how it was fixed, or "
            "why it was left. The earlier reports:\n" + reports()
        )
        scope = (
            f"Review only the fixes since the last review: `{rng}` (the rest of the PR was already reviewed; read "
            f"`git diff {base} {head}` only for context). Report bugs these lines introduce and earlier findings "
            f"they fail to fix; do not report anything else."
        )
    lines = [
        f"Merge blocked: {what}.",
        f"Under review: {len(rows)} files; source (src/execsql, tests): {len(src)} files, {src_lines} lines "
        f"changed." + (f" High-risk paths: {' '.join(risky)}" if risky else ""),
        f"Suggested review effort: {level} (raise medium to high for subtle logic, concurrency, security or "
        f"data-handling changes; never go below the suggestion).",
        "",
        "1. Launch a NEW reviewer with fresh context using the current tool's supported delegation mechanism "
        "at the chosen effort. In Claude Code use a general-purpose agent, not fork; in Codex spawn an agent "
        "without inherited conversation. If delegation is unavailable, stop and tell the user. Its prompt must contain:",
        f"   - INTENT: {intent}",
        f"   - INSTRUCTION: \"Follow the merge-review skill ({SKILL}; read the file if the skill isn't listed). "
        f'{scope} {pinned} {RULES} Do not edit code, commit, push, merge, write approvals or comment on GitHub. {report}"',
        f"2. Wait for the sub-agent's completion notification. Do not retry the merge before it arrives; the merge goes "
        f"through only once {report_path} holds a finished report.",
    ]
    if rnd < MAX_ROUNDS:
        lines.append(f"""3. Triage each finding:
   - Fix it yourself only if it is a clear correctness bug inside this PR's scope.
   - Surface it to the user and do not merge until they answer if it is a design choice, a user-visible behavior change, outside the PR's scope, or a finding you are unsure about.
   - Tell the user which findings you fixed, which you are raising, and which you judged wrong (with the reason).
4. Commit the fixes on the PR's branch ({head_ref}) and push them, then retry the merge on its own (not in the same command as the push). A new head is blocked again for a review of just the fixes, up to {MAX_ROUNDS} rounds in all. Rebasing a stacked PR onto its base without changing it doesn't use a round.
5. Retry the merge once the review is clean or every finding is triaged, with `--match-head-commit <the reviewed head>`. Merge only on the user's word. If the user says to merge without a review, ask them to run in their terminal `echo "<what they said>" > {shlex.quote(os.path.join(d, head + ".approved"))}`; you can't write it yourself.""")
    else:
        lines.append(
            "3. This is the last review round. If it is clean, retry the merge with "
            f"`--match-head-commit {head}`. If it finds anything, do not just fix it and retry.\n" + step_back(),
        )
    block("\n".join(lines))


def main(raw: str) -> None:
    data = json.loads(raw)
    tool, ti = data.get("tool_name", "Bash"), data.get("tool_input") or {}
    global _deadline
    _deadline = time.monotonic() + CHECK_BUDGET
    guard_records(tool, ti, data)
    if tool != "Bash":
        sys.exit(0)
    cmd = ti.get("command") or ""
    if "merge" not in cmd:
        sys.exit(0)
    try:
        cmds = simple_commands(cmd)
    except ValueError as e:
        block(
            f"Merge blocked: the review hook couldn't read this command ({e}). Run the merge as a plain command of its "
            f"own: `gh pr merge <number> ...`.",
        )
    # An unquoted `$(...)` is read both on its own and in its command's words: count the same merge once.
    merges = list({json.dumps(m, sort_keys=True): m for m in (merge_of(w, x) for w, x in cmds) if m}.values())
    if not merges:
        sys.exit(0)
    if len(merges) > 1:
        block("Merge blocked: merge one PR per command, so each is checked against its own review.")
    gate(merges[0], str(project_dir(data)))


def handle(raw: str) -> None:
    """Fail closed when a sensitive tool call cannot be checked."""
    try:
        main(raw)
    except SystemExit:
        raise
    except Exception as e:  # fail closed on anything that could be a merge or touch the review records
        if "merge" not in raw and "claude-review" not in raw:
            sys.exit(0)
        block(
            f"Merge blocked: the review hook failed ({type(e).__name__}: {e}). Fix the hook in .agents/hooks or ask "
            f"the user.",
        )


if __name__ == "__main__":
    handle(sys.stdin.read())
