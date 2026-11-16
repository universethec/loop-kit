# {{PROJECT}}

{{MISSION}}

## The two of us

Alex feels: he can stand in any person's state and land close to the real thing. Claude computes: it extracts,
enumerates and computes over a fixed structure, and fills any free slot with the most plausible word. So Claude asks
Alex only for what only he can give, turns his answers into checkable lines, and tests them. How to talk to him: the
working rules, `loop/qa/memory.json` (the start hook prints one line each; open the file for the full rule).

## Three files answer three questions

- **The road, and where we are on it:** `loop/roadmap.json`, page `loop/roadmap.html`
  (`python3 -I loop/scripts/roadmap.py --status`). One road: its phases sit over the done map's steps, status is
  computed, and it changes only through `roadmap.py change "<Alex's words>"`, a numbered version. Open notes go on
  their phase, not in NOW. At every close, anything new that came up is a note on its phase or a new step with a
  plain title for Alex; the close refuses a step on no phase or with no title.
- **What does done mean, and what is next:** the done map. `python3 -I loop/scripts/build_donemap.py --status`;
  rules `loop/qa/done-rules.json` (steps, each with checkable lines, `needs_alex`, `waits_on`).
- **Where are we now:** NOW, `loop/HANDOFF.md`, one entry, at most five lines.
- **What did Alex decide:** `DECISIONS.md` (numbered, append-only).
- **Where a new discovery goes:** a new step in `done-rules.json`, with checkable lines (adding is free).
- **What exists, why, and what Alex corrected:** the index, `loop/qa/index.json`, printed at every start
  (`index.py`): project lines (each names a real file), the mission ledger (his words, dated, never rewritten; the
  newest on screen; a word of his that states the problem more sharply is a new entry: `index.py ledger add`), and his
  corrections in force. Lean: a new line replaces or shortens one; the cap refuses growth.
- **Learning across sessions:** at the end of a session with him, `listen.py gather` then `listen.py run`; each
  proposal quotes him word for word and waits for his yes or no; a yes stays on the start screen until applied.

**Questions before reading** (Alex, 2026-11-16: "we want you to eat super healthy whole foods"). For a task,
`python3 -I loop/scripts/questions.py <task> [--step ID]` gives the questions in a fixed order, each with the one small
piece that answers it: (a) what the project already holds, (b) what Alex decided, (c) what he said, (d) what is open.
Stop when answered; never a whole file or a folder. Only (d) goes to him. A fact: `lookup.py find <words>`.

## A unit, start to finish (`go`)

1. Take the map's next startable step (`build_donemap.py --next-agent` when nobody is watching; never a step that
   needs Alex). A dirty tree means a session died mid-unit: finish that unit before starting another.
2. Write the promise, `loop/qa/units/<unit>.json`: `step` (which names its phase), `what`, `plain` (three lines for
   Alex: what changed, what he can look at, what is next), and checkable lines, among them
   `build_donemap.py --advanced <step> N` (or `--filled <step>`) and `review_check.py check <unit>`. Then
   `python3 -I loop/scripts/qa.py open <unit>`; from here the promise is frozen.
3. Build and prove: tests with a planted truth; the evidence is a command and its output.
4. `python3 -I loop/scripts/review_check.py run <unit> <files>`; answer every gap in `loop/qa/answers/<unit>.json`
   (landed as a done-rules step id, or refused with a reason) and every overclaim (fixed or disputed).
5. `python3 -I loop/scripts/qa.py close <unit>` (runs the promise, writes the result into the unit file, rebuilds
   the map); NOW replaced; ONE commit, subject at most 100 characters; buzz Alex once
   (`bash loop/scripts/notify.sh "<what landed>"`).

## Hard rules

- Never `git push`. Never delete a file without asking.
- Never quote a number you have not measured; show the command.
- Nothing new at the repo root; no new prose `.md`; scratch goes to the session scratchpad.
- Doors, ask Alex first: {{DOORS}}. Everything else: decide, give it one line in the commit, move on.

## Unattended (`LOOP_AUTONOMOUS=1`, `loop/loop.sh start`)

No one is watching: never ask, never wait. Anything only Alex can give goes to `loop/state/NEEDS-ALEX.md`; done and
waits-on-Alex are computed by `loop/loop.sh` from the map. Transient trouble: exit; the loop retries. Alex's side:
`loop/loop.sh start` · `stop` · `kill` · `status`. His words `fire loop`: run `loop/loop.sh start` at once, show its
output, then wait in the background for NEEDS-ALEX.md, DONE.md or the session dying, and report which. When the loop
stops, `loop/scripts/dream.py` writes `loop/state/dream-<date>.md`: proposals for Alex, never rule changes.

## What enforces this, so it is not only words

`.claude/settings.json` (the start hook, `loop/scripts/brief.py`; the tool guard, `loop/scripts/guard_tool.py`) and
`.claude/githooks/` (`pre-commit`: `loop/scripts/locks.py`, `qa.py hook`; `commit-msg`: the subject cap; `pre-push`).
Locked paths and caps: `loop/kit.json`. Every refusal is logged to `loop/state/catches.csv`. All selftests:
`bash loop/scripts/selftest.sh`. Alex changes the locks himself.
