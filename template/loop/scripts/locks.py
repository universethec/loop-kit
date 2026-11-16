# The commit locks, run by .claude/githooks/pre-commit on what is staged (and the subject cap, by commit-msg).
# Each refuses a commit that would weaken what keeps the project honest; every refusal is logged (kit.catch).
#
#   locks.py                  check the staged files            locks.py subject <msgfile>   the subject cap
#   locks.py selftest         every lock refuses its planted break
#
# 1. done-rules: no step removed; a step's done_when lines and waits_on only grow; needs_alex never goes true -> false.
# 2. DECISIONS.md is append-only: no line removed (a line may grow, e.g. a '(replaced by D7)' mark at its end).
# 3. Sizes (kit.json): CLAUDE.md <= 200 lines, loop/HANDOFF.md <= 20, memory.json <= 12 rules, headlines <= 170 chars.
# 4. A lock (the kit's scripts, kit.json, loop.sh, settings, githooks) changes only by Alex's own hand.
# 5. No new entry at the repo root outside kit.json root_ok.       6. A commit subject over kit.json subject_max (100).
# Alex's own hand: LOOP_ALEX=1 in his environment skips 1, 2, 4 and 5; the tool guard refuses that token from a session.
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402
from guard_tool import LOCKS, WRITTEN_BY_SCRIPTS  # noqa: E402

RULES = "loop/qa/done-rules.json"
COMMIT_LOCKS = [x for x in LOCKS if x not in WRITTEN_BY_SCRIPTS]


def git(root, *a):
    r = subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)
    return r.returncode, r.stdout


def staged(root):
    _, out = git(root, "diff", "--cached", "--name-status", "-M")
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        st = parts[0][0]
        rows.append((st, parts[-1], parts[1] if st == "R" else parts[-1]))
    return rows


def shown(root, rev, path):
    rc, out = git(root, "show", f"{rev}:{path}")
    return out if rc == 0 else None


def check_rules(old, new):
    if old is None:
        return []
    try:
        O, N = json.loads(old), json.loads(new)
    except Exception:
        return ["done-rules: not JSON"]
    out = []
    nb = {s.get("id"): s for s in N.get("steps", [])}
    canon = lambda x: json.dumps(x, sort_keys=True)
    for s in O.get("steps", []):
        n = nb.get(s.get("id"))
        if n is None:
            out.append(f"done-rules: step '{s.get('id')}' was removed; adding is free, removing needs Alex's own hand")
            continue
        newlines = [canon(x) for x in n.get("done_when", [])]
        for x in s.get("done_when", []):
            if canon(x) in newlines:
                newlines.remove(canon(x))
            else:
                out.append(f"done-rules: step '{s['id']}' lost or changed a line ({kit.describe(x)[:70]})")
        gone = set(s.get("waits_on", [])) - set(n.get("waits_on", []))
        if gone:
            out.append(f"done-rules: step '{s['id']}' no longer waits on {sorted(gone)}")
        if s.get("needs_alex") and not n.get("needs_alex"):
            out.append(f"done-rules: step '{s['id']}' no longer needs Alex")
    return out


