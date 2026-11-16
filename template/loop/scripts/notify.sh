#!/usr/bin/env bash
# One buzz to the owner's phone via ntfy. No loop, no state, no ceremony.
#
#   bash loop/scripts/notify.sh "message" ["title"]
#
# The topic and default title come from loop/kit.json (ntfy_topic, notify_title); NTFY_TOPIC overrides the topic.
# NOTIFY_DRY=1 prints what would be sent instead of sending it (selftests, demos).
# A unit buzzes once, when it lands; the loop buzzes when it parks, stops or finishes.
# Never fails the caller: a buzz that cannot be sent is printed to stderr and the work goes on.
#
# The loop's preflight refuses to start without this file: a loop that cannot reach the owner must not run.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONF="$(python3 -I -c 'import json,sys
c=json.load(open(sys.argv[1]))
print(c.get("ntfy_topic","")); print(c.get("notify_title","loop"))' "$ROOT/loop/kit.json" 2>/dev/null)"
TOPIC="${NTFY_TOPIC:-$(printf '%s\n' "$CONF" | sed -n 1p)}"
TITLE="${2:-$(printf '%s\n' "$CONF" | sed -n 2p)}"
if [ -n "${NOTIFY_DRY:-}" ]; then
  echo "notify (dry): [$TITLE] ${1:-done} -> ntfy.sh/${TOPIC:-<no topic>}"
  exit 0
fi
if [ -z "$TOPIC" ]; then
  echo "notify: no ntfy_topic in loop/kit.json; message was: ${1:-done}" >&2
  exit 0
fi
curl -fsS -H "Title: ${TITLE}" -d "${1:-done}" "https://ntfy.sh/${TOPIC}" >/dev/null || echo "notify: send failed: ${1:-done}" >&2
