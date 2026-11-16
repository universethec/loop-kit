# The dossier: where every resource lives and what it answers, so a session looks a thing up instead of loading a
# folder. THE RULE FOR READING: find first, then open only the one file it names, at the part you need.
#
#   lookup.py find WORDS    the resources (loop/qa/resources.json) whose id, place or 'answers' hold every word,
#                           then tracked files whose path holds every word (names only, never contents)
#   lookup.py check         exit 1 if a resource points at a path that does not exist
#   lookup.py selftest      planted resources: find hits all words, misses one, check refuses a dead path
#
# resources.json: {"resources": [{"id": "...", "where": "path", "answers": "the question you would bring to it"}]}
# A new resource is one more entry; nothing here reads a file's contents.
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402


def resources(root):
    f = Path(root) / "loop" / "qa" / "resources.json"
    return json.loads(f.read_text())["resources"] if f.exists() else []


def find(root, words, cap=20):
    words = [w.lower() for w in words]
    hits = [r for r in resources(root) if all(w in f"{r['id']} {r['where']} {r['answers']}".lower() for w in words)]
    out = [f"{r['where']}  ·  {r['answers']}" for r in hits]
    files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True).stdout.splitlines()
    named = [f for f in files if all(w in f.lower() for w in words) and f not in {r["where"] for r in hits}]
    out += [f"{f}  ·  (a tracked file whose name matches)" for f in named[:cap]]
    if len(named) > cap:
        out.append(f"… {len(named) - cap} more files; add a word")
    return out


def check(root):
    return [f"{r['id']}: {r['where']} does not exist" for r in resources(root) if not (Path(root) / r["where"]).exists()]


def selftest():
    import tempfile
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "loop" / "qa").mkdir(parents=True)
        (root / "a.json").write_text("{}")
        (root / "loop" / "qa" / "resources.json").write_text(json.dumps({"resources": [
            {"id": "map", "where": "a.json", "answers": "is the project done and what is next"}]}))
        must(find(root, ["done", "next"]) and "a.json" in find(root, ["done", "next"])[0], "find hits a resource holding every word")
        must(find(root, ["done", "banana"]) == [], "find misses when one word is absent")
        must(check(root) == [], "check passes when every path exists")
        (root / "loop" / "qa" / "resources.json").write_text(json.dumps({"resources": [{"id": "x", "where": "gone.json", "answers": "y"}]}))
        must(check(root), "check refuses a dead path")
    if bad:
        print("lookup selftest: FAILED: " + "; ".join(bad))
        return 1
    print(f"lookup selftest: ALL GREEN · {n} controls")
    return 0


def main(argv):
    if argv[:1] == ["selftest"]:
        return selftest()
    if argv[:1] == ["check"]:
        p = check(kit.ROOT)
        print("lookup check: " + ("ok" if not p else "REFUSED\n  " + "\n  ".join(p)))
        return 1 if p else 0
    if argv[:1] == ["find"] and argv[1:]:
        hits = find(kit.ROOT, argv[1:])
        print("\n".join(hits) if hits else f"nothing holds every word of: {' '.join(argv[1:])} (try fewer words)")
        return 0
    print("usage: lookup.py find WORDS | check | selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
