# Growth: what keeps a project readable as it gets big. The owner, on "Growth": "100%".
#
#   growth.py archive [--date D]   phases whose steps are all done go on the road's archive list; they stop
#                                  printing in full (status shows one line each). The road itself is not changed.
#   growth.py size                 a step with too many done lines, or a piece of work whose promise touches too
#                                  many files, is flagged with a proposed split; exit 1 when something is flagged
#   growth.py decisions            one line per decision in DECISIONS.md (number, date, the first words)
#   growth.py selftest             planted: a done phase is archived and collapses; a big step is flagged with a
#                                  split; the decisions list; a cap keeps the last line
#
# Caps (loop/kit.json, defaults here): step_max_lines 6, promise_max_files 8, status_max_lines 80,
# screen_max_lines 60 (the start screen, brief.py). Stdlib only; loop.py calls it (archive, size, decisions, status).
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402

CAPS = {"step_max_lines": 6, "promise_max_files": 8, "status_max_lines": 80, "screen_max_lines": 60}


def caps(root):
    c = kit.conf(root)
    return {k: int(c.get(k, v)) for k, v in CAPS.items()}


def cap(lines, n, hint):
    """At most n lines; the last line is always kept (the start screen ends with the next action)."""
    if len(lines) <= n:
        return lines
    return lines[:n - 2] + [f"  ({len(lines) - n + 1} more lines not shown: {hint})", lines[-1]]


def road(root):
    f = Path(root) / "loop" / "roadmap.json"
    return json.loads(f.read_text()) if f.exists() else None


def archived(root):
    R = road(root) or {}
    return {a["id"]: a for a in R.get("archived", [])}


def archive(root, date=None):
    """-> (code, text). Puts every finished phase (its steps done and its marks true) on the archive list."""
    import roadmap
    R = road(root)
    if R is None:
        return 2, "archive: no loop/roadmap.json"
    cfg = roadmap.Cfg(root)
    C = roadmap.build(cfg)[1]
    have = archived(root)
    new = [p for p in C["phases"] if p["done"] and p["id"] not in have]
    if not new:
        return 0, "archive: no finished phase to archive"
    date = date or dt.date.today().isoformat()
    R["archived"] = list(have.values()) + [{"id": p["id"], "name": p["name"], "steps": len(p["steps"]), "date": date} for p in new]
    (Path(root) / "loop" / "roadmap.json").write_text(json.dumps(R, ensure_ascii=False, indent=1) + "\n")
    roadmap.write(cfg)
    return 0, "archive: " + "; ".join(f"phase '{p['name']}' ({len(p['steps'])} steps, all done)" for p in new)


def status_lines(root, D, show_all=False):
    """loop.py status: the map with archived phases folded to one line each, capped."""
    import build_donemap as BM
    A, R = archived(root), road(root) or {}
    folded = {s for p in R.get("phases", []) if p["id"] in A for s in p.get("steps", [])}
    out = [BM.headline(D)] + BM.road_line(root) + [BM.step_line(s) for s in D["steps"] if s["id"] not in folded]
    out += [f"  [archived ] phase '{a['name']}': {a['steps']} steps, all done ({a['date']})" for a in A.values()]
    out += [f"  TOO BIG: {x}" for x in too_big(root, D)]
    return out if show_all else cap(out + [""], caps(root)["status_max_lines"], "loop.py status --all")[:-1]


def paths_of(line):
    return [line[k] for k in ("file", "grep", "git", "json") if isinstance(line.get(k), str)]


def too_big(root, D=None):
    """Flags, each with a proposed split: a step over step_max_lines done lines, a promise over promise_max_files."""
    root, C = Path(root), caps(root)
    out = []
    try:
        rules = json.loads((root / "loop" / "qa" / "done-rules.json").read_text())["steps"]
    except Exception:
        rules = []
    for s in rules:
        n = len(s.get("done_when", []))
        if n > C["step_max_lines"]:
            k = (n + 1) // 2
            out.append(f"step {s['id']} has {n} done lines (cap {C['step_max_lines']}): split it into {s['id']}-a "
                       f"(lines 1 to {k}, '{s['done_when'][0].get('what', '')}' first) and {s['id']}-b (lines {k + 1} to {n}, "
                       f"waiting on {s['id']}-a), each its own step")
    for f in sorted((root / "loop" / "qa" / "units").glob("*.json")):
        try:
            u = json.loads(f.read_text())
        except Exception:
            continue
        if "result" in u:
            continue
        touched = {p for ln in u.get("promise", []) if isinstance(ln, dict) for p in paths_of(ln)}
        if (root / "loop" / "state" / "opened" / f.name).exists():
            import subprocess
            por = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=root, capture_output=True, text=True).stdout
            touched |= {x[3:].strip() for x in por.splitlines() if x.strip() and not x[3:].startswith("loop/")}
        if len(touched) > C["promise_max_files"]:
            out.append(f"the piece of work {f.stem} touches {len(touched)} files (cap {C['promise_max_files']}): close what is "
                       f"done as one piece, and promise the rest as a second piece (`loop.py redo {f.stem}` starts it)")
    return out


