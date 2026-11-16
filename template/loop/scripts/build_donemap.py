# The done map: what "done" means, computed from the files. loop/qa/done-rules.json lists steps; each step has
# checkable lines (done_when), may need Alex (needs_alex) and may wait on other steps (waits_on). A line is met
# only when its check passes, never because a sentence says so. Output: loop/qa/done-map.json (do not hand-edit).
#
#   build_donemap.py                 write the map          --check        fail if the map differs from a fresh build
#   build_donemap.py --status        every step             --brief        headline + startable steps only
#   build_donemap.py --next-agent    for loop.sh: exit 0 + step id (take it), 2 = only Alex can unblock, 3 = done
#   build_donemap.py --require S     exit 1 unless every step S waits on is done
#   build_donemap.py --filled S      exit 1 unless every line of S is met
#   build_donemap.py --advanced S N  exit 1 unless at least N lines of S are met
#   build_donemap.py selftest        planted maps: --next-agent 0/2/3, --brief keeps every startable step
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402


def paths(root):
    return Path(root) / "loop" / "qa" / "done-rules.json", Path(root) / "loop" / "qa" / "done-map.json"


def rule_problems(R):
    out, ids = [], set()
    for i, s in enumerate(R.get("steps", [])):
        sid = s.get("id")
        if not sid or sid in ids:
            out.append(f"step {i}: missing or repeated id {sid!r}")
        ids.add(sid)
        if not s.get("done_when"):
            out.append(f"step {sid}: no done_when line, so it could never be done")
        for j, ln in enumerate(s.get("done_when", [])):
            out += [f"step {sid} line {j}: {p}" for p in kit.problems(ln)]
    for s in R.get("steps", []):
        out += [f"step {s.get('id')}: waits on unknown step {w!r}" for w in s.get("waits_on", []) if w not in ids]
    if not R.get("steps"):
        out.append("no steps")
    return out


def build(root=None, rules=None, live=False):
    root = Path(root or kit.ROOT)
    R = rules if rules is not None else json.loads(paths(root)[0].read_text())
    bad = rule_problems(R)
    if bad:
        print("build_donemap: done-rules.json is not valid:\n  " + "\n  ".join(bad))
        sys.exit(1)
    steps = []
    for s in R["steps"]:
        lines = []
        for ln in s["done_when"]:
            ok, saw = kit.check(ln, root)
            row = {"what": ln.get("what") or kit.describe(ln), "met": ok}
            if live:
                row["saw"] = saw  # live only: a command's output may differ run to run, the map must not
            lines.append(row)
        steps.append({"id": s["id"], "name": s.get("name", s["id"]), "needs_alex": bool(s.get("needs_alex")),
                      "waits_on": list(s.get("waits_on", [])), "lines": lines,
                      "met": sum(x["met"] for x in lines), "of": len(lines)})
    by = {s["id"]: s for s in steps}
    for s in steps:
        s["done"] = s["met"] == s["of"] > 0
    for s in steps:
        s["waits_open"] = [w for w in s["waits_on"] if not by[w]["done"]]
        s["status"] = "done" if s["done"] else ("blocked" if s["waits_open"] else "startable")
    nxt = next((s["id"] for s in steps if s["status"] == "startable"), None)
    nxt_agent = next((s["id"] for s in steps if s["status"] == "startable" and not s["needs_alex"]), None)
    return {"what": "Computed by loop/scripts/build_donemap.py from loop/qa/done-rules.json; do not edit by hand.",
            "project": R.get("project") or kit.conf(root)["project"], "mission": R.get("mission", ""),
            "done": all(s["done"] for s in steps), "met": sum(s["met"] for s in steps), "of": sum(s["of"] for s in steps),
            "steps_done": sum(s["done"] for s in steps), "next": nxt, "next_agent": nxt_agent, "steps": steps}


def headline(D):
    by = {s["id"]: s for s in D["steps"]}
    nm = lambda i: f"{i} '{by[i]['name']}'" if i else "none"
    return (f"{D['project']} done: {'YES' if D['done'] else 'NO'} · {D['met']} of {D['of']} lines met · "
            f"{D['steps_done']} of {len(D['steps'])} steps done · next: {nm(D['next'])} · next without Alex: {D['next_agent'] or 'none'}")


