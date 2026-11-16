---
name: new-project
description: Create a new project that already runs Alex's autonomous Claude loop (lean loop-kit), with the road, the done map, the start-screen index (what exists, the mission ledger in his words, his corrections) and listening across sessions. Use when Alex says "boot loop-kit", "new project", "start a project with the loop", "set up a project like harbingr", or types /new-project.
---

# New project, already on the loop

The kit lives at `<path to loop-kit>`. Its `new_project.py --help` is the full
reference for answers.json; read it only if something below is unclear.

## 1. Ask, on one screen

Draft every answer yourself first from what Alex already said, then show him ONE message, plain words, each line
with your pick so he can answer "yes" or change one line:

1. **Name** — your pick.
2. **Mission**, one sentence: what "done" means for the whole project — your draft. And his own words for it, if he
   said them (they become ledger entry 1, `mission_words`, word for word), and what is open, one sentence
   (`open_problem`), if there is one.
3. **Steps** (2 to 6, in order of work). For each: a name, what done means as lines a machine can check (a file
   exists, a command passes, a file holds some words), and whether only Alex can finish it. Draft them all.
4. **Doors** — what always needs him. Default: what a user sees; money. (Deleting files, rewriting git history and
   a new root entry are always added.)
5. **Project rules**, optional: one line each. Default: none.
6. **Model / effort** — default `claude-opus-5-5` / `xhigh`.
7. **Phone title** — default: the name.
8. **Where** — default `<your projects folder>/<name-slug>`; root folders besides the kit's
   own (default `src`, `tests`).

Do not ask anything else. If he says "your call", take your picks.

## 2. Make it

Write `answers.json` in the session scratchpad (format: `python3 new_project.py --help`; a step's lines may be
shorthand `file:<path>`, `cmd:<shell>`, `grep:<path>::<words>`). Then:

```bash
python3 "<path to loop-kit>/new_project.py" "<path>" --answers "<scratchpad>/answers.json"
cd "<path>" && bash loop/scripts/selftest.sh && python3 -I loop/scripts/index.py --check && python3 -I loop/scripts/brief.py
```

If new_project refuses (a bad line, a taken path), fix the answers and run it again; never edit the kit.

## 3. Report, in four lines

The path; the map's first line (quoted from `--brief`); the selftest's last line (`selftest: ALL GREEN` or what
failed); and the one command to start: `loop/loop.sh start` (only when he says "fire loop"; never start it yourself).
Never push. Never delete a file.
