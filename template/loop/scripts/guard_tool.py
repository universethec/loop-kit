# The tool guard: a PreToolUse hook (.claude/settings.json) that refuses, before it happens, every tool call that
# would get around the locks. It reads the call as JSON on stdin; exit 2 refuses (the reason goes back to the
# session), exit 0 lets it through. Every refusal is logged to loop/state/catches.csv (kit.catch).
#
# Refused: skipping or moving the commit hooks (--no-verify, commit -n, hooksPath, git -c, plumbing); git push; the
# human-only override token; code (python -c, heredoc, perl, node -e, patch) naming a lock; a write, by an edit tool or
# a shell command, to a lock (the kit's scripts, kit.json, loop.sh, settings, githooks, .git), to kit.json
# "locked_globs", to an opened unit's promise, to the transcripts; a new entry at the repo root (kit.json "root_ok").
# The owner changes any of these himself: a command he types after `!` is not a tool call and this guard never sees it.
#
#   guard_tool.py            (the hook; stdin = the tool call)       guard_tool.py selftest   planted calls
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402

HOME = str(Path.home())
OVERRIDE = "LOOP_OWNER"
SCRIPTS = ["kit.py", "guard_tool.py", "locks.py", "qa.py", "review_check.py", "build_donemap.py", "handoff_check.py",
           "dream.py", "brief.py", "lookup.py", "notify.sh", "selftest.sh"]
LOCKS = [".claude/settings.json", ".claude/settings.local.json", ".claude/githooks/", ".git/", "loop/kit.json", "loop/loop.sh",
         "loop/loop-mcp.json"] + [f"loop/scripts/{s}" for s in SCRIPTS]
# Written only by the scripts, never by hand: locked for the tool guard, but a commit carries them freely (qa close
# rebuilds the map in every unit; handoff_check refuses a stale one before every slice).
WRITTEN_BY_SCRIPTS = ["loop/state/opened/", "loop/state/catches.csv", "loop/qa/done-map.json"]
LOCKS += WRITTEN_BY_SCRIPTS
LOCK_NAMES = ["guard_tool", "locks.py", "kit.py", "kit.json", "githooks", "settings.json", "settings.local", ".jsonl", "loop/reviews",
              "loop/qa/units", "loop/state/opened", "catches.csv", "done-rules", "done-map", "hookspath", ".git/"]
WRITE = re.compile(r"(?<![0-9&])>(?!&)|\btee\b|\bsed\s+-[a-zA-Z]*i|\bmv\b|\bcp\b|\brm\b|\btruncate\b|write_text|\.write\(|open\([^)]*['\"](w|a|x)"
                   r"|\bunlink\b|\brename\b|shutil|\bgit\s+(rm|mv|restore|checkout\s+--)|\bln\b|\binstall\b|\bdd\b|\bchmod\b")


class Refused(Exception):
    def __init__(self, check, why):
        super().__init__(why)
        self.check = check


def root_of(path, root):
    """The checkout a path lives in (a worktree has its own .git), never above the project."""
    p = Path(path).resolve()
    for q in [p, *p.parents]:
        if (q / ".git").exists():
            return q
        if q == root:
            return root
    return root


def rel(p, root):
    try:
        return str(Path(p).resolve().relative_to(root_of(p, root)))
    except ValueError:
        return None


def protected(absolute, root, edit_tool):
    """(check id, why) when the session may not change this path, else None."""
    if "/.claude/projects/" in absolute and absolute.endswith(".jsonl"):
        return "guard:edit-lock", "a session transcript"
    if absolute == os.path.join(HOME, ".claude", "settings.json"):
        return "guard:edit-lock", "The owner's user settings"
    r = rel(absolute, root)
    if r is None:
        return None
    base = root_of(absolute, root)
    for x in LOCKS:
        if r == x.rstrip("/") or (x.endswith("/") and r.startswith(x)):
            return "guard:edit-lock", "a lock (the kit's scripts, kit.json, loop.sh, the settings, the git hooks or the loop's state)"
    for g in kit.conf(base).get("locked_globs", []):
        if fnmatch.fnmatch(r, g):
            return "guard:edit-lock", f"locked by kit.json ({g})"
    m = re.fullmatch(r"loop/qa/units/([^/]+)\.json", r)
    if m and (base / "loop" / "state" / "opened" / f"{m.group(1)}.json").exists():
        return "guard:edit-lock", "an opened unit's promise (frozen at qa open; close writes the result)"
    if edit_tool and "/" not in r and r not in kit.conf(base)["root_ok"] and not (base / r).exists():
        return "guard:root-entry", "a new entry at the repo root (kit.json root_ok; a door)"
    return None


