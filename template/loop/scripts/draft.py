# The first draft of a promise, so a piece of work never starts from a blank page. It reads the done map and writes
# loop/qa/units/<unit>.json for a step: the step's open lines as checkable lines, the map line (the step advances by
# one more line met), the review line, and DRAFT words where only the session can say what it will make. The session
# fixes every DRAFT line, then stamps it with `qa.py open <unit>`, which refuses a promise that still says DRAFT.
#
#   draft.py <step> [unit]    write the draft (unit defaults to <step>-1, -2, ...); never overwrites a file
#   draft.py small "<what>" [--check "<cmd>"]   the light track for a small change: no interview, no step; a short
#                             promise (the project's checks, kit.json small_checks, and your own check) written and opened
#   draft.py selftest         planted: a draft is refused until fixed, then opens; a second draft gets a new name
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402

MAP = "python3 -I loop/scripts/build_donemap.py"
REVIEW = "python3 -I loop/scripts/review_check.py check"


def units_dir(root):
    return Path(root) / "loop" / "qa" / "units"


def free_name(root, step):
    n = 1
    while (units_dir(root) / f"{step}-{n}.json").exists():
        n += 1
    return f"{step}-{n}"


def draft(root, step, unit=None):
    """-> (exit code, text). Writes the draft for one step of the done map."""
    import loop
    root = Path(root)
    D = loop.the_map(root)
    if D is None:
        return 1, "draft: the done map does not build"
    s = next((x for x in D["steps"] if x["id"] == step), None)
    if s is None:
        return 2, f"draft: no step {step!r} on the done map ({', '.join(x['id'] for x in D['steps'])})"
    unit = unit or free_name(root, step)
    f = units_dir(root) / f"{unit}.json"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", unit) or f.exists():
        return 2, f"draft: {unit} is taken or not a plain name; a new piece of work gets a new name"
    rules = json.loads((root / "loop" / "qa" / "done-rules.json").read_text())
    lines = next(x for x in rules["steps"] if x["id"] == step)["done_when"]
    open_ = [ln for ln, row in zip(lines, s["lines"]) if not row["met"]]
    first = open_[0].get("what", "") if open_ else ""
    goal = (f"--filled {step}" if len(open_) <= 1 else f"--advanced {step} {s['met'] + 1}")
    u = {"unit": unit, "step": step,
         "what": f"DRAFT: one sentence on what this piece of work makes for '{s['name']}' (first open line: {first})",
         "plain": ["DRAFT: what changed, in words a friend who never saw the project understands",
                   "DRAFT: what you, the owner, can look at to see it",
                   "DRAFT: what is next"],
         "promise": [*open_[:1],
                     {"what": f"step {step} has one more line met on the done map", "cmd": f"{MAP} {goal}"},
                     {"what": "every point the blind review raised is answered", "cmd": f"{REVIEW} {unit}"}]}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(u, ensure_ascii=False, indent=1) + "\n")
    return 0, (f"draft: loop/qa/units/{unit}.json for step {step} '{s['name']}'\n"
               f"  fix every DRAFT line (and sharpen the checkable lines), then: python3 -I loop/scripts/qa.py open {unit}")


