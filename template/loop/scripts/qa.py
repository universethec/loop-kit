# QA that survives sessions, lean: no session says how a unit went; this script does, from the files.
# A unit's promise is written BEFORE the work in loop/qa/units/<unit>.json; `open` freezes it; `close` runs every
# promise line and writes the result INTO that same file; the unit lands in ONE commit.
#
#   qa.py open <unit>    where we are + is the promise valid (exit 2 if not); freezes it (loop/state/opened/)
#   qa.py close <unit>   run the promise, write "result" into the unit file, rebuild the done map; exit 1 on a fail
#   qa.py hook           pre-commit: a staged unit is closed, and a committed unit never changes
#   qa.py selftest       planted failures: no promise, a changed promise, a failing line, a vacuous promise
#
# Unit file: {"unit": "u1", "step": "<done-map step>", "what": "one sentence", "plain": [three lines for Alex: what changed,
# what he can look at, what is next], "promise": [{"what": "...", <check>}]}. The step names its phase on the roadmap.
# The promise must hold the lines kit.json "promise_requires" names (default: build_donemap --advanced/--filled on
# its step, and review_check.py check <unit>). Checks: file / cmd / json / grep / git (kit.py).
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402
import build_donemap as BM  # noqa: E402

REQUIRES = [r"build_donemap\.py --(advanced|filled) {step}\b", r"review_check\.py check {unit}\b"]
MAP_LINE = r"build_donemap\.py --(advanced|filled) "


def unit_file(root, unit):
    return Path(root) / "loop" / "qa" / "units" / f"{unit}.json"


def opened_file(root, unit):
    return Path(root) / "loop" / "state" / "opened" / f"{unit}.json"


def promise_sha(u):
    core = {k: u.get(k) for k in ("unit", "step", "what", "promise")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def git(root, *a):
    r = subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)
    return r.returncode, r.stdout


def validate(root, unit, u):
    out = []
    if u.get("unit") != unit:
        out.append(f"'unit' must be {unit!r}")
    steps = {s["id"] for s in json.loads((Path(root) / "loop" / "qa" / "done-rules.json").read_text())["steps"]}
    if u.get("step") not in steps:
        out.append(f"'step' must be a done-map step ({', '.join(sorted(steps))})")
    if not isinstance(u.get("what"), str) or len(u.get("what", "")) < 12:
        out.append("'what': one sentence on what this unit makes")
    P = u.get("promise")
    if not isinstance(P, list) or not P:
        return out + ["'promise' is empty: say what a pass looks like, in checkable lines"]
    for i, ln in enumerate(P):
        out += [f"promise[{i}]: {p}" for p in kit.problems(ln)]
        if isinstance(ln, dict) and not ln.get("what"):
            out.append(f"promise[{i}]: no 'what' (the plain words for the line)")
    pl = u.get("plain")  # Alex, 2026-11-13: "I want as a rule everything that you do, to be human readable for me"
    if not (isinstance(pl, list) and len(pl) == 3 and all(isinstance(x, str) and len(x.strip()) >= 12 for x in pl)):
        out.append("'plain': three plain lines for Alex: what changed, what he can look at, what is next")
    cmds = " \n ".join(ln.get("cmd", "") for ln in P if isinstance(ln, dict))
    for pat in kit.conf(root).get("promise_requires", REQUIRES):
        rx = pat.replace("{step}", re.escape(str(u.get("step")))).replace("{unit}", re.escape(unit))
        if not re.search(rx, cmds):
            out.append(f"the promise needs a cmd line matching /{rx}/")
    return out


def where_we_are(root, unit):
    D = BM.build(root)
    print(BM.headline(D))
    now = Path(root) / "loop" / "HANDOFF.md"
    entry = next((x for x in now.read_text().splitlines() if x.startswith("**Where we are")), "") if now.exists() else ""
    print("NOW: " + (entry[:300] or "(no 'Where we are' entry)"))
    rc, por = git(root, "status", "--porcelain", "-uall")
    own = {f"loop/qa/units/{unit}.json", f"loop/qa/answers/{unit}.json"}
    other = [x for x in por.splitlines() if x.strip() and x[3:].strip() not in own]
    if rc == 0 and other:
        print(f"tree: DIRTY ({len(other)} file(s), first: {other[0][3:]}) · a session died mid-unit "
              f"({kit.current_unit(root)}): finish that unit before this one")
    return D


