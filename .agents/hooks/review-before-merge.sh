#!/bin/sh
# PreToolUse hook (Bash, Write, Edit): runs review-before-merge.py, which blocks `gh pr merge` until the PR has been
# reviewed; see there. It fails closed: without python3, or if the script fails, a command that mentions a merge or
# the review records is blocked, and anything else runs.
input=$(cat)
if command -v python3 >/dev/null 2>&1; then
  printf '%s' "$input" | python3 "$(dirname "$0")/review-before-merge.py"
  rc=$?
  [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ] && exit "$rc"
  why="the review hook failed (exit $rc)"
else
  why="python3 isn't available, so the review hook can't check it"
fi
case "$input" in
  *merge* | *claude-review*)
    echo "Blocked: $why. Fix .agents/hooks/review-before-merge.py, or ask the user to run the command." >&2
    exit 2
    ;;
esac
exit 0
