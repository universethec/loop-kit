---
name: new-project
description: Boot a new project that already runs the loop-kit method: a genesis interview first, then a road proposed from it, the done map, the start-screen index (what exists, the mission ledger in the owner's words, the owner's corrections) and listening across sessions. Use when the owner says "boot loop-kit", "new project", "start a project with the loop", or types /new-project.
---

# Boot a project with loop-kit

The kit lives at `<path to loop-kit>`. `python3 new_project.py --help` there is the full reference for answers.json.

## 0. A folder that already has code? Adopt it

If the owner points at a folder that already holds code, adopt it instead of making a new one. First read the code
(the top-level folders, the README, the entry points, the tests, `git log --oneline -20`) and draft your answers to
the five genesis questions and a road from what is there: what is built becomes done lines that already pass, what is
missing becomes the steps. Then still hold the interview below, each question with your drafted answer as the guess:
the code says what exists, only the owner says what it is for. In step 3 add `--adopt`. It never overwrites a file:
it adds `loop/`, `.claude/` and the kit's root files that are missing, keeps the existing git repo, and makes one
commit of only what it added. A root file that was already there (say a `CLAUDE.md`) is kept; the kit's version goes
to `loop/adopt/`, and you merge the two with the owner, by hand.

## 1. The genesis interview: understand before proposing anything

Interview the owner, one question at a time, plain words, each question with your guess so they can say "yes" or
correct it. Keep their own sentences word for word; they go into GENESIS.md and ledger entry 1.

1. **What is this?** In one or two sentences, in their words.
2. **Why does it matter, and for whom?**
3. **What is it not?** The nearest thing people would mistake it for.
4. **What does done look like?** Something you could watch happen or check.
5. **What is open?** The question nobody can answer yet; the part they are least sure of.

Ask a follow-up only when an answer could mean two different projects. Stop when you can say the project back in
two sentences and they agree. Then say it back, and ask for their yes.

## 2. Propose the road, from the genesis

Only now. One screen, your pick on every line, so they answer "yes" or change a line:

- **Phases:** 2 to 6 stretches of the road, in order, each with a plain title someone outside the project would
  understand, and one sentence of what done means for that phase.
- **Steps:** the smallest pieces of work inside each phase. Each step names what done means as lines a machine can
  check (a file exists, a command passes, a file holds some words), never a sentence that only sounds done; says
  whether only the owner can finish it; and sits on exactly one phase. A step waits on the step before it unless
  you say otherwise.
- **A good road:** the first phase can start today; each phase ends on something the owner can look at; owner-only
  steps are few and marked; nothing on it is a guess dressed as a fact.
- **Also, with defaults:** the name; the doors (what always needs the owner: default what a user sees, money;
  deleting files, rewriting git history and a new root entry are always added); project rules (default none);
  model and effort (default `claude-opus-5-5` / `xhigh`); a phone title and an ntfy topic if they want buzzes;
  where (a new empty folder); top-level folders besides the kit's (default `src`, `tests`; the boot makes each
  missing one as an empty folder).

## 3. Make it

Write `answers.json` in the session scratchpad: `name`, `mission`, `genesis` (what, why, for_whom, not, done, open,
and `words`: their own sentences, verbatim), `steps`, `phases`, and the defaults. Then:

```bash
python3 "<path to loop-kit>/new_project.py" "<path>" --answers "<scratchpad>/answers.json"
cd "<path>" && bash loop/scripts/selftest.sh && python3 -I loop/scripts/index.py --check && python3 -I loop/scripts/brief.py
```

For a folder that already has code, the same line with `--adopt` at the end. If it refuses (a bad line, a taken path, a file the kit would add already there), fix the answers and run it again; never edit the kit from here. The road's
page, `loop/roadmap.html`, is built by `python3 -I loop/scripts/roadmap.py`; the boot builds it once.

## 4. Report, in four lines

The path; the map's first line; the checks' last line (`selftest: ALL GREEN` or what failed); and how to begin:
say `go` in a session there. The unattended loop starts only on the owner's `fire loop`. Never push, never delete.
