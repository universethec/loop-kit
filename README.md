# loop-kit

Start a project with Claude Code that already knows how to work: one road, a done map a machine checks, a promise
before every piece of work, a blind review after it, and a start screen that carries what exists, what you said and
what you corrected from one session to the next.

You say **"boot loop-kit"**. Claude first interviews you about the project, one question at a time (what it is, why
and for whom, what it is not, what done looks like, what is open), and writes your answers, in your words, into the
project's genesis. Only then does it propose the road: phases with plain titles, steps a machine can check. You say
yes or change a line; it builds the project, makes the first commit, and every session after opens already informed.

## What a project gets

- **A genesis.** `GENESIS.md`: what the project is, why, for whom, what it is not, what is open, your words quoted
  exactly; it grows by dated entries and is never rewritten. The road is proposed from it.
- **The road and the done map.** Your project is a few steps; each step is done only when its lines pass (a file
  exists, a command passes, a file holds some words), never because a sentence says so. The road (phases over the
  steps) changes only through your own words, as a numbered version. A page, `loop/roadmap.html`, shows where you are.
- **A rhythm for every piece of work.** Write the promise first (what will change and how it is proven), build, run a
  blind review by a fresh read-only session, answer every point it raises, then close: the promise is checked, the
  result is kept with the commit. One page, `loop/activity.html`, shows every piece of work, newest first.
- **Guards that are not only words.** No `git push` without you, no deleting files, locked paths, short commit
  subjects. Each guard plants its own failure in a self-check, so you know it still bites.
- **The start screen, every session:** where you are on the map, NOW (a few lines), the last commits, the working
  rules, and the project index:
  - **what exists**, one line each, every line naming a real file (the check refuses a line whose file is gone);
  - **the mission ledger**, your words on the mission and the open problem, dated, never rewritten (a sharper word
    of yours becomes a new entry; the check refuses an edit or a removal of an old one); the newest is on screen;
  - **your corrections in force**, so a session does not repeat a mistake you already named.
- **Questions before reading.** For a task, `questions.py <task>` turns it into questions in a fixed order: what the
  project already holds, what you decided, what you said, what is still open; each with the one small piece that
  answers it. Only the last kind comes to you.
- **Learning across sessions.** At the end of a session with you, `listen.py` reads only the messages you typed and
  proposes changes to the index and the rules. Each proposal must quote you word for word or it is thrown away. You
  say yes or no; a yes stays on the start screen until the commit that applies it.
- **An unattended loop**, when you want one: `loop/loop.sh start` works through the steps that do not need you and
  leaves what does in `loop/state/NEEDS-OWNER.md`.

## Set up once

```bash
git clone https://github.com/universethec/loop-kit.git
bash loop-kit/skill/install.sh
```

