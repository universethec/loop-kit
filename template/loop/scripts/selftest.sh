#!/usr/bin/env bash
# Every gate's selftest in one run, plus the hooks exactly as git and Claude Code call them. A gate nobody has
# watched fail is a gate nobody should trust: each control plants a break and must see it refused.
#
#   bash loop/scripts/selftest.sh        exit 0 only when every control is green; one line per gate
#
# Gates: build_donemap (--next-agent 0/2/3, --brief), qa (promise), review_check, guard_tool, locks (incl. subject
# cap), handoff_check (dirty tree), dream (pruning + lessons), lookup, questions, index, listen. Then end to end: the commit-msg hook on a
# 101-char and a 100-char subject, the guard hook on stdin (push, a lock, a normal edit), and the briefing size.
# Planted catches go to a temp file (LOOP_CATCHES), never the project's own catch log.
# The pre-commit hook runs this whenever a file under loop/scripts/ is staged.
cd "$(dirname "$0")/../.." || exit 1
fail=0
for s in build_donemap qa review_check guard_tool locks handoff_check dream lookup roadmap questions index listen; do
  out="$(python3 -I "loop/scripts/$s.py" selftest 2>&1)"; rc=$?
  printf '%s\n' "$out" | tail -1
  if [ $rc -ne 0 ]; then printf '%s\n' "$out"; fail=1; fi
done

T="$(mktemp -d)"
export LOOP_CATCHES="$T/catches.csv"
printf '%0101d\n' 0 > "$T/msg"
if bash .claude/githooks/commit-msg "$T/msg" >/dev/null 2>&1; then echo "BAD commit-msg hook: a 101-char subject got through"; fail=1
else echo "commit-msg hook: ok · a 101-char subject is refused"; fi
printf '%0100d\n' 0 > "$T/msg"
if bash .claude/githooks/commit-msg "$T/msg" >/dev/null 2>&1; then echo "commit-msg hook: ok · a 100-char subject passes"
else echo "BAD commit-msg hook: a 100-char subject was refused"; fail=1; fi

guard() {  # guard <expected exit> <what> <json>
  printf '%s' "$3" | python3 -I loop/scripts/guard_tool.py >/dev/null 2>&1; rc=$?
  if [ "$rc" = "$1" ]; then echo "guard hook: ok · $2"; else echo "BAD guard hook: $2 (exit $rc, wanted $1)"; fail=1; fi
}
guard 2 "git push refused" '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}'
guard 2 "an edit to loop/kit.json refused" "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$PWD/loop/kit.json\"}}"
guard 0 "a normal edit allowed" "{\"tool_name\":\"Edit\",\"tool_input\":{\"file_path\":\"$PWD/CLAUDE.md\"}}"
if grep -q "guard:push" "$T/catches.csv" 2>/dev/null; then echo "catch log: ok · the hook's refusals are logged"
else echo "BAD catch log: the guard's refusal was not logged"; fail=1; fi
rm -rf "$T"

if [ -f loop/qa/done-rules.json ]; then
  bytes="$(python3 -I loop/scripts/brief.py | wc -c | tr -d ' ')"
  if [ "$bytes" -le 5120 ]; then echo "briefing: ok · $bytes bytes (target under 5 KB)"; else echo "WARN briefing: $bytes bytes, over 5 KB"; fi
fi
[ $fail -eq 0 ] && echo "selftest: ALL GREEN" || echo "selftest: FAILED"
exit $fail
