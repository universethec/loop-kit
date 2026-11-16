# What the agent did, on one page: loop/activity.html, built from the files, newest first. For each piece of work:
# its promise (what it said it would make, the three plain lines, the checkable lines), the blind review's gaps and
# overclaims with how each was answered, the result line by line, and the commit it landed in.
#
#   activity.py            write loop/activity.html (qa.py close and `loop.py activity` run it); print its path
#   activity.py selftest   planted: two pieces of work, one closed and committed, one abandoned; the page lists both,
#                          newest first, with the gap and its answer, the result and the commit, and escapes the text
# Reads only: loop/qa/units/, loop/reviews/review-<unit>.json, loop/qa/answers/<unit>.json, git log. Stdlib only.
import html
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402

OUT = "loop/activity.html"
CSS = """:root{--bg:#121212;--surface:#191919;--stroke:#2c2c2c;--ink:#ffffffe5;--ink2:#ffffffb2;--muted:#8a8a8a;--accent:#ccbf17;
--green:#97c459;--yellow:#e4c07a;--red:#ef8787;--sans:"Neue Montreal",ui-sans-serif,system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:400 15px/22px var(--sans)}
main{max-width:860px;margin:0 auto;padding:28px 16px 60px}h1{font:500 28px/34px var(--sans);margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 24px}article{background:var(--surface);border:1px solid var(--stroke);border-radius:12px;padding:16px 18px;margin:0 0 14px}
article header{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:baseline}h2{font:500 18px/24px var(--sans);margin:0}
.mono,.tag{font:400 12px/18px var(--mono);color:var(--muted)}.tag{text-transform:uppercase;letter-spacing:.1em}
.pass{color:var(--green)}.partial,.abandoned,.open,.draft{color:var(--yellow)}.fail{color:var(--red)}
h3{font:500 11px/16px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:14px 0 6px}
ul{margin:0;padding-left:18px}li{margin:2px 0;color:var(--ink2)}li b{color:var(--ink);font-weight:500}p{margin:6px 0;color:var(--ink2)}
.what{color:var(--ink);margin-top:8px}.none{color:var(--muted)}"""


def git(root, *a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True).stdout.strip()


def gather(root):
    """[dict]: every piece of work with its review, answers, result and commit, newest first."""
    root = Path(root)
    names = {}
    try:
        names = {s["id"]: s.get("name", s["id"]) for s in json.loads((root / "loop/qa/done-rules.json").read_text())["steps"]}
    except Exception:
        pass
    rows = []
    for f in (root / "loop" / "qa" / "units").glob("*.json"):
        try:
            u = json.loads(f.read_text())
        except Exception:
            continue
        unit = f.stem
        load = lambda p: json.loads(p.read_text()) if p.exists() else {}  # noqa: E731
        rv, an = load(root / "loop/reviews" / f"review-{unit}.json"), load(root / "loop/qa/answers" / f"{unit}.json")
        opened = load(root / "loop/state/opened" / f"{unit}.json")
        r = u.get("result") or {}
        state = r.get("overall") or ("open" if opened else "draft")
        commit = git(root, "log", "--diff-filter=A", "--format=%h %ad %s", "--date=short", "-1", "--", f"loop/qa/units/{unit}.json")
        rows.append({"unit": unit, "step": u.get("step", ""), "step_name": names.get(u.get("step"), ""), "what": u.get("what", ""),
                     "plain": u.get("plain") or [], "promise": u.get("promise") or [], "state": state, "result": r,
                     "review": rv, "answers": an, "commit": commit, "redo_of": u.get("redo_of", ""),
                     "when": r.get("closed_at") or opened.get("at") or "9999 (not stamped yet)"})
    return sorted(rows, key=lambda x: x["when"], reverse=True)


def answer_of(ans, kind, i):
    x = (ans.get(kind) or [])[i] if i < len(ans.get(kind) or []) else {}
    for k, label in (("landed", "landed as step"), ("refused", "refused"), ("fixed", "fixed"), ("disputed", "disputed")):
        if x.get(k):
            return f"{label}: {x[k]}"
    return "not answered yet"


