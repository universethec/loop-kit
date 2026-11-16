#!/usr/bin/env python3
"""new_project.py — create a project already running the owner's autonomous Claude loop (lean form).

  python3 new_project.py <path> --answers answers.json    create it: copy template/, fill it, git init, hooks, commit
  python3 new_project.py <path> --answers a.json --adopt   a folder that already has code: add only loop/, .claude/
                                                         and the kit's root files that are missing; never overwrite
  python3 new_project.py --selftest                      create a sample project in a temp dir and run its selftests
  python3 new_project.py --sample                        print a sample answers.json
  python3 new_project.py --upgrade <project> [--diff]    what changed in the kit since the project was booted (reads only)
  python3 new_project.py --help                          this text

What it does: copies template/ to <path> (which must not exist or be empty); fills CLAUDE.md, loop/HANDOFF.md,
DECISIONS.md; writes loop/kit.json, loop/qa/done-rules.json, loop/qa/memory.json (the owner's personal rules, then
the project's), loop/qa/resources.json; `git init -b main`; core.hooksPath = .claude/githooks; builds the done map;
first commit. Then, in the project: `python3 -I loop/scripts/build_donemap.py --brief`, `bash loop/scripts/selftest.sh`,
and when the owner says so, `loop/loop.sh start`.

answers.json (only name, mission and steps are required):
  {"name": "Toy Counter",                       project name (the tmux session is its slug)
   "mission": "one sentence: what done means for the whole project",
   "steps": [                                   the done map, in order of work
     {"id": "core", "name": "Counter works",    id optional (slug of name)
      "done_when": [                            checkable lines, at least one per step
        "file:src/counter.py",                  shorthand: file:<glob> | cmd:<shell> | grep:<path>::<text> | git:<path>
        {"what": "tests pass", "cmd": "python3 -m unittest -q"},     or a full line (kit.py: file/cmd/json/grep/git)
        {"what": "v1", "json": "loop/x.json", "field": "a.b", "op": ">=", "value": 1}],
      "needs_owner": false,                      true: the unattended loop never takes it
      "waits_on": []}],                         default: the step before it
   "phases": [{"name": "Counter works",          the roadmap, optional; default: one phase per step. Each step in one
               "steps": ["core"], "done_means": "..."}],   phase; version 1's reason is the mission
   "architecture": {"read": "...", "nodes": [{"id": "a", "name": "...", "does": "...", "x": 20, "y": 20, "w": 160, "h": 90, "ruled": ["step:core"],
                     "built": [...], "proven": [...], "code": ["src/x.py"]}], "edges": [{"from": "a", "to": "b", "label": "..."}]},  the schematic, optional
   "words": [{"word": "...", "means": "..."}],  the shared words, optional
   "genesis": {"what": "...", "why": "...", "for_whom": "...", "not": "...", "done": "...", "open": "...",
               "words": ["the owner's own sentences, verbatim"]},   the founding interview -> GENESIS.md
   "mission_words": "The owner's own words for the mission, if they gave them: ledger entry 1 (default: the mission line)",
   "open_problem": "what is open, one sentence, optional: the ledger's first Open line",
   "doors": ["money", "what a user sees"],      what always needs the owner (deleting files, rewriting git history and
                                                a new root entry are always added)
   "rules": [{"id": "x", "headline": "<=170 chars, printed at every start", "rule": "the full rule"}],
   "model": "claude-opus-5-5", "effort": "xhigh", "notify_title": "Toy Counter", "ntfy_topic": "<ntfy topic>",
   "root_entries": ["src", "tests"],             allowed at the repo root besides the kit's own (the default); each
                                                 missing one is made at boot as an empty folder with a .gitkeep
   "locked_globs": ["data/raw/*"],               paths no session may change (loop/reviews/* is always locked)
   "allowed_tools_extra": ["Bash(npm test:*)"]}  extra tools for unattended slices
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent
TEMPLATE = KIT / "template"
DEFAULT_TOPIC = ""  # no default: each project names its own ntfy topic in answers.json ("ntfy_topic"); without one, notify.sh prints instead of buzzing
ALWAYS_DOORS = ["deleting files, rewriting git history or a new root entry"]
SAMPLE = {
    "name": "Toy Counter",
    "mission": "A tiny word counter: a script that counts the words of a file, with tests that prove it.",
    "genesis": {"what": "A counter of the words in a text file.", "why": "Tools that count words disagree on hyphens and numbers.",
                "not": "Not an editor, not a spell checker.", "done": "It counts my own files the way I count them.",
                "open": "Whether a hyphenated word is one word or two.",
                "words": ["I want a counter I can trust on my own files, not a toy that only passes its tests"]},
    "steps": [
        {"id": "counter", "name": "The counter counts", "done_when": [
            "file:src/count.py",
            {"what": "the counter's tests pass", "cmd": "python3 -I -m unittest discover -s tests -q"}]},
        {"id": "ship", "name": "The owner tries it on their own file", "needs_owner": True, "done_when": [
            {"what": "The owner's verdict is recorded", "grep": "DECISIONS.md", "has": "counter accepted"}]}],
    "doors": ["what a user sees", "money"],
    "rules": [{"id": "small", "headline": "Keep every file under 200 lines; split before it grows.",
               "rule": "Keep every source file under 200 lines; when one would grow past it, split it first."}],
    "notify_title": "Toy Counter",
    "root_entries": ["src", "tests"],
}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "project"


def line_of(x):
    """A done_when entry -> a checkable line (kit.py's vocabulary)."""
    if isinstance(x, dict):
        return x
    if not isinstance(x, str) or ":" not in x:
        raise ValueError(f"not a checkable line: {x!r} (use file:/cmd:/grep:path::text/git: or an object)")
    kind, rest = x.split(":", 1)
    kind, rest = kind.strip(), rest.strip()
    if kind == "file":
        return {"what": f"{rest} exists", "file": rest}
    if kind == "cmd":
        return {"what": f"`{rest}` passes", "cmd": rest}
    if kind == "git":
        return {"what": f"{rest} is tracked", "git": rest}
    if kind == "grep" and "::" in rest:
        p, has = rest.split("::", 1)
        return {"what": f"{p.strip()} holds '{has.strip()}'", "grep": p.strip(), "has": has.strip()}
    raise ValueError(f"not a checkable line: {x!r}")


def problems(A):
    sys.path.insert(0, str(TEMPLATE / "loop" / "scripts"))
    import kit  # the template's own vocabulary, so the kit and its projects never disagree
    out = []
    for k in ("name", "mission"):
        if not isinstance(A.get(k), str) or not A[k].strip():
            out.append(f"'{k}' is required")
    steps = A.get("steps") or []
    if not steps:
        out.append("'steps': at least one step, each with done_when lines")
    ids = []
    for i, s in enumerate(steps):
        sid = s.get("id") or slug(s.get("name", f"step-{i + 1}"))
        if sid in ids:
            out.append(f"step {sid}: repeated id")
        ids.append(sid)
        if not s.get("done_when"):
            out.append(f"step {sid}: no done_when line, so it could never be done")
        for j, x in enumerate(s.get("done_when") or []):
            try:
                out += [f"step {sid} line {j}: {p}" for p in kit.problems(line_of(x))]
            except ValueError as e:
                out.append(f"step {sid} line {j}: {e}")
    for sid, s in zip(ids, steps):
        out += [f"step {sid}: waits on unknown step {w!r}" for w in s.get("waits_on", []) if w not in ids]
    rules = A.get("rules") or []
    base = len(json.loads((TEMPLATE / "loop" / "qa" / "memory.json").read_text())["rules"])
    if base + len(rules) > 12:
        out.append(f"{base} personal + {len(rules)} project rules is over the cap of 12")
    for r in rules:
        if not r.get("id") or not r.get("rule") or not r.get("headline") or len(r["headline"]) > 170:
            out.append(f"rule {r.get('id')!r}: needs id, rule, and a headline of at most 170 characters")
    return out


GENESIS_PARTS = [("what", "What this is"), ("why", "Why it matters"), ("for_whom", "For whom"), ("not", "What it is not"),
                 ("done", "What done looks like"), ("open", "What is open")]


def first_words(A):
    """Ledger entry 1: the owner's own words, from the genesis interview where there was one."""
    g = A.get("genesis") or {}
    q = [w for w in (g.get("words") or []) if str(w).strip()]
    return q[0] if q else A.get("mission_words")


def genesis_text(A, name, today):
    """GENESIS.md: the founding interview, written once at boot. The owner's words are quoted exactly; each part says
    what Claude understood. Like the ledger it grows by dated entries at the end and is never rewritten."""
    g = A.get("genesis") or {}
    out = [f"# {name}: genesis", "",
           "What this project is, why, for whom, what it is not, what done looks like and what is open: the founding",
           "interview, the owner's words quoted exactly, each part in Claude's reading. Written at boot; it grows by dated",
           "entries at the end and is never rewritten. The road (loop/roadmap.json) was proposed from it.", "",
           f"## The interview ({today})", ""]
    if not g:
        out += ["Not held yet. The first session interviews the owner, one question at a time, and writes each answer here",
                "in the owner's words before the road is touched.", ""]
    for key, title in GENESIS_PARTS:
        if g.get(key):
            out += [f"**{title}.** {g[key].strip()}", ""]
    if g.get("words"):
        out += ["**In the owner's words:**", ""] + [f'> "{w.strip()}"' for w in g["words"] if str(w).strip()] + [""]
    out += ["## Entries", "", "(Dated entries go here, newest last, each in the owner's words.)", ""]
    return "\n".join(out)


def fill(text, V):
    for k, v in V.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def create(dest, A, quiet=False, adopt=False):
    dest = Path(dest).expanduser().resolve()
    bad = problems(A)
    if bad:
        sys.exit("new_project: answers.json is not valid:\n  " + "\n  ".join(bad))
    if adopt:  # a folder that already has code: skill/adopt.py adds only the method's files, never overwrites
        sys.path.insert(0, str(KIT / "skill"))
        import adopt as AD
        return AD.adopt(dest, A, write_files, finish, quiet)
    if dest.exists() and any(dest.iterdir()):
        sys.exit(f"new_project: {dest} exists and is not empty; pick a new path, or add --adopt to keep its code")
    name, V = write_files(dest, A)
    return finish(dest, name, V, ["git", "init", "-q", "-b", "main"], ["-A"], quiet)


def write_files(dest, A):
    """Everything the kit writes into a project folder, before git. -> (name, the filled values)."""
    name, today = A["name"].strip(), dt.date.today().isoformat()
    shutil.copytree(TEMPLATE, dest, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"), dirs_exist_ok=True)
    A = {**A, "root_entries": list(A.get("root_entries") or ["src", "tests"])}
    for e in A["root_entries"]:  # the project's empty work folders, kept by git through a .gitkeep (adopt skips any already there)
        if "." not in e and not (dest / e).exists():
            (dest / e).mkdir()
            (dest / e / ".gitkeep").write_text("")
    (dest / "dot-gitignore").rename(dest / ".gitignore")
    for d in ("loop/qa/units", "loop/qa/answers", "loop/reviews"):
        (dest / d).mkdir(parents=True, exist_ok=True)
    doors = [d.strip() for d in (A.get("doors") or []) if d.strip()] + ALWAYS_DOORS
    V = {"PROJECT": name, "MISSION": A["mission"].strip(), "DOORS": "; ".join(doors), "DATE": today}
    for rel in ("CLAUDE.md", "loop/HANDOFF.md", "DECISIONS.md"):
        f = dest / rel
        f.write_text(fill(f.read_text(), V))
    (dest / "GENESIS.md").write_text(genesis_text(A, name, today))
    steps, prev = [], None
    for i, s in enumerate(A["steps"]):
        sid = s.get("id") or slug(s.get("name", f"step-{i + 1}"))
        steps.append({"id": sid, "name": s.get("name", sid), "needs_owner": bool(s.get("needs_owner")),
                      "waits_on": list(s["waits_on"]) if "waits_on" in s else ([prev] if prev else []),
                      "done_when": [line_of(x) for x in s["done_when"]]})
        prev = sid
    W = lambda rel, obj: (dest / rel).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")
    W("loop/qa/done-rules.json", {"what": "What 'done' means: steps, each with checkable lines. Adding is free; weakening needs the owner's own hand (loop/scripts/locks.py).",
                                  "project": name, "mission": V["MISSION"], "steps": steps})
    # the roadmap (the owner, 2026-11-13: "standardized, visual, minimalist, works with the loop-project we did and will be used
    # for all project moving forward"): one road, its phases over the done map's steps; version 1 is written below
    by = {s["id"]: s for s in steps}
    phases = [{"id": slug(ph["name"]), "name": ph["name"], "plain": ph.get("plain") or ph["name"],
               "done_means": ph.get("done_means") or "; ".join(x.get("what") or kit.describe(x) for sid in ph["steps"] for x in by[sid]["done_when"]),
               "steps": list(ph["steps"]), "marks": [], "notes": []} for ph in (A.get("phases") or [])] or \
             [{"id": s["id"], "name": s["name"], "plain": s["name"], "done_means": "; ".join(x.get("what") or kit.describe(x) for x in s["done_when"]),
               "steps": [s["id"]], "marks": [], "notes": []} for s in steps]
    W("loop/roadmap.json", {"what": "The one road of this project, written to be read; the page loop/roadmap.html is built from it by "
                                    "loop/scripts/roadmap.py. Status is computed from the done map, never typed. The road changes only through "
                                    "`python3 -I loop/scripts/roadmap.py change \"<the owner's words>\"`, which numbers the version; notes change freely.",
                            "project": name, "goal": V["MISSION"], "page": "loop/roadmap.html", "fonts": "assets/v1-fonts.css", "style": "assets/dashboard.css", "signoffs": "loop/qa",
                            "phases": phases, "architecture": dict(A.get("architecture") or {}), "words": list(A.get("words") or []),
                            "health": {"engine": {"dirs": [e for e in (A.get("root_entries") or ["src"]) if e not in ("tests", "test", "docs")], "skip": [".test.ts", "_test.py"]},
                                       "helpers": {"dirs": ["loop"], "ext": [".py", ".sh", ".mjs"]},
                                       "instructions": [{"name": "Instructions", "file": "CLAUDE.md", "cap": 200, "unit": "lines"},
                                                        {"name": "NOW", "file": "loop/HANDOFF.md", "count": "now_words", "cap": 150, "unit": "words"},
                                                        {"name": "Working rules", "file": "loop/qa/memory.json", "count": "rules", "cap": 12, "unit": "rules"}],
                                       "clutter": [{"name": "loose items in loop/state", "dir": "loop/state"}],
                                       "retired": [], "checks": [], "loop": "bash loop/loop.sh status", "needs_owner": "loop/state/NEEDS-OWNER.md", "work": "units"},
                            "versions": [], "before": []})
    kitroot = ["CLAUDE.md", "DECISIONS.md", "GENESIS.md", "loop", ".claude", ".git", ".gitignore"]
    W("loop/kit.json", {"what": "This project's loop config. A lock: the owner changes it by hand.", "project": name, "session": slug(name),
                        "model": A.get("model") or "claude-opus-5-5", "effort": A.get("effort") or "xhigh",
                        "notify_title": A.get("notify_title") or name, "ntfy_topic": A.get("ntfy_topic") or DEFAULT_TOPIC,
                        "root_ok": kitroot + [e for e in (A.get("root_entries") or []) if e not in kitroot],
                        "locked_globs": ["loop/reviews/*"] + [g for g in (A.get("locked_globs") or []) if g != "loop/reviews/*"],
                        "caps": {"CLAUDE.md": 200, "loop/HANDOFF.md": 20}, "max_rules": 12, "headline_max": 170, "subject_max": 100,
                        "allowed_tools_extra": list(A.get("allowed_tools_extra") or []), "max_iters": int(A.get("max_iters") or 30),
                        "created": f"{today} by loop-kit"})
    mem = json.loads((dest / "loop/qa/memory.json").read_text())
    mem["rules"] += [{"id": r["id"], "headline": r["headline"], "rule": r["rule"], "since": today, "from": name} for r in (A.get("rules") or [])]
    W("loop/qa/memory.json", mem)
    # The index on the start screen (index.py): what exists, the mission ledger, the owner's corrections. Entry 1 of the ledger is
    # the mission in the owner's own words where given ("mission_words"), else the mission line.
    W("loop/qa/index.json", {"what": "The project's index, printed at every start by loop/scripts/brief.py through index.py: project lines (each names a real file), the mission ledger (the owner's words, dated, never rewritten) and the owner's corrections in force. Lean: replace or shorten, never only add.",
                             "project": [
                                 {"says": "The instructions: the mission, how a unit runs, the hard rules and the doors.", "file": "CLAUDE.md"},
                                 {"says": "The genesis: what this is, why, for whom, what it is not, what is open, in the owner's words.", "file": "GENESIS.md"},
                                 {"says": "What the owner decided, numbered and append-only.", "file": "DECISIONS.md"},
                                 {"says": "The road: phases over the done map's steps; it changes only by the owner's words, as a numbered version.", "file": "loop/roadmap.json"},
                                 {"says": "What done means: every step, each with lines a machine checks.", "file": "loop/qa/done-rules.json"}],
                             "ledger": [{"n": 1, "date": today, "words": (first_words(A) or V["MISSION"]).strip(),
                                         **({"open": A["open_problem"].strip()} if (A.get("open_problem") or "").strip() else {})}],
                             "corrections": []})
    W("loop/qa/resources.json", {"what": "Where every resource lives and what it answers; lookup.py find reads this. Add a row per new resource.", "resources": [
        {"id": "done-map", "where": "loop/qa/done-map.json", "answers": "is the project done; which line is open in which step; which step can start"},
        {"id": "done-rules", "where": "loop/qa/done-rules.json", "answers": "what done means: every step and its checkable lines"},
        {"id": "now", "where": "loop/HANDOFF.md", "answers": "where we are now, the last unit, what is open"},
        {"id": "roadmap", "where": "loop/roadmap.json", "answers": "the road: the phases, where we are, every version of the road (page loop/roadmap.html)"},
        {"id": "decisions", "where": "DECISIONS.md", "answers": "what the owner decided, numbered"},
        {"id": "rules", "where": "loop/qa/memory.json", "answers": "how to work with the owner: the working rules in full"},
        {"id": "units", "where": "loop/qa/units", "answers": "every unit's promise and its result"},
        {"id": "index", "where": "loop/qa/index.json", "answers": "what exists in the project, the mission ledger in the owner's words, the owner's corrections in force"},
        {"id": "config", "where": "loop/kit.json", "answers": "model, effort, locked paths, caps, root entries"}]})
    for p in list((dest / ".claude" / "githooks").iterdir()) + list((dest / "loop" / "scripts").glob("*.sh")) + [dest / "loop" / "loop.sh"]:
        p.chmod(0o755)
    return name, V


def finish(dest, name, V, init, paths, quiet=False, said="created"):
    """git (init unless the folder has a repo), the hooks, the map, road version 1, one commit of `paths`."""
    env = {**os.environ, "LOOP_OWNER": "1"}
    run = lambda *a: subprocess.run(list(a), cwd=dest, capture_output=True, text=True, env=env)
    for cmd in ([init] if init else []) + [["git", "config", "core.hooksPath", ".claude/githooks"],
                [sys.executable, "-I", "loop/scripts/build_donemap.py"],
                [sys.executable, "-I", "loop/scripts/roadmap.py", "change", V["MISSION"], "--date", V["DATE"]],
                [sys.executable, "-I", "loop/scripts/roadmap.py", "--measure"], ["git", "add", *(["--", *paths] if paths != ["-A"] else paths)],
                ["git", "commit", "-q", "-m", f"{name[:60]}: {said} by loop-kit"]]:
        r = run(*cmd)
        if r.returncode != 0:
            sys.exit(f"new_project: `{' '.join(cmd)}` failed in {dest}:\n{(r.stdout + r.stderr)[-1500:]}")
    brief = run(sys.executable, "-I", "loop/scripts/build_donemap.py", "--brief").stdout.strip()
    if not quiet:
        print(f"new_project: {said} {dest}")
        print(f"  map: {brief.splitlines()[0] if brief else '(no map)'}")
        print("  next: bash loop/scripts/selftest.sh · python3 -I loop/scripts/build_donemap.py --status · loop/loop.sh start (when the owner says)")
    return dest, brief


FILLED = {"CLAUDE.md", "loop/HANDOFF.md", "DECISIONS.md", "loop/qa/memory.json"}  # filled at boot: compare by hand


def upgrade(project, show_diff=False):
    """List the kit's template files that differ from a running project, or that it lacks. Never writes."""
    import difflib
    project = Path(project).expanduser().resolve()
    if not (project / "loop" / "kit.json").exists():
        sys.exit(f"new_project: {project} is not a loop-kit project (no loop/kit.json)")
    changed, new, filled = [], [], []
    for f in sorted(TEMPLATE.rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts or f.name == ".DS_Store":
            continue
        rel = f.relative_to(TEMPLATE).as_posix().replace("dot-gitignore", ".gitignore")
        mine = project / rel
        if not mine.exists():
            new.append(rel)
        elif mine.read_bytes() != f.read_bytes():
            (filled if rel in FILLED else changed).append(rel)
            if show_diff and rel not in FILLED:
                sys.stdout.writelines(difflib.unified_diff(mine.read_text(errors="replace").splitlines(True),
                                      f.read_text(errors="replace").splitlines(True), f"project/{rel}", f"kit/{rel}"))
    print(f"upgrade: {project} against the kit at {KIT} (nothing is changed)")
    print(f"  changed in the kit ({len(changed)}):" + "".join(f"\n    {r}" for r in changed))
    print(f"  new in the kit, missing here ({len(new)}):" + "".join(f"\n    {r}" for r in new))
    print(f"  filled at boot, compare by hand ({len(filled)}): " + ", ".join(filled))
    if changed or new:
        print(f"  to see one: diff -u \"{project}/<file>\" \"{TEMPLATE}/<file>\"   (or --diff for all)")
    return {"changed": changed, "new": new, "filled": filled}


def kit_words(codespeak=False):
    """The plain-words check (template/loop/scripts/plain.py) over the kit's own text: template, skill, README."""
    sys.path.insert(0, str(TEMPLATE / "loop" / "scripts"))
    import plain
    files = [p for p in [*TEMPLATE.rglob("*"), *(KIT / "skill").rglob("*"), KIT / "README.md", KIT / "new_project.py"]
             if p.is_file() and "__pycache__" not in p.parts and p.name != "plain.py"]  # plain.py names what it refuses
    return [b.replace(str(KIT) + "/", "") for b in plain.check([str(p) for p in files], codespeak)]


def up_check(dest):
    import contextlib, io
    quiet = lambda: contextlib.redirect_stdout(io.StringIO())
    with quiet():
        fresh = upgrade(dest)
    (dest / "loop/scripts/lookup.py").write_text("# an older lookup\n")
    (dest / "loop/scripts/plain.py").unlink()
    snap = sorted((p.as_posix(), p.stat().st_mtime_ns) for p in dest.rglob("*") if p.is_file())
    with quiet():
        after = upgrade(dest)
    same = snap == sorted((p.as_posix(), p.stat().st_mtime_ns) for p in dest.rglob("*") if p.is_file())
    for rel in ("loop/scripts/lookup.py", "loop/scripts/plain.py"):  # put the sample back for the checks after this
        shutil.copy2(TEMPLATE / rel, dest / rel)
    return (fresh["changed"] == [] and fresh["new"] == [] and after["changed"] == ["loop/scripts/lookup.py"]
            and after["new"] == ["loop/scripts/plain.py"] and same)


def install_check(td):
    """Run skill/install.sh with a fake HOME and a PATH that has everything but tmux; '' when it behaves."""
    import shutil as sh
    home, bin_ = td / "home", td / "bin"
    bin_.mkdir()
    for tool in ("bash", "python3", "git", "claude", "gh", "caffeinate", "uname", "mkdir"):
        where = sh.which(tool)
        if where:
            (bin_ / tool).symlink_to(where)
    r = subprocess.run(["bash", str(KIT / "skill" / "install.sh")], env={"HOME": str(home), "PATH": str(bin_)},
                       capture_output=True, text=True)
    skill = home / ".claude/skills/new-project/SKILL.md"
    text = skill.read_text() if skill.exists() else ""
    if not text or "<path to loop-kit>" in text or str(KIT) not in text:
        return "the skill was not installed with the kit's path filled in"
    if "MISSING  tmux" not in r.stdout or r.returncode != 1:
        return "a missing tmux was not reported (exit %d)" % r.returncode
    return ""


SCREEN_WORDS = ["startable", "blocked", "flags", "red", "amber", "NOW", "working rules", "mission ledger",
                "proposals from listening", "next without the owner", "phase", "step", "lines met"]


def glossary_gaps(dest):
    """Each word the start screen shows must be explained in README's word list."""
    screen = subprocess.run([sys.executable, "-I", "loop/scripts/brief.py"], cwd=dest, capture_output=True, text=True).stdout.lower()
    readme = (KIT / "README.md").read_text().lower()
    words = readme.split("## words you will see")[1].split("\n## ")[0] if "## words you will see" in readme else ""
    out = [f"the start screen shows '{w}' but the README word list does not explain it"
           for w in SCREEN_WORDS if w.lower() in screen and w.lower().split()[-1] not in words]
    return out + ([] if all(w.lower() in screen for w in ("startable", "mission ledger", "proposals from listening"))
                  else ["the start screen no longer shows the words the list was made for"])


def selftest():
    with tempfile.TemporaryDirectory() as td:
        dest, brief = create(Path(td) / "sample", SAMPLE, quiet=True)
        r = subprocess.run(["bash", "loop/scripts/selftest.sh"], cwd=dest, capture_output=True, text=True)
        print(r.stdout.strip())
        page = (dest / "loop" / "roadmap.html").read_text() if (dest / "loop" / "roadmap.html").exists() else ""
        road = json.loads((dest / "loop" / "roadmap.json").read_text())
        first = road["phases"][0]["name"]
        road_ok = bool(page and "Phase 1 of" in page and first in page and road["versions"][0]["v"] == 1 and "Health" in page and "Red flags" in page
                       and (dest / "loop" / "qa" / "health-log.json").exists()
                       and subprocess.run([sys.executable, "-I", "loop/scripts/roadmap.py", "--check"], cwd=dest, capture_output=True).returncode == 0)
        print(f"roadmap: {'ok · the dashboard shows phase 1, ' + first + ', as where we are, version 1 is written and health is measured' if road_ok else 'FAILED'}")
        gen = (dest / "GENESIS.md").read_text() if (dest / "GENESIS.md").exists() else ""
        gen_ok = bool(gen and SAMPLE["genesis"]["words"][0] in gen and "What it is not" in gen
                      and SAMPLE["genesis"]["words"][0] in (dest / "loop" / "qa" / "index.json").read_text())
        print(f"genesis: {'ok · written from the interview, the owner' + chr(39) + 's words quoted, ledger entry 1 is them' if gen_ok else 'FAILED'}")
        kept = subprocess.run(["git", "ls-files", "src/.gitkeep", "tests/.gitkeep"], cwd=dest, capture_output=True, text=True).stdout.split()
        work_ok = kept == ["src/.gitkeep", "tests/.gitkeep"]
        print(f"work folders: {'ok · src and tests made empty, each kept by a .gitkeep in the first commit' if work_ok else 'FAILED'}")
        up_ok = up_check(dest)
        print(f"upgrade: {'ok · a fresh project matches the kit; a changed and a missing tool are listed; nothing is written' if up_ok else 'FAILED'}")
        inst = install_check(Path(td))
        print(f"install: {'ok · the skill lands under a fake home with the path filled; tmux missing is reported' if not inst else 'FAILED: ' + inst}")
        sys.path.insert(0, str(KIT / "skill"))
        import adopt
        (Path(td) / "answers.json").write_text(json.dumps(SAMPLE))
        ad = adopt.check(KIT, Path(td) / "answers.json")
        print(f"adopt: {'ok · code and its CLAUDE.md kept, the repo kept, one commit of only loop/, .claude/ and the missing root files; a clash is refused untouched' if not ad else 'FAILED: ' + ad}")
        words = kit_words(codespeak=True) + glossary_gaps(dest)
        words += [] if subprocess.run([sys.executable, "-I", "loop/scripts/plain.py", "check"], cwd=dest, capture_output=True).returncode == 0 else ["the sample project's own text fails plain.py check"]
        print(f"plain words: {'ok · no persona name, the owner is you, no codespeak; every start-screen word is in the README list' if not words else 'FAILED'}")
        for w in words[:10]:
            print("  BAD", w)
        ok = r.returncode == 0 and road_ok and gen_ok and not words and up_ok and not inst and not ad and work_ok
        print(f"new_project selftest: {'ALL GREEN' if ok else 'FAILED'} · sample map: {brief.splitlines()[0]}")
        return 0 if ok else 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if argv[0] == "--selftest":
        return selftest()
    if argv[0] == "--upgrade" and len(argv) >= 2:
        upgrade(argv[1], "--diff" in argv)
        return 0
    if argv[0] == "--sample":
        print(json.dumps(SAMPLE, indent=1))
        return 0
    if "--answers" not in argv or len(argv) < 3:
        print("usage: python3 new_project.py <path> --answers answers.json   (--help for the answers format)")
        return 2
    A = json.loads(Path(argv[argv.index("--answers") + 1]).expanduser().read_text())
    dest = next(a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--answers"))
    create(dest, A, adopt="--adopt" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