DEC = re.compile(r"^(D\d+)\s*\(([^)]*)\):\s*(.*)")


def decisions(root):
    f = Path(root) / "DECISIONS.md"
    rows = [DEC.match(x) for x in (f.read_text().splitlines() if f.exists() else [])]
    out = [f"{m[1]:>4} {m[2]:10} {m[3][:100]}{' …' if len(m[3]) > 100 else ''}" for m in rows if m]
    return out or ["(no decisions yet in DECISIONS.md)"]


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
        lines = [{"what": f"f{i} exists", "file": f"f{i}.txt"} for i in range(8)]
        root = loop.plant(td, steps=[{"id": "s1", "name": "the first file", "done_when": [{"what": "a.txt exists", "file": "a.txt"}]},
                                     {"id": "s2", "name": "eight files", "waits_on": ["s1"], "done_when": lines}])
        os.environ["LOOP_CATCHES"] = str(root / "catches.csv")
        ph = lambda i, s: {"id": i, "name": f"Phase {i}", "plain": "p", "done_means": "d", "steps": [s], "marks": [], "notes": []}
        (root / "loop" / "roadmap.json").write_text(json.dumps({"project": "t", "phases": [ph("p1", "s1"), ph("p2", "s2")], "versions": []}))
        (root / "DECISIONS.md").write_text("# t\n\nD1 (2026-11-16): the mission, kept short\nD2 (2026-11-17): a second one (replaced by D3)\n")
        run = lambda *a: loop.sh(root, sys.executable, "-I", "loop/scripts/" + a[0], *a[1:])
        run("build_donemap.py")
        must("no finished phase" in archive(root)[1], "nothing is archived while no phase is done")
        (root / "a.txt").write_text("x")
        loop.commit(root, "a")
        run("build_donemap.py")
        code, text = archive(root, "2026-11-16")
        must(code == 0 and "Phase p1" in text and list(archived(root)) == ["p1"], f"a finished phase is archived ({text})")
        D = loop.the_map(root)
        st = status_lines(root, D, show_all=True)
        must(any("[archived ] phase 'Phase p1'" in x for x in st) and not any("'the first file'" in x for x in st),
             "status folds the archived phase to one line")
        flags = too_big(root)
        must(len(flags) == 1 and "s2 has 8 done lines" in flags[0] and "s2-a" in flags[0] and "s2-b" in flags[0],
             f"a step over the cap is flagged with a split ({flags})")
        u = {"unit": "w1", "step": "s2", "promise": [{"what": f"g{i}", "file": f"g{i}.txt"} for i in range(9)]}
        (root / "loop" / "qa" / "units" / "w1.json").write_text(json.dumps(u))
        must(any("w1 touches 9 files" in x for x in too_big(root)), "a promise over the file cap is flagged")
        d = decisions(root)
        must(len(d) == 2 and d[0].split()[0] == "D1" and "replaced by D3" in d[1], f"one line per decision ({d})")
        c = cap([str(i) for i in range(10)] + ["--- next: x"], 6, "more")
        must(len(c) == 6 and c[-1] == "--- next: x" and "not shown" in c[-2], "a cap keeps the last line and says what it cut")
        del os.environ["LOOP_CATCHES"]
    print(f"growth selftest: {'ALL GREEN' if not bad else 'FAILED: ' + '; '.join(bad)} · {n} controls")
    return 1 if bad else 0


def main(argv, root=None):
    root = Path(root or kit.ROOT)
    word = argv[0] if argv else "size"
    if word == "selftest":
        return selftest()
    if word == "archive":
        code, text = archive(root, argv[argv.index("--date") + 1] if "--date" in argv else None)
        print(text)
        return code
    if word == "size":
        flags = too_big(root)
        print("\n".join(f"too big: {x}" for x in flags) or "size: no step or piece of work is over its cap")
        return 1 if flags else 0
    if word == "decisions":
        print("\n".join(decisions(root)))
        return 0
    print("usage: growth.py archive [--date D] | size | decisions | selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