def step_line(s, cap=None):
    open_ = [x["what"] + (f" ({x['saw']})" if x.get("saw") else "") for x in s["lines"] if not x["met"]]
    shown = open_ if cap is None else open_[:cap]
    more = f" … {len(open_) - len(shown)} more" if len(open_) > len(shown) else ""
    return (f"  [{s['status']:9}]{' (needs Alex)' if s['needs_alex'] else ''} {s['id']} '{s['name']}': {s['met']}/{s['of']}"
            + (f" · open: {'; '.join(shown)}{more}" if shown else "")
            + (f" · waits on: {', '.join(s['waits_open'])}" if s["waits_open"] else ""))


def road_line(root):
    """The roadmap's one line (loop/roadmap.json, roadmap.py): the version, the phase we are in, the next step."""
    if not (Path(root) / "loop" / "roadmap.json").exists():
        return []
    import roadmap
    try:
        cfg = roadmap.Cfg(root)
        return [roadmap.status(roadmap.build(cfg)[1])]
    except SystemExit as ex:
        return [f"roadmap: {ex}"]


def status_text(D, root=None):
    return "\n".join([headline(D)] + road_line(root or kit.ROOT) + [step_line(s) for s in D["steps"]])


def brief_text(D, root=None):
    start = [s for s in D["steps"] if s["status"] == "startable"]
    rest = len(D["steps"]) - len(start) - D["steps_done"]
    return "\n".join([headline(D)] + road_line(root or kit.ROOT) + [step_line(s, cap=4) for s in start]
                     + ([f"  ({rest} blocked step(s) not shown: --status)"] if rest else []))


def next_agent(D):
    """-> (exit code, text) for loop.sh: 0 a step to take, 2 only Alex can unblock, 3 every line met."""
    if D["done"]:
        return 3, "done: every line of the map is met"
    if D["next_agent"]:
        return 0, D["next_agent"]
    start = [f"{s['id']} '{s['name']}'" for s in D["steps"] if s["status"] == "startable"]
    return 2, "waits on Alex: " + ("; ".join(start) + " (each needs Alex)" if start else "no step is startable")


def main(argv, root=None):
    root = Path(root or kit.ROOT)
    if argv[:1] == ["selftest"]:
        return selftest()
    live = any(a in argv for a in ("--status", "--brief"))
    D = build(root, live=live)
    by = {s["id"]: s for s in D["steps"]}
    if "--next-agent" in argv:
        code, text = next_agent(D)
        print(text)
        return code
    if "--status" in argv:
        print(status_text(D, root))
        return 0
    if "--brief" in argv:
        print(brief_text(D, root))
        return 0
    for flag in ("--require", "--filled", "--advanced"):
        if flag in argv:
            sid = argv[argv.index(flag) + 1] if len(argv) > argv.index(flag) + 1 else ""
            if sid not in by:
                print(f"build_donemap {flag}: no step {sid!r}; steps: {', '.join(by)}")
                return 1
            s = by[sid]
            if flag == "--require":
                if s["waits_open"]:
                    print(f"build_donemap --require {sid}: REFUSED · waits on {', '.join(s['waits_open'])}")
                    kit.catch("map:require", f"{sid} waits on {', '.join(s['waits_open'])}", root=root)
                    return 1
                print(f"build_donemap --require {sid}: ok · nothing it waits on is open")
                return 0
            want = s["of"] if flag == "--filled" else int(argv[argv.index(flag) + 2])
            if s["met"] < want:
                print(f"build_donemap {flag} {sid}: REFUSED · {s['met']} of {s['of']} lines met, {want} needed")
                return 1
            print(f"build_donemap {flag} {sid}: ok · {s['met']} of {s['of']} lines met")
            return 0
    text = json.dumps(D, ensure_ascii=False, indent=1) + "\n"
    out = paths(root)[1]
    if "--check" in argv:
        if not out.exists() or out.read_text() != text:
            print("build_donemap: loop/qa/done-map.json differs from a fresh build (run build_donemap.py)")
            return 1
        print(f"build_donemap: matches · {D['met']} of {D['of']} met · next {D['next']}")
        return 0
    out.write_text(text)
    if (root / "loop" / "roadmap.json").exists():  # the roadmap page reads this map: rebuilt with it, so the two never disagree
        import roadmap
        try:
            roadmap.write(roadmap.Cfg(root))
        except SystemExit as ex:
            print(f"build_donemap: the roadmap page was not rebuilt: {ex}")
    print(f"build_donemap: wrote loop/qa/done-map.json · {D['met']} of {D['of']} met · next {D['next']}")
    return 0


