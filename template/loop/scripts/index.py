#!/usr/bin/env python3
# The project's index on the start screen: what exists, the mission ledger's newest entry, and the owner's corrections in
# force. Ported from harbingr-v2 (2026-11-16, the owner: "we don't have a summary of the project"; "this is like a ledger that
# in theory should focus the mission more and more"; "we literally have this built"). One file holds all three:
# loop/qa/index.json. Lean on purpose: the start screen reads one screen, and depth is one command away.
#
#   index.py                                         print it (brief.py prints it at every start)
#   index.py ledger [N]                              one ledger entry (default: the newest)
#   index.py ledger add DATE "your words" [--sharper "..."] [--open "..."]   a new entry, the owner's words exactly; never an edit
#   index.py correct DATE "your words" "the rule a session follows"        a correction in force
#   index.py line "what exists, one sentence" FILE                         a project line, its file must exist
#   index.py --check                                 every line's file exists, the ledger is numbered and never rewritten
#   index.py selftest                                planted truths
#
# A LEDGER ENTRY IS NEVER REWRITTEN: --check compares every entry with the last commit's and refuses a change or a
# removal. The words are the owner's; 'sharper' is Claude's wording of the problem, the owner's to correct; 'open' names what is open.
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402

CAP = 30
REL = "loop/qa/index.json"


def path(root=None):
    return Path(root or kit.ROOT) / REL


def load(root=None):
    f = path(root)
    return json.loads(f.read_text()) if f.exists() else {"project": [], "ledger": [], "corrections": []}


def save(I, root=None):
    path(root).write_text(json.dumps(I, indent=1, ensure_ascii=False) + "\n")


def dreams(root=None):
    """(proposals waiting for the owner, the owner's yeses not yet applied), read off loop/state/dreams (listen.py)."""
    d = Path(root or kit.ROOT) / "loop" / "state" / "dreams"
    w = y = 0
    for f in d.glob("proposals-*.json") if d.exists() else []:
        try:
            P = json.loads(f.read_text())["proposals"]
        except (ValueError, KeyError):
            continue
        w += sum(1 for p in P if p.get("answer") is None)
        y += sum(1 for p in P if (p.get("answer") or {}).get("yes") and not p.get("applied"))
    return w, y


def lines(I, root=None):
    L = ["--- PROJECT (what exists; the file beside each line is where to read more)"]
    L += [f"- {p['says']} [{p['file']}]" for p in I.get("project", [])] or ["- (no project lines yet: index.py line \"...\" FILE)"]
    led = I.get("ledger", [])
    if led:
        e = led[-1]
        L.append(f"--- MISSION LEDGER, entry {e['n']} of {len(led)} ({e['date']}; any entry: index.py ledger N)")
        L.append(f"The owner: \"{e['words']}\"")
        if e.get("sharper"):
            L.append(f"Sharper (Claude's wording, yours to correct): {e['sharper']}")
        if e.get("open"):
            L.append(f"Open: {e['open']}")
    if I.get("corrections"):
        L.append("--- THE OWNER'S CORRECTIONS, IN FORCE")
        L += [f"- {c['date']} \"{c['words']}\" → {c['rule']}" for c in I["corrections"]]
    w, y = dreams(root)
    if y:
        L.append(f"Proposals from listening: {y} of the owner's yeses not yet applied: apply them first, one commit, then mark each applied (listen.py show).")
    L.append(f"Proposals from listening: {w} wait for the owner (listen.py show)." if w else "Proposals from listening: none waiting (at the end of a session with the owner: listen.py gather, then listen.py run).")
    return L