def small(root, what, check=None):
    """-> (exit code, text). The light track: a short promise for a small change, opened at once. The checks still run."""
    import subprocess
    import qa
    root = Path(root)
    if len(what.strip()) < 12:
        return 2, "small: say what the change is in a sentence (at least 12 characters)"
    unit = free_name(root, "small")
    guard = kit.conf(root).get("small_checks", qa.SMALL_CHECKS)
    u = {"unit": unit, "kind": "small", "what": what.strip(),
         "plain": [f"a small change: {what.strip()}", "you can see it in the commit it lands in (git show)",
                   "next: back to the map, the start screen says what"],
         "promise": [{"what": "the project's checks and guards still pass", "cmd": guard}]
         + ([{"what": f"`{check}` passes", "cmd": check}] if check else [])}
    f = units_dir(root) / f"{unit}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(u, ensure_ascii=False, indent=1) + "\n")
    r = subprocess.run([sys.executable, "-I", str(HERE / "qa.py"), "open", unit], cwd=root, capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode != 0:
        return r.returncode, f"small: loop/qa/units/{unit}.json written but not opened: {last}"
    return 0, (f"small: {unit} opened ({len(u['promise'])} promise lines). Make the change, then "
               f"`python3 -I loop/scripts/qa.py close {unit}` and one commit")


def selftest():
    import os
    import tempfile
    import loop
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    with tempfile.TemporaryDirectory() as td:
        root = loop.plant(td, steps=[{"id": "s1", "name": "two files", "done_when": [
            {"what": "a.txt exists", "file": "a.txt"}, {"what": "c.txt exists", "file": "c.txt"}]}])
        os.environ["LOOP_CATCHES"] = str(root / "catches.csv")
        run = lambda *a: loop.sh(root, sys.executable, "-I", *a)
        r = run("loop/scripts/loop.py", "go")
        f = units_dir(root) / "s1-1.json"
        must(r.returncode == 0 and f.exists() and "qa.py open s1-1" in r.stdout, f"go drafts the promise for s1 ({r.stdout.strip()})")
        u = json.loads(f.read_text()) if f.exists() else {}
        cmds = " ".join(x.get("cmd", "") for x in u.get("promise", []))
        must("--advanced s1 1" in cmds and "check s1-1" in cmds and u.get("promise", [{}])[0].get("file") == "a.txt",
             "the draft holds the step's first open line, the map line and the review line")
        r = run("loop/scripts/qa.py", "open", "s1-1")
        must(r.returncode == 2 and "DRAFT" in r.stdout, "qa open refuses a promise that still says DRAFT")
        u["what"] = "make a.txt appear for the first of two files"
        u["plain"] = ["the file a.txt is there now", "you can open a.txt and read it", "next comes the file c.txt"]
        f.write_text(json.dumps(u))
        r = run("loop/scripts/qa.py", "open", "s1-1")
        must(r.returncode == 0, f"the fixed draft opens ({r.stdout.strip().splitlines()[-1]})")
        r = run("loop/scripts/draft.py", "s1")
        must(r.returncode == 0 and (units_dir(root) / "s1-2.json").exists() and json.loads(f.read_text())["what"] == u["what"],
             "a second draft gets a new name and never overwrites the first")
        must(run("loop/scripts/draft.py", "nope").returncode == 2, "a step not on the map is refused")
        (root / "loop" / "state" / "opened" / "s1-1.json").unlink()
        (root / "loop" / "kit.json").write_text(json.dumps({"small_checks": "test -f guard-ok.txt"}))
        r = run("loop/scripts/loop.py", "small", "fix the spelling of a word")
        must(r.returncode == 0 and "small-1 opened" in r.stdout, f"loop.py small writes and opens a short promise ({r.stdout.strip()})")
        r = run("loop/scripts/qa.py", "close", "small-1")
        must(r.returncode == 1 and "FAIL" in r.stdout, "the light track's close still fails when a planted check fails")
        (root / "guard-ok.txt").write_text("ok")
        run("loop/scripts/loop.py", "small", "fix the spelling of another word")
        must(run("loop/scripts/qa.py", "close", "small-2").returncode == 0, "the same close passes once the check passes")
        (units_dir(root) / "small-9.json").write_text(json.dumps({"unit": "small-9", "kind": "small", "what": "a promise with no checks line",
              "plain": ["a line of twelve chars", "a line of twelve chars", "a line of twelve chars"], "promise": [{"what": "x", "file": "a.txt"}]}))
        must(run("loop/scripts/qa.py", "open", "small-9").returncode == 2, "a small promise without the checks line is refused")
        del os.environ["LOOP_CATCHES"]
    print(f"draft selftest: {'ALL GREEN' if not bad else 'FAILED: ' + '; '.join(bad)} · {n} controls")
    return 1 if bad else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["selftest"]:
        sys.exit(selftest())
    if a[:1] == ["small"] and len(a) in (2, 4):
        code, text = small(kit.ROOT, a[1], a[3] if len(a) == 4 and a[2] == "--check" else None)
        print(text)
        sys.exit(code)
    if len(a) in (1, 2):
        code, text = draft(kit.ROOT, *a)
        print(text)
        sys.exit(code)
    print("usage: draft.py <step> [unit] | draft.py selftest")
    sys.exit(2)
