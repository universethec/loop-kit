# The roadmap and the dashboard of building the product: one road per project and the project's health, on one page.
# The owner, 2026-11-13: "we need to fix the roadmap and replace what we have now"; "I would like to see a dashboard on the
# project health overall as we build it, because a lot of the time we bloat and we have shit floating around in several
# places"; "most importabtly is for the project to be actually mainted pristine, minimalistic, highly-performant not
# just for the dashboard to look good, the dashboard is just a meassure of that". The same program runs in every
# project made by the loop kit.
#
# loop/roadmap.json is the road, written to be read: the phases (what each is, what done means, the done-map steps and
# the marks under it, its open notes), the parts of the product for the drawing, the 'health' block (which folders are
# engine and which are helpers, each instruction file and its cap, the folders that collect loose things, retired
# files, the checks to run, how to ask the loop its state), every version of the road and its history before version 1.
# Status is computed from the done map and the marks' proofs; health from one dated log, loop/qa/health-log.json,
# written by --measure at each close (files counted from git, so the page is the same on any machine).
#
# The road (phases, steps, marks, parts, health caps) changes only through `change`, which refuses words the owner did not
# type (where the project has a words check), numbers the version and computes what changed. A phase is done when its
# steps are done AND its marks are true. It cannot stop an edit of a kept version together with its fingerprint; git
# shows that. Notes are not the road: they change freely.
#
#   roadmap.py                         write the page               roadmap.py --measure   add today's health row, write the page
#   roadmap.py --check                 exit 1 on any problem         roadmap.py --status    one line: version, phase, next step
#   roadmap.py change "his words" [--date D]                         a new version of the road, with his reason
#   roadmap.py --sign DATE "his words" [roadmap|dashboard]           the owner's sign-off (he runs it himself)
#   roadmap.py selftest                the planted truths            (run each as python3 -I loop/scripts/roadmap.py ...)
import datetime as dt
import glob
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LEVELS = ("ruled", "built", "proven")
ROAD_KEYS = ("id", "name", "plain", "done_means", "steps", "marks")
PROGRAM_CAP = 900  # this program's own lines; past it the dashboard flags itself (the owner's yes, 2026-11-13)
DRIFT_AT = 5
BLOAT_RED, BLOAT_AMBER = 3.0, 1.5  # lines of helper code per line of engine code


class Cfg:
    def __init__(self, root=None):
        self.root = Path(root) if root else (Path(os.environ["LOOP_ROOT"]) if os.environ.get("LOOP_ROOT") else HERE.parents[1])
        self.road = self.root / "loop" / "roadmap.json"
        self.map = self.root / "loop" / "qa" / "done-map.json"
        self.log = self.root / "loop" / "qa" / "health-log.json"


def fail(msg):
    raise SystemExit("roadmap: " + msg)


def J(p):
    return json.loads(Path(p).read_text())


def dump(x):
    return json.dumps(x, indent=1, ensure_ascii=False) + "\n"


def said_checker():
    """Whether a line is among what the owner typed: this project's words check when it has one; None when it has none."""
    try:
        import alex_said
        return alex_said.said
    except ImportError:
        return None


# ── the road ─────────────────────────────────────────────────────────────────────────────────────────────────
def road_of(R):
    """The part of the file that is the road: what a version keeps and what may change only through `change`."""
    out = {"phases": [{k: ph.get(k, [] if k in ("steps", "marks") else "") for k in ROAD_KEYS} for ph in R.get("phases", [])],
           "architecture": R.get("architecture", {}), "arcs": R.get("arcs", [])}
    if R.get("health"):
        out["health"] = R["health"]
    return out


