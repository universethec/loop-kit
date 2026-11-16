# The everyday command: one short name for what you do most, so nobody has to remember paths.
#
#   loop.py              the one suggested next action (the same as `loop.py next`)
#   loop.py next         the one suggested next action, computed from the files
#   loop.py status       the whole map, every step and line, and the road's one line
#   loop.py go           take the next step Claude can do alone: draft its promise (draft.py), then what to run
#   loop.py ledger [N]   one mission ledger entry (default: the newest); `ledger add DATE "your words"` adds one
#   loop.py abandon <unit> "why" · redo <unit>   when a piece of work goes wrong (recover.py)
#   loop.py activity     write the activity page, loop/activity.html (activity.py): what the agent did, newest first
#   loop.py small "<what>" [--check "<cmd>"]   the light track (draft.py small): a short promise, opened; close as usual
#   loop.py decisions · archive · size   growth.py: the decisions list; fold finished phases; flag what is too big
#   loop.py status [--all]               capped at kit.json status_max_lines unless --all; archived phases one line
#   loop.py help         this list
#   loop.py selftest     planted projects: each state gets the right next action; the start screen ends with it
#
# Nothing here judges: it reads the map and the work in progress and points at the one command to run. Stdlib only.
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402

S = "python3 -I loop/scripts/"
HELP = """loop.py, the everyday command (python3 -I loop/scripts/loop.py <word>):
  next      the one thing to do now
  status    every step, every line, met or not, and where we are on the road
  go        take the next step Claude can do alone
  ledger    the newest mission ledger entry; ledger add DATE "your words" adds one
  abandon   abandon <unit> "why": close a stuck piece of work, with the reason
  redo      redo <unit>: start it again under a new name, the old promise as a draft
  activity  the page of what the agent did, newest first: loop/activity.html
  small     small "what": a small change on the light track: a short promise, the checks still run
  decisions one line per decision you made (DECISIONS.md)
  archive   fold the finished phases of the road to one line each
  size      flag a step or a piece of work that is too big, with a proposed split
  help      this list"""


def work_in_progress(root):
    """[(unit, 'open' | 'draft')]: pieces of work written but not closed. Open means its promise is frozen."""
    out = []
    for f in sorted((Path(root) / "loop" / "qa" / "units").glob("*.json")):
        try:
            u = json.loads(f.read_text())
        except Exception:
            u = {}
        if "result" not in u:
            out.append((f.stem, "open" if (Path(root) / "loop" / "state" / "opened" / f.name).exists() else "draft"))
    return out


def the_map(root):
    import contextlib
    import io
    import build_donemap as BM
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return BM.build(root)
    except SystemExit:
        return None


def next_action(root):
    """The one suggested next action, one line, from the files."""
    root = Path(root)
    D = the_map(root)
    if D is None:
        return f"the done map does not build: fix `loop/qa/done-rules.json` (`{S}build_donemap.py --status` says why)"
    wip = work_in_progress(root)
    for u, kind in wip:
        if kind == "open" and u.startswith("small-"):
            return f"finish the small change {u}, then close it (`{S}qa.py close {u}`) and commit once"
        if kind == "open":
            return (f"finish the piece of work {u}: review it (`{S}review_check.py run {u} <files>`), answer the review,"
                    f" then close it (`{S}qa.py close {u}`); stuck: `loop.py abandon {u} \"why\"`")
    for u, kind in wip:
        return f"fix the drafted promise {u} (`loop/qa/units/{u}.json`), then stamp it: `{S}qa.py open {u}`"
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout.strip()
    if dirty:
        return "files are changed but not committed: finish that work and commit it, or ask what it was (`git status`)"
    if D["done"]:
        return "every step on the map is done: say what comes next, in your words; it becomes a new step"
    by = {s["id"]: s for s in D["steps"]}
    if D["next_agent"]:
        return f"say `go`: Claude takes step {D['next_agent']} '{by[D['next_agent']]['name']}'"
    if D["next"]:
        s = by[D["next"]]
        first = next((x["what"] for x in s["lines"] if not x["met"]), "")
        return f"step {s['id']} '{s['name']}' needs you" + (f": {first}" if first else "")
    return f"no step can start: `{S}loop.py status` shows what waits on what"


def go(root):
    """Where a piece of work starts: the work in progress first, else the next step Claude can take alone."""
    D = the_map(root)
    if D is None or work_in_progress(root) or not D["next_agent"]:
        return 1, "go: " + next_action(root)
    import draft
    s = next(x for x in D["steps"] if x["id"] == D["next_agent"])
    code, text = draft.draft(root, s["id"])
    return code, (f"go: step {s['id']} '{s['name']}' ({s['met']} of {s['of']} lines met)\n{text}\n"
                  f"  then build, `{S}review_check.py run <unit> <files>`, `{S}qa.py close <unit>`")