def check_decisions(diff):
    removed = [l[1:].strip() for l in diff.splitlines() if l.startswith("-") and not l.startswith("---") and l[1:].strip()]
    added = [l[1:].strip() for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    return [f"DECISIONS.md: a line was removed (“{r[:70]}”); a decision is replaced by a new one and marked, never deleted"
            for r in removed if not any(a.startswith(r) for a in added)]


def check_text(path, text, c):
    out = []
    cap = c["caps"].get(path)
    if cap and len(text.splitlines()) > cap:
        out.append(f"{path}: {len(text.splitlines())} lines, the cap is {cap}")
    if path == "loop/qa/memory.json":
        try:
            rules = json.loads(text)["rules"]
        except Exception:
            return out + ["loop/qa/memory.json: not valid (needs a 'rules' list)"]
        if len(rules) > c["max_rules"]:
            out.append(f"loop/qa/memory.json: {len(rules)} rules, the cap is {c['max_rules']}")
        out += [f"loop/qa/memory.json: rule '{r.get('id')}' headline is {len(r.get('headline', ''))} chars (cap {c['headline_max']}, and not empty)"
                for r in rules if not r.get("headline") or len(r["headline"]) > c["headline_max"]]
    return out


def is_lock(path):
    return any(path == x.rstrip("/") or (x.endswith("/") and path.startswith(x)) for x in COMMIT_LOCKS)


def check(root):
    c = kit.conf(root)
    alex = os.environ.get("LOOP_ALEX") == "1"
    first = git(root, "rev-parse", "--verify", "-q", "HEAD")[0] != 0
    out = []  # (check id, problem)
    for st, path, old in staged(root):
        if not alex and not first and (is_lock(path) or is_lock(old)):
            out.append(("locks:lock-changed", f"{path}: a lock changes only by Alex's own hand"))
        if not alex and st in ("A", "R") and "/" not in path and path not in c["root_ok"]:
            out.append(("locks:root-entry", f"{path}: a new entry at the repo root (kit.json root_ok)"))
        new = shown(root, "", path) if st != "D" else None
        if not alex and old == RULES and (st in ("D", "R")):
            out.append(("locks:rules-weakened", "done-rules: the file was deleted or renamed"))
        elif not alex and path == RULES:
            out += [("locks:rules-weakened", p) for p in check_rules(shown(root, "HEAD", old), new)]
        if not alex and path == "DECISIONS.md" and st in ("M", "D"):
            _, d = git(root, "diff", "--cached", "-U0", "--", "DECISIONS.md")
            out += [("locks:decisions-append-only", p) for p in check_decisions(d)]
        if new is not None:
            out += [("locks:size-cap", p) for p in check_text(path, new, c)]
    return out


def subject(root, msgfile):
    c = kit.conf(root)
    lines = [l for l in Path(msgfile).read_text().splitlines() if not l.startswith("#")]
    subj = lines[0] if lines else ""
    if len(subj) > c["subject_max"]:
        kit.catch("locks:subject-cap", f"{len(subj)} chars: {subj[:80]}", root=root)
        print(f"  commit BLOCKED — the subject is {len(subj)} chars; the cap is {c['subject_max']}. Say it shorter; detail goes in the body.")
        return 1
    if not subj.strip():
        print("  commit BLOCKED — empty subject.")
        return 1
    return 0


def selftest():
    import tempfile
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    R = {"steps": [{"id": "a", "done_when": [{"file": "x"}], "waits_on": [], "needs_alex": True}, {"id": "b", "done_when": [{"file": "y"}], "waits_on": ["a"]}]}
    cp = lambda: json.loads(json.dumps(R))
    must(check_rules(json.dumps(R), json.dumps(R)) == [], "unchanged rules pass")
    R1 = cp(); R1["steps"].append({"id": "c", "done_when": [{"file": "z"}]}); R1["steps"][0]["done_when"].append({"file": "w"})
    must(check_rules(json.dumps(R), json.dumps(R1)) == [], "an added step and an added line pass")
    R2 = cp(); R2["steps"].pop(1)
    must(check_rules(json.dumps(R), json.dumps(R2)), "a removed step is refused")
    R3 = cp(); R3["steps"][0]["done_when"] = [{"file": "other"}]
    must(check_rules(json.dumps(R), json.dumps(R3)), "a changed line is refused")
    R4 = cp(); R4["steps"][1]["waits_on"] = []
    must(check_rules(json.dumps(R), json.dumps(R4)), "a dropped wait is refused")
    R5 = cp(); R5["steps"][0]["needs_alex"] = False
    must(check_rules(json.dumps(R), json.dumps(R5)), "needs_alex true -> false is refused")
    must(check_decisions("--- a\n+++ b\n-D1 old\n+D1 old (replaced by D2)\n") == [], "a decision marked replaced passes")
    must(check_decisions("--- a\n+++ b\n-D1 old\n+D1 new wording\n"), "a reworded decision is refused")
    c = dict(kit.DEFAULTS)
    must(check_text("CLAUDE.md", "x\n" * 201, c), "a 201-line CLAUDE.md is refused")
    must(check_text("loop/HANDOFF.md", "x\n" * 21, c), "a 21-line NOW is refused")
    must(check_text("loop/qa/memory.json", json.dumps({"rules": [{"id": "r", "headline": "h"}] * 13}), c), "13 working rules are refused")
    must(check_text("loop/qa/memory.json", json.dumps({"rules": [{"id": "r", "headline": "h" * 171}]}), c), "a 171-char headline is refused")
    must(check_text("loop/qa/memory.json", json.dumps({"rules": [{"id": "r", "headline": "h" * 170}]}), c) == [], "a 170-char headline passes")
    import contextlib
    import io
    outer = os.environ.pop("LOOP_ALEX", None)  # a selftest run under Alex's hand must still see the locks refuse
    with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(io.StringIO()):
        root = Path(td) / "repo"
        root.mkdir()
        os.environ["LOOP_CATCHES"] = str(Path(td) / "catches.csv")
        msg = Path(td) / "msg.txt"
        msg.write_text("x" * 101 + "\n\nbody\n")
        must(subject(root, msg) == 1, "a 101-char subject is refused")
        must("locks:subject-cap" in (Path(td) / "catches.csv").read_text(), "the subject refusal lands in the catch log")
        msg.write_text("x" * 100 + "\n\n" + "body " * 50 + "\n")
        must(subject(root, msg) == 0, "a 100-char subject with a long body passes")
        msg.write_text("# a comment line git strips\n" + "x" * 60 + "\n")
        must(subject(root, msg) == 0, "comment lines are not the subject")
        sh = lambda *a: subprocess.run(a, cwd=root, capture_output=True, text=True)
        sh("git", "init", "-q", "-b", "main")
        (root / "loop" / "scripts").mkdir(parents=True)
        (root / "loop" / "scripts" / "qa.py").write_text("v1")
        (root / "CLAUDE.md").write_text("x")
        sh("git", "add", "-A")
        must(check(root) == [], "the first commit passes (nothing to weaken yet)")
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")
        (root / "loop" / "qa").mkdir(parents=True)
        (root / "loop" / "qa" / "done-map.json").write_text("{}")
        sh("git", "add", "-A")
        must(check(root) == [], "a rebuilt done map commits freely (scripts write it; only hand edits are refused)")
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "map")
        (root / "loop" / "scripts" / "qa.py").write_text("v2")
        (root / "stray.txt").write_text("x")
        sh("git", "add", "-A")
        ids = [i for i, _ in check(root)]
        must("locks:lock-changed" in ids, "a staged change to a lock is refused")
        must("locks:root-entry" in ids, "a new root entry is refused")
        os.environ["LOOP_ALEX"] = "1"
        must(check(root) == [], "Alex's own hand passes both")
        del os.environ["LOOP_ALEX"]
        del os.environ["LOOP_CATCHES"]
    if outer is not None:
        os.environ["LOOP_ALEX"] = outer
    if bad:
        print("locks selftest: FAILED: " + "; ".join(bad))
        return 1
    print(f"locks selftest: ALL GREEN · {n} controls")
    return 0


def main(argv):
    root = kit.ROOT
    if argv[:1] == ["selftest"]:
        return selftest()
    if len(argv) == 2 and argv[0] == "subject":
        return subject(root, argv[1])
    p = check(root)
    for cid, what in p:
        kit.catch(cid, what, root=root)
    if p:
        print("  commit BLOCKED — a lock refused it (loop/scripts/locks.py):\n    " + "\n    ".join(w for _, w in p))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