def head_entries(root=None):
    r = subprocess.run(["git", "show", f"HEAD:{REL}"], cwd=root or kit.ROOT, capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("ledger", []) if r.returncode == 0 else []
    except ValueError:
        return []


def problems(I, root=None, before=None):
    bad = []
    root = Path(root or kit.ROOT)
    for p in I.get("project", []):
        if not p.get("says") or not p.get("file") or not (root / p["file"]).exists():
            bad.append(f"the project line '{p.get('says', '')[:60]}' names no file that exists ({p.get('file')!r})")
    led = I.get("ledger", [])
    for i, e in enumerate(led, 1):
        if e.get("n") != i:
            bad.append(f"ledger entry {e.get('n')} is not numbered {i}: entries are numbered 1, 2, 3 in order")
        if not str(e.get("words", "")).strip():
            bad.append(f"ledger entry {i} carries no words of the owner's")
    for old in (before if before is not None else head_entries(root)):
        now = next((e for e in led if e.get("n") == old.get("n")), None)
        if now is None:
            bad.append(f"ledger entry {old.get('n')} was removed: an entry is never removed")
        elif now != old:
            bad.append(f"ledger entry {old.get('n')} was rewritten: an entry is never rewritten; a new one says what changed")
    for c in I.get("corrections", []):
        if not c.get("words") or not c.get("rule"):
            bad.append("a correction needs the owner's words and the rule a session follows")
    if len(lines(I, root)) > CAP:
        bad.append(f"the index prints {len(lines(I, root))} lines, over its cap of {CAP}: replace or shorten, never only add")
    return bad


def selftest():
    import tempfile
    bad = []
    must = lambda ok, what: ok or bad.append(what)  # noqa: E731
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "DECISIONS.md").write_text("x")
        e1 = {"n": 1, "date": "d", "words": "the mission"}
        good = {"project": [{"says": "decisions", "file": "DECISIONS.md"}], "ledger": [e1], "corrections": []}
        must(problems(good, td, before=[]) == [], f"a good index was refused: {problems(good, td, before=[])}")
        must(any("names no file" in p for p in problems({**good, "project": [{"says": "x", "file": "nope.md"}]}, td, before=[])), "a line with a missing file was let through")
        must(any("rewritten" in p for p in problems({**good, "ledger": [{**e1, "words": "softer"}]}, td, before=[e1])), "a rewritten ledger entry was let through")
        must(any("removed" in p for p in problems({**good, "ledger": []}, td, before=[e1])), "a removed ledger entry was let through")
        must(any("numbered" in p for p in problems({**good, "ledger": [e1, {"n": 3, "date": "d", "words": "w"}]}, td, before=[])), "a gap in the numbering was let through")
        must(any("cap" in p for p in problems({**good, "project": [{"says": f"l{i}", "file": "DECISIONS.md"} for i in range(CAP)]}, td, before=[])), "an index over its cap was let through")
        L = lines({**good, "ledger": [e1, {"n": 2, "date": "d2", "words": "sharper now", "open": "how"}]}, td)
        must(any("entry 2 of 2" in x for x in L) and any("sharper now" in x for x in L) and not any("the mission" in x for x in L), "the start screen did not show the newest entry alone")
    if bad:
        print("index selftest: FAIL\n  - " + "\n  - ".join(bad))
        return 1
    print("index selftest: ok · a missing file, a rewritten or removed entry, a numbering gap and the cap are refused")
    return 0


def main(a):
    if a and a[0] == "selftest":
        return selftest()
    I = load()
    if a and a[0] == "--check":
        bad = problems(I)
        if bad:
            print("index check: FAIL\n  - " + "\n  - ".join(bad))
            return 1
        print(f"index check: pass · {len(I.get('project', []))} project lines, {len(I.get('ledger', []))} ledger entries, {len(lines(I))} of {CAP} lines")
        return 0
    if a and a[0] == "ledger":
        led = I.get("ledger", [])
        if len(a) >= 3 and a[1] == "add":
            opt = lambda k: a[a.index(k) + 1] if k in a else ""  # noqa: E731
            led.append({"n": len(led) + 1, "date": a[2], "words": a[3], **({"sharper": opt("--sharper")} if opt("--sharper") else {}), **({"open": opt("--open")} if opt("--open") else {})})
            I["ledger"] = led
            save(I)
            print(f"index: ledger entry {len(led)} added")
            return 0
        n = int(a[1]) if len(a) > 1 else len(led)
        e = next((x for x in led if x["n"] == n), None)
        print(json.dumps(e, indent=1, ensure_ascii=False) if e else f"index: no ledger entry {n}")
        return 0
    if a and a[0] == "correct" and len(a) >= 4:
        I.setdefault("corrections", []).append({"date": a[1], "words": a[2], "rule": a[3]})
        save(I)
        print("index: correction added")
        return 0
    if a and a[0] == "line" and len(a) >= 3:
        if not (kit.ROOT / a[2]).exists():
            print(f"index: {a[2]} does not exist; a project line names a real file")
            return 1
        I.setdefault("project", []).append({"says": a[1], "file": a[2]})
        save(I)
        print("index: project line added")
        return 0
    print("\n".join(lines(I)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
