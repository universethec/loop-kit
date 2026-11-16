# {{PROJECT}}

{{MISSION}}

## The two of us

You, the owner, feel: you can stand in any person's state and land close to the real thing. Claude computes: it
extracts, enumerates and computes over a fixed structure, and fills any free slot with the most plausible word. So
Claude asks you only for what only you can give, turns your answers into checkable lines, and tests them. How Claude
talks to you: the working rules, `loop/qa/memory.json` (the start hook prints one line each; open the file for the full rule).
**Codespeak** is text that looks plain but is made of the program's own names and shapes (a file key, a flag, a
script name, `a · b · c` strings). Never write it to the owner. The test: would a friend who never saw the project
understand it on first read? Name each part by what it does; a program name, when needed, goes in `backticks`.
`python3 -I loop/scripts/plain.py check` catches the common cases.

## Three files answer three questions

- **What is this, and why:** `GENESIS.md`, the founding interview, the owner's words quoted exactly; it grows by
  dated entries and is never rewritten. If it says the interview has not been held, hold it first, one question at
  a time (what this is, why and for whom, what it is not, what done looks like, what is open), before the road.
- **The road, and where we are on it:** a good road is proposed from the genesis: 2 to 6 phases with plain titles
  and one sentence of what done means each; steps, the smallest pieces, each with lines a machine checks, on exactly
  one phase, owner-only steps few and marked; the first phase can start today. `loop/roadmap.json`, page `loop/roadmap.html`
  (`python3 -I loop/scripts/roadmap.py --status`). One road: its phases sit over the done map's steps, status is
  computed, and it changes only through `roadmap.py change "<the owner's words>"`, a numbered version. Open notes go on
  their phase, not in NOW. At every close, anything new that came up is a note on its phase or a new step with a
  plain title for the owner; the close refuses a step on no phase or with no title.
- **What does done mean, and what is next:** the done map. `python3 -I loop/scripts/build_donemap.py --status`;
  rules `loop/qa/done-rules.json` (steps, each with checkable lines, `needs_owner`, `waits_on`).
- **Where are we now:** NOW, `loop/HANDOFF.md`, one entry, at most five lines.
- **What did the owner decide:** `DECISIONS.md` (numbered, append-only).
- **Where a new discovery goes:** a new step in `done-rules.json`, with checkable lines (adding is free).
- **What exists, why, and what the owner corrected:** the index, `loop/qa/index.json`, printed at every start
  (`index.py`): project lines (each names a real file), the mission ledger (your words, dated, never rewritten; the
  newest on screen; a word of yours that states the problem more sharply is a new entry: `index.py ledger add`), and
  your corrections in force. Lean: a new line replaces or shortens one; the cap refuses growth.
- **Learning across sessions:** at the end of a session with you, `listen.py gather` then `listen.py run`; each
  proposal quotes you word for word and waits for your yes or no; a yes stays on the start screen until applied.

**Questions before reading** (the owner, 2026-11-16: "we want you to eat super healthy whole foods"). For a task,
`python3 -I loop/scripts/questions.py <task> [--step ID]` gives the questions in a fixed order, each with the one small
piece that answers it: (a) what the project already holds, (b) what the owner decided, (c) what you said, (d) what is open.
Stop when answered; never a whole file or a folder. Only (d) goes to you. A fact: `lookup.py find <words>`.

## A unit, start to finish (`go`)

1. `python3 -I loop/scripts/loop.py go`: it takes the map's next step that does not need the owner and drafts its
   promise, `loop/qa/units/<unit>.json`, from the done map. Work in progress or a dirty tree comes first; it says so.
2. Fix the draft: each DRAFT line made true (`what`; `plain`, three lines for the owner: what changed, what you can
   look at, what is next), the checkable lines sharpened, keeping `build_donemap.py --advanced <step> N` (or
   `--filled <step>`) and `review_check.py check <unit>`. Then `qa.py open <unit>`: the promise is frozen.
3. Build and prove: tests with a planted truth; the evidence is a command and its output.
4. `python3 -I loop/scripts/review_check.py run <unit> <files>`; answer every gap in `loop/qa/answers/<unit>.json`
   (landed as the id of a step on the done map, or refused with a reason) and every overclaim (fixed or disputed).
5. `python3 -I loop/scripts/qa.py close <unit>` (runs the promise, writes the result into the unit file, rebuilds
   the map); NOW replaced; ONE commit, subject at most 100 characters; buzz the owner once
   (`bash loop/scripts/notify.sh "<what landed>"`).

A small change (a typo, a renamed label, one line of a fix): `loop.py small "<what>"` instead of steps 1 and 2;
no review; the close still runs the project's checks; one commit.

## Hard rules

- Never `git push`. Never delete a file without asking.
- Never quote a number you have not measured; show the command.
- Nothing new at the repo root; no new prose `.md`; scratch goes to the session scratchpad.
- Doors, ask the owner first: {{DOORS}}. Everything else: decide, give it one line in the commit, move on.

## Unattended (`LOOP_AUTONOMOUS=1`, `loop/loop.sh start`)

No one is watching: never ask, never wait. Anything only the owner can give goes to `loop/state/NEEDS-OWNER.md`; done and
waits-on-the owner are computed by `loop/loop.sh` from the map. Transient trouble: exit; the loop retries. The owner's side:
`loop/loop.sh start` · `stop` · `kill` · `status`. Your words `fire loop`: run `loop/loop.sh start` at once, show its
output, then wait in the background for NEEDS-OWNER.md, DONE.md or the session dying, and report which. When the loop
stops, `loop/scripts/dream.py` writes `loop/state/dream-<date>.md`: proposals for the owner, never rule changes.

## What enforces this, so it is not only words

`.claude/settings.json` (the start hook, `loop/scripts/brief.py`; the tool guard, `loop/scripts/guard_tool.py`) and
`.claude/githooks/` (`pre-commit`: `loop/scripts/locks.py`, `qa.py hook`; `commit-msg`: the subject cap; `pre-push`).
Locked paths and caps: `loop/kit.json`. Every refusal is logged to `loop/state/catches.csv`. All selftests:
`bash loop/scripts/selftest.sh`. You, the owner, change the locks yourself.