def open_(root, unit):
    D = where_we_are(root, unit)
    f = unit_file(root, unit)
    if not f.exists():
        print(f"qa open {unit}: NOT READY · no loop/qa/units/{unit}.json: write the promise before any work")
        kit.catch("qa:open-no-promise", f"{unit}: no promise file", unit, root)
        return 2
    try:
        u = json.loads(f.read_text())
    except Exception as e:
        print(f"qa open {unit}: NOT READY · not JSON ({e})")
        kit.catch("qa:open-no-promise", f"{unit}: not JSON", unit, root)
        return 2
    if "result" in u:
        print(f"qa open {unit}: REFUSED · this unit is closed; a new attempt is a new unit")
        return 2
    bad = validate(root, unit, u)
    if bad:
        print(f"qa open {unit}: NOT READY\n  " + "\n  ".join(bad))
        kit.catch("qa:open-no-promise", f"{unit}: {bad[0]}", unit, root)
        return 2
    sha = promise_sha(u)
    of = opened_file(root, unit)
    if of.exists() and json.loads(of.read_text())["sha"] != sha:
        print(f"qa open {unit}: REFUSED · the promise changed since it was opened; a changed promise is a new unit")
        kit.catch("qa:close-promise-changed", f"{unit}: re-open with a changed promise", unit, root)
        return 2
    step = next(s for s in D["steps"] if s["id"] == u["step"])
    if step["waits_open"]:
        print(f"qa open {unit}: REFUSED · step {u['step']} waits on {', '.join(step['waits_open'])}")
        kit.catch("map:require", f"{u['step']} waits on {', '.join(step['waits_open'])}", unit, root)
        return 2
    already = [ln["what"] for ln in u["promise"] if re.search(MAP_LINE, ln.get("cmd", "")) and kit.check(ln, root)[0]]
    if already:
        print(f"qa open {unit}: REFUSED · the map line already passes before any work, so it promises nothing: {already[0]}")
        kit.catch("qa:open-vacuous", f"{unit}: {already[0]}", unit, root)
        return 2
    if not of.exists():
        of.parent.mkdir(parents=True, exist_ok=True)
        _, head = git(root, "rev-parse", "--short", "HEAD")
        of.write_text(json.dumps({"unit": unit, "sha": sha, "at": dt.datetime.now().isoformat(timespec="seconds"), "head": head.strip()}) + "\n")
    (Path(root) / "loop" / "state" / "current-unit").write_text(unit + "\n")
    print(f"qa open {unit}: ok · step {u['step']} · {len(u['promise'])} promise lines, frozen from now on")
    return 0


def close_(root, unit):
    f, of = unit_file(root, unit), opened_file(root, unit)
    if not f.exists() or not of.exists():
        print(f"qa close {unit}: REFUSED · never opened (qa.py open {unit} first)")
        kit.catch("qa:close-unopened", unit, unit, root)
        return 1
    u = json.loads(f.read_text())
    O = json.loads(of.read_text())
    if promise_sha(u) != O["sha"]:
        print(f"qa close {unit}: REFUSED · the promise changed after qa open; the work is judged on what was promised")
        kit.catch("qa:close-promise-changed", unit, unit, root)
        return 1
    rows = []
    for ln in u["promise"]:
        ok, saw = kit.check(ln, root)
        rows.append({"what": ln["what"], "ok": ok, "saw": saw})
    passed = sum(r["ok"] for r in rows)
    overall = "pass" if passed == len(rows) else ("fail" if passed == 0 else "partial")
    _, head = git(root, "rev-parse", "--short", "HEAD")
    u["result"] = {"overall": overall, "passed": passed, "of": len(rows), "promise_sha": O["sha"],
                   "opened_at": O["at"], "closed_at": dt.datetime.now().isoformat(timespec="seconds"),
                   "head_before": head.strip(), "lines": rows}
    f.write_text(json.dumps(u, ensure_ascii=False, indent=1) + "\n")
    (Path(root) / "loop" / "state" / "current-unit").write_text("-\n")
    rc = subprocess.run([sys.executable, "-I", str(HERE / "build_donemap.py")], cwd=root, capture_output=True, text=True,
                        env={**__import__("os").environ, "LOOP_ROOT": str(root)})
    if (Path(root) / "loop" / "roadmap.json").exists():  # the dashboard's health row for today, at every close
        subprocess.run([sys.executable, "-I", str(HERE / "roadmap.py"), "--measure"], cwd=root, capture_output=True, text=True,
                       env={**__import__("os").environ, "LOOP_ROOT": str(root)})
    print(f"qa close {unit}: {overall} · {passed}/{len(rows)}")
    for r in rows:
        print(f"  {'ok  ' if r['ok'] else 'FAIL'}  {r['what']} · {r['saw']}")
    print("  " + (rc.stdout.strip() or rc.stderr.strip()))
    if isinstance(u.get("plain"), list):
        print("for Alex, in three lines:\n" + "\n".join("  " + x for x in u["plain"]))
    if overall != "pass":
        kit.catch("qa:close-failed", f"{unit}: {passed}/{len(rows)}", unit, root)
        return 1
    return 0


