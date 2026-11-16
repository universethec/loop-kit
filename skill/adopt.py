"""Adopt mode: boot the method into a folder that already has code (new_project.py <path> --answers a.json --adopt).

The owner's words: "what is this?", answered in chat: booting into a folder that already has code, adding only the
method's folders, drafting the genesis and the road from the code, still interviewing the owner.

What it does: builds the project in a temp folder exactly as a fresh boot would, then copies it in WITHOUT touching
anything that is there. A file under loop/ or .claude/ that already exists stops it before anything is written. A
root file the kit brings (CLAUDE.md, DECISIONS.md, GENESIS.md, .gitignore) that already exists is kept as it is; the
kit's version goes to loop/adopt/ for you to merge by hand. Every top-level entry already there becomes an allowed
root entry. An existing git repo is used as it is (no new repo); the boot is one commit of only the added files.
Kit-side only: projects never get this file.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_FILES = ["CLAUDE.md", "DECISIONS.md", "GENESIS.md", ".gitignore"]
OWN = ("loop", ".claude")  # the method's folders: everything else in the folder stays the owner's
NESTED_IGNORE = {"loop/.gitignore": "/state/\n/activity.html\n__pycache__/\n", ".claude/.gitignore": "settings.local.json\n"}


def adopt(dest, A, write_files, finish, quiet=False):
    dest = Path(dest).expanduser().resolve()
    there = sorted(p.name for p in dest.iterdir()) if dest.is_dir() else []
    if not [x for x in there if x != ".git"]:
        sys.exit(f"new_project: {dest} has no code to adopt; boot it without --adopt")
    if (dest / ".git").exists() and subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=dest).returncode != 0:
        sys.exit(f"new_project: refused, nothing written: {dest} has staged changes; commit or unstage them first, so the "
                 "boot commit holds only the kit's files")
    keep = [x for x in there if x not in (".git", *OWN, *ROOT_FILES)]
    A2 = {**A, "root_entries": list(dict.fromkeys(list(A.get("root_entries") or []) + keep))}
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "stage"
        name, V = write_files(stage, A2)
        files = sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file())
        clash = [f for f in files if f.split("/")[0] in OWN and (dest / f).exists()]
        if clash:
            sys.exit(f"new_project: refused, nothing written: {len(clash)} file(s) the kit would add already exist in "
                     f"{dest}: " + ", ".join(clash[:8]))
        for d in (p for p in stage.rglob("*") if p.is_dir() and p.relative_to(stage).parts[0] in OWN):
            (dest / d.relative_to(stage)).mkdir(parents=True, exist_ok=True)
        kept = [f for f in files if "/" not in f and (dest / f).exists()]
        work = sorted({f.split("/")[0] for f in files if "/" in f and f.split("/")[0] not in OWN} - set(there))
        for f in files:
            if "/" in f and f.split("/")[0] not in (*OWN, *work):
                continue  # a work folder that is already there: left as it is
            to = dest / ("loop/adopt/" + f.lstrip(".") if f in kept else f)
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage / f, to)
    if ".gitignore" in kept:  # keep the owner's file; the loop's own ignores go next to what they ignore
        for rel, text in NESTED_IGNORE.items():
            (dest / rel).write_text(text)
    hooks = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=dest, capture_output=True, text=True).stdout.strip()
    init = None if (dest / ".git").exists() else ["git", "init", "-q", "-b", "main"]
    added = [*OWN, *[f for f in ROOT_FILES if f not in kept and (dest / f).exists()], *work]
    out = finish(dest, name, V, init, added, quiet=True, said="adopted")
    if not quiet:
        print(f"new_project: adopted {dest} ({'its git repo kept' if not init else 'a new git repo'}; one commit of "
              f"{', '.join(added)})")
        if kept:
            print(f"  kept as they were: {', '.join(kept)}; the kit's versions are in loop/adopt/ to merge by hand")
        if hooks and hooks != ".claude/githooks":
            print(f"  the repo's hooks folder was {hooks}; it is .claude/githooks now: move any hook you need there")
        print(f"  root entries allowed: {', '.join(keep) or '(none)'}")
        print("  next: bash loop/scripts/selftest.sh · python3 -I loop/scripts/brief.py")
    return out


def check(kit, answers):
    """The planted check for the kit's self-test: '' when adopt behaves, else what went wrong."""
    run = lambda *a, cwd=None: subprocess.run(list(a), cwd=cwd, capture_output=True, text=True)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        app = td / "app"
        (app / "lib").mkdir(parents=True)
        (app / "lib" / "main.py").write_text("print('mine')\n")
        (app / "CLAUDE.md").write_text("# my own instructions\n")
        (app / "tests").mkdir()
        (app / "tests" / "test_main.py").write_text("# mine\n")
        g = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        run("git", "init", "-q", "-b", "main", cwd=app)
        run("git", "add", "-A", cwd=app)
        run(*g, "commit", "-q", "-m", "my code", cwd=app)
        first = run("git", "rev-parse", "HEAD", cwd=app).stdout.strip()
        boot = [sys.executable, "-I", str(kit / "new_project.py"), str(app), "--answers", str(answers), "--adopt"]
        r = run(*boot)
        if r.returncode != 0:
            return "adopt failed: " + (r.stdout + r.stderr)[-300:]
        if (app / "CLAUDE.md").read_text() != "# my own instructions\n" or (app / "lib/main.py").read_text() != "print('mine')\n":
            return "an existing file was overwritten"
        if run("git", "rev-parse", "HEAD~1", cwd=app).stdout.strip() != first:
            return "the existing repo was not kept, or the boot was not one commit on top of it"
        names = run("git", "show", "--name-only", "--format=", "HEAD", cwd=app).stdout.split()
        bad = [n for n in names if n.split("/")[0] not in (*OWN, "DECISIONS.md", "GENESIS.md", ".gitignore") and n != "src/.gitkeep"]
        if bad or not names:
            return f"the boot commit holds paths outside the allowed ones: {bad[:4]}"
        if "src/.gitkeep" not in names or sorted(p.name for p in (app / "tests").iterdir() if p.name != "__pycache__") != ["test_main.py"]:
            return "a missing work folder was not made, or one already there was touched"
        if not (app / "loop/adopt/CLAUDE.md").exists() or "lib" not in (app / "loop/kit.json").read_text():
            return "the kit's CLAUDE.md was not set aside, or the existing folder is not an allowed root entry"
        other = td / "other"
        (other / "loop").mkdir(parents=True)
        (other / "loop" / "kit.json").write_text("{}\n")
        (other / "a.txt").write_text("x\n")
        snap = sorted(p.as_posix() for p in other.rglob("*"))
        r = run(*boot[:3], str(other), *boot[4:])
        if r.returncode == 0 or "refused" not in r.stderr or sorted(p.as_posix() for p in other.rglob("*")) != snap:
            return "a folder whose loop/ already has the kit's file was not refused untouched"
        if run(*boot[:3], str(td / "empty"), *boot[4:]).returncode == 0:
            return "an empty folder was adopted"
    return ""