def selftest():
    import contextlib
    import io
    import tempfile
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "loop" / "qa").mkdir(parents=True)
        (root / "have.txt").write_text("x")
        yes, no = {"file": "have.txt"}, {"file": "missing.txt"}

        def run(rules, *argv):
            (root / "loop" / "qa" / "done-rules.json").write_text(json.dumps(rules))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(list(argv), root)
            return code, buf.getvalue()

        # 0: an agent step is startable
        R0 = {"project": "t", "steps": [{"id": "a", "done_when": [yes]}, {"id": "b", "done_when": [no], "waits_on": ["a"]}]}
        code, out = run(R0, "--next-agent")
        must(code == 0 and out.strip() == "b", f"--next-agent exits 0 and names b when b is startable (got {code} {out.strip()!r})")
        # 2: only a step that needs Alex is startable
        R2 = {"project": "t", "steps": [{"id": "a", "done_when": [no], "needs_alex": True}, {"id": "b", "done_when": [no], "waits_on": ["a"]}]}
        code, out = run(R2, "--next-agent")
        must(code == 2 and "waits on Alex" in out, f"--next-agent exits 2 when only Alex can unblock (got {code})")
        # 2: nothing startable at all (b waits on a, a needs Alex and is blocked by nothing else) -> still 2, never 0
        R2b = {"project": "t", "steps": [{"id": "a", "done_when": [no], "waits_on": ["b"]}, {"id": "b", "done_when": [no], "waits_on": ["a"]}]}
        code, out = run(R2b, "--next-agent")
        must(code == 2 and "no step is startable" in out, f"--next-agent exits 2 on a wait cycle (got {code})")
        # 3: everything met
        R3 = {"project": "t", "steps": [{"id": "a", "done_when": [yes]}]}
        code, out = run(R3, "--next-agent")
        must(code == 3, f"--next-agent exits 3 when every line is met (got {code})")
        # --brief keeps every startable step, drops done and blocked ones
        RB = {"project": "t", "steps": [{"id": "d1", "done_when": [yes]}] + [{"id": f"s{i}", "name": f"start {i}", "done_when": [no] * 6} for i in range(7)]
              + [{"id": "blk", "done_when": [no], "waits_on": ["s0"]}]}
        code, out = run(RB, "--brief")
        must(all(f"s{i} 'start {i}'" in out for i in range(7)), "--brief keeps every startable step")
        must("d1 " not in out and "blk " not in out and "1 blocked step" in out, "--brief leaves out done and blocked steps")
        must("… 2 more" in out, "--brief cuts each step's open lines to four")
        # gates
        code, _ = run(R0, "--require", "b")
        must(code == 0, "--require passes when what it waits on is done")
        code, _ = run(R2, "--require", "b")
        must(code == 1, "--require refuses when a wait is open")
        code, _ = run(R0, "--advanced", "b", "1")
        must(code == 1, "--advanced refuses below N")
        code, _ = run(R0, "--filled", "a")
        must(code == 0, "--filled passes when every line is met")
        # --check against a stale map, then a fresh one
        run(R0)
        code, _ = run(R0, "--check")
        must(code == 0, "--check passes on a fresh map")
        (root / "have.txt").unlink()
        code, _ = run(R0, "--check")
        must(code == 1, "--check refuses a stale map")
        # invalid rules refuse
        try:
            run({"steps": [{"id": "x", "done_when": []}]})
            must(False, "a step with no line is refused")
        except SystemExit as e:
            must(e.code == 1, "a step with no line is refused")
    if bad:
        print("build_donemap selftest: FAILED: " + "; ".join(bad))
        return 1
    print(f"build_donemap selftest: ALL GREEN · {n} controls")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
