#!/usr/bin/env python3
# From a task to the questions it needs, and the one small piece that answers each. Alex, 2026-11-16: "it seems like
# you always try to brute force your way into solution, digets everything, but that's you eating junk food, we want you
# to eat super healthy whole foods"; "who do we decide the question ... we need to have an intelligence layer to decide
# the question". A whole food is the smallest piece that is complete on its own, from the source: one decision line,
# one step's lines, one note. Not a summary, not the file around it.
#
#   questions.py <task words> [--step ID]   the target, where it stands, then the questions in order, each answered
#                                           by a few lines or by the one command that gives them
#   questions.py decision D4                one decision, and the later ones that name it (replaced, amended)
#   questions.py selftest                   planted truths
#
# THE ORDER IS THE RULE: (a) what the project already holds (the done map's met lines, the resources), (b) what Alex
# decided (DECISIONS.md), (c) what he said (the road's versions, in his words), (d) what is still open (the phase notes,
# the step's unmet lines). Only (d) may go to Alex. A target is never chosen from words alone: they guess badly.
# Nothing here writes. It cannot judge whether a question is the right one; that stays the session's. Stdlib only.
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402

STOP = set("the a an and or of to in on for with what how why when is are be it its this that go card cards about make "
           "sure do does we you i me my your our from by as at into then than more most next new let lets one two three "
           "she her hers they them their people person someone".split())


def words_of(text):
    return [w for w in re.findall(r"[a-z][a-z'-]{2,}", text.lower()) if w not in STOP]


def holds(text, ws):
    t = str(text).lower()
    return any(re.search(rf"\b{re.escape(w)}", t) for w in ws)


def rank(texts, ws):
    """Indexes of texts, best first, by how rare the words they hold are among them; a word most texts hold says little."""
    N = max(len(texts), 1)
    df = {w: sum(holds(t, [w]) for t in texts) for w in ws}
    rare = [w for w in ws if df[w] and (N < 4 or df[w] < N / 2)]  # with under four texts, rarity says nothing
    scored = [(sum(math.log(N / df[w]) + 1e-9 for w in rare if holds(t, [w])), i) for i, t in enumerate(texts)]
    return [i for s, i in sorted(scored, key=lambda x: -x[0]) if s > 0]


def decisions(text):
    """[(D-number, line)]: each line of DECISIONS.md that starts 'Dn ('."""
    return [(int(m.group(1)), ln.strip()) for ln in text.splitlines() for m in [re.match(r"\s*D(\d+) \(", ln)] if m]


def decision(text, n):
    D = decisions(text)
    own = [ln for k, ln in D if k == n]
    if not own:
        return [f"decision D{n}: not in DECISIONS.md"]
    later = [ln for k, ln in D if k > n and re.search(rf"\bD{n}\b", ln)]
    return own + (["named by later decisions:"] + [f"  {ln}" for ln in later] if later else [])


def load(root):
    J = lambda p: json.loads((root / p).read_text()) if (root / p).exists() else {}
    return {"map": J("loop/qa/done-map.json"), "road": J("loop/roadmap.json"),
            "decisions": (root / "DECISIONS.md").read_text() if (root / "DECISIONS.md").exists() else "",
            "resources": J("loop/qa/resources.json").get("resources", [])}