def fingerprint(road):
    return hashlib.sha256(json.dumps(road, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def changes(old, new):
    """What changed between two roads, in plain lines."""
    if old is None:
        return [f"the road set: {len(new['phases'])} phases, " + ", ".join(p["name"] for p in new["phases"])]
    out = []
    op, np_ = {p["id"]: p for p in old["phases"]}, {p["id"]: p for p in new["phases"]}
    out += [f"phase added: {np_[i]['name']}" for i in np_ if i not in op]
    out += [f"phase removed: {op[i]['name']}" for i in op if i not in np_]
    if [i for i in op if i in np_] != [i for i in np_ if i in op]:
        out.append("the phases are in a new order")
    where_old = {s: p["id"] for p in old["phases"] for s in p["steps"]}
    where_new = {s: p["id"] for p in new["phases"] for s in p["steps"]}
    for i in [i for i in np_ if i in op]:
        a, b = op[i], np_[i]
        if a["name"] != b["name"]:
            out.append(f"phase renamed: {a['name']} → {b['name']}")
        if a["plain"] != b["plain"] or a["done_means"] != b["done_means"]:
            out.append(f"what '{b['name']}' means, reworded")
        if a["marks"] != b["marks"]:
            out.append(f"the marks of '{b['name']}' changed")
        if set(a["steps"]) == set(b["steps"]) and a["steps"] != b["steps"]:
            out.append(f"the steps of '{b['name']}' reordered")
    name = lambda d, i: d[i]["name"] if i in d else i
    out += [f"step '{s}' moved: {name(op, where_old[s])} → {name(np_, where_new[s])}" for s in where_new if s in where_old and where_old[s] != where_new[s]]
    out += [f"step '{s}' added to '{name(np_, where_new[s])}'" for s in where_new if s not in where_old]
    out += [f"step '{s}' taken off the road (it was in '{name(op, where_old[s])}')" for s in where_old if s not in where_new]
    nodes = lambda r: {b["name"]: b for b in (r.get("architecture") or {}).get("nodes", [])} if isinstance(r.get("architecture"), dict) else {}
    oa, na = nodes(old), nodes(new)
    if (old.get("architecture") or {}) != (new.get("architecture") or {}) and oa == na:
        out.append("architecture: the wiring or the reading line changed")
    out += [f"architecture: '{k}' added" for k in na if k not in oa] + [f"architecture: '{k}' taken off" for k in oa if k not in na]
    out += [f"architecture: '{k}' changed" for k in na if k in oa and na[k] != oa[k]]
    if old.get("parts") and not new.get("parts"):
        out.append("the drawing of parts became the architecture map")
    if old.get("arcs", []) != new.get("arcs", []):
        out.append("the arcs changed: " + " → ".join(a["name"] for a in new.get("arcs", [])))
    if old.get("health") != new.get("health"):
        out.append("the health block changed (what is counted, or a cap)")
    return out or ["nothing on the road changed"]


def problems(R, D):
    out = []
    steps_on_map = {s["id"] for s in D.get("steps", [])}
    ph_ids = [p.get("id") for p in R.get("phases", [])]
    if not ph_ids:
        out.append("the road has no phases")
    out += [f"phase id {i!r} is used twice" for i in sorted({i for i in ph_ids if ph_ids.count(i) > 1})]
    placed = [s for p in R.get("phases", []) for s in p.get("steps", [])]
    out += [f"step '{s}' sits in two phases" for s in sorted({s for s in placed if placed.count(s) > 1})]
    out += [f"step '{s}' is on the done map but in no phase" for s in sorted(steps_on_map - set(placed))]
    out += [f"phase names step '{s}', which the done map does not have" for s in sorted(set(placed) - steps_on_map)]
    for p in R.get("phases", []):
        out += [f"phase {p.get('id')!r} has no {k}" for k in ("name", "plain", "done_means") if not str(p.get(k, "")).strip()]
    mk = [m["id"] for p in R.get("phases", []) for m in p.get("marks", [])]
    out += [f"mark {i!r} is used twice" for i in sorted({i for i in mk if mk.count(i) > 1})]
    out += [f"mark {m['id']!r} has no proof" for p in R.get("phases", []) for m in p.get("marks", []) if not m.get("proof")]
    out += [f"a title names {k!r}, which is neither a phase nor a step" for k in R.get("titles", {}) if k not in set(ph_ids) | steps_on_map]
    if R.get("titles"):  # once a project names things for the owner, every new phase and step needs his kind of name before a close
        out += [f"'{k}' has no plain title for the owner: add one to 'titles'" for k in list(ph_ids) + sorted(steps_on_map) if k not in R["titles"]]
    in_arcs = [i for a in R.get("arcs", []) for i in a["phases"]]
    if R.get("arcs"):
        out += [f"phase {i!r} sits in no arc" for i in ph_ids if i not in in_arcs] + [f"phase {i!r} sits in two arcs" for i in sorted({i for i in in_arcs if in_arcs.count(i) > 1})]
        out += [f"an arc names phase {i!r}, which the road does not have" for i in in_arcs if i not in ph_ids]
    ids = {b["id"] for b in R.get("architecture", {}).get("nodes", [])}
    out += [f"wire {x['from']} → {x['to']} names a part the drawing does not have" for x in R.get("architecture", {}).get("edges", []) if not {x["from"], x["to"]} <= ids]
    for b in R.get("architecture", {}).get("nodes", []):
        for lv in LEVELS:
            for ref in b.get(lv, []):
                kind, _, rid = ref.partition(":")
                if (kind == "step" and rid not in steps_on_map) or (kind == "mark" and rid not in mk) or kind not in ("step", "mark"):
                    out.append(f"part {b['name']!r}: {lv} by {ref!r}, which is neither a step on the map nor a mark")
    return out


def proof_ok(root, p):
    """A mark's proof, in the QA's vocabulary: file, grep, json."""
    if "file" in p:
        return bool(glob.glob(str(root / p["file"])))
    if "grep" in p:
        f = root / p["grep"]
        return f.exists() and p["has"] in f.read_text(errors="replace")
    if "json" in p:
        hits = sorted(glob.glob(str(root / p["json"])))
        try:
            v = json.loads(Path(hits[-1]).read_text())
            for k in p["field"].split("."):
                v = v[int(k)] if isinstance(v, list) else v[k]
        except Exception:
            return False
        op, want = p.get("op", "=="), p.get("value")
        if op in ("==", "!=", "exists"):
            return {"==": v == want, "!=": v != want, "exists": True}[op]
        return v is not None and {">=": v >= want, "<=": v <= want, ">": v > want, "<": v < want}.get(op, False)
    return False


# ── health: measured at each close into one dated log ───────────────────────────────────────────────────────
def project_files(root):
    r = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=root, capture_output=True, text=True)
    if r.returncode == 0:
        return [x for x in r.stdout.splitlines() if x]
    return [str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file() and ".git" not in p.parts]


def code_count(root, files, spec):
    hit = [f for f in files if any(f.startswith(d.rstrip("/") + "/") for d in spec.get("dirs", []))
           and f.endswith(tuple(spec.get("ext", [""]))) and not f.endswith(tuple(spec.get("skip", []) or ["\0"]))]
    lines = sum((Path(root) / f).read_bytes().count(b"\n") for f in hit if (Path(root) / f).is_file())
    return {"files": len(hit), "lines": lines}


def instruction_size(root, x):
    f = Path(root) / x["file"]
    if not f.exists():
        return 0
    t = f.read_text(errors="replace")
    if x.get("count") == "rules":
        return len(json.loads(t).get("rules", []))
    if x.get("count") == "now_words":
        ls = t.splitlines()
        head = next((i for i, s in enumerate(ls) if s.startswith("## NOW")), -1)
        return sum(len(s.split()) for s in ls[head + 1:] if not s.startswith("<!-- qa:"))
    return len(t.splitlines())


def recent_work(root, how):
    """The last five pieces of work and the count since the goal was last measured (None where the project has no such count)."""
    if how == "qa":
        import qa
        vs = sorted(qa.all_verdicts(), key=lambda v: v.get("at", ""), reverse=True)
        def title(u):
            f = qa.QA / f"expect-{u}.json"
            e = json.loads(f.read_text()) if f.exists() else {}
            m = re.search(r"\('([^']+)'\)", e.get("what", ""))
            return (e.get("plain") or [""])[0].split(": ", 1)[-1] or (m.group(1) if m else u)
        return [{"unit": v["unit"], "title": title(v["unit"]), "at": v.get("at", "")[:10], "overall": v.get("overall"), "passed": v.get("passed"), "of": v.get("of")}
                for v in vs[:5]], qa.drift()[0]
    rows = []
    for f in sorted((Path(root) / "loop" / "qa" / "units").glob("*.json")):
        u = json.loads(f.read_text())
        r = u.get("result")
        if r:
            rows.append({"unit": u.get("unit", f.stem), "at": r.get("closed_at", "")[:10], "overall": r.get("overall"), "passed": r.get("passed"), "of": r.get("of")})
    return sorted(rows, key=lambda v: v["at"], reverse=True)[:5], None


def joined_dates(root, ids, known):
    """The day each step first appeared in the map's rules, from git; days already known are kept, so a close stays fast."""
    out = {}
    for sid in ids:
        if sid in known:
            out[sid] = known[sid]
            continue
        r = subprocess.run(["git", "log", "--reverse", "--format=%ad", "--date=short", "-S", f'"id": "{sid}"', "--", "loop/qa/done-rules.json"],
                           cwd=root, capture_output=True, text=True)
        days = r.stdout.split()
        out[sid] = days[0] if r.returncode == 0 and days else dt.date.today().isoformat()
    return out


def measure(cfg, date=None):
    R, D = J(cfg.road), J(cfg.map)
    H, root = R.get("health", {}), cfg.root
    files = project_files(root)
    run = lambda c: subprocess.run(c, shell=True, cwd=root, capture_output=True, text=True, timeout=120)
    work, drift = recent_work(root, H.get("work", "units"))
    loop = run(H["loop"]).stdout.strip().splitlines() if H.get("loop") else []
    row = {"date": date or dt.date.today().isoformat(), "progress": {"met": D.get("met"), "of": D.get("cells", D.get("of"))}, "drift": drift,
           "engine": code_count(root, files, H.get("engine", {})), "helpers": code_count(root, files, H.get("helpers", {})),
           "instructions": [{"name": x["name"], "size": instruction_size(root, x), "cap": x["cap"], "unit": x.get("unit", "lines")} for x in H.get("instructions", [])],
           "clutter": [{"name": x["name"], "count": len(glob.glob(str(root / x["dir"] / x.get("glob", "*"))))} for x in H.get("clutter", [])],
           "retired_present": [p for p in H.get("retired", []) if (root / p).exists()],
           "red_checks": [c["name"] for c in H.get("checks", []) if run(c["cmd"]).returncode != 0],
           "loop": {"running": any("RUNNING" in s for s in loop), "line": loop[0] if loop else "", "needs_owner": bool(H.get("needs_owner")) and (root / H["needs_owner"]).exists()},
           "work": work, "roadmap_lines": (HERE / "roadmap.py").read_bytes().count(b"\n"),
           "joined": joined_dates(root, [s["id"] for s in D["steps"]], ((J(cfg.log)["rows"] or [{}])[-1].get("joined", {}) if cfg.log.exists() else {}))}
    log = J(cfg.log) if cfg.log.exists() else {"what": "The project's health, one row per day, written by `roadmap.py --measure` at each close; the dashboard reads it. Never edited by hand.", "rows": []}
    log["rows"] = [r for r in log["rows"] if r["date"] != row["date"]] + [row]
    log["latest"] = row
    cfg.log.write_text(dump(log))
    return row


def flags(C, row):
    """Red flags, computed: (level, what, what it means in plain words, what to do). level: red or amber."""
    out = [] if row else [("amber", "Health has not been measured yet", "The dashboard has no numbers to show.", "measure at the next close")]
    row = row or {"drift": None, "instructions": [], "red_checks": [], "retired_present": [], "roadmap_lines": 0, "loop": {"needs_owner": False}}
    if row.get("drift") is not None and row["drift"] >= DRIFT_AT:
        out.append(("red", f"{row['drift']} pieces of work in a row without measuring the goal",
                    "We kept building but never checked whether the engine predicts real people better. Building without measuring is how a project drifts.",
                    "make the next big piece of work score one real story"))
    for x in row["instructions"]:
        if x["size"] > x["cap"]:
            out.append(("red", f"{x['name']} is over its cap ({x['size']} of {x['cap']} {x['unit']})",
                        "The instructions every session reads got too long; long instructions get skimmed and ignored.", "cut it back under the cap"))
        elif x["size"] == x["cap"]:
            out.append(("amber", f"{x['name']} is full ({x['size']} of {x['cap']} {x['unit']})",
                        "There is no room left; one more would make it too long to read.", "anything new must replace something old"))
    out += [("red", f"A test is broken: {c}", "A check that used to guard the work now fails, so it guards nothing.", "fix it or retire it") for c in row["red_checks"]]
    out += [("amber", f"A retired file is still here: {p}", "Nothing reads it any more, but it still sits in the project and can confuse the next session.",
             "yours to remove") for p in row["retired_present"]]
    eng, hlp = row.get("engine", {}).get("lines", 0), row.get("helpers", {}).get("lines", 0)
    if eng and hlp / eng > BLOAT_RED:
        out.append(("red", f"Helper code is {hlp / eng:.1f}× the engine",
                    f"For every line of the engine itself there are {hlp / eng:.1f} lines of tools around it ({hlp:,} to {eng:,}). The tools are outgrowing the product.",
                    "the clean-up: remove or fold what nothing uses"))
    prev = C["rows"][-2] if len(C.get("rows", [])) > 1 else None
    grew = sum(x["count"] for x in row.get("clutter", [])) - sum(x["count"] for x in prev["clutter"]) if prev else 0
    if grew > 0:
        out.append(("amber", f"Clutter grew by {grew} since {fmt_date(prev['date'])}", "More loose files appeared than were cleared.", "give each a home or remove it"))
    if C.get("waiting"):
        out.append(("amber", f"{len(C['waiting'])} steps are ready and wait on you", "Work can go on, but only with you there.", "see 'Waits on you' in the loop"))
    if row["roadmap_lines"] > PROGRAM_CAP:
        out.append(("red", f"The dashboard's own program is past {PROGRAM_CAP} lines", "The measuring tool is itself bloating.", "cut it; the cap stays"))
    if not C["fresh"]:
        out.append(("red", "The road changed without your words", "Someone moved the plan without asking you.", "version it with your reason"))
    if row["loop"]["needs_owner"]:
        out.append(("amber", "The loop left a note that it waits on you", "When the loop works alone and gets stuck, it leaves you a note. One is still lying there.",
                    "read it, then clear it"))
    if C["versions"] and not C["versions"][-1].get("words_checked", True):
        out.append(("amber", "The road's last reason was not checked against what you typed", "This project cannot check your words yet.", "add a words check"))
    return out


# ── compute ──────────────────────────────────────────────────────────────────────────────────────────────────
def compute(cfg, R, D, log=None):
    bad = problems(R, D)
    if bad:
        fail("the road is not valid:\n  " + "\n  ".join(bad))
    by = {s["id"]: s for s in D["steps"]}
    marks, phases = {}, []
    for p in R["phases"]:
        ss = [{"id": i, "name": by[i]["name"], "status": by[i]["status"], "met": by[i]["met"], "of": by[i].get("cells", by[i].get("of", 0)),
               "owner": bool(by[i].get("needs_owner"))} for i in p["steps"]]
        ms = [{"id": m["id"], "name": m["name"], "says": m.get("says", ""), "met": all(proof_ok(cfg.root, x) for x in m["proof"])} for m in p.get("marks", [])]
        marks.update({m["id"]: m for m in ms})
        phases.append({"id": p["id"], "name": p["name"], "plain": p["plain"], "done_means": p["done_means"], "steps": ss, "marks": ms,
                       "notes": p.get("notes", []), "done": bool(ss or ms) and all(s["status"] == "done" for s in ss) and all(m["met"] for m in ms),
                       "steps_done": sum(s["status"] == "done" for s in ss)})
    T = R.get("titles", {})  # The owner's names for the phases and steps (2026-11-13: 'you are focused on describing it to yourself not to me')
    for p in phases:
        p["name"] = T.get(p["id"], p["name"])
        for s_ in p["steps"]:
            s_["name"] = T.get(s_["id"], s_["name"])
    here = next((i for i, p in enumerate(phases) if not p["done"]), None)
    for i, p in enumerate(phases):
        p["where"] = "done" if p["done"] else ("here" if i == here else "later")
        p["next"] = next((s for s in p["steps"] if s["status"] != "done"), None)
    met = lambda ref: (by[ref[5:]]["status"] == "done") if ref.startswith("step:") else marks[ref[5:]]["met"]
    named = lambda ref: by[ref[5:]]["name"] if ref.startswith("step:") else marks[ref[5:]]["name"]
    arch = []
    for bx in R.get("architecture", {}).get("nodes", []):
        level = "open"
        for lv in LEVELS:
            if not (bx.get(lv) and all(met(r) for r in bx[lv])):
                break
            level = lv
        nxt = (("open",) + LEVELS)[(("open",) + LEVELS).index(level) + 1] if level != "proven" else None
        arch.append(dict(bx, level=level, next=nxt, waits=[named(r) for r in bx.get(nxt, []) if not met(r)] if nxt else [],
                         code=bool(bx.get("code")) and all(glob.glob(str(cfg.root / f)) for f in bx["code"])))
    joined = ((log or {}).get("rows") or [{}])[-1].get("joined", {})
    for p in phases:  # a step that joined its phase after the phase's first step: added along the way
        first = min((joined[s["id"]] for s in p["steps"] if s["id"] in joined), default=None)
        for s_ in p["steps"]:
            s_["added"] = joined.get(s_["id"]) if first and joined.get(s_["id"], first) > first else None
    versions, last, prev = R.get("versions", []), {}, None
    for v in versions:
        old = {p["id"]: p for p in (prev or {}).get("phases", [])}
        last.update({p["id"]: v for p in v["road"]["phases"] if prev is None or old.get(p["id"]) != p})
        prev = v["road"]
    for p in phases:
        v = last.get(p["id"])
        p["last_change"] = {"v": v["v"], "date": v["date"]} if v else None
    rows = (log or {}).get("rows", [])
    C = {"project": R.get("project", ""), "goal": R.get("goal", ""), "phases": phases, "here": here, "arcs": R.get("arcs", []), "arch": arch, "edges": R.get("architecture", {}).get("edges", []),
         "arch_read": R.get("architecture", {}).get("read", ""), "versions": versions,
         "before": R.get("before", []), "fresh": bool(versions) and versions[-1]["fingerprint"] == fingerprint(road_of(R)),
         "fonts": R.get("fonts"), "style": R.get("style"), "words": R.get("words", []), "rows": rows, "row": rows[-1] if rows else None,
         "waiting": [s["name"] for p in phases for s in p["steps"] if s["status"] == "startable" and s["owner"]]}
    C["flags"] = flags(C, C["row"])
    return C


# ── the page ─────────────────────────────────────────────────────────────────────────────────────────────────
def fmt_date(d):
    try:
        x = dt.date.fromisoformat(d)
        return f"{x.day} {x.strftime('%b')} {x.year}"
    except Exception:
        return d





def page(C):
    """One screen: the arcs and where we are on top, the phases of this arc as bars, health, red flags and the architecture;
    everything else opens in a drawer (a link to an anchor; no script)."""
    e = lambda s: html.escape(str(s), quote=True)
    n, here, row, rows = len(C["phases"]), C["here"], C["row"], C["rows"]
    cur = C["phases"][here] if here is not None else None
    v = C["versions"][-1] if C["versions"] else None
    num = {p["id"]: i + 1 for i, p in enumerate(C["phases"])}
    prog = lambda s: "done" if s["status"] == "done" else f"{s['met']}/{s['of']}"
    added = lambda s: f"<span class='add'>+ added {e(fmt_date(s['added']))}</span>" if s.get("added") else ""
    stepli = lambda s: (f"<li class='s {e(s['status'])}'><span class='dot'></span><span>{e(s['name'])}{added(s)}</span>"
                        f"<span class='mono'>{prog(s)}</span></li>")
    allsteps = [s for p in C["phases"] for s in p["steps"]]
    panel = lambda p: (f"<div class='panel'><div class='ps'>{ {'done': 'Done', 'here': 'You are here', 'later': 'Not started'}[p['where']]} · phase {num[p['id']]}</div>"
                       f"<h3>{e(p['name'])}</h3><p>{e(p['done_means'])}</p>" + (f"<ul class='sl'>{''.join(stepli(s) for s in p['steps'])}</ul>" if p["steps"] else "")
                       + "".join(f"<p class='mono'>{'◆' if m['met'] else '◇'} {e(m['name'])}: {'true' if m['met'] else 'not yet'}</p>" for m in p["marks"])
                       + f"<p class='foot mono'>{len(p['notes'])} open items" + (f" · last change: version {p['last_change']['v']}" if p["last_change"] else "") + "</p></div>")
    pct = lambda p: round(100 * p["steps_done"] / len(p["steps"])) if p["steps"] else (100 if p["done"] else 0)
    now_id = cur["next"]["id"] if cur and cur["next"] else None
    segbar = lambda p, big="": (f"<span class='segs {big}'>" + "".join(
        f"<i class='{'done' if s['status'] == 'done' else 'now' if s['id'] == now_id else 'todo'}' data-n='{e(s['name'])}'></i>" for s in p["steps"])
        + ("" if p["steps"] else "<i class='todo goal'></i>") + "</span>")
    rowli = lambda p: (f"<li class='row {p['where']}' tabindex='0'><span class='rn'>{num[p['id']]}</span><span class='rname'>{e(p['name'])}</span>"
                       f"{segbar(p)}"
                       f"<span class='rc'>{p['steps_done']} of {len(p['steps'])}</span><span class='rs'>{'✓' if p['done'] else ''}</span>{panel(p)}</li>")
    arcs = C["arcs"] or [{"id": "all", "name": "The road", "plain": "", "phases": [p["id"] for p in C["phases"]]}]
    ph = {p["id"]: p for p in C["phases"]}
    arc_here = next((a for a in arcs if cur and cur["id"] in a["phases"]), arcs[-1])
    arc_here = dict(arc_here, index=arcs.index(arc_here) + 1)
    def arcchip(a):
        a = arc_here if a["id"] == arc_here["id"] else a
        ss = [s for i in a["phases"] for s in ph[i]["steps"]]
        d = sum(s["status"] == "done" for s in ss)
        st = "done" if all(ph[i]["done"] for i in a["phases"]) else "here" if a["id"] == arc_here["id"] else "later"
        return (f"<li class='arc {st}'><b>{e(a['name'])}</b><span class='meter'><i style='width:{round(100 * d / len(ss)) if ss else 0}%'></i></span>"
                f"<span class='mono'>{f'{d}/{len(ss)} steps' if ss else 'the goal'}</span></li>")
    arcbar = f"<ol class='arcs'>{''.join(arcchip(a) for a in arcs)}</ol>"
    now_id = cur["next"]["id"] if cur and cur["next"] else None
    ck = lambda s: (f"<li class='ck done'><span>✓</span>{e(s['name'])}</li>" if s["status"] == "done" else
                    f"<li class='ck now'><span>▶</span><b>Now</b>{e(s['name'])}</li>" if s["id"] == now_id else f"<li class='ck'><span>○</span>{e(s['name'])}</li>")
    hero = (f"<div class='hero'><span class='gl'>Phase {num[cur['id']]} · you are here</span><h3>{e(cur['name'])}</h3>"
            f"{segbar(cur, 'big')}<span class='mono'>{cur['steps_done']} of {len(cur['steps'])} steps done</span>"
            f"<ul class='cl'>" + (f"<li class='ck done' tabindex='0'><span>✓</span>{sum(s['status'] == 'done' for s in cur['steps'])} done: "
                                  + " · ".join(e(s["name"].split(":")[0].split(",")[0]) for s in cur["steps"] if s["status"] == "done")
                                  + f"<div class='pop'><span class='gl'>Done in this phase</span><ul class='sl'>{''.join(stepli(s) for s in cur['steps'] if s['status'] == 'done')}</ul></div></li>"
                                  if cur["steps_done"] else "")
            + "".join(ck(s) for s in cur["steps"] if s["status"] != "done") + "</ul></div>") if cur else ""
    rows_here = "".join(rowli(ph[i]) for i in arc_here["phases"] if not cur or i != cur["id"])
    allrows = "".join(f"<h4>{e(a['name'])} · {e(a['plain'])}</h4><ol class='rows'>{''.join(rowli(ph[i]) for i in a['phases'])}</ol>" for a in arcs)

    def trend(key):
        vals = [key(r) for r in rows if key(r) is not None][-12:]
        if len(vals) < 2:
            return ""
        d = vals[-1] - vals[0]
        return f"{'+' if d >= 0 else ''}{d:,} since {fmt_date(rows[-len(vals)]['date'])}"

    meter = lambda part, whole, cls="": f"<div class='meter {cls}'><i style='width:{min(100, round(100 * part / whole, 1)) if whole else 0}%'></i></div>"
    gauges = "<p class='mono'>Not measured yet.</p>"
    if row:
        eng, hlp = row["engine"]["lines"], row["helpers"]["lines"]
        ratio = hlp / eng if eng else 0
        caps = "".join(f"<li class='{'over' if x['size'] > x['cap'] else 'at' if x['size'] == x['cap'] else ''}'><span>{e(x['name'])}</span>"
                       f"<span class='mono'>{x['size']}/{x['cap']}</span></li>" for x in row["instructions"])
        G = [("Progress", f"{round(100 * row['progress']['met'] / row['progress']['of']) if row['progress']['of'] else 0}%",
              f"{row['progress']['met']:,} of {row['progress']['of']:,} checks say yes", "ok", trend(lambda r: r["progress"]["met"]), meter(row["progress"]["met"], row["progress"]["of"])),
             ("Goal measured", "never" if row["drift"] is not None and row["drift"] >= DRIFT_AT else "—" if row["drift"] is None else "recently",
              f"{row['drift']} pieces of work in a row, none measured whether it predicts real people" if row["drift"] is not None else "not counted here",
              "red" if (row["drift"] or 0) >= DRIFT_AT else "ok", trend(lambda r: r.get("drift")), ""),
             ("Bloat", f"{ratio:.1f}×", "lines of tools for every line of engine; lower is better",
              "red" if ratio > BLOAT_RED else "amber" if ratio > BLOAT_AMBER else "ok", trend(lambda r: r["helpers"]["lines"]),
              f"<div class='split'><i style='width:{round(100 * eng / (eng + hlp), 1) if eng + hlp else 0}%'></i></div><ul class='caps'>{caps}</ul>"),
             ("Clutter", f"{sum(x['count'] for x in row['clutter']):,}", " · ".join(f"{x['count']} {x['name']}" for x in row["clutter"]),
              "amber", trend(lambda r: sum(x["count"] for x in r["clutter"])), "")]
        gauges = "<div class='gauges'>" + "".join(
            f"<div class='g {cls}'><span class='gl'>{t}</span><span class='gv'>{val}</span><p>{e(d)}</p>{extra}<span class='delta'>{e(tr)}</span></div>"
            for t, val, d, cls, tr, extra in G) + "</div>"
    flag = lambda f: (f"<li class='{f[0]}'><span class='fd'></span><div><b>{e(f[1])}</b><p>{e(f[2])}</p></div>"
                      f"<span class='do'><span class='gl'>What to do</span>{e(f[3])}</span></li>")
    ranked = [f for f in C["flags"] if f[0] == "red"] + [f for f in C["flags"] if f[0] != "red"]
    top = "".join(f"<li class='{f[0]}'><span class='fd'></span><b>{e(f[1])}</b></li>" for f in ranked[:5]) or "<li class='none'>No red flags.</li>"
    allflags = "".join(flag(f) for f in ranked) or "<li class='none'>No red flags.</li>"
    opens = "".join(f"<h4>{e(p['name'])}</h4><ul>{''.join(f'<li>{e(x)}</li>' for x in p['notes'])}</ul>" for p in C["phases"] if p["notes"])
    def schematic():
        if not C["arch"]:
            return ""
        by = {b["id"]: b for b in C["arch"]}
        W, H = max(b["x"] + b["w"] for b in C["arch"]) + 20, max(b["y"] + b["h"] for b in C["arch"]) + 30
        out = []
        for x in C["edges"]:
            f, t = by[x["from"]], by[x["to"]]
            if x.get("back"):  # a wire going back: under both boxes
                y = max(f["y"] + f["h"], t["y"] + t["h"]) + 26
                pts = [(f["x"] + 40, f["y"] + f["h"]), (f["x"] + 40, y), (t["x"] + t["w"] / 2, y), (t["x"] + t["w"] / 2, t["y"] + t["h"])]
            elif f["x"] + f["w"] <= t["x"]:
                pts = [(f["x"] + f["w"], f["y"] + f["h"] / 2), (t["x"], t["y"] + t["h"] / 2)]
                if pts[0][1] != pts[1][1]:
                    mx = (pts[0][0] + pts[1][0]) / 2
                    pts = [pts[0], (mx, pts[0][1]), (mx, pts[1][1]), pts[1]]
            else:
                down, lo, hi = f["y"] < t["y"], max(f["x"], t["x"]), min(f["x"] + f["w"], t["x"] + t["w"])
                if lo < hi:  # they share a column: a straight wire down or up through the middle of what they share
                    pts = [((lo + hi) / 2, f["y"] + f["h"] if down else f["y"]), ((lo + hi) / 2, t["y"] if down else t["y"] + t["h"])]
                else:  # out of the side, across, then down into the target
                    tx, fy = t["x"] + t["w"] / 2, f["y"] + f["h"] / 2
                    pts = [(f["x"] if tx < f["x"] else f["x"] + f["w"], fy), (tx, fy), (tx, t["y"] if down else t["y"] + t["h"])]
            d = "M" + " L".join(f"{a_:.0f},{b_:.0f}" for a_, b_ in pts)
            mx, my = (pts[len(pts) // 2 - 1][0] + pts[len(pts) // 2][0]) / 2, (pts[len(pts) // 2 - 1][1] + pts[len(pts) // 2][1]) / 2
            out.append(f"<path class='w{' back' if x.get('back') else ''}' d='{d}' marker-end='url(#ah)'/>"
                       f"<text class='wl' x='{mx:.0f}' y='{my - 5:.0f}' text-anchor='middle'>{e(x['label'])}</text>")
        for b in C["arch"]:
            cls = f"n {b['level']}{'' if b['code'] else ' todo'}"
            wrap, line = [], ""
            for word in b["does"].split():  # the line under the name, wrapped to the box (about 6 px a letter)
                if len(line) + len(word) + 1 > (b["w"] - 24) // 6 and line:
                    wrap, line = wrap + [line], word
                else:
                    line = (line + " " + word).strip()
            wrap += [line] if line else []
            does = "".join(f"<text class='nd' x='{b['x'] + 12}' y='{b['y'] + 40 + 14 * i}'>{e(q)}</text>" for i, q in enumerate(wrap))
            top, half = b["y"] + 48 + 14 * len(wrap), len(b.get("parts") or []) > 4
            lines = "".join(f"<text class='np' x='{b['x'] + 12 + ((b['w'] - 24) / 2 if half and i >= 4 else 0)}' y='{top + 16 * (i % 4 if half else i)}'>{e(q)}</text>"
                            for i, q in enumerate(b.get("parts") or []))
            tip = f"{b['name']}: {b['does']}. {b['level']}" + (f"; to be {b['next']}: {'; '.join(b['waits'])}" if b["waits"] else "")
            out.append(f"<g class='{cls}'><title>{e(tip)}</title><rect x='{b['x']}' y='{b['y']}' width='{b['w']}' height='{b['h']}' rx='8'/>"
                       f"<text class='nt' x='{b['x'] + 12}' y='{b['y'] + 22}'>{e(b['name'])}</text>"
                       f"<text class='ns' x='{b['x'] + b['w'] - 10}' y='{b['y'] + b['h'] - 10}' text-anchor='end'>{'PLACEHOLDER' if not b['code'] else b['level'].upper()}</text>"
                       f"{does}{lines}</g>")
        legend = ("<div class='legend'><span><i class='lg built'></i>code exists</span><span><i class='lg ruled'></i>ruled by you</span>"
                  "<span><i class='lg todo'></i>placeholder: not built yet</span><span><i class='lg wire'></i>what flows</span><span>hover a box for what it waits on</span></div>")
        return (f"{legend}<div class='schem'><svg viewBox='0 0 {W:.0f} {H:.0f}' role='img' aria-label='The architecture'>"
                "<defs><marker id='ah' viewBox='0 0 8 8' refX='7' refY='4' markerWidth='7' markerHeight='7' orient='auto'><path d='M0,0 L8,4 L0,8 z'/></marker></defs>"
                + "".join(out) + "</svg></div>")
    arch = schematic()
    words = "".join(f"<div><dt>{e(w['word'])}</dt><dd>{e(w['means'])}</dd></div>" for w in C["words"])
    vers = "".join(f"<h4>Version {x['v']} · {e(fmt_date(x['date']))}</h4><ul><li>“" + "” · “".join(e(r) for r in x["reason"]) + "”"
                   + ("" if x.get("words_checked", True) else " (not verified as typed by the owner)")
                   + "".join(f"</li><li>{e(c)}" for c in x["changed"]) + "</li></ul>" for x in reversed(C["versions"]))
    before = "".join(f"<li>{e(fmt_date(b['date']))}: {e(b['what'])} ({e(b['road'])}, {e(b['commit'])})</li>" for b in C["before"])
    title = e(cur["name"]) if cur else "Every phase is done"
    sub = (f"Phase {here + 1} of {n} · {sum(s['status'] == 'done' for s in allsteps)} of {len(allsteps)} steps done"
           + (f" · next: <b>{e(cur['next']['name'])}</b>" if cur["next"] else "")) if cur else ""
    drawer = lambda id_, t, body: (f"<section class='drawer' id='{id_}' aria-label='{e(t)}'><a class='scrim' href='#'></a><div class='dw'>"
                                   f"<header><h2>{e(t)}</h2><a class='x' href='#'>Close</a></header>{body}</div></section>")
    nred, namb = sum(f[0] == "red" for f in C["flags"]), sum(f[0] == "amber" for f in C["flags"])
    links = "".join(f"<link rel='stylesheet' href='{e(C[k])}'>" for k in ("fonts", "style") if C.get(k))
    stamp = f"{e(C['project'])} · roadmap v{v['v'] if v else 0}" + (f" · measured {e(fmt_date(row['date']))}" if row else "")
    card = lambda id_, t, small, body, more="": (f"<section class='card' id='c-{id_}'><header><h2>{t}</h2><span class='gl'>{small}</span>"
                                                 + (f"<a class='more' href='#d-{id_}'>{more} →</a>" if more else "") + f"</header>{body}</section>")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{e(C['project'])} dashboard</title>\n<!-- GENERATED by loop/scripts/roadmap.py from loop/roadmap.json, the done map and "
            f"loop/qa/health-log.json; do not edit by hand. -->\n{links}</head><body><div class='dash'>"
            f"<header class='top'><div><div class='tag'>{stamp}</div><h1>{title}</h1><p class='sub'>{sub}</p></div>{arcbar}"
            f"<nav class='jump'><a href='#d-words'>Words</a><a href='#d-history'>History</a></nav></header>"
            + card("road", f"{e(arc_here['name'])}", f"{len(arc_here['phases'])} phases · {arc_here['index']} of {len(arcs)} on the road", f"{hero}<ol class='rows'>{rows_here}</ol>", f"all {n} phases")
            + card("health", "Health", "is it staying small and on course?", gauges)
            + card("flags", "Red flags", f"{nred} red · {namb} amber", f"<ul class='flags mini'>{top}</ul>", "explained")
            + card("arch", "Architecture", "how the product fits together", f"<div class='mini'>{arch}</div>" if arch else "<p class='mono'>Not drawn yet.</p>", "full view")
            + "</div>"
            + drawer("d-road", "The whole road", f"<div class='legend'><span><i class='lg done'></i>step done</span><span><i class='lg startable'></i>can start now</span>"
                     f"<span><i class='lg blocked'></i>waits on another step</span><span>hover a phase: steps added along the way are marked there</span></div>{allrows}")
            + drawer("d-flags", "Red flags, explained", f"<ul class='flags'>{allflags}</ul>")
            + drawer("d-arch", "Architecture", f"<p class='lede'>{e(C['arch_read'])}</p>{arch}")
            + drawer("d-words", "Words we use", f"<dl class='words'>{words}</dl>")
            + drawer("d-history", "History", f"<h4>Open items by phase</h4>{opens}<h4>How the road changed</h4>{vers}"
                     + (f"<h4>Before version 1</h4><ul>{before}</ul>" if before else ""))
            + "</body></html>\n")


# ── the planted truths (every project runs these: `roadmap.py selftest`) ──────────────────────────────────────
def selftest():
    """Made-up projects where the answer is written down first, and every refusal."""
    import tempfile
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    def refused(fn):
        try:
            fn()
        except SystemExit as ex:
            return str(ex)
        return ""

    STEP = lambda i, st, met, of: {"id": i, "name": f"step {i}", "status": st, "met": met, "cells": of, "needs_owner": i == "b2"}
    MAP = {"met": 7, "cells": 12, "steps": [STEP("a1", "done", 3, 3), STEP("a2", "done", 2, 2), STEP("b1", "done", 1, 1),
                                            STEP("b2", "startable", 1, 4), STEP("c1", "blocked", 0, 2)]}
    HEALTH = {"engine": {"dirs": ["eng"], "ext": [".ts"], "skip": [".test.ts"]}, "helpers": {"dirs": ["tools"], "ext": [".py"]},
              "instructions": [{"name": "Rules file", "file": "RULES.md", "cap": 3}], "clutter": [{"name": "loose", "dir": "loose"}],
              "retired": ["old.json"], "work": "units"}

    def road():
        return {"project": "Toy", "goal": "a toy goal", "page": "loop/roadmap.html",
                "phases": [{"id": "a", "name": "First", "plain": "the first", "done_means": "a1 and a2 done", "steps": ["a1", "a2"],
                            "marks": [{"id": "M1", "name": "made", "says": "the made file exists", "proof": [{"file": "made.txt"}]}], "notes": []},
                           {"id": "b", "name": "Second", "plain": "the second", "done_means": "b1 and b2 done", "steps": ["b1", "b2"], "marks": [],
                            "notes": ["a note for the second"]},
                           {"id": "c", "name": "Third", "plain": "the third", "done_means": "c1 done", "steps": ["c1"],
                            "marks": [{"id": "M2", "name": "never", "says": "a file nobody made", "proof": [{"file": "never.txt"}]}], "notes": []}],
                "architecture": {"read": "read it left to right", "nodes": [
                    {"id": "p1", "name": "Built part", "does": "x", "x": 10, "y": 10, "w": 100, "h": 60, "ruled": ["step:a1"], "built": ["mark:M1"], "proven": ["mark:M2"], "code": ["made.txt"]},
                    {"id": "p2", "name": "Open part", "does": "y", "x": 200, "y": 10, "w": 100, "h": 60, "ruled": ["step:c1"], "built": ["step:c1"], "proven": ["step:c1"]}],
                    "edges": [{"from": "p1", "to": "p2", "label": "feeds"}, {"from": "p2", "to": "p1", "label": "back", "back": True}]},
                "words": [{"word": "Phase", "means": "one big stretch of the road"}],
                "health": HEALTH, "versions": [], "before": []}

    def setup(td, R=None, D=None):
        T = Path(td)
        (T / "loop" / "qa").mkdir(parents=True, exist_ok=True)
        (T / "loop" / "roadmap.json").write_text(json.dumps(R or road()))
        (T / "loop" / "qa" / "done-map.json").write_text(json.dumps(D or MAP))
        for f, t in [("made.txt", "x"), ("eng/a.ts", "1\n" * 10), ("eng/a.test.ts", "1\n" * 50), ("tools/x.py", "1\n" * 5),
                     ("tools/y.py", "1\n" * 3), ("tools/z.py", "1\n" * 2), ("RULES.md", "a\nb\nc\nd\n"), ("old.json", "{}")]:
            (T / f).parent.mkdir(parents=True, exist_ok=True)
            (T / f).write_text(t)
        (T / "loose").mkdir(exist_ok=True)
        for i in range(4):
            (T / "loose" / f"l{i}").write_text("x")
        return Cfg(T)

    HIS = lambda w: w == "his words, typed by him"
    with tempfile.TemporaryDirectory() as td:
        cfg = setup(td)
        R, C, pg = build(cfg)
        ph = {p["id"]: p for p in C["phases"]}
        # A KNOWN ROAD GIVES THE KNOWN PAGE
        must(ph["a"]["where"] == "done" and ph["b"]["where"] == "here" and ph["c"]["where"] == "later", "done, here, later are computed from the map")
        must(C["here"] == 1 and ph["b"]["next"]["id"] == "b2", "where we are is the first phase not done, and its next step the first not done")
        must(ph["b"]["steps_done"] == 1 and [s["of"] for s in ph["b"]["steps"]] == [1, 4], "each step carries its progress from the map")
        must(ph["a"]["marks"][0]["met"] and not ph["c"]["marks"][0]["met"], "a mark is met only when its proof passes")
        parts = {b["name"]: b for b in C["arch"]}
        must(parts["Built part"]["level"] == "built" and parts["Built part"]["waits"] == ["never"] and parts["Built part"]["code"], "a part ruled and built shows built, naming what it waits on to be proven")
        must(parts["Open part"]["level"] == "open" and parts["Open part"]["waits"] == ["step c1"] and not parts["Open part"]["code"], "a part whose ruling waits shows open, naming what it waits on")
        must("<g class='n open todo'>" in pg and ">PLACEHOLDER<" in pg and "<g class='n built'>" in pg and ">feeds</text>" in pg and "class='w back'" in pg,
             "ARCHITECTURE: a schematic; a part with no code is a placeholder, the wires carry their labels, a wire going back is drawn back")
        card = pg.split("<section class='drawer'")[0]
        must(card.count("class='hero'") == 1 and "<li class='ck now'><span>▶</span><b>Now</b>step b2</li>" in card and "<li class='ck done' tabindex='0'><span>✓</span>1 done: step b1<div class='pop'>" in card and "<i class='now' data-n='step b2'>" in card
             and card.count("<li class='row ") == 2 and "3 of 5 steps done" in pg and "<script" not in pg,
             "NEXT UP: the phase we are in as a card with its steps, the one to do now lit; the other phases as one line each")
        must(pg.count("class='drawer'") == 5 and "href='#d-road'" in card and "href='#d-flags'" in card, "ONE SCREEN: the rest opens in drawers from the cards")
        must("<dt>Phase</dt><dd>one big stretch of the road</dd>" in pg, "WORDS: the shared words are on the page")
        must("You are here" in pg and "step b2" in pg and "1/4" in pg, "the page shows where we are and each step's progress")
        drw = pg.split("id='d-road'")[1]
        must(drw.split("class='row here'")[1].split("<div class='panel'>")[1].split("</div></li>")[0].count("<p") == 2 and "1 open items" in pg, "HIERARCHY: a panel holds what done means, the steps and one footer line")
        must(drw.count("class='row here'") == 1 and "a note for the second" not in card, "HIERARCHY: one phase is here; open items sit in a drawer, not on the screen")
        R2 = dict(R, arcs=[{"id": "x", "name": "Arc one", "plain": "p", "phases": ["a"]}, {"id": "y", "name": "Arc two", "plain": "q", "phases": ["b", "c"]}])
        pg2 = page(compute(cfg, R2, MAP))
        card2 = pg2.split("<section class='drawer'")[0]
        must("<h2>Arc two</h2>" in card2 and card2.count("<li class='row ") == 1 and "<li class='arc done'><b>Arc one</b>" in card2 and "<li class='arc here'><b>Arc two</b>" in card2,
             "TWO LEVELS: the arcs on top, and only the phases of the arc we are in on the screen")
        must(any("sits in no arc" in x for x in problems(dict(R2, arcs=R2["arcs"][:1]), MAP)), "a phase in no arc is refused")
        pg3 = page(compute(cfg, dict(R, titles={"a": "First thing", "b": "Do the second thing", "c": "Third thing", "a1": "s1", "a2": "s2", "b1": "s3", "b2": "Ship the widget", "c1": "s4"}), MAP))
        must("<h3>Do the second thing</h3>" in pg3 and "Ship the widget" in pg3 and "step b2" not in pg3.split("<section class='drawer'")[0],
             "NAMES FOR THE OWNER: their titles replace the map's names on the page")
        must(any("neither a phase nor a step" in x for x in problems(dict(R, titles={"zz": "x"}), MAP)), "a title for nothing is refused")
        must(any("'c1' has no plain title" in x for x in problems(dict(R, titles={"b2": "Ship the widget"}), MAP)), "a new step without a plain title is refused")
        must(C["waiting"] == ["step b2"], "a startable step that needs the owner is listed as waiting on him")
        must(any("no version" in x for x in check(cfg)) and any("changed without your words" in f[1] for f in C["flags"]), "a road with no version is refused and flagged")
        must(any("not been measured" in f[1] for f in C["flags"]), "an unmeasured project says so")
        # NO SILENT CHANGE
        must("not found among what the owner typed" in refused(lambda: change(cfg, "words he never typed", "2026-11-13", said=HIS)), "a change without his words is refused")
        must("yyyy-mm-dd" in refused(lambda: change(cfg, "his words, typed by him", "13 Nov", said=HIS)), "a version with a bad date is refused")
        v = change(cfg, "his words, typed by him", "2026-11-13", said=HIS)
        must(v["v"] == 1 and "the road set" in v["changed"][0], "version 1 is written with his words and what it set")
        must("nothing to version" in refused(lambda: change(cfg, "his words, typed by him", "2026-11-14", said=HIS)), "a version that changes nothing is refused")
        R = J(cfg.road)
        R["phases"][1]["name"] = "Second, renamed"
        R["health"]["instructions"][0]["cap"] = 4
        cfg.road.write_text(json.dumps(R))
        must(any("without a new version" in x for x in check(cfg)), "renaming a phase or raising a cap without a version fails --check")
        R["phases"][1]["steps"].remove("b2")
        R["phases"][2]["steps"].insert(0, "b2")
        cfg.road.write_text(json.dumps(R))
        v2 = change(cfg, "his words, typed by him", "2026-11-14", said=HIS)
        must(v2["v"] == 2 and "phase renamed: Second → Second, renamed" in v2["changed"] and "step 'b2' moved: Second → Third" in v2["changed"]
             and any("health" in c for c in v2["changed"]), "version 2 names the rename, the move and the cap it carries")
        R = J(cfg.road)
        R["health"]["instructions"][0]["cap"] = 3
        R["phases"][0]["notes"] = ["a free note"]
        cfg.road.write_text(json.dumps(R))
        change(cfg, "his words, typed by him", "2026-11-14", said=HIS)
        # A KNOWN PROJECT GIVES KNOWN GAUGES
        row = measure(cfg, "2026-11-14")
        must(row["engine"] == {"files": 1, "lines": 10} and row["helpers"] == {"files": 3, "lines": 10}, "the code is counted, tests left out")
        must(row["instructions"][0]["size"] == 4 and row["clutter"][0]["count"] == 4 and row["retired_present"] == ["old.json"], "instruction size, clutter and retired files are counted")
        R, C, pg = build(cfg)
        fw = [f[1] for f in C["flags"]]
        must(any("over its cap (4 of 3" in w for w in fw) and any("old.json" in w for w in fw), "RED FLAGS: a cap crossed and a retired file present are flagged")
        must(all(f[2] and f[3] for f in C["flags"]) and ("cut it back under the cap" in pg and "yours to remove" in pg and "can confuse the next session" in pg), "every flag says what to do, on the page")
        must("1.0×" in pg and "4 loose" in pg and "4/3" in pg and "of 12 checks say yes" in pg, "the page shows the measured counts")
        must(any("wait on you" in w for w in fw), "a startable step waiting on the owner is flagged")
        must(check(cfg) != [] and write(cfg) and check(cfg) == [], "THE PAGE IS THE LOG'S: after a new measurement the page is stale until rebuilt")
        must("1.0×" in pg and " since " not in pg.split("<section class=" + chr(39) + "drawer")[0], "one row shows no trend, not a made-up one")
        (Path(td) / "tools" / "w.py").write_text("1\n" * 25)
        measure(cfg, "2026-11-15")
        pg = build(cfg)[2]
        must("+25 since 14 Nov 2026" in pg, "THE TREND IS REAL: two rows on different dates show the change between them")
        C2 = build(cfg)[1]
        log = J(cfg.log)
        log["rows"][-1]["joined"] = {"b1": "2026-11-01", "b2": "2026-11-09", "a1": "2026-11-01", "a2": "2026-11-01", "c1": "2026-11-01"}
        log["latest"] = log["rows"][-1]
        cfg.log.write_text(json.dumps(log))
        pg3 = build(cfg)[2]
        must("step b2<span class='add'>+ added 9 Nov 2026</span>" in pg3 and "step b1<span class='add'>" not in pg3 and "class='startable add'" not in pg3, "ADDED ALONG THE WAY: a step that joined its phase later is marked, the first is not")
        must(any("Helper code is 3.5×" in f[1] for f in C2["flags"]), "helper code past 3× the engine is flagged")
        row = dict(row, drift=5, roadmap_lines=PROGRAM_CAP + 1, instructions=[], retired_present=[], red_checks=["t"])
        fw = [f[1] for f in flags(dict(C, fresh=True), row)]
        must(any("5 pieces of work" in w for w in fw) and any("past 900" in w for w in fw) and any("test is broken" in w for w in fw),
             "drift at 5, the program past its cap and a failing check are flagged")
        clean = dict(row, drift=0, roadmap_lines=10, red_checks=[])
        must(flags(dict(C, fresh=True, versions=[], waiting=[]), clean) == [], "a clean project raises no flag")
        must(J(cfg.log)["rows"][-1] == J(cfg.log)["latest"] and len(J(cfg.log)["rows"]) == 2, "one row per day; the log's latest row is its last row")
        R = J(cfg.road)
        R["versions"][0]["road"]["phases"][0]["name"] = "rewritten history"
        cfg.road.write_text(json.dumps(R))
        must(any("does not match its fingerprint" in x for x in check(cfg)), "a kept version rewritten by hand is caught")
    with tempfile.TemporaryDirectory() as td:
        cfg = setup(td)
        must("not signed" in refused(lambda: sign(cfg, "2026-11-13", "his words, typed by him", said=HIS)), "no sign-off on a road with no version")
        change(cfg, "his words, typed by him", "2026-11-13", said=HIS)
        write(cfg)
        must("not signed" in refused(lambda: sign(cfg, "2026-11-13", "words he never typed", said=HIS)), "a sign-off in words he never typed is refused")
        out = sign(cfg, "2026-11-13", "his words, typed by him", said=HIS, name="dashboard")
        must(out.name == "owner-dashboard-2026-11-13.json" and J(out)["version"] == 1, "a sign-off names what it signs and the version")
        must("never written over" in refused(lambda: sign(cfg, "2026-11-14", "his words, typed by him", said=HIS, name="dashboard")), "a second sign-off is refused")
        R = J(cfg.road)
        R["phases"][0]["marks"][0]["proof"] = [{"file": "never.txt"}]
        R["versions"][0]["words_checked"] = False
        C = compute(cfg, R, MAP)
        must(C["phases"][0]["where"] != "done", "a phase whose steps are done but whose mark is not true is not done")
        must(any("not checked" in f[1] for f in C["flags"]) and "not verified as typed by the owner" in page(C), "unchecked words are flagged and shown")
    # EVERY STEP ONCE, AND THE OTHER REFUSALS
    for mutate, what in [(lambda R: R["phases"][1]["steps"].append("a1"), "sits in two phases"), (lambda R: R["phases"][2]["steps"].remove("c1"), "in no phase"),
                         (lambda R: R["phases"][2]["steps"].append("zz"), "does not have"), (lambda R: R["architecture"]["nodes"][0]["ruled"].append("step:zz"), "neither a step"),
                         (lambda R: R["architecture"]["edges"].append({"from": "p1", "to": "zz", "label": "x"}), "names a part the drawing does not have"),
                         (lambda R: R["phases"][1].update({"id": "a"}), "used twice"), (lambda R: R["phases"][2]["marks"][0].update({"proof": []}), "has no proof")]:
        with tempfile.TemporaryDirectory() as td:
            R = road()
            mutate(R)
            cfg = setup(td, R)
            must(any(what in x for x in check(cfg)) and what in refused(lambda: build(cfg)), f"the build refuses a road where {what}")
    if bad:
        print(f"roadmap selftest: FAILED {len(bad)} of {n}:\n  " + "\n  ".join(bad))
        return 1
    print(f"roadmap selftest: ALL GREEN ({n} planted checks)")
    return 0


# ── commands ─────────────────────────────────────────────────────────────────────────────────────────────────
def build(cfg):
    R, D = J(cfg.road), J(cfg.map)
    C = compute(cfg, R, D, J(cfg.log) if cfg.log.exists() else None)
    return R, C, page(C)


def write(cfg):
    R, C, pg = build(cfg)
    (cfg.root / R.get("page", "loop/roadmap.html")).write_text(pg)
    return C


def check(cfg):
    R, D = J(cfg.road), J(cfg.map)
    out = problems(R, D)
    if out:
        return out
    if not R.get("versions"):
        out.append("the road has no version yet: run `roadmap.py change \"<his words>\"`")
    elif R["versions"][-1]["fingerprint"] != fingerprint(road_of(R)):
        out.append("the road changed without a new version: run `roadmap.py change \"<his words>\"`")
    for i, v in enumerate(R.get("versions", [])):
        if v.get("v") != i + 1:
            out.append(f"version {i + 1} is numbered {v.get('v')}")
        if v.get("fingerprint") != fingerprint(v.get("road", {})):
            out.append(f"version {v.get('v')}'s kept road does not match its fingerprint")
    pp = cfg.root / R.get("page", "loop/roadmap.html")
    if not pp.exists() or pp.read_text() != build(cfg)[2]:
        out.append(f"the page {R.get('page', 'loop/roadmap.html')} differs from a fresh build")
    return out


def change(cfg, words_, date=None, said=None):
    R = J(cfg.road)
    lines = [w.strip() for w in words_.split(";") if w.strip()]
    said = said if said is not None else said_checker()
    if not lines:
        fail("no change without his words: give the reason the owner typed")
    if said is not None and not all(said(w) for w in lines):
        fail("not changed: those words are not found among what the owner typed in this project")
    bad = problems(R, J(cfg.map))
    if bad:
        fail("the road is not valid, so no version is written:\n  " + "\n  ".join(bad))
    road, vs = road_of(R), R.setdefault("versions", [])
    if vs and vs[-1]["fingerprint"] == fingerprint(road):
        fail(f"the road is the same as version {vs[-1]['v']}: nothing to version")
    date = date or dt.date.today().isoformat()
    if not re.fullmatch(r"20\d\d-\d\d-\d\d", date):
        fail("the date is yyyy-mm-dd")
    v = {"v": len(vs) + 1, "date": date, "reason": lines, "words_checked": said is not None,
         "changed": changes(vs[-1]["road"] if vs else None, road), "fingerprint": fingerprint(road), "road": road}
    vs.append(v)
    cfg.road.write_text(dump(R))
    write(cfg)
    return v


SIGNS = {"roadmap": "The owner's sign-off on the roadmap: this road, on this page, is the one road of the project from now on; it changes only through a "
                    "numbered version carrying his words. It rules no part of the engine and does not say the phases are right.",
         "dashboard": "The owner's sign-off on the dashboard: this page is how the project's health is watched from now on, every number from the dated "
                      "measurement written at each close. It does not say the project is pristine; it says this is how we will see whether it is."}


def sign(cfg, date, words_, said=None, name="roadmap"):
    R = J(cfg.road)
    folder = cfg.root / R.get("signoffs", "loop/qa")
    if name not in SIGNS or not re.fullmatch(r"20\d\d-\d\d-\d\d", date):
        fail(f"sign what ({', '.join(SIGNS)}), on a date yyyy-mm-dd")
    if any(folder.glob(f"owner-{name}-*.json")):
        fail("not signed: a sign-off is already there, and it is never written over")
    bad = check(cfg)
    if bad:
        fail("not signed: " + "; ".join(bad))
    said = said if said is not None else said_checker()
    lines = [w.strip() for w in words_.split(";") if w.strip()]
    if not lines or (said is not None and not all(said(w) for w in lines)):
        fail("not signed: those words are not found among what the owner typed in this project")
    v = R["versions"][-1]
    out = folder / f"owner-{name}-{date}.json"
    out.write_text(dump({"what": SIGNS[name], "words": lines, "at": date, "road": "loop/roadmap.json", "version": v["v"],
                         "fingerprint": v["fingerprint"], "phases": [p["name"] for p in v["road"]["phases"]]}))
    return out


def status(C):
    v = C["versions"][-1]["v"] if C["versions"] else None
    if C["here"] is None:
        return f"Roadmap v{v}: all {len(C['phases'])} phases done"
    p = C["phases"][C["here"]]
    return (f"Roadmap v{v} · phase {C['here'] + 1} of {len(C['phases'])}: {p['name']} ({p['steps_done']} of {len(p['steps'])} steps done)"
            + (f" · next: {p['next']['name']}" if p["next"] else "") + f" · flags: {sum(f[0] == 'red' for f in C['flags'])} red, {sum(f[0] == 'amber' for f in C['flags'])} amber" + ("" if C["fresh"] else " · THE ROAD CHANGED WITHOUT A VERSION"))


def main(argv):
    if argv[:1] == ["selftest"]:
        return selftest()
    cfg = Cfg()
    if argv[:1] == ["change"]:
        v = change(cfg, argv[1], argv[argv.index("--date") + 1] if "--date" in argv else None)
        print(f"roadmap: version {v['v']} written · " + " · ".join(v["changed"]))
        return 0
    if "--sign" in argv:
        i = argv.index("--sign")
        out = sign(cfg, argv[i + 1], argv[i + 2], name=argv[i + 3] if len(argv) > i + 3 else "roadmap")
        print(f"roadmap: signed, {out.relative_to(cfg.root)}")
        return 0
    if "--check" in argv:
        bad = check(cfg)
        print("roadmap: one road, versioned, and the page is a fresh build" if not bad else "roadmap: NOT CLEAN\n  " + "\n  ".join(bad))
        return 1 if bad else 0
    if "--measure" in argv:
        row = measure(cfg)
        print(f"roadmap: measured {row['date']} · helpers {row['helpers']['lines']:,} lines to engine {row['engine']['lines']:,}")
    if "--status" in argv:
        print(status(build(cfg)[1]))
        return 0
    print(status(write(cfg)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