def hook_problems(root):
    _, out = git(root, "diff", "--cached", "--name-status")
    probs = []
    for line in out.splitlines():
        parts = line.split("\t")
        st, path = parts[0][0], parts[-1]
        if not re.fullmatch(r"loop/qa/units/[^/]+\.json", path) and not (st == "R" and re.fullmatch(r"loop/qa/units/[^/]+\.json", parts[1])):
            continue
        if st in ("D", "R"):
            probs.append(f"{path}: a unit never goes or moves")
            continue
        rc, _ = git(root, "cat-file", "-e", f"HEAD:{path}")
        if rc == 0:
            probs.append(f"{path}: a committed unit never changes; a new attempt is a new unit")
            continue
        _, txt = git(root, "show", f":{path}")
        try:
            u = json.loads(txt)
        except Exception:
            probs.append(f"{path}: not JSON")
            continue
        if "result" not in u:
            probs.append(f"{path}: not closed; a unit is committed once, after `qa.py close`")
        elif u["result"].get("promise_sha") != promise_sha(u):
            probs.append(f"{path}: the promise differs from the one the result was computed on")
    return probs


def hook(root):
    p = hook_problems(root)
    for x in p:
        kit.catch("qa:hook-unit", x, root=root)
    if p:
        print("  commit BLOCKED (qa.py hook):\n    " + "\n    ".join(p))
        return 1
    return 0


