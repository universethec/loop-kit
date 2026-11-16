# The second eyes: a separate read-only `claude -p` that never saw the session reads only the done map, the unit's
# promise and the unit's files, and lists what the result cannot say, gaps the map does not hold, and overclaims.
# Every gap must be answered before close: landed (a done-rules step id that now holds it) or refused with a reason;
# every overclaim fixed or disputed. The answers live in loop/qa/answers/<unit>.json; loop/reviews/ is the reviewer's.
#
#   review_check.py run UNIT FILE...      run the blind reviewer; writes loop/reviews/review-UNIT.json (stamped)
#   review_check.py packet UNIT FILE...   print the reviewer's prompt (what `run` sends)
#   review_check.py check UNIT            exit 1 unless the review exists, is stamped, and every item is answered
#   review_check.py selftest              planted reviews: unanswered refused, answered passes, a forged stamp refused
#
# Answers file: {"missing": [{"landed": "<step id>"} | {"refused": "reason"}], "overclaims": [{"fixed": ".."} | {"disputed": ".."}]}
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402

BY = "claude -p, read-only (Read, Grep, Glob), a fresh session"
PROMPT = """You are a reviewer who has never seen the session that made this result. You get only the project's done
map (what 'done' means, step by step), the unit's promise, and the unit's own files. Read them; read nothing else
except files they cite. You do not know what the author concluded and you must not guess it. Find three things:
1. cannot_say: what this result cannot show, however it is read (at least one, in plain words).
2. missing: anything the mission needs that this unit did not touch AND that the done map does not already hold as a
   step or a line. For each: what, why. Empty only if you looked and found none; say how you looked.
3. overclaims: any sentence in the unit's files that claims more than the files themselves show, quoted, with why.
Copy every path you read exactly as given below, with nothing added.
Answer as JSON only: {"unit": "<unit>", "read": [paths], "how_looked": "...", "cannot_say": ["..."],
"missing": [{"what": "...", "why": "..."}], "overclaims": [{"claim": "...", "where": "...", "why": "..."}]}.

The map now:
"""


def dirs(root):
    return Path(root) / "loop" / "reviews", Path(root) / "loop" / "qa" / "answers"


def make_packet(root, unit, files):
    st = subprocess.run([sys.executable, "-I", str(HERE / "build_donemap.py"), "--status"], cwd=root, capture_output=True, text=True).stdout
    allowed = ["loop/qa/done-rules.json", f"loop/qa/units/{unit}.json"] + list(files)
    prompt = PROMPT.replace("<unit>", unit) + st + "\nFiles you may read:\n" + "\n".join(f"- {f}" for f in allowed)
    sha = hashlib.sha256(prompt.encode()).hexdigest()
    rv, _ = dirs(root)
    rv.mkdir(parents=True, exist_ok=True)
    (rv / f"allowed-{unit}.json").write_text(json.dumps({"unit": unit, "allowed": allowed, "packet_sha": sha}, indent=1) + "\n")
    return prompt, sha


def run(root, unit, files):
    prompt, sha = make_packet(root, unit, files)
    c = kit.conf(root)
    r = subprocess.run(["claude", "-p", "--model", c["model"], "--allowedTools", "Read,Grep,Glob",
                        "--disallowedTools", "Bash,Write,Edit,NotebookEdit,WebFetch,WebSearch",
                        "--mcp-config", str(Path(root) / "loop" / "loop-mcp.json"), "--strict-mcp-config"],
                       input=prompt, cwd=root, capture_output=True, text=True, timeout=1800)
    m = re.search(r"\{.*\}", r.stdout, re.S)
    if r.returncode != 0 or not m:
        print(f"review_check run {unit}: the reviewer returned no JSON (exit {r.returncode})\n{r.stdout[-800:]}{r.stderr[-400:]}")
        return 1
    v = json.loads(m.group(0))
    v.update({"unit": unit, "by": BY, "packet_sha": sha})
    rv, _ = dirs(root)
    (rv / f"review-{unit}.json").write_text(json.dumps(v, indent=1, ensure_ascii=False) + "\n")
    print(f"review_check run {unit}: written · cannot say {len(v.get('cannot_say', []))} · missing {len(v.get('missing', []))} · "
          f"overclaims {len(v.get('overclaims', []))}. Answer each in loop/qa/answers/{unit}.json, then `check`.")
    return 0


