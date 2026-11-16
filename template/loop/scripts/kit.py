# The shared core of the loop's scripts: where the project is, its config (loop/kit.json), the one vocabulary of
# checkable lines, and the catch log every gate appends to when it refuses something.
#
#   import kit; kit.ROOT; kit.conf(); kit.check(line) -> (ok, saw); kit.catch("guard:push", "git push origin")
#
# Checkable lines (a done-map line, a promise line, all made of these; "what" is the plain words beside them):
#   {"file": "<path or glob>"}                                         exists
#   {"cmd": "<shell>"}                                                 exits 0 (120 s)
#   {"json": "<path>", "field": "a.b.0", "op": "==|!=|>=|<=|>|<|len>=|len==|exists", "value": ...}
#   {"grep": "<path>", "has": "<string>"}                              the file holds the string
#   {"git": "<path>"}                                                  tracked by git
# Catches: loop/state/catches.csv (date,check,unit,what); LOOP_CATCHES overrides the path (selftests). Stdlib only.
import csv
import datetime as dt
import glob
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(os.environ["LOOP_ROOT"]).resolve() if os.environ.get("LOOP_ROOT") else Path(__file__).resolve().parents[2]
KINDS = ("file", "cmd", "json", "grep", "git")
OPS = ("==", "!=", ">=", "<=", ">", "<", "len>=", "len==", "exists")

DEFAULTS = {"project": "project", "session": "loop", "model": "claude-opus-5-5", "effort": "xhigh",
            "notify_title": "loop", "ntfy_topic": "", "autonomous_env": "LOOP_AUTONOMOUS",
            "root_ok": ["CLAUDE.md", "DECISIONS.md", "loop", ".claude", ".git", ".gitignore"],
            "locked_globs": ["loop/reviews/*"], "caps": {"CLAUDE.md": 200, "loop/HANDOFF.md": 20},
            "max_rules": 12, "headline_max": 170, "subject_max": 100, "allowed_tools_extra": [], "max_iters": 30}

# Every gate that can refuse, by the id it logs under. dream.py reads this list, so a gate that never catches
# anything still shows up with zero.
CHECKS = {
    "guard:hooks-skip": "a command skips or moves the commit hooks (--no-verify, hooksPath, git -c, -n)",
    "guard:push": "git push",
    "guard:override-token": "a command or file names the human-only override",
    "guard:code-names-lock": "a command runs code (python -c, heredoc, perl, node -e, patch) and names a lock",
    "guard:writes-lock": "a shell command writes and names a locked path",
    "guard:edit-lock": "an edit tool targets a locked path (locks, locked globs, an opened promise)",
    "guard:root-entry": "an edit tool makes a new entry at the repo root",
    "locks:rules-weakened": "done-rules lost a step, a line, a wait, or a needs_owner flag",
    "locks:decisions-append-only": "a line was removed from DECISIONS.md",
    "locks:size-cap": "CLAUDE.md, NOW or the working rules over their caps",
    "locks:lock-changed": "a lock file changed without the owner's own hand",
    "locks:root-entry": "a commit adds a new entry at the repo root",
    "locks:subject-cap": "a commit subject over the cap",
    "qa:open-no-promise": "qa open with no valid promise written",
    "qa:open-vacuous": "qa open on a promise whose map line already passes",
    "qa:close-unopened": "qa close on a unit never opened",
    "qa:close-promise-changed": "qa close after the promise was changed",
    "qa:close-failed": "qa close with a promise line failing",
    "qa:hook-unit": "a commit with a unit not closed, or a closed unit edited",
    "handoff:dirty-tree": "a new round would start on an uncommitted tree",
    "handoff:now-shape": "NOW is not one entry within its cap",
    "handoff:map-stale": "the done map differs from a fresh build",
    "review:unanswered": "a review gap or overclaim left unanswered",
    "map:require": "a step was taken before what it waits on was done",
    "loop:barren-park": "two slices in a row committed nothing",
}
SAFETY_FLOOR = {"guard:push", "guard:hooks-skip", "guard:override-token", "locks:lock-changed"}


def conf(root=None):
    f = Path(root or ROOT) / "loop" / "kit.json"
    c = dict(DEFAULTS)
    if f.exists():
        c.update(json.loads(f.read_text()))
    return c