def card(w):
    e = html.escape
    r, rv = w["result"], w["review"]
    res = f"{r.get('passed', 0)} of {r.get('of', 0)} promise lines passed" if r else "not closed yet"
    top = (f"<header><h2>{e(w['unit'])}</h2><span class='tag {e(w['state'])}'>{e(w['state'])}</span>"
           f"<span class='mono'>step {e(w['step'])} {e(w['step_name'])} · {e(w['when'][:16].replace('T', ' '))}</span></header>"
           f"<p class='what'>{e(w['what'])}</p>" + (f"<p class='mono'>a redo of {e(w['redo_of'])}</p>" if w["redo_of"] else ""))
    plain = "".join(f"<li>{e(x)}</li>" for x in w["plain"])
    lines = {x.get("what"): x for x in r.get("lines", [])}
    prom = "".join(f"<li><b>{e(x.get('what', ''))}</b>"
                   + (f" <span class='{'pass' if lines[x.get('what')]['ok'] else 'fail'}'>{'passed' if lines[x.get('what')]['ok'] else 'failed'}</span>"
                      f" <span class='mono'>{e(str(lines[x.get('what')].get('saw', ''))[:160])}</span>" if x.get("what") in lines else "")
                   + "</li>" for x in w["promise"])
    gaps = "".join(f"<li><b>{e(str(m.get('what', '')))}</b> {e(str(m.get('why', '')))} · {e(answer_of(w['answers'], 'missing', i))}</li>"
                   for i, m in enumerate(rv.get("missing", [])))
    over = "".join(f"<li><b>{e(str(o.get('claim', '')))}</b> {e(str(o.get('why', '')))} · {e(answer_of(w['answers'], 'overclaims', i))}</li>"
                   for i, o in enumerate(rv.get("overclaims", [])))
    review = (f"<ul>{gaps}{over}</ul>" if gaps or over else "<p class='none'>" + ("no gaps, no overclaims" if rv else "no review yet") + "</p>")
    why = f"<p>reason: {e(r['reason'])}</p>" if r.get("reason") else ""
    return (f"<article>{top}<h3>The promise</h3><ul>{plain}</ul><ul>{prom}</ul><h3>The review: gaps and how they were answered</h3>"
            f"{review}<h3>The result</h3><p class='{e(w['state'])}'>{e(w['state'])} · {e(res)}</p>{why}"
            f"<h3>The commit</h3><p class='mono'>{e(w['commit']) or 'not committed yet'}</p></article>")


def build(root):
    root = Path(root)
    rows = gather(root)
    name = kit.conf(root).get("project", "project")
    body = "".join(card(w) for w in rows) or "<p class='none'>No piece of work yet. Say go to start one.</p>"
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(name)} activity</title><link rel='stylesheet' href='assets/v1-fonts.css'><style>{CSS}</style></head>"
            f"<body><main><h1>What the agent did</h1><p class='sub'>{html.escape(name)} · {len(rows)} piece(s) of work, newest first."
            f" Built from the files by activity.py.</p>{body}</main></body></html>\n")
    (root / OUT).write_text(page)
    return root / OUT


def selftest():
    import os
    import tempfile
    import loop
    bad, n = [], 0

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)

    with tempfile.TemporaryDirectory() as td:
        root = loop.plant(td)
        os.environ["LOOP_CATCHES"] = str(root / "catches.csv")
        run = lambda *a: loop.sh(root, sys.executable, "-I", *a)
        run("loop/scripts/loop.py", "go")
        f = root / "loop/qa/units/s1-1.json"
        u = json.loads(f.read_text())
        u.update(what="make a.txt appear, the first file", plain=["the file a.txt is there now", "you can open a.txt and read it", "next comes the owner's look"])
        f.write_text(json.dumps(u))
        run("loop/scripts/qa.py", "open", "s1-1")
        (root / "loop/reviews/review-s1-1.json").write_text(json.dumps({"missing": [{"what": "no test for <script>x</script>", "why": "a planted gap"}]}))
        (root / "loop/qa/answers/s1-1.json").write_text(json.dumps({"missing": [{"refused": "the page escapes text, planted reason"}]}))
        (root / "a.txt").write_text("x")
        run("loop/scripts/qa.py", "close", "s1-1")
        must("s1-1" in ((root / OUT).read_text() if (root / OUT).exists() else ""), "qa close builds the page")
        loop.commit(root, "s1-1: the planted piece of work")
        sha = git(root, "log", "-1", "--format=%h")
        run("loop/scripts/draft.py", "s1", "later")
        g = root / "loop/qa/units/later.json"
        v = json.loads(g.read_text())
        v["result"] = {"overall": "abandoned", "reason": "a planted later abandon", "closed_at": "9998-01-01T00:00:00"}
        g.write_text(json.dumps(v))
        r = run("loop/scripts/loop.py", "activity")
        page = (root / OUT).read_text() if (root / OUT).exists() else ""
        must(r.returncode == 0 and "s1-1" in page and "later" in page, "the page lists both planted pieces of work")
        must(page.find("<h2>later") < page.find("<h2>s1-1") and page.find("<h2>later") > 0, "newest first")
        must("refused: the page escapes text, planted reason" in page and "a planted gap" in page, "the gap and how it was answered")
        must("&lt;script&gt;" in page and "<script>x" not in page, "the review's words are escaped")
        must(sha in page and "the planted piece of work" in page, "the commit it landed in")
        must("of 3 promise lines passed" in page and "a planted later abandon" in page, "the result, and the reason of an abandon")
        must("make a.txt appear, the first file" in page and "you can open a.txt and read it" in page, "the promise and its plain lines")
        del os.environ["LOOP_CATCHES"]
    print(f"activity selftest: {'ALL GREEN' if not bad else 'FAILED: ' + '; '.join(bad)} · {n} controls")
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        sys.exit(selftest())
    print(build(kit.ROOT).relative_to(kit.ROOT))