def selftest():
    import contextlib
    import io
    import os
    import shutil
    import tempfile
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        os.environ["LOOP_CATCHES"] = str(root / "catches.csv")
        shutil.copytree(HERE, root / "loop" / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        (root / "loop" / "qa" / "units").mkdir(parents=True)
        (root / "loop" / "qa" / "done-rules.json").write_text(json.dumps({"project": "t", "steps": [
            {"id": "s1", "name": "one", "done_when": [{"what": "a exists", "file": "a.txt"}, {"what": "b exists", "file": "b.txt"}]}]}))
        (root / "loop" / "HANDOFF.md").write_text("# NOW\n**Where we are (t):** planted\n")
        sh = lambda *a: subprocess.run(a, cwd=root, capture_output=True, text=True)
        sh("git", "init", "-q", "-b", "main")
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
        maps = lambda n_: {"what": "the step advanced", "cmd": f"python3 -I loop/scripts/build_donemap.py --advanced s1 {n_}"}
        rev = lambda u: {"what": "the review is answered", "cmd": f"python3 -I loop/scripts/review_check.py check {u}"}
        PL = ["what changed, in plain words", "what he can look at, in plain words", "what is next, in plain words"]
        write = lambda u, body: (root / "loop" / "qa" / "units" / f"{u}.json").write_text(json.dumps({"plain": PL, **body}))

        def run(cmd, unit):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                c = open_(root, unit) if cmd == "open" else close_(root, unit)
            return c, buf.getvalue()

        c, _ = run("open", "u0")
        must(c == 2, "open with no promise file exits 2")
        write("u1", {"unit": "u1", "step": "s1", "what": "make a.txt appear", "promise": [maps(1)]})
        c, out = run("open", "u1")
        must(c == 2 and "review_check" in out, "open refuses a promise without the review line")
        write("u1", {"unit": "u1", "step": "s1", "what": "make a.txt appear", "promise": [maps(1), rev("u1")], "plain": ["only one line, plain"]})
        c, out = run("open", "u1")
        must(c == 2 and "'plain'" in out, "open refuses a promise without three plain lines for Alex")
        write("u1", {"unit": "u1", "step": "s1", "what": "make a.txt appear", "promise": [maps(1), rev("u1")]})
        c, out = run("open", "u1")
        must(c == 0, f"open accepts a valid promise ({out.strip().splitlines()[-1]})")
        # a failing promise line fails close, and the result says so inside the unit file
        c, out = run("close", "u1")
        u = json.loads((root / "loop/qa/units/u1.json").read_text())
        must(c == 1 and u["result"]["overall"] == "fail", "a failing promise line fails close, recorded as fail in the unit file")
        # a promise changed after open is refused at close
        (root / "loop" / "kit.json").write_text(json.dumps({"promise_requires": [r"build_donemap\.py --(advanced|filled) {step}\b"]}))
        write("u2", {"unit": "u2", "step": "s1", "what": "make a.txt appear", "promise": [maps(1)]})
        c, _ = run("open", "u2")
        must(c == 0, "open accepts a promise meeting the project's own requires")
        write("u2", {"unit": "u2", "step": "s1", "what": "make a.txt appear", "promise": [maps(0)]})
        c, out = run("close", "u2")
        must(c == 1 and "changed" in out, "close refuses a promise changed after open")
        c, _ = run("close", "u9")
        must(c == 1, "close refuses a unit never opened")
        # the kept promise: a.txt appears, close passes
        write("u3", {"unit": "u3", "step": "s1", "what": "make a.txt appear", "promise": [maps(1)]})
        must(run("open", "u3")[0] == 0, "open u3")
        (root / "a.txt").write_text("x")
        c, out = run("close", "u3")
        must(c == 0 and json.loads((root / "loop/qa/units/u3.json").read_text())["result"]["overall"] == "pass", "a kept promise closes as pass")
        # vacuous: the map line already passes
        write("u4", {"unit": "u4", "step": "s1", "what": "nothing new at all", "promise": [maps(1)]})
        c, out = run("open", "u4")
        must(c == 2 and "already passes" in out, "open refuses a promise whose map line already passes")
        # the hook: an unclosed unit staged is refused; a closed one passes; a committed one never changes
        sh("git", "add", "loop/qa/units/u4.json")
        must(hook_problems(root), "the hook refuses a staged unit that is not closed")
        sh("git", "reset", "-q")
        sh("git", "add", "loop/qa/units/u3.json")
        must(hook_problems(root) == [], "the hook passes a closed unit")
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "u3")
        u3 = json.loads((root / "loop/qa/units/u3.json").read_text())
        u3["result"]["overall"] = "pass!"
        write("u3", u3)
        sh("git", "add", "loop/qa/units/u3.json")
        must(hook_problems(root), "the hook refuses a change to a committed unit")
        must((root / "catches.csv").exists() and "qa:close-failed" in (root / "catches.csv").read_text(), "refusals land in the catch log")
        del os.environ["LOOP_CATCHES"]
    if bad:
        print("qa selftest: FAILED: " + "; ".join(bad))
        return 1
    print(f"qa selftest: ALL GREEN · {n} controls")
    return 0


def main(argv):
    root = kit.ROOT
    if argv[:1] == ["selftest"]:
        return selftest()
    if argv[:1] == ["hook"]:
        return hook(root)
    if len(argv) == 2 and argv[0] in ("open", "close") and re.fullmatch(r"[A-Za-z0-9_.-]+", argv[1]):
        return open_(root, argv[1]) if argv[0] == "open" else close_(root, argv[1])
    print("usage: qa.py open <unit> | close <unit> | hook | selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
