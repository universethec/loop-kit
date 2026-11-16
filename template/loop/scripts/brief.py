# The start hook's briefing (.claude/settings.json SessionStart): everything a fresh session needs to know where we
# are, computed from the files, kept slim (target under 5 KB) so it costs little context on every start.
#
#   brief.py            print the briefing        brief.py --bytes   print it, then its size in bytes
#
# What it prints, in order: the done map's --brief (headline + startable steps only); the NOW entry (cut to 600
# chars); a DIRTY TREE line when a session died mid-unit; the last 5 commit subjects (cut to 100 chars); ONE line per
# working rule (the 'headline' of loop/qa/memory.json, never the full 'rule'); how to look a fact up.
# Nothing here writes. Stdlib only. Run with python3 -I.
#
# If the done map cannot be built (a broken rules file), the briefing says so instead of failing the session start.
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402


def text(root):
    root = Path(root)
    run = lambda *a: subprocess.run(list(a), cwd=root, capture_output=True, text=True)
    out = ["START (computed from the files; quote the map's first line in your first message; work only a startable step):"]
    r = run(sys.executable, "-I", str(HERE / "build_donemap.py"), "--brief")
    out.append(r.stdout.strip() or f"(the done map did not build: {r.stdout.strip() or r.stderr.strip()[-200:]})")
    now = root / "loop" / "HANDOFF.md"
    entry = next((x for x in now.read_text().splitlines() if x.startswith("**Where we are")), "") if now.exists() else ""
    out += ["--- NOW", entry[:600] or "(NOW has no 'Where we are' entry)"]
    dirty = [x for x in run("git", "status", "--porcelain").stdout.splitlines() if x.strip()]
    if dirty:
        out.append(f"DIRTY TREE: {len(dirty)} file(s) uncommitted; a session died mid-unit ({kit.current_unit(root)}): finish that unit first")
    out.append("--- last five commits")
    out += [x[:100] for x in run("git", "log", "--format=%s", "-5").stdout.splitlines()]
    mem = root / "loop" / "qa" / "memory.json"
    out.append("--- working rules (one line each; full text: loop/qa/memory.json)")
    try:
        out += [f"- {r['id']}: {r.get('headline') or r['rule'][:160]}" for r in json.loads(mem.read_text())["rules"]]
    except Exception as e:
        out.append(f"(memory.json unreadable: {e})")
    # The project's index (index.py): what exists, the mission ledger's newest entry, Alex's corrections in force, and
    # the dreams waiting or applied. Read from loop/qa/index.json, every line's file checked by `index.py --check`.
    try:
        import index
        out += index.lines(index.load(root), root)
    except Exception as e:
        out.append(f"(the index did not print: {e})")
    out.append("--- before reading for a task: python3 -I loop/scripts/questions.py <task> [--step ID] (the questions in order,"
               " each with its one small piece; stop when answered, never a whole file or a folder)")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    t = text(kit.ROOT)
    sys.stdout.write(t)
    if "--bytes" in sys.argv[1:]:
        print(f"[briefing: {len(t.encode())} bytes]")