def problems_of(root, unit):
    rv, an = dirs(root)
    f, a = rv / f"review-{unit}.json", rv / f"allowed-{unit}.json"
    if not f.exists() or not a.exists():
        return [f"no review for {unit}: run `review_check.py run {unit} <files>`"]
    try:
        v, A = json.loads(f.read_text()), json.loads(a.read_text())
    except Exception as e:
        return [f"the review is not JSON ({e})"]
    out = []
    if v.get("by") != BY or v.get("packet_sha") != A.get("packet_sha"):
        out.append("the review was not written by `review_check.py run` on this packet (its stamp does not match)")
    extra = [p for p in v.get("read", []) if p not in A["allowed"]]
    if extra:
        out.append(f"the reviewer read files outside its packet: {extra}")
    if not v.get("read"):
        out.append("the reviewer read nothing")
    if not v.get("how_looked"):
        out.append("how_looked is empty")
    if not v.get("cannot_say"):
        out.append("cannot_say is empty: every result cannot say something")
    ans = json.loads((an / f"{unit}.json").read_text()) if (an / f"{unit}.json").exists() else {}
    steps = {s["id"] for s in json.loads((Path(root) / "loop" / "qa" / "done-rules.json").read_text())["steps"]}
    for i, m in enumerate(v.get("missing", [])):
        x = (ans.get("missing") or [{}] * (i + 1))[i] if i < len(ans.get("missing") or []) else {}
        if x.get("landed") in steps or len(x.get("refused") or "") >= 12:
            continue
        out.append(f"missing[{i}] '{str(m.get('what'))[:60]}' is neither landed (a done-rules step id) nor refused with a reason")
    for i, o in enumerate(v.get("overclaims", [])):
        x = (ans.get("overclaims") or [])[i] if i < len(ans.get("overclaims") or []) else {}
        if len(x.get("fixed") or "") >= 8 or len(x.get("disputed") or "") >= 12:
            continue
        out.append(f"overclaims[{i}] '{str(o.get('claim'))[:60]}' is neither fixed nor disputed with a reason")
    return out


def check(root, unit):
    p = problems_of(root, unit)
    if p:
        print(f"review_check {unit}: REFUSED\n  " + "\n  ".join(p))
        kit.catch("review:unanswered", f"{unit}: {p[0]}", unit, root)
        return 1
    print(f"review_check {unit}: ok · every gap landed or refused, every overclaim fixed or disputed")
    return 0


def selftest():
    import contextlib
    import io
    import os
    import tempfile
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        os.environ["LOOP_CATCHES"] = str(root / "catches.csv")
        (root / "loop" / "qa" / "answers").mkdir(parents=True)
        (root / "loop" / "qa" / "done-rules.json").write_text(json.dumps({"steps": [{"id": "s1", "done_when": [{"file": "x"}]}, {"id": "s2", "done_when": [{"file": "y"}]}]}))
        rv, an = dirs(root)
        rv.mkdir(parents=True)
        sha = "abc"
        (rv / "allowed-u1.json").write_text(json.dumps({"unit": "u1", "allowed": ["loop/qa/units/u1.json"], "packet_sha": sha}))
        review = {"unit": "u1", "by": BY, "packet_sha": sha, "read": ["loop/qa/units/u1.json"], "how_looked": "read the promise",
                  "cannot_say": ["whether it runs at scale"], "missing": [{"what": "a load test", "why": "x"}], "overclaims": [{"claim": "it is fast", "why": "no timing"}]}
        (rv / "review-u1.json").write_text(json.dumps(review))
        def q():
            with contextlib.redirect_stdout(io.StringIO()):
                return check(root, "u1")
        must(q() == 1, "an unanswered gap and overclaim are refused")
        (an / "u1.json").write_text(json.dumps({"missing": [{"landed": "nope"}], "overclaims": [{"fixed": "removed the claim"}]}))
        must(q() == 1, "a gap 'landed' on a step that does not exist is refused")
        (an / "u1.json").write_text(json.dumps({"missing": [{"landed": "s2"}], "overclaims": [{"fixed": "removed the claim"}]}))
        must(q() == 0, "a gap landed on a real step and a fixed overclaim pass")
        (an / "u1.json").write_text(json.dumps({"missing": [{"refused": "short"}], "overclaims": [{"disputed": "the timing table shows it, line 4"}]}))
        must(q() == 1, "a refusal without a real reason is refused")
        (rv / "review-u1.json").write_text(json.dumps({**review, "packet_sha": "forged"}))
        (an / "u1.json").write_text(json.dumps({"missing": [{"landed": "s2"}], "overclaims": [{"fixed": "removed the claim"}]}))
        must(q() == 1, "a review whose stamp does not match its packet is refused")
        (rv / "review-u1.json").write_text(json.dumps({**review, "read": ["src/secret.py"]}))
        must(q() == 1, "a reviewer that read outside its packet is refused")
        must("review:unanswered" in (root / "catches.csv").read_text(), "refusals land in the catch log")
        del os.environ["LOOP_CATCHES"]
    if bad:
        print("review_check selftest: FAILED: " + "; ".join(bad))
        return 1
    print(f"review_check selftest: ALL GREEN · {n} controls")
    return 0


def main(argv):
    root = kit.ROOT
    if argv[:1] == ["selftest"]:
        return selftest()
    if len(argv) >= 2 and argv[0] == "run":
        return run(root, argv[1], argv[2:])
    if len(argv) >= 2 and argv[0] == "packet":
        print(make_packet(root, argv[1], argv[2:])[0])
        return 0
    if len(argv) == 2 and argv[0] == "check":
        return check(root, argv[1])
    print("usage: review_check.py run UNIT FILE... | packet UNIT FILE... | check UNIT | selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