def sh(cmd, root=None, timeout=120):
    try:
        r = subprocess.run(cmd, shell=True, cwd=root or ROOT, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def field(obj, path):
    cur = obj
    for part in str(path).split("."):
        if isinstance(cur, list) and re.fullmatch(r"-?\d+", part) and -len(cur) <= int(part) < len(cur):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None, False
    return cur, True


def compare(actual, op, value):
    if op == "exists":
        return actual is not None
    if op in ("len>=", "len=="):
        n = len(actual) if isinstance(actual, (list, dict, str)) else -1
        return n >= value if op == "len>=" else n == value
    try:
        return {"==": actual == value, "!=": actual != value, ">=": actual >= value, "<=": actual <= value,
                ">": actual > value, "<": actual < value}[op]
    except TypeError:
        return False


def problems(line):
    """Why a line is not a checkable line, or []."""
    if not isinstance(line, dict):
        return ["not an object"]
    kinds = [k for k in KINDS if k in line]
    if len(kinds) != 1:
        return [f"needs exactly one of {', '.join(KINDS)}"]
    if "json" in line and (not line.get("field") or line.get("op") not in OPS):
        return [f"a json line needs field and op (one of {' '.join(OPS)})"]
    if "grep" in line and not isinstance(line.get("has"), str):
        return ["a grep line needs has"]
    return []


def describe(line):
    if "file" in line:
        return f"{line['file']} exists"
    if "cmd" in line:
        return f"`{line['cmd']}` exits 0"
    if "json" in line:
        return f"{line['json']} {line['field']} {line['op']} {json.dumps(line.get('value'))}"
    if "grep" in line:
        return f"{line['grep']} holds '{line['has']}'"
    if "git" in line:
        return f"{line['git']} is tracked"
    return json.dumps(line)


def check(line, root=None, timeout=120):
    """-> (ok, what it saw)."""
    root = Path(root or ROOT)
    bad = problems(line)
    if bad:
        return False, f"not a checkable line: {bad[0]}"
    if "file" in line:
        hits = sorted(glob.glob(str(root / line["file"])))
        return bool(hits), (os.path.relpath(hits[-1], root) if hits else f"no {line['file']}")
    if "cmd" in line:
        rc, out = sh(line["cmd"], root, timeout)
        last = next((x for x in reversed(out.splitlines()) if x.strip()), "no output")
        last = re.sub(r"(?:/[^/\s'\"]+)+/([^/\s'\"]+)", r"\1", last)  # an absolute path says little; keep its name
        return rc == 0, f"exit {rc} · {last.strip()[:110]}"
    if "json" in line:
        f = root / line["json"]
        if not f.exists():
            return False, f"no {line['json']}"
        try:
            val, present = field(json.loads(f.read_text()), line["field"])
        except Exception as e:
            return False, f"{line['json']}: {e}"
        ok = compare(val if present else None, line["op"], line.get("value"))
        return ok, f"{line['field']} = {json.dumps(val)[:60] if present else 'absent'}"
    if "grep" in line:
        f = root / line["grep"]
        if not f.exists():
            return False, f"no {line['grep']}"
        hit = line["has"] in f.read_text(errors="replace")
        return hit, f"'{line['has'][:40]}' {'found' if hit else 'absent'} in {line['grep']}"
    rc, _ = sh(f"git ls-files --error-unmatch -- '{line['git']}'", root)
    return rc == 0, ("tracked" if rc == 0 else "not tracked")


def current_unit(root=None):
    f = Path(root or ROOT) / "loop" / "state" / "current-unit"
    return f.read_text().strip() if f.exists() else "-"


def catch(check_id, what, unit=None, root=None):
    """Append one refusal to the catch log. Never raises: a gate must refuse even when the log cannot be written."""
    try:
        f = Path(os.environ.get("LOOP_CATCHES") or (Path(root or ROOT) / "loop" / "state" / "catches.csv"))
        f.parent.mkdir(parents=True, exist_ok=True)
        new = not f.exists()
        with f.open("a", newline="") as h:
            w = csv.writer(h)
            if new:
                w.writerow(["date", "check", "unit", "what"])
            w.writerow([dt.datetime.now().isoformat(timespec="seconds"), check_id, unit or current_unit(root),
                        re.sub(r"\s+", " ", str(what))[:200]])
    except Exception:
        pass
