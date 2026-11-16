# Dreaming: an out-of-band pass after a run (loop.sh runs it once when the loop stops or parks). It never edits a rule;
# it writes proposals to loop/state/dream-<date>.md for the owner to accept or reject.
#   (a) process pruning: every gate logs its refusals to loop/state/catches.csv (kit.catch); each gate's catches over
#       the last 20 closed units are counted, and a gate with zero is proposed for removal (safety-floor gates marked).
#   (b) lessons: the last run's slice transcripts (session ids from loop/state/metrics.csv, read-only under
#       ~/.claude/projects/<slug>/) are read for refused tool calls, permission denials, repeated errors; plus the
#       run's barren slices. Each becomes a proposal with its count and example sessions.
#
#   dream.py [--run RUN] [--transcripts DIR] [--window 20]    write the report and print its path
#   dream.py selftest                                          a 0-catch gate over 20 units is proposed; a refused
#                                                              tool call in a planted transcript is reported
import csv
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402


def closed_units(root):
    out = []
    for f in sorted((Path(root) / "loop" / "qa" / "units").glob("*.json")):
        try:
            u = json.loads(f.read_text())
        except Exception:
            continue
        if isinstance(u.get("result"), dict) and u["result"].get("closed_at"):
            out.append(u)
    return sorted(out, key=lambda u: u["result"]["closed_at"])


def read_catches(path):
    if not Path(path).exists():
        return []
    with open(path, newline="") as h:
        return list(csv.DictReader(h))


def pruning(root, catches, window=20):
    units = closed_units(root)
    last = units[-window:]
    rows, props = [], []
    if len(units) < window:
        return units, rows, props, f"{len(units)} closed unit(s) so far; pruning proposals start at {window}."
    start = min(u["result"].get("opened_at") or u["result"]["closed_at"] for u in last)
    inwin = Counter(c["check"] for c in catches if c.get("date", "") >= start)
    alltime = Counter(c["check"] for c in catches)
    ids = list(kit.CHECKS) + sorted(set(alltime) - set(kit.CHECKS))
    for cid in ids:
        rows.append((cid, inwin[cid], alltime[cid], kit.CHECKS.get(cid, "(a project's own gate)")))
        if inwin[cid] == 0:
            props.append((cid, cid in kit.SAFETY_FLOOR))
    return units, rows, props, f"window: the last {window} closed units, since {start}."


def slug(root):
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(root).resolve()))


def last_run(root, run=None):
    f = Path(root) / "loop" / "state" / "metrics.csv"
    if not f.exists():
        return None, []
    with open(f, newline="") as h:
        rows = list(csv.DictReader(h))
    if not rows:
        return None, []
    run = run or rows[-1].get("run")
    return run, [r for r in rows if r.get("run") == run]


