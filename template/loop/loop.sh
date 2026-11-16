#!/usr/bin/env bash
#
# The autonomous loop. Each slice fires ONE fresh headless Claude with the one-word prompt "go"; CLAUDE.md defines
# go (one unit, start to finish). The process exit IS the /clear: every slice starts with fresh context.
# Model, effort, tmux session name and slice cap come from loop/kit.json (env LOOP_MODEL / LOOP_EFFORT / MAX_ITERS
# override). Each slice gets its own --session-id, logged in loop/state/metrics.csv, so dream.py can read it later.
#
# Sentinels (the slice or the map writes them, the loop reads them):
#   loop/state/NEEDS-OWNER.md  -> only the owner can unblock. Buzz, park.      loop/state/STOP -> the owner's stop.
#   loop/state/DONE.md        -> every line of the done map met. Buzz, stop.
# Safety: LOOP_AUTONOMOUS=1 makes the pre-push hook refuse any push; the tool guard and commit locks hold in every
# slice; a slice cap and a per-slice timeout; two barren slices in a row park the loop.
# When the loop stops or parks, dream.py runs once and writes loop/state/dream-<date>.md (proposals for the owner).
#
#   loop/loop.sh start | stop | kill | status | run        (start = detached tmux + caffeinate; walk away)

set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOOP_DIR="$REPO/loop/state"
KIT="$REPO/loop/kit.json"
MCP_CONFIG="$REPO/loop/loop-mcp.json"   # empty on purpose: no MCP servers headless

cfg() {  # cfg <key> <default>: one value from kit.json (a list prints one item per line)
  python3 -I -c 'import json,sys
try: c=json.load(open(sys.argv[1]))
except Exception: c={}
v=c.get(sys.argv[2], sys.argv[3])
print("\n".join(v) if isinstance(v,list) else v)' "$KIT" "$1" "$2" 2>/dev/null || echo "$2"
}

SESSION="$(cfg session loop)"
MAX_ITERS="${MAX_ITERS:-$(cfg max_iters 30)}"   # safety cap; raise once trusted
ITER_TIMEOUT="${ITER_TIMEOUT:-9000}"            # 2.5h per slice (1h was too tight)
SLEEP_BETWEEN="${SLEEP_BETWEEN:-5}"
CLAUDE_MODEL="${LOOP_MODEL:-$(cfg model claude-opus-5-5)}"
STEP_EFFORT="${LOOP_EFFORT:-$(cfg effort xhigh)}" # PRIVATE name: CLAUDE_EFFORT gets clobbered by a parent session
RETRY_WAIT="${RETRY_WAIT:-1200}"      # 20m between limit-reset retries
RETRY_MAX="${RETRY_MAX:-12}"
RETRY_WAIT_API="${RETRY_WAIT_API:-60}" # short wait for socket/overload blips
TITLE="$(cfg notify_title "$SESSION")"

NOTIFY_SH="$REPO/loop/scripts/notify.sh"
notify() { bash "$NOTIFY_SH" "$1" "$TITLE"; echo ">> NOTIFY: $1"; }
catch() { ( cd "$REPO" && python3 -I -c 'import sys; sys.path.insert(0, "loop/scripts"); import kit; kit.catch(sys.argv[1], sys.argv[2])' "$1" "$2" ) || true; }

# PREFLIGHT: a loop that cannot reach the owner, or whose gates are not wired, must not run unattended. (A moved
# notify.sh once made every buzz of a 12-slice run exit 127 into a log nobody read; silence must be impossible.)
preflight() {
  local missing=""
  [ -f "$NOTIFY_SH" ]              || missing="$missing  $NOTIFY_SH (the only way this loop reaches the owner)\n"
  [ -f "$MCP_CONFIG" ]             || missing="$missing  $MCP_CONFIG\n"
  [ -f "$KIT" ]                    || missing="$missing  $KIT\n"
  [ -f "$REPO/loop/HANDOFF.md" ]   || missing="$missing  $REPO/loop/HANDOFF.md (the slice has no map without it)\n"
  [ -f "$REPO/CLAUDE.md" ]         || missing="$missing  $REPO/CLAUDE.md\n"
  [ "$(git -C "$REPO" config core.hooksPath)" = ".claude/githooks" ] || missing="$missing  core.hooksPath is not .claude/githooks (the commit locks would not run)\n"
  command -v claude >/dev/null     || missing="$missing  the 'claude' CLI is not on PATH\n"
  command -v uuidgen >/dev/null    || missing="$missing  uuidgen (each slice's session id)\n"
  if [ -n "$missing" ]; then
    printf '\n  loop REFUSED to start — these are missing:\n\n' >&2
    printf "$missing" >&2
    printf '\n  Fix them, then start again. A loop that cannot buzz the owner is worse than a loop that never ran.\n\n' >&2
    exit 1
  fi
}