def questions(task, F, step_id=None):
    ws = words_of(task)
    steps = F["map"].get("steps", [])
    S = next((s for s in steps if s["id"] in (step_id, task.strip())), None)
    out = [f"TASK: {task}"]
    if S:
        out.append(f"TARGET: {S['name']} [{S['id']}] · {S.get('status')} · {S.get('met')} of {S.get('of')} lines met"
                   + ("; waits on: " + ", ".join(S["waits_open"]) if S.get("waits_open") else "") + ("; needs Alex" if S.get("needs_alex") else ""))
    else:
        best = rank([s["name"] + " " + " ".join(x["what"] for x in s.get("lines", [])) for s in steps], ws)[:3]
        out.append("TARGET: not chosen from words (they guess badly); the closest steps, pick one with --step ID:"
                   if best else "TARGET: no step's words name it; pick one with --step ID")
        out += [f"  {steps[i]['id']} · {steps[i]['name']} · {steps[i].get('status')}" for i in best]
    out.append("QUESTIONS, in this order; stop when one is answered:")
    out.append("a. What does the project already hold?")
    if S:
        out += [f"   met: {x['what']}" for x in S.get("lines", []) if x.get("met")] or ["   none of the step's lines is met yet"]
    R = F["resources"]
    out += [f"   open: {R[i]['where']}  ·  {R[i]['answers']}" for i in rank([f"{r['id']} {r['where']} {r['answers']}" for r in R], ws)[:3]]
    out.append(f"   more: python3 -I loop/scripts/lookup.py find {' '.join(ws[:2])}")
    out.append("b. What did Alex decide?")
    D = decisions(F["decisions"])
    hit = [D[i] for i in rank([ln for _, ln in D], ws)[:4]]
    out += [f"   {ln}" for _, ln in hit] or ["   no decision holds the words"]
    out.append("c. What did he say about it? (the road's versions, his words)")
    V = F["road"].get("versions", [])
    vt = [" ".join(v.get("reason", [])) if isinstance(v.get("reason"), list) else str(v.get("reason", "")) for v in V]
    out += [f"   v{V[i]['v']} ({V[i].get('date')}): {vt[i][:220]}" for i in rank(vt, ws)[:2]] or ["   no version of the road holds the words"]
    out.append("d. What is still open? (only this may go to Alex: two concrete cases, my pick, what each answer changes)")
    phase = next((p for p in F["road"].get("phases", []) if S and S["id"] in p.get("steps", [])), None)
    notes = [x for p in ([phase] if phase else F["road"].get("phases", [])) for x in p.get("notes", []) if holds(x, ws)]
    out += [f"   note: {x[:220]}" for x in notes[-3:]]
    if S:
        out += [f"   unmet: {x['what']}" for x in S.get("lines", []) if not x.get("met")]
    out.append("WHY IT MATTERS: the mission, " + (F["map"].get("mission") or "(no mission in the map)") + " Each answer: what does it do for that?")
    return out


def selftest():
    bad = []
    must = lambda ok, what: ok or bad.append(what)  # noqa: E731
    DT = "# x\n\nD1 (2026-01-01): the mission\nD2 (2026-01-02): counters count in tens\nD3 (2026-01-03): counters count in fives (replaces D2)\n"
    must(decision(DT, 2)[0].startswith("D2 (") and any("D3" in x for x in decision(DT, 2)), "a later decision naming D2 was not shown")
    must(not any("D3" in x for x in decision(DT, 1)), "a decision that does not name D1 was shown with it")
    F = {"map": {"mission": "a counter", "steps": [
            {"id": "core", "name": "Counter works", "status": "startable", "met": 1, "of": 2, "waits_open": [],
             "lines": [{"what": "counter file exists", "met": True}, {"what": "counter tests pass", "met": False}]},
            {"id": "ui", "name": "A page shows it", "status": "blocked", "met": 0, "of": 1, "waits_open": ["core"], "lines": [{"what": "page", "met": False}]}]},
         "road": {"phases": [{"id": "p", "steps": ["core"], "notes": ["counter speed is open"]}],
                  "versions": [{"v": 1, "date": "d", "reason": ["the counter first"]}]},
         "decisions": DT, "resources": [{"id": "r", "where": "src/counter.py", "answers": "how the counter counts"}]}
    q = questions("the counter", F, "core")
    idx = [next((i for i, x in enumerate(q) if x.startswith(k)), -1) for k in ("a.", "b.", "c.", "d.")]
    must(all(i >= 0 for i in idx) and idx == sorted(idx), f"the four kinds did not come in order: {idx}")
    must(any("met: counter file exists" in x for x in q) and any("unmet: counter tests pass" in x for x in q), "the step's met and unmet lines were not split into a and d")
    must(any("src/counter.py" in x for x in q), "a resource holding the words was not under a")
    must(any("D2 (" in x for x in q) and any("v1 (" in x for x in q) and any("counter speed is open" in x for x in q), "a decision, a version or a note holding the words was missed")
    q2 = questions("the counter", F)
    must(not any(x.startswith("TARGET: Counter") for x in q2), "a target was chosen from words alone")
    if bad:
        print("questions selftest: FAIL\n  - " + "\n  - ".join(bad))
        return 1
    print("questions selftest: ok · four kinds in order · a decision with what names it · no target from words alone")
    return 0


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print("usage: questions.py <task words> [--step ID] | decision Dn | selftest")
        return 2
    if a[0] == "selftest":
        return selftest()
    if a[0] == "decision" and len(a) >= 2:
        n = int(a[1].lstrip("Dd"))
        print("\n".join(decision((kit.ROOT / "DECISIONS.md").read_text(), n)))
        return 0
    sid = a[a.index("--step") + 1] if "--step" in a else None
    task = " ".join(x for i, x in enumerate(a) if x != "--step" and (i == 0 or a[i - 1] != "--step"))
    print("\n".join(questions(task, load(kit.ROOT), sid)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
