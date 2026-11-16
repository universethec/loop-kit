# Is the handoff clean before a new round starts? Run by loop/loop.sh before every slice; any problem parks the loop
# with the reason in loop/state/NEEDS-OWNER.md, so a new round never starts on top of a dirty one.
#
#   handoff_check.py            exit 0 and 'clean', or exit 1 and one line per problem
#   handoff_check.py selftest   every check refuses its planted break (a dirty tree, two NOW entries, a stale map)
#
# The checks: the tree is committed (loop/state/ is gitignored, so the loop's own files never count); NOW
# (loop/HANDOFF.md) holds exactly one '**Where we are' entry within its line cap; the done map equals a fresh build.
# Every refusal is logged to loop/state/catches.csv (kit.catch).
#
# Stdlib only. Run with python3 -I.
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402


def tree_problems(porcelain):
    lines = [x for x in porcelain.splitlines() if x.strip()]
    return [f"the tree is not committed ({len(lines)} file(s), first: {lines[0].strip()}): finish and commit the last unit before a new one"] if lines else []


NOW_LINES, NOW_WORDS = 5, 150


def now_problems(text, cap=20):
    lines = text.splitlines()
    out = []
    where = [x for x in lines if x.startswith("**Where we are")]
    if len(where) != 1:
        out.append(f"NOW holds {len(where)} 'Where we are' entries; it holds exactly one")
    if len(lines) > cap:
        out.append(f"NOW is {len(lines)} lines; the cap is {cap}")
    # the NOW section itself (the owner, 2026-11-13, the owner's yes to 'NOW capped at five lines'): open notes go on the roadmap
    head = next((i for i, x in enumerate(lines) if x.startswith("## NOW")), None)
    body = [x for x in lines[head + 1:] if x.strip()] if head is not None else []
    if len(body) > NOW_LINES:
        out.append(f"the NOW section is {len(body)} lines; the cap is {NOW_LINES} (open notes go on the roadmap's phases)")
    words = sum(len(x.split()) for x in body if not x.startswith("<!-- qa:"))
    if words > NOW_WORDS:
        out.append(f"the NOW section is {words} words; the cap is {NOW_WORDS}")
    return out


def road_problems(root):
    if not (Path(root) / "loop" / "roadmap.json").exists():
        return []
    r = subprocess.run([sys.executable, "-I", str(HERE / "roadmap.py"), "--check"], cwd=root, capture_output=True, text=True,
                       env={**__import__("os").environ, "LOOP_ROOT": str(root)})
    return [] if r.returncode == 0 else [f"the roadmap: {(r.stdout or r.stderr).strip()[-200:]}"]


def map_problems(root):
    r = subprocess.run([sys.executable, "-I", str(HERE / "build_donemap.py"), "--check"], cwd=root, capture_output=True, text=True,
                       env={**__import__("os").environ, "LOOP_ROOT": str(root)})
    return [] if r.returncode == 0 else [f"the done map differs from a fresh build: {(r.stdout or r.stderr).strip()[-160:]}"]


def check(root):
    root = Path(root)
    porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
    now = root / "loop" / "HANDOFF.md"
    cap = kit.conf(root)["caps"].get("loop/HANDOFF.md", 20)
    out = [("handoff:dirty-tree", p) for p in tree_problems(porcelain)]
    out += [("handoff:now-shape", p) for p in now_problems(now.read_text() if now.exists() else "", cap)]
    out += [("handoff:map-stale", p) for p in map_problems(root)]
    out += [("handoff:road", p) for p in road_problems(root)]
    return out


def selftest():
    import json
    import os
    import tempfile
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    must(tree_problems("") == [], "a clean tree passes")
    must(tree_problems(" M loop/HANDOFF.md\n"), "an uncommitted file is refused")
    good = "# NOW\n**Where we are (2026-11-11):** one entry\n"
    must(now_problems(good) == [], "one entry passes")
    must(now_problems(good + "**Where we are (2026-11-12):** a second\n"), "two entries are refused")
    must(now_problems("x\n" * 21 + "**Where we are**\n"), "22 lines are refused")
    sect = lambda body: "\n".join(["# NOW", "## NOW — you are here", ""] + body)
    must(now_problems(sect(["**Where we are (d):** one", "b", "c", "d", "e"])) == [], "a NOW section of five lines passes")
    must(now_problems(sect(["**Where we are (d):** one", "b", "c", "d", "e", "f"])), "a NOW section of six lines is refused")
    must(now_problems(sect(["**Where we are (d):** " + "w " * 150])), "a NOW section over 150 words is refused")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        os.environ["LOOP_CATCHES"] = str(root / "catches.csv")
        sh = lambda *a: subprocess.run(a, cwd=root, capture_output=True, text=True)
        (root / "loop" / "qa").mkdir(parents=True)
        (root / "loop" / "HANDOFF.md").write_text(good)
        (root / "loop" / "qa" / "done-rules.json").write_text(json.dumps({"steps": [{"id": "a", "done_when": [{"file": "x.txt"}]}]}))
        subprocess.run([sys.executable, "-I", str(HERE / "build_donemap.py")], cwd=root, capture_output=True, env={**os.environ, "LOOP_ROOT": str(root)})
        sh("git", "init", "-q", "-b", "main")
        sh("git", "add", "-A")
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")
        must(check(root) == [], f"a committed, fresh project is clean ({check(root)})")
        (root / "half-done.py").write_text("x")
        ids = [i for i, _ in check(root)]
        must(ids == ["handoff:dirty-tree"], f"a dirty tree is refused ({ids})")
        sh("git", "add", "-A")
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "more")
        (root / "x.txt").write_text("x")
        sh("git", "add", "-A")
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "x without the map")
        ids = [i for i, _ in check(root)]
        must(ids == ["handoff:map-stale"], f"a stale done map is refused ({ids})")
        del os.environ["LOOP_CATCHES"]
    if bad:
        print("handoff_check selftest: FAILED: " + "; ".join(bad))
        return 1
    print(f"handoff_check selftest: ALL GREEN · {n} controls")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        sys.exit(selftest())
    p = check(kit.ROOT)
    for cid, what in p:
        kit.catch(cid, what)
    if p:
        print("handoff_check: NOT CLEAN\n  " + "\n  ".join(w for _, w in p))
        sys.exit(1)
    print("handoff_check: clean · the tree committed, NOW one entry, the done map and the roadmap fresh")