The installer puts the boot skill in `~/.claude/skills/new-project/` with the kit's real path filled in (no hand
edit), then checks and lists what is missing, with how to get it: Python 3, git and
[Claude Code](https://claude.com/claude-code) are needed; tmux, and on macOS `caffeinate`, only for the unattended
loop; `gh` (GitHub) is optional. Run it again after you move or update the kit. The skill is what makes
"boot loop-kit" work; edit its default projects folder (`<your projects folder>`) to taste. An
[ntfy](https://ntfy.sh) topic, if you want a buzz on your phone when a piece of work lands, is asked at boot.

## Boot a project

In Claude Code, say **"boot loop-kit"** (or "new project"). It drafts, on one screen, with its pick on each line: the
name, the mission (and your own words for it, which become ledger entry 1), what is open, the steps with their
checkable lines, the doors (what always needs you), and where to put it. Answer "yes" or change a line.

Without the skill, the same thing by hand:

```bash
python3 loop-kit/new_project.py --sample > answers.json      # a sample to edit
python3 loop-kit/new_project.py ~/code/my-project --answers answers.json
cd ~/code/my-project && bash loop/scripts/selftest.sh && python3 -I loop/scripts/brief.py
```

`python3 loop-kit/new_project.py --help` is the full reference for `answers.json`.

**A folder that already has code:** say so, and the boot reads the code first, drafts the genesis and the road from
it, then still interviews you. By hand, add `--adopt` to the second line. It never overwrites anything: it adds
`loop/`, `.claude/` and the kit's root files you do not have yet, keeps your git repo, and makes one commit of only
those. A file you already had (a `CLAUDE.md`, a `.gitignore`) stays as it is; the kit's version is put in
`loop/adopt/` for you to merge by hand.

## Working in a project

| You say / run | What happens |
|---|---|
| `go` | The session takes the map's next startable step through the rhythm above, and commits once. It starts with `loop.py go`, which drafts the promise from the done map for the session to fix and stamp. |
| `python3 -I loop/scripts/loop.py` | The one thing to do now (the start screen ends with the same line). `help` lists the words. |
| `loop.py status` | The whole map, every step and line, met or not, and where you are on the road. |
| `loop.py activity` | Writes `loop/activity.html`: each piece of work, newest first, with its promise, the review's gaps and how each was answered, the result and the commit. |
| `loop.py small "what"` | The light track for a small change: no interview, a short promise opened at once; the close still runs every check. |
| `loop.py decisions` | One line per decision you made, from `DECISIONS.md`: its number, date and first words. |
| `loop.py archive` | Folds each finished phase of the road to one line, so `status` stays short; the road itself is not changed. |
| `loop.py size` | Flags a step with too many done lines, or a piece of work touching too many files, and proposes how to split it. The start screen (60 lines) and `status` (80 lines, `--all` for everything) have caps, set in `loop/kit.json`. |
| `loop.py ledger` · `loop.py ledger add DATE "your words"` | The newest ledger entry · a new one, your words exactly. |
| `python3 -I loop/scripts/questions.py <task>` | The questions a task needs, in order, each with its one small piece. |
| `python3 -I loop/scripts/listen.py gather` then `run` | The learning pass over the session; `show` and `answer` for its proposals. |
| `fire loop` | Starts the unattended loop and waits for it to stop or to need you. |
| `bash loop/scripts/selftest.sh` | Every guard and check, each watched failing on purpose. |

## Words you will see

What the start screen and the commands say, in plain words.

| Word | What it means |
|---|---|
| genesis | The first interview: what the project is, why, for whom, what it is not, in your words. |
| road, phase | The plan: a few stretches (phases), in order. The road changes only when you say so, as a new numbered version. |
| done map, step | The list of small pieces of work (steps). A step is done only when a machine can check it. |
| line, met | One thing a machine checks for a step (a file is there, a command works). Met means it passed. |
| startable, blocked | Startable: can begin now. Blocked: waits for an earlier step. |
| needs the owner | A step only you can finish; Claude never takes it alone. |
| archived | A finished phase folded to one line, so the list stays short. Nothing in it is lost. |
| too big | A step or a piece of work over its cap; the line says how to split it in two. |
| next without the owner | The next step Claude could do while you are away. |
| flags: red, amber | Warnings about the project's health. Red: fix now. Amber: worth a look soon. |
| next | The start screen's last line: the one thing to do now. `loop.py next` prints it any time. |
| NOW | A note of at most five lines: where we are today. |
| working rules | How Claude works with you, one line each on the start screen. |
| mission ledger, entry | Your words about the goal and the hard part, dated; a new entry is added, an old one is never changed. |
| corrections in force | Mistakes you pointed out, so Claude does not repeat them. |
| proposals from listening | Changes Claude suggests after reading what you typed in a session; each waits for your yes. |
| unit, piece of work | One go at one step: promise, build, review, close, one commit. |
| promise, draft | Written before the work: what will change and how it will be checked. A draft is filled from the done map; its DRAFT lines are fixed before it is stamped. |
| review, gap, overclaim | A fresh Claude reads the work without the story. A gap: something missing. An overclaim: a promise said more than the work shows. |
| close | The promise is checked for real and the result is kept with the commit. |
| door | Something Claude always asks you first (money, deleting files, and what you named). |
| lock, guard | Files and actions Claude cannot touch alone; the guard stops the attempt, logs it, and prints the command for you to type yourself after `!`. |
| abandon, redo | Abandon: close a stuck piece of work, with the reason kept. Redo: start it again under a new name, the old promise as a draft. |
| self-test, ALL GREEN | Every check made to fail on purpose and seen to catch it. ALL GREEN: all of them caught. |
| unattended loop, `fire loop` | Claude works through the steps that do not need you while you are away; it stops when it needs you. |
| codespeak | Text that looks plain but is made of the program's own names. The kit avoids it: `plain.py check` catches it. |

## When things go wrong

One command per problem; `loop.py` is `python3 -I loop/scripts/loop.py`.

| Problem | Run |
|---|---|
| You do not know what to do next, or the start screen says DIRTY TREE | `loop.py next` |
| A piece of work is stuck, or its promise was wrong | `loop.py abandon <unit> "why"` |
| A piece of work failed its close, or was abandoned, and should be tried again | `loop.py redo <unit>` |
| The guard refused something you want done | type the command it printed, after `!` (the guard never sees what you type) |
| The done map does not build | `loop.py status` (it names the broken line) |
| The close refuses because the review is not answered | `python3 -I loop/scripts/review_check.py check <unit>` (each point left) |
| You are not sure the checks still catch what they should | `bash loop/scripts/selftest.sh` |
| The unattended loop stopped | `loop/loop.sh status` (what it needs from you is in `loop/state/NEEDS-OWNER.md`) |

## How it thinks

- Plain words for everyone: explained so someone aged 6 to 8 could follow, and the owner is "you".
- Done means a check passes, never a sentence.
- Read the question first, then the one small piece that answers it; never a whole file or a folder.
- Ask the owner only what the project, their decisions and their words leave open.
- The owner's words are kept as they were said; a summary of them is labelled as one.
- A new lesson replaces or shortens a line; the caps refuse growth.

## Limits

The kit is proven by its own checks on sample projects and by the project it was grown in; your first real project
is the real test. Improvements to the kit reach projects booted after them. For a project already running,
`python3 loop-kit/new_project.py --upgrade ~/code/my-project` lists what changed in the kit since (files that differ,
files that are new, and the files filled at boot to compare by hand); `--diff` shows the lines. It only reads: you
or a session copy over what you want, then run the project's checks.