def decide(call, root):
    """Raise Refused for a call the session may not make; return None to let it through."""
    tool, inp = call.get("tool_name", ""), call.get("tool_input") or {}
    root = Path(root)
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        p = inp.get("file_path") or inp.get("notebook_path") or ""
        ab = str(Path(p).expanduser().resolve())
        why = protected(ab, root, True)
        if why:
            raise Refused(why[0], f"{p} is {why[1]}.")
        body = json.dumps(inp)
        if OVERRIDE in body:
            raise Refused("guard:override-token", f"the file names {OVERRIDE}, the override only the owner uses.")
        return None
    if tool != "Bash":
        return None
    cmd = inp.get("command", "")
    flat = re.sub(r"\s+", " ", cmd)
    if OVERRIDE in flat:
        raise Refused("guard:override-token", f"{OVERRIDE} is the override only the owner types.")
    if re.search(r"(?i)--no-ve\w*|hookspath|\bHUSKY=0|\bSKIP_HOOKS\b|GIT_CONFIG_|\bGIT_DIR=|\bcommit-tree\b|\bupdate-ref\b|\balias\.\w+\s*=", flat) or re.search(r"\bgit\s+-c\b", flat):
        raise Refused("guard:hooks-skip", "Skipping or moving the commit hooks, git plumbing that makes commits, and git -c are never allowed.")
    unquoted = re.sub(r'"(?:[^"\\]|\\.)*"|\'[^\']*\'', '""', flat)  # a commit message is words, never flags
    for m in re.finditer(r"\bgit\b[^;&|]*\bcommit\b([^;&|]*)", unquoted):
        if re.search(r"\s-[a-zA-Z]*n[a-zA-Z]*\b", m.group(1)):
            raise Refused("guard:hooks-skip", "`git commit -n` skips the commit hooks.")
    if re.search(r"\bgit\b[^;&|]*\bp\\?u\\?s\\?h\b", flat):
        raise Refused("guard:push", "Never git push (CLAUDE.md, hard rules).")
    body = re.sub(r"2>&1|>\s*/dev/null|2>\s*/dev/null", " ", cmd)
    if re.search(r"\bpython3?\b[^|;&]*(-c\b|<<)|\bperl\b|\bnode\s+-e\b|\bruby\b|\bgit\s+apply\b|\bpatch\b", body):
        low = body.lower()
        hit = next((n for n in LOCK_NAMES if n.lower() in low), None)
        if hit:
            raise Refused("guard:code-names-lock", f"This command runs code and names '{hit}', a lock or a recorded file.")
    cwd = root
    for m in re.finditer(r"\bcd\s+(\"[^\"]+\"|'[^']+'|\S+)", cmd):
        d = m.group(1).strip("\"'")
        cwd = Path(d.replace("~", HOME)) if d.startswith(("/", "~")) else (cwd / d)
    if WRITE.search(body):
        for tok in re.findall(r"[A-Za-z0-9_~./\-]+", cmd):
            for base in (root, cwd):
                absolute = str(Path(tok.replace("~", HOME)).expanduser()) if tok.startswith(("~", "/")) else str(base / tok)
                why = protected(absolute, root, False) if (Path(absolute).exists() or "/" in tok) else None
                if why:
                    raise Refused("guard:writes-lock", f"This command writes and names {tok}, which is {why[1]}.")
    return None