# Portable timeout: macOS has no GNU `timeout`.
with_timeout() {  # with_timeout <seconds> <cmd...>
  local secs="$1"; shift
  "$@" &
  local cmd_pid=$!
  ( sleep "$secs"; kill -TERM "$cmd_pid" 2>/dev/null; sleep 5; kill -KILL "$cmd_pid" 2>/dev/null ) &
  local killer_pid=$!
  local rc=0
  wait "$cmd_pid" 2>/dev/null || rc=$?
  if ! kill -0 "$killer_pid" 2>/dev/null; then rc=124; fi
  kill -TERM "$killer_pid" 2>/dev/null
  wait "$killer_pid" 2>/dev/null || true
  return $rc
}

# A dead network makes `claude -p` hang the whole ITER_TIMEOUT instead of failing fast.
net_wait() {
  until curl -s -o /dev/null --max-time 10 "https://api.anthropic.com/" 2>/dev/null; do
    echo "network/API unreachable — waiting 120s before dispatch."
    sleep 120
  done
}

# The scar tissue: which failures to wait out vs stop on.
TRANSIENT_API_RE="socket connection was closed|socket hang up|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|fetch failed|Connection error|overloaded|rate.?limit|ConnectionRefused|ECONNREFUSED|Unable to connect|ENETDOWN|ENETUNREACH|network is (down|unreachable)|session limit|usage limit|hit your.*limit|API Error|[Cc]onnection (closed|lost|reset|refused)|mid-response"
# Human-only blockers: waiting cannot clear them. Tested BEFORE the transient regex, which also matches these
# strings (12 retries over 4h40m once learned nothing). A per-model limit is human-only too: the owner picks the model.
HARD_BLOCK_RE="credit balance is too low|weekly limit|reached your .*limit"

cmd="${1:-run}"
case "$cmd" in
  start)
    tmux has-session -t "$SESSION" 2>/dev/null && { echo "already running (tmux: $SESSION)"; exit 1; }
    preflight   # fail in the owner's terminal, not silently inside tmux
    mkdir -p "$LOOP_DIR"; rm -f "$LOOP_DIR/STOP"
    tmux new -d -s "$SESSION" "caffeinate -dis bash '$REPO/loop/loop.sh' run"
    echo "loop started, detached (tmux: $SESSION). Mac stays awake, lid OPEN, plugged in."
    echo "  peek:  tmux attach -t $SESSION     stop: loop/loop.sh stop"
    exit 0;;
  stop)
    mkdir -p "$LOOP_DIR"; touch "$LOOP_DIR/STOP"
    echo "STOP set — the loop parks after the slice now running."; exit 0;;
  kill)
    tmux kill-session -t "$SESSION" 2>/dev/null && echo "killed." || echo "nothing running."
    exit 0;;
  status)
    tmux has-session -t "$SESSION" 2>/dev/null && echo "loop: RUNNING (tmux: $SESSION)" || echo "loop: not running"
    [ -f "$LOOP_DIR/STOP" ] && echo "STOP requested — parking after current slice"
    [ -f "$LOOP_DIR/DONE.md" ] && echo "DONE: $(head -1 "$LOOP_DIR/DONE.md")"
    [ -f "$LOOP_DIR/NEEDS-OWNER.md" ] && { echo "--- NEEDS THE OWNER:"; head -5 "$LOOP_DIR/NEEDS-OWNER.md"; }
    [ -f "$LOOP_DIR/metrics.csv" ] && { echo "--- last slices:"; tail -3 "$LOOP_DIR/metrics.csv"; }
    git -C "$REPO" log --oneline -3
    exit 0;;
  run) ;;
  *) echo "usage: loop.sh [start|stop|kill|status|run]"; exit 1;;
esac

# ------------------------------- the loop -------------------------------
export LOOP_AUTONOMOUS=1   # <-- the pre-push hook keys off this
# Headless `claude -p` kills background agents 10 minutes after its last turn; wait for them however long they take.
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0

