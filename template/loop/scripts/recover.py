# When a piece of work goes wrong: close it honestly, or start it again, never edit a frozen promise.
#
#   recover.py abandon <unit> "why"    close a stuck piece of work with a reason (its result says abandoned); the
#                                      unit file is then committed like any closed one, and the work files are yours
#                                      to keep or put back (`git status`)
#   recover.py redo <unit> [new]       start it again under a new name: the old promise copied as a draft, marked
#                                      DRAFT, for the session to fix and stamp with `qa.py open <new>`
#   recover.py selftest                planted: abandon closes one and the commit check passes it; redo drafts a new one
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402

NAME = re.compile(r"[A-Za-z0-9_.-]+")


def files(root, unit):
    return (Path(root) / "loop" / "qa" / "units" / f"{unit}.json", Path(root) / "loop" / "state" / "opened" / f"{unit}.json")


def abandon(root, unit, why):
    import qa
    f, of = files(root, unit)
    if not NAME.fullmatch(unit) or not f.exists():
        return 2, f"abandon: no piece of work {unit!r} (loop/qa/units/)"
    u = json.loads(f.read_text())
    if "result" in u:
        return 2, f"abandon: {unit} is already closed ({u['result'].get('overall')}); to try again: loop.py redo {unit}"
    if len(why.strip()) < 12:
        return 2, "abandon: say why in a few words (at least 12 letters); the reason stays with the work"
    O = json.loads(of.read_text()) if of.exists() else {}
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    u["result"] = {"overall": "abandoned", "reason": why.strip(), "passed": 0, "of": len(u.get("promise") or []),
                   "promise_sha": O.get("sha") or qa.promise_sha(u), "opened_at": O.get("at", ""),
                   "closed_at": dt.datetime.now().isoformat(timespec="seconds"), "head_before": head, "lines": []}
    f.write_text(json.dumps(u, ensure_ascii=False, indent=1) + "\n")
    cur = Path(root) / "loop" / "state" / "current-unit"
    if kit.current_unit(root) == unit:
        cur.write_text("-\n")
    return 0, (f"abandon: {unit} closed as abandoned ({why.strip()[:80]})\n"
               f"  commit loop/qa/units/{unit}.json; keep or put back the work files yourself (git status shows them);"
               f" to try again: loop.py redo {unit}")


def redo(root, old, new=None):
    f, _ = files(root, old)
    if not NAME.fullmatch(old) or not f.exists():
        return 2, f"redo: no piece of work {old!r} (loop/qa/units/)"
    u = json.loads(f.read_text())
    r = u.get("result")
    if not r:
        return 2, f"redo: {old} is still open; close it first, or: loop.py abandon {old} \"why\""
    n = 1
    while not new and files(root, f"{old}-redo{n if n > 1 else ''}")[0].exists():
        n += 1
    new = new or f"{old}-redo{n if n > 1 else ''}"
    nf, _ = files(root, new)
    if not NAME.fullmatch(new) or nf.exists():
        return 2, f"redo: {new} is taken or not a plain name"
    why = r.get("reason") or f"{r.get('passed')} of {r.get('of')} promise lines passed at close"
    promise = [{**ln, "cmd": re.sub(rf"(review_check\.py check ){re.escape(old)}\b", rf"\g<1>{new}", ln["cmd"])} if "cmd" in ln else ln
               for ln in u.get("promise", [])]
    v = {"unit": new, "step": u.get("step"), "redo_of": old, **({"kind": u["kind"]} if u.get("kind") else {}),
         "what": f"DRAFT: redo of {old} ({why}): {u.get('what', '')}",
         "plain": [f"DRAFT: {x}" for x in (u.get("plain") or ["what changed", "what you can look at", "what is next"])],
         "promise": promise}
    nf.write_text(json.dumps(v, ensure_ascii=False, indent=1) + "\n")
    return 0, (f"redo: loop/qa/units/{new}.json drafted from {old} ({why})\n"
               f"  fix every DRAFT line and the promise lines that were wrong, then: python3 -I loop/scripts/qa.py open {new}")


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
        root = loop.plant(td)
        os.environ["LOOP_CATCHES"] = str(root / "catches.csv")
        run = lambda *a: loop.sh(root, sys.executable, "-I", "loop/scripts/loop.py", *a)
        run("go")
        f = root / "loop" / "qa" / "units" / "s1-1.json"
        u = json.loads(f.read_text())
        u.update(what="make a.txt appear, the first file", plain=["the file a.txt is there now", "you can open a.txt and read it", "next comes the owner's look"])
        f.write_text(json.dumps(u))
        must(loop.sh(root, sys.executable, "-I", "loop/scripts/qa.py", "open", "s1-1").returncode == 0, "the planted piece of work opens")
        must(run("abandon", "s1-1", "short").returncode == 2, "abandon refuses a reason too short to say anything")
        must(run("redo", "s1-1").returncode == 2, "redo refuses a piece of work still open")
        r = run("abandon", "s1-1", "the promise named the wrong file")
        u = json.loads(f.read_text())
        must(r.returncode == 0 and u.get("result", {}).get("overall") == "abandoned" and "wrong file" in u["result"]["reason"],
             "abandon closes it with the reason inside the unit file")
        import qa
        loop.sh(root, "git", "add", "loop/qa/units/s1-1.json")
        must(qa.hook_problems(root) == [], f"the commit check passes an abandoned piece of work ({qa.hook_problems(root)})")
        loop.commit(root, "abandon s1-1")
        must(kit.current_unit(root) == "-" and "say `go`" in run("next").stdout, "after abandon and its commit, the next action is go again")
        r = run("redo", "s1-1")
        v = json.loads((root / "loop/qa/units/s1-1-redo.json").read_text()) if r.returncode == 0 else {}
        cmds = " ".join(x.get("cmd", "") for x in v.get("promise", []))
        must(v.get("redo_of") == "s1-1" and "check s1-1-redo" in cmds and "DRAFT" in v.get("what", "") and "wrong file" in v["what"],
             "redo drafts a new piece of work from the old promise, the review line renamed, the reason kept")
        must(loop.sh(root, sys.executable, "-I", "loop/scripts/qa.py", "open", "s1-1-redo").returncode == 2, "the redo draft must be fixed before it opens")
        must(run("redo", "s1-1").returncode == 0 and (root / "loop/qa/units/s1-1-redo2.json").exists(), "a second redo gets its own name")
        del os.environ["LOOP_CATCHES"]
    print(f"recover selftest: {'ALL GREEN' if not bad else 'FAILED: ' + '; '.join(bad)} · {n} controls")
    return 1 if bad else 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["selftest"]:
        sys.exit(selftest())
    if len(a) == 3 and a[0] == "abandon":
        code, text = abandon(kit.ROOT, a[1], a[2])
    elif len(a) in (2, 3) and a[0] == "redo":
        code, text = redo(kit.ROOT, *a[1:])
    else:
        code, text = 2, 'usage: recover.py abandon <unit> "why" | redo <unit> [new] | selftest'
    print(text)
    sys.exit(code)