def main():
    try:
        call = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    try:
        decide(call, kit.ROOT)
    except Refused as r:
        kit.catch(r.check, f"{call.get('tool_name')}: {r}")
        print(f"guard: refused. {r} the owner can do it himself with a command he types after `!`.", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


def selftest():
    import tempfile
    bad, n = [], 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        for d in ("loop/state/opened", "loop/qa/units", "loop/scripts", ".claude/githooks", "loop/reviews", "src"):
            (root / d).mkdir(parents=True)
        (root / ".git").mkdir()
        (root / "loop" / "kit.json").write_text(json.dumps({"root_ok": ["CLAUDE.md", "loop", ".claude", "src"], "locked_globs": ["loop/reviews/*", "data/raw/**"]}))
        (root / "CLAUDE.md").write_text("x")
        (root / "loop" / "state" / "opened" / "u1.json").write_text("{}")
        B = lambda c: {"tool_name": "Bash", "tool_input": {"command": c}}
        W = lambda p, content="x": {"tool_name": "Write", "tool_input": {"file_path": str(root / p), "content": content}}
        E = lambda p: {"tool_name": "Edit", "tool_input": {"file_path": str(root / p), "old_string": "a", "new_string": "b"}}
        cases = [  # (call, expected check id or None, what)
            (B("git push origin main"), "guard:push", "git push is refused"),
            (B("git -C . push"), "guard:push", "git -C . push is refused"),
            (B("git -C src status"), None, "git -C (a folder) is allowed"),
            (B("git -c core.x=y status"), "guard:hooks-skip", "git -c (a config override) is refused"),
            (B("cd src && git push"), "guard:push", "push after cd is refused"),
            (B("git commit --no-verify -m x"), "guard:hooks-skip", "--no-verify is refused"),
            (B("git commit -n -m x"), "guard:hooks-skip", "commit -n is refused"),
            (B("git commit -m 'fix the -n flag'"), None, "a -n inside a commit message is allowed"),
            (B("git config core.hooksPath /dev/null"), "guard:hooks-skip", "moving hooksPath is refused"),
            (B("LOOP_OWNER=1 git commit -m x"), "guard:override-token", "the override token is refused"),
            (E(".claude/settings.json"), "guard:edit-lock", "editing the settings is refused"),
            (W("loop/scripts/guard_tool.py"), "guard:edit-lock", "writing the guard is refused"),
            (W("loop/reviews/review-u1.json"), "guard:edit-lock", "a kit.json locked glob is refused"),
            (W("data/raw/a/b.csv"), "guard:edit-lock", "a nested locked glob is refused"),
            (W("loop/qa/units/u1.json"), "guard:edit-lock", "an opened promise is refused"),
            (W("loop/qa/units/u2.json"), None, "a promise not yet opened may be written"),
            (W("src/app.py"), None, "a normal edit is allowed"),
            (E("CLAUDE.md"), None, "editing an existing root file is allowed"),
            (W("notes.txt"), "guard:root-entry", "a new root entry is refused"),
            (W("src/x.py", "os.environ['LOOP_OWNER']='1'"), "guard:override-token", "a file naming the override is refused"),
            (B("echo x > .claude/settings.json"), "guard:writes-lock", "a shell write to the settings is refused"),
            (B("sed -i '' s/a/b/ loop/kit.json"), "guard:writes-lock", "sed -i on kit.json is refused"),
            (B("python3 -c \"open('loop/kit.json','w')\""), "guard:code-names-lock", "python -c naming a lock is refused"),
            (B("cat loop/kit.json"), None, "reading a lock is allowed"),
            (B("python3 -I loop/scripts/qa.py open u1"), None, "running a kit script is allowed"),
            (B("ls -la src"), None, "a plain read command is allowed"),
        ]
        for call, want, what in cases:
            n += 1
            try:
                decide(call, root)
                got = None
            except Refused as r:
                got = r.check
            if got != want:
                bad.append(f"{what} (got {got})")
    if bad:
        print("guard_tool selftest: FAILED: " + "; ".join(bad))
        return 1
    print(f"guard_tool selftest: ALL GREEN · {n} controls")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        sys.exit(selftest())
    main()