def norm(text):
    lines = [x for x in (text or "").strip().splitlines() if x.strip() and not re.fullmatch(r"\s*Exit code \d+\s*", x)]
    t = lines[0] if lines else (text or "").strip()
    t = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`", "'…'", t)
    t = re.sub(r"(?<![A-Za-z])(/|~/)[^\s,;:]+", "<path>", t)
    t = re.sub(r"\d+", "N", t)
    return t[:140]


def result_text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
    return str(c)


def scan(files):
    """-> {kind: {key: {"n": int, "sessions": set, "example": str}}} over refused / permission / error."""
    found = {"refused": defaultdict(lambda: {"n": 0, "sessions": set(), "example": ""}),
             "permission": defaultdict(lambda: {"n": 0, "sessions": set(), "example": ""}),
             "error": defaultdict(lambda: {"n": 0, "sessions": set(), "example": ""})}
    for f in files:
        uses = {}
        sid = Path(f).stem
        try:
            lines = Path(f).read_text(errors="replace").splitlines()
        except Exception:
            continue
        for line in lines:
            try:
                d = json.loads(line)
            except Exception:
                continue
            m = d.get("message") if isinstance(d, dict) else None
            content = m.get("content") if isinstance(m, dict) else None
            if not isinstance(content, list):
                continue
            for x in content:
                if not isinstance(x, dict):
                    continue
                if x.get("type") == "tool_use":
                    inp = x.get("input") or {}
                    arg = re.sub(r"\s+", " ", str(inp.get("command") or inp.get("file_path") or inp.get("url") or inp.get("query") or ""))
                    uses[x.get("id")] = f"{x.get('name')}: {arg[:100]}"
                if x.get("type") == "tool_result" and x.get("is_error"):
                    text = result_text(x.get("content"))
                    pm = re.search(r"requested permissions to (use|write to|read from|edit) ?(\S+)?", text)
                    if pm:
                        what = pm.group(2) or ""
                        target = what.rstrip(",.") if pm.group(1) == "use" else str(Path(what.rstrip(",.")).parent)
                        kind, key = "permission", f"{pm.group(1)} {target}"
                    elif re.search(r"requires? (explicit )?approval|haven't granted|permission to use", text):
                        part = re.search(r"requires approval: ([\w./-]+(?: [\w./-]+)?)", text)  # the command, by its first two words
                        kind, key = "permission", (f"needs approval: {part.group(1)}" if part else norm(text))
                    elif re.search(r"hook error|guard: refused|BLOCKED|refused", text):
                        tail = text.split("refused.", 1)[-1] if "refused." in text else text
                        kind, key = "refused", norm(tail.split(" you, the owner, can do it yourself")[0])
                    else:
                        kind, key = "error", norm(text)
                    e = found[kind][key]
                    e["n"] += 1
                    e["sessions"].add(sid[:8])
                    e["example"] = e["example"] or uses.get(x.get("tool_use_id"), "")
    return found


def transcripts(root, sessions, tdir=None, fallback=10):
    tdir = Path(tdir) if tdir else Path.home() / ".claude" / "projects" / slug(root)
    hits = [tdir / f"{s}.jsonl" for s in sessions if s and (tdir / f"{s}.jsonl").exists()]
    if hits or not tdir.exists():
        return hits, tdir
    cands = sorted(tdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    head = lambda p: p.open(errors="replace").read(20000)
    return [p for p in cands if '"entrypoint":"sdk-cli"' in head(p)][:fallback], tdir


def report(root, run=None, tdir=None, window=20, today=None):
    root = Path(root)
    import os
    catches = read_catches(os.environ.get("LOOP_CATCHES") or root / "loop" / "state" / "catches.csv")
    units, rows, props, note = pruning(root, catches, window)
    run, mrows = last_run(root, run)
    files, tdir = transcripts(root, [r.get("session_id") for r in mrows], tdir)
    found = scan(files)
    barren = [r for r in mrows if r.get("rc") == "0" and r.get("new_commits") == "0"]
    today = today or dt.date.today().isoformat()
    L = [f"# Dream {today} · {kit.conf(root)['project']}", "",
         "Proposals only: nothing here changed a rule. Tick accept or reject; a change lands by the owner's hand.", "",
         "## (a) Gates and what they caught", "", note, ""]
    if rows:
        L += ["| gate | catches in window | all time | what it refuses |", "|---|---|---|---|"]
        L += [f"| {cid} | {a} | {b} | {w} |" for cid, a, b, w in rows]
        L += [""]
    for cid, floor in props:
        L.append(f"- [ ] accept  [ ] reject — remove gate `{cid}`: zero catches over the last {window} units"
                 + (" (safety floor: Claude's pick is KEEP)" if floor else ""))
    L += ["", f"## (b) Lessons from the last run ({run or 'no run recorded'}: {len(mrows)} slice(s), {len(files)} transcript(s) read from {tdir})", ""]
    n = 0
    advice = {"refused": "slices keep hitting this gate: add a working rule naming the right road, or check the gate is not miswired",
              "permission": "slices keep asking for this: allow it for slices (kit.json allowed_tools_extra) or a rule to avoid it",
              "error": "the same error, again: a working rule or a fix"}
    for kind, title in (("refused", "Refused tool calls"), ("permission", "Permission denials"), ("error", "Repeated errors")):
        items = sorted(found[kind].items(), key=lambda kv: -kv[1]["n"])
        if kind == "error":
            items = [kv for kv in items if kv[1]["n"] >= 2]
        if not items:
            continue
        L += [f"### {title}", ""]
        for key, e in items:
            n += 1
            L.append(f"- [ ] accept  [ ] reject — {advice[kind]}. **{key}** · {e['n']}x · sessions: {', '.join(sorted(e['sessions']))}"
                     + (f" · e.g. `{e['example']}`" if e["example"] else ""))
        L.append("")
    if barren:
        n += 1
        L += ["### Barren slices", "", f"- [ ] accept  [ ] reject — {len(barren)} slice(s) exited clean with no commit "
              f"(slices {', '.join(r.get('slice', '?') for r in barren)}): usually a decision only the owner can make, asked in the "
              "log instead of written to loop/state/NEEDS-OWNER.md. Proposal: a working rule, or make that step needs_owner.", ""]
    if n == 0:
        L += ["Nothing to learn from this run: no refusals, denials, repeated errors or barren slices found.", ""]
    out = root / "loop" / "state" / f"dream-{today}.md"
    if out.exists():
        out = root / "loop" / "state" / f"dream-{today}-{dt.datetime.now().strftime('%H%M%S')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    return out, props, found, barren


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
        root = Path(td) / "proj"
        (root / "loop" / "qa" / "units").mkdir(parents=True)
        (root / "loop" / "state").mkdir(parents=True)
        os.environ["LOOP_CATCHES"] = str(root / "loop" / "state" / "catches.csv")
        for i in range(19):
            (root / "loop/qa/units" / f"u{i:02}.json").write_text(json.dumps({"unit": f"u{i:02}", "result": {"opened_at": f"2026-11-01T10:{i:02}:00", "closed_at": f"2026-11-01T11:{i:02}:00"}}))
        for cid in kit.CHECKS:
            if cid != "guard:root-entry":
                kit.catch(cid, "planted", "u05", root)
        _, props, _, _ = report(root, tdir=Path(td) / "none", today="t19")
        must(props == [], "with 19 closed units nothing is proposed")
        (root / "loop/qa/units/u19.json").write_text(json.dumps({"unit": "u19", "result": {"opened_at": "2026-11-01T12:00:00", "closed_at": "2026-11-01T12:30:00"}}))
        out, props, _, _ = report(root, tdir=Path(td) / "none", today="t20")
        must([p for p, _ in props] == ["guard:root-entry"], f"over 20 units the one gate with 0 catches is proposed, and only it ({[p for p, _ in props]})")
        must("remove gate `guard:root-entry`" in out.read_text(), "the proposal is written to the dream report")
        # an old catch, before the window, does not keep a gate alive
        with open(os.environ["LOOP_CATCHES"], "a", newline="") as h:
            csv.writer(h).writerow(["2026-10-01T00:00:00", "guard:root-entry", "old", "before the window"])
        _, props, _, _ = report(root, tdir=Path(td) / "none", today="t20b")
        must([p for p, _ in props] == ["guard:root-entry"], "a catch before the window does not count")
        # lessons from a planted transcript
        tdir = Path(td) / "transcripts"
        tdir.mkdir()
        sid = "11111111-2222-3333-4444-555555555555"
        tu = lambda i, name, inp: json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": i, "name": name, "input": inp}]}})
        tr = lambda i, text: json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "content": text, "is_error": True}]}})
        (tdir / f"{sid}.jsonl").write_text("\n".join([
            tu("a", "Bash", {"command": "git push origin main"}),
            tr("a", "PreToolUse:Bash hook error: [python3 guard_tool.py]: guard: refused. Never git push (CLAUDE.md, hard rules). you, the owner, can do it yourself."),
            tu("b", "WebSearch", {"query": "x"}),
            tr("b", "Claude requested permissions to use WebSearch, but you haven't granted it yet."),
            tu("c", "Bash", {"command": "npm test"}), tr("c", "Exit code 1\nnpm ERR! missing script: test"),
            tu("d", "Bash", {"command": "npm test"}), tr("d", "Exit code 1\nnpm ERR! missing script: test"),
            "not json at all"]) + "\n")
        (root / "loop/state/metrics.csv").write_text("date,run,slice,try,rc,duration_s,new_commits,session_id,last_commit_subject\n"
                                                     f"2026-11-11T10:00:00,r1,1,0,0,300,1,{sid},u20 landed\n"
                                                     "2026-11-11T10:10:00,r1,2,0,0,200,0,,nothing\n")
        out, _, found, barren = report(root, tdir=tdir, today="t21")
        txt = out.read_text()
        must(any("Never git push" in k and v["n"] == 1 for k, v in found["refused"].items()), "a refused tool call in a transcript is found")
        must("Never git push" in txt and "git push origin main" in txt, "the refused call is reported with its example command")
        must(any(k == "use WebSearch" for k in found["permission"]), "a permission denial is found by tool")
        must("missing script: test** · 2x" in txt, "a repeated error is reported with its count")
        must(len(barren) == 1 and "Barren slices" in txt, "a barren slice is reported")
        must(sid[:8] in txt, "example sessions are named")
        del os.environ["LOOP_CATCHES"]
    if bad:
        print("dream selftest: FAILED: " + "; ".join(bad))
        return 1
    print(f"dream selftest: ALL GREEN · {n} controls")
    return 0


def main(argv):
    if argv[:1] == ["selftest"]:
        return selftest()
    opt = lambda k, d=None: argv[argv.index(k) + 1] if k in argv and len(argv) > argv.index(k) + 1 else d
    out, props, found, barren = report(kit.ROOT, run=opt("--run"), tdir=opt("--transcripts"), window=int(opt("--window", 20)))
    lessons = sum(len(v) for k, v in found.items() if k != "error") + sum(1 for v in found["error"].values() if v["n"] >= 2) + (1 if barren else 0)
    print(f"dream: wrote {out.relative_to(kit.ROOT)} · {len(props)} gate(s) proposed for removal · {lessons} lesson(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
