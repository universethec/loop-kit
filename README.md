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
  result is kept with the commit.
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

Needs Python 3, git and [Claude Code](https://claude.com/claude-code). Optional: `gh` (GitHub), and an
[ntfy](https://ntfy.sh) topic if you want a buzz on your phone when a piece of work lands.

```bash
git clone https://github.com/universethec/loop-kit.git
mkdir -p ~/.claude/skills/new-project
sed "s|<path to loop-kit>|$PWD/loop-kit|g" loop-kit/skill/new-project/SKILL.md > ~/.claude/skills/new-project/SKILL.md
```

The skill is what makes "boot loop-kit" work. Edit its default projects folder (`<your projects folder>`) to taste.

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

## Working in a project

| You say / run | What happens |
|---|---|
| `go` | The session takes the map's next startable step through the rhythm above, and commits once. |
| `python3 -I loop/scripts/build_donemap.py --status` | The whole map: every step, every line, met or not. |
| `python3 -I loop/scripts/roadmap.py --status` | One line: the road's version, the phase, the next step. |
| `python3 -I loop/scripts/questions.py <task>` | The questions a task needs, in order, each with its one small piece. |
| `python3 -I loop/scripts/index.py ledger add DATE "your words"` | A new ledger entry, your words exactly. |
| `python3 -I loop/scripts/listen.py gather` then `run` | The learning pass over the session; `show` and `answer` for its proposals. |
| `fire loop` | Starts the unattended loop and waits for it to stop or to need you. |
| `bash loop/scripts/selftest.sh` | Every guard and check, each watched failing on purpose. |

## How it thinks

- Done means a check passes, never a sentence.
- Read the question first, then the one small piece that answers it; never a whole file or a folder.
- Ask the owner only what the project, their decisions and their words leave open.
- The owner's words are kept as they were said; a summary of them is labelled as one.
- A new lesson replaces or shortens a line; the caps refuse growth.

## Limits

The kit is proven by its own checks on sample projects and by the project it was grown in; your first real project
is the real test. Improvements to the kit reach projects booted after them, not ones already running.