preflight   # again: `run` is reachable directly, and tmux swallows stderr
mkdir -p "$LOOP_DIR/logs"
rm -f "$LOOP_DIR/NEEDS-OWNER.md" "$LOOP_DIR/DONE.md"
RUN_ID="$(date '+%Y%m%dT%H%M%S')"

# DREAM once, whenever and however the run ends (stop, park, done, error, cap): proposals only, never a rule change.
DREAMED=0
dream_once() {
  [ "$DREAMED" = 1 ] && return; DREAMED=1
  ( cd "$REPO" && python3 -I loop/scripts/dream.py --run "$RUN_ID" ) || echo "dream: failed (the run's result stands)"
}
trap dream_once EXIT

EXTRA_TOOLS=()
while IFS= read -r t; do [ -n "$t" ] && EXTRA_TOOLS+=("$t"); done < <(cfg allowed_tools_extra "")

notify "Loop started. cap=$MAX_ITERS slices, model $CLAUDE_MODEL ($STEP_EFFORT)."

steps=0
retries=0
barren=0        # consecutive clean slices that committed nothing — see the park below
while [ "$steps" -lt "$MAX_ITERS" ]; do
  if [ -f "$LOOP_DIR/STOP" ]; then
    notify "Stopped on your STOP after $steps slice(s). 'loop/loop.sh start' resumes from the repo."
    exit 0
  fi

  # THE HANDOFF IS CLEAN BEFORE A NEW ROUND: the tree committed, NOW one entry, the done map fresh; any problem parks
  # the loop with the reason, so a new round never starts on top of a dirty one.
  HANDOFF=$(cd "$REPO" && python3 -I loop/scripts/handoff_check.py); HANDOFF_RC=$?
  if [ "$HANDOFF_RC" -ne 0 ]; then echo "$HANDOFF" > "$LOOP_DIR/NEEDS-OWNER.md"; notify "NEEDS YOU, the handoff is not clean: $(head -c 240 "$LOOP_DIR/NEEDS-OWNER.md")"; exit 0; fi

  # THE MAP DECIDES: exit 3 = every line met; 2 = only steps that need the owner; 0 = the step id to take.
  NEXT=$(cd "$REPO" && python3 -I loop/scripts/build_donemap.py --next-agent); NEXT_RC=$?
  if [ "$NEXT_RC" -eq 3 ]; then echo "$NEXT" > "$LOOP_DIR/DONE.md"; notify "DONE (computed from the map): $NEXT"; exit 0; fi
  if [ "$NEXT_RC" -eq 2 ]; then echo "$NEXT" > "$LOOP_DIR/NEEDS-OWNER.md"; notify "NEEDS YOU (computed from the map): $(head -c 240 "$LOOP_DIR/NEEDS-OWNER.md")"; exit 0; fi
  if [ "$NEXT_RC" -ne 0 ]; then echo "$NEXT" > "$LOOP_DIR/NEEDS-OWNER.md"; notify "NEEDS YOU, the done map did not build: $(head -c 240 "$LOOP_DIR/NEEDS-OWNER.md")"; exit 0; fi

  echo ""
  echo "=== slice $((steps+1))/$MAX_ITERS  step $NEXT  (retries $retries/$RETRY_MAX)  ($(date '+%H:%M:%S')) ==="

  LOG="$LOOP_DIR/logs/$RUN_ID-slice-$((steps+1))-try$retries.log"
  SID="$(uuidgen | tr 'A-Z' 'a-z')"
  T0=$(date +%s)
  HEAD_T0=$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo none)
  net_wait
  ( cd "$REPO" && with_timeout "$ITER_TIMEOUT" \
      claude -p --model "$CLAUDE_MODEL" --effort "$STEP_EFFORT" --session-id "$SID" \
        --permission-mode acceptEdits \
        --allowedTools "WebSearch" "WebFetch" "Bash(python3:*)" ${EXTRA_TOOLS[@]+"${EXTRA_TOOLS[@]}"} \
        --mcp-config "$MCP_CONFIG" --strict-mcp-config "go" ) \
      >"$LOG" 2>&1
  rc=$?

  DUR=$(( $(date +%s) - T0 ))
  NEW_COMMITS=$(git -C "$REPO" rev-list --count "$HEAD_T0..HEAD" 2>/dev/null || echo 0)
  LAST_SUBJ=$(git -C "$REPO" log -1 --format=%s 2>/dev/null | tr ',' ';' | head -c 120)
  METRICS="$LOOP_DIR/metrics.csv"
  [ -f "$METRICS" ] || echo "date,run,slice,try,rc,duration_s,new_commits,session_id,last_commit_subject" > "$METRICS"
  echo "$(date '+%Y-%m-%dT%H:%M:%S'),$RUN_ID,$((steps+1)),$retries,$rc,$DUR,$NEW_COMMITS,$SID,$LAST_SUBJ" >> "$METRICS"
  tail -20 "$LOG"

  if [ -f "$LOOP_DIR/NEEDS-OWNER.md" ]; then
    notify "NEEDS YOU: $(head -c 240 "$LOOP_DIR/NEEDS-OWNER.md")"
    echo "parked on NEEDS-OWNER."; exit 0
  fi
  if [ -f "$LOOP_DIR/DONE.md" ]; then
    notify "BUILD COMPLETE: $(head -c 200 "$LOOP_DIR/DONE.md")"
    echo "done."; exit 0
  fi
  if [ "$rc" -eq 124 ] || [ "$rc" -ge 128 ]; then
    notify "STUCK: slice $((steps+1)) timed out/killed (rc=$rc) after ${ITER_TIMEOUT}s. Stopped. See $LOG"
    exit 1
  fi
  if [ "$rc" -ne 0 ] && grep -qiE "$HARD_BLOCK_RE" "$LOG" 2>/dev/null; then
    notify "STOPPED: human-only blocker (credits, weekly cap, or this model's limit). Switch model or wait. No retries spent. See $LOG"
    exit 1
  fi
  if [ "$rc" -ne 0 ] && grep -qiE "$TRANSIENT_API_RE" "$LOG" 2>/dev/null; then
    retries=$((retries + 1))
    if [ "$retries" -gt "$RETRY_MAX" ]; then
      notify "STILL hitting transient API errors after $RETRY_MAX retries. Stopped. See $LOG"
      exit 1
    fi
    WAIT="$RETRY_WAIT_API"
    if grep -qiE "session limit|usage limit|hit your.*limit" "$LOG" 2>/dev/null; then
      WAIT="$RETRY_WAIT"   # limits reset on a schedule; quiet 20m backoff, buzz once
      [ "$retries" -eq 1 ] && notify "Usage limit — quiet backoff, retrying every $((RETRY_WAIT/60))min (max $RETRY_MAX). Resumes alone."
    fi
    echo "transient — waiting ${WAIT}s, retrying the SAME slice."
    sleep "$WAIT"
    continue   # does NOT consume a productive slice
  fi
  if [ "$rc" -ne 0 ]; then
    notify "ERROR: slice $((steps+1)) exited rc=$rc. Stopped. See $LOG"
    exit 1
  fi

  # A SILENT SPIN IS WORSE THAN A PARK. Slices once exited rc=0 five times in a row having committed nothing, each
  # asking for a decision in its log instead of writing NEEDS-OWNER.md; the buzz is wired to that file, so the loop
  # looked healthy while achieving nothing. A rule with no mechanical check is a wish: two barren slices park it.
  if [ "$NEW_COMMITS" -eq 0 ]; then
    barren=$((barren + 1))
    if [ "$barren" -ge 2 ]; then
      {
        echo "# The loop parked itself — $barren slices in a row committed nothing"
        echo
        echo "Neither NEEDS-OWNER.md nor DONE.md was written and nothing was committed, so no slice is making"
        echo "progress. The usual cause: a slice needs a decision only the owner can make and asked for it in its log."
        echo
        echo "Last log: \`$LOG\`"
        echo
        echo "## What the last slice said"
        echo
        echo '```'
        tail -40 "$LOG"
        echo '```'
      } > "$LOOP_DIR/NEEDS-OWNER.md"
      catch "loop:barren-park" "$barren slices, zero commits; last log $LOG"
      notify "PARKED: $barren slices, zero commits. A slice wants a decision — see loop/state/NEEDS-OWNER.md"
      echo "parked — $barren barren slices."; exit 0
    fi
    echo "slice $((steps+1)) committed nothing (barren $barren/2)."
  else
    barren=0
  fi

  steps=$((steps + 1)); retries=0
  echo "slice $steps landed; continuing."
  sleep "$SLEEP_BETWEEN"
done

notify "Hit the safety cap ($MAX_ITERS slices), all clean. 'loop/loop.sh start' continues from the repo."