def main(argv, root=None):
    root = Path(root or kit.ROOT)
    word = argv[0] if argv else "next"
    if word == "selftest":
        return selftest()
    if word == "next":
        print("next: " + next_action(root))
        return 0
    if word == "status":
        import build_donemap as BM
        import growth
        D = the_map(root)
        print("\n".join(growth.status_lines(root, BM.build(root, live=True), "--all" in argv)) if D else "next: " + next_action(root))
        return 0 if D else 1
    if word == "small":
        import draft
        if len(argv) not in (2, 4):
            print('usage: loop.py small "what the change is" [--check "<cmd>"]')
            return 2
        code, text = draft.small(root, argv[1], argv[3] if len(argv) == 4 and argv[2] == "--check" else None)
        print(text)
        return code
    if word in ("archive", "size", "decisions"):
        import growth
        return growth.main(argv, root)
    if word == "go":
        code, text = go(root)
        print(text)
        return code
    if word in ("abandon", "redo"):
        import recover
        code, text = (recover.abandon(root, *argv[1:3]) if word == "abandon" and len(argv) == 3
                      else recover.redo(root, *argv[1:3]) if word == "redo" and len(argv) in (2, 3)
                      else (2, 'usage: loop.py abandon <unit> "why" | loop.py redo <unit> [new]'))
        print(text)
        return code
    if word == "activity":
        import activity
        print(f"activity: {activity.build(root).relative_to(root)} (open it in a browser)")
        return 0
    if word == "ledger":
        import index
        return index.main(["ledger", *argv[1:]])
    print(HELP)
    return 0 if word in ("help", "-h", "--help") else 2


def plant(td, steps=None):
    """A small project in a temp folder, the kit's scripts copied in, one commit made. Other selftests use it."""
    import shutil
    root = Path(td)
    shutil.copytree(HERE, root / "loop" / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    for d in ("units", "answers"):
        (root / "loop" / "qa" / d).mkdir(parents=True, exist_ok=True)
    (root / "loop" / "reviews").mkdir(exist_ok=True)
    (root / "loop" / "qa" / "done-rules.json").write_text(json.dumps({"project": "t", "steps": steps or [
        {"id": "s1", "name": "the first file", "done_when": [{"what": "a.txt exists", "file": "a.txt"}]},
        {"id": "s2", "name": "the owner's look", "needs_owner": True, "waits_on": ["s1"],
         "done_when": [{"what": "b.txt exists", "file": "b.txt"}]}]}))
    (root / "loop" / "HANDOFF.md").write_text("# NOW\n**Where we are (t):** planted\n")
    (root / ".gitignore").write_text("/loop/state/\n__pycache__/\n")
    sh(root, "git", "init", "-q", "-b", "main")
    commit(root, "init")
    return root


def sh(root, *a):
    return subprocess.run(list(a), cwd=root, capture_output=True, text=True)


def commit(root, msg):
    sh(root, "git", "add", "-A")
    return sh(root, "git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", msg)


def selftest():
    import os
    import tempfile
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    with tempfile.TemporaryDirectory() as td:
        root = plant(td)
        os.environ["LOOP_CATCHES"] = str(root / "catches.csv")
        say = lambda *w: sh(root, sys.executable, "-I", "loop/scripts/loop.py", *w)
        out = say("next").stdout
        must("say `go`" in out and "s1" in out, f"a fresh project: the next action is go on s1 ({out.strip()})")
        r = say("go")
        must(r.returncode == 0 and "s1" in r.stdout and "qa.py open" in r.stdout, "go names s1 and the steps in order")
        last = sh(root, sys.executable, "-I", "loop/scripts/brief.py").stdout.strip().splitlines()[-1]
        must(last.startswith("--- next:") and "s1" in last, f"the start screen ends with the next action ({last})")
        out = say("next").stdout
        must("drafted promise s1-1" in out and "qa.py open s1-1" in out, "a promise not yet stamped: fix it, then stamp it")
        (root / "loop" / "state" / "opened").mkdir(parents=True)
        (root / "loop" / "state" / "opened" / "s1-1.json").write_text("{}")
        out = say("next").stdout
        must("finish the piece of work s1-1" in out and "qa.py close s1-1" in out, "an open piece of work: finish it first")
        must(say("go").returncode == 1, "go refuses a new step while a piece of work is open")
        (root / "loop" / "qa" / "units" / "s1-1.json").unlink()
        (root / "a.txt").write_text("x")
        out = say("next").stdout
        must("not committed" in out, "an uncommitted change is named before a new step")
        commit(root, "a")
        out = say("next").stdout
        must("s2" in out and "needs you" in out and "b.txt" in out, f"only the owner's step is left: it needs you ({out.strip()})")
        (root / "b.txt").write_text("x")
        commit(root, "b")
        must("every step on the map is done" in say("next").stdout, "a finished map says so")
        say("ledger", "add", "2026-11-16", "the words exactly")
        must("the words exactly" in say("ledger").stdout, "ledger add writes an entry and ledger shows the newest")
        must(say("nonsense").returncode == 2 and "next" in say("help").stdout, "help lists the words; an unknown word exits 2")
        del os.environ["LOOP_CATCHES"]
    print(f"loop selftest: {'ALL GREEN' if not bad else 'FAILED: ' + '; '.join(bad)} · {n} controls")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
