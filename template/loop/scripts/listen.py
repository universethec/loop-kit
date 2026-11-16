#!/usr/bin/env python3
# Listening: dreaming from the owner's own words (ported from harbingr-v2, 2026-11-16, the owner: "dreaming with self-learning,
# without bloating"; "I want you to become intelligent from session to session"). A pass after a session with him that
# reads only the messages the harness marks as typed by a person, and proposes changes to the project's index
# (loop/qa/index.json: project lines, ledger, corrections) and to the working rules (loop/qa/memory.json). Every
# proposal must quote him word for word, or it is thrown away. It never changes a file in git: the owner says yes or no;
# a yes stays on the start screen (index.py) until the commit that applies it is marked with `applied`.
# (dream.py is the other pass: it prunes gates and reads refused tool calls after the unattended loop.)
#
#   listen.py gather [--sessions N]    his typed words since the last pass (or the last N sessions) -> a packet
#   listen.py run                      one read-only `claude -p` on Opus over the packet, the index and the rules
#   listen.py show                     the proposals waiting, in plain words
#   listen.py answer ID yes|no "<his words>"   records his answer
#   listen.py applied ID <commit>      marks a yes applied; until then the start screen asks for it
#   listen.py selftest                 planted truths
#
# WHERE IT WRITES: loop/state/dreams/ only (git-ignored). WHAT IT COSTS: one Opus run on his subscription per `run`.
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "loop" / "state" / "dreams"
TRANSCRIPTS = Path(os.path.expanduser("~/.claude/projects")) / ("-" + str(ROOT).strip("/").replace("/", "-").replace(" ", "-"))
RULES = ROOT / "loop" / "qa" / "memory.json"
BEFORE = 700          # characters of what Claude said just before each of his messages
BUDGET = 160_000      # characters of the packet handed to the dreamer
KINDS = ("project-line", "ledger", "correction", "working-rule", "stale")

PROMPT = """You are the listening pass of a project. You never saw these sessions live. Below are: the project's index
(what every session reads at the start: what exists, the mission ledger's newest entry, the owner's corrections in force), the
working rules (how sessions must work with the owner), and a packet of the owner's own typed messages from recent sessions, each
with what Claude had said just before it.

Find what should change so that the NEXT session is less blind and makes fewer of the same mistakes:
- correction: a correction the owner made more than once, or once and sharply, about how Claude works or about Claude
  ignoring what is already built; say the rule a session should follow.
- ledger: words of the owner's that state the mission or the open problem more sharply than the ledger's newest entry.
- project-line: something that exists in the project that the index's project lines lack or get wrong.
- working-rule: a pattern in how the owner wants to be worked with that no current rule covers.
- stale: an index line or a rule that his words show is out of date.
Keep only patterns that matter. Prefer few, sharp proposals over many. Never propose what the index or rules already say.

Every proposal MUST quote the owner word for word from the packet (copy exactly; a quote not found verbatim is thrown away).
Answer with JSON only:
{"proposals": [{"kind": one of %s, "change": "the exact line to add or replace, in plain words",
"replaces": "the line it replaces, or null", "why": "one sentence", "quotes": [{"session": "<id>", "words": "<verbatim>"}],
"sessions_seen": <how many sessions show it>, "pick": "yes or no: whether you would accept it, and why in a few words"}]}

THE INDEX:
%s

THE WORKING RULES (headlines):
%s

THE PACKET:
%s
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def text_of(content):
    if isinstance(content, str):
        return content
    if any(b.get("type") == "tool_result" for b in content):
        return None
    return " ".join(b.get("text", "") for b in content if b.get("type") == "text")


def his_words(d):
    """His own typed message, or None. A message counts only if the harness marks it as typed by a person; where an
    older transcript carries no such mark, anything that is a tool result, a system note, a hook's feedback, a task
    notification or another agent's message is left out."""
    if d.get("type") != "user" or d.get("isMeta"):
        return None
    t = text_of(d.get("message", {}).get("content", ""))
    if not t or not t.strip():
        return None
    origin = d.get("origin")
    # Only a message the harness marks as typed by a person. A transcript with no such marks (older ones, and the
    # headless `claude -p` helpers whose prompt is a user turn) gives nothing: a helper's brief must never pass as his.
    return t.strip() if isinstance(origin, dict) and origin.get("kind") == "human" else None


def claude_said(d):
    if d.get("type") != "assistant":
        return None
    c = d.get("message", {}).get("content", [])
    t = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text") if isinstance(c, list) else str(c)
    return t.strip() or None


def session_turns(lines):
    turns, last = [], ""
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        said = claude_said(d)
        if said:
            last = said
            continue
        w = his_words(d)
        if w:
            turns.append({"at": d.get("timestamp", ""), "claude_before": last[-BEFORE:], "owner": w})
    return turns


def last_dream():
    f = OUT / "last.json"
    return json.loads(f.read_text())["until"] if f.exists() else None


def gather(sessions=None):
    files = sorted(TRANSCRIPTS.glob("*.json" + "l"), key=lambda p: p.stat().st_mtime)
    since = last_dream()
    if sessions:
        files = files[-sessions:]
    elif since:
        files = [f for f in files if datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).strftime("%Y%m%dT%H%M%SZ") > since]
    else:
        files = files[-10:]
    packet, size = [], 0
    for f in reversed(files):   # newest first, until the budget is spent
        turns = session_turns(f.read_text(errors="replace").splitlines())
        if not turns:
            continue
        s = {"session": f.stem, "turns": turns}
        n = len(json.dumps(s, ensure_ascii=False))
        if size + n > BUDGET:
            break
        packet.append(s)
        size += n
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = now()
    P = {"made": stamp, "sessions": packet}
    (OUT / f"packet-{stamp}.json").write_text(json.dumps(P, indent=1, ensure_ascii=False) + "\n")
    print(f"listen gather: {len(packet)} sessions, {sum(len(s['turns']) for s in packet)} of his messages, {size:,} characters → loop/state/dreams/packet-{stamp}.json")
    return P


def flat(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def verified(proposals, packet):
    """Keep a proposal only if it is well formed and every quote stands word for word in his messages of the packet."""
    said = {s["session"]: flat(" \n ".join(t["owner"] for t in s["turns"])) for s in packet["sessions"]}
    kept, thrown = [], []
    for p in proposals:
        qs = p.get("quotes") or []
        ok = p.get("kind") in KINDS and p.get("change") and qs and all(flat(q.get("words", "")) and flat(q["words"]) in said.get(q.get("session"), "") for q in qs)
        (kept if ok else thrown).append(p)
    return kept, thrown


def run():
    packets = sorted(OUT.glob("packet-*.json"))
    if not packets:
        print("listen run: no packet; run `listen.py gather` first")
        return 1
    P = json.loads(packets[-1].read_text())
    index = subprocess.run([sys.executable, "-I", str(HERE / "index.py")], capture_output=True, text=True).stdout
    rules = "\n".join("- " + r.get("headline", r["rule"]) for r in json.loads(RULES.read_text())["rules"])
    prompt = PROMPT % (list(KINDS), index, rules, json.dumps(P["sessions"], ensure_ascii=False))
    r = subprocess.run(["claude", "-p", "--model", "opus", "--allowedTools", "", "--disallowedTools", "Bash,Write,Edit,NotebookEdit,Read,Grep,Glob,WebFetch,WebSearch"],
                       input=prompt, capture_output=True, text=True, timeout=1800, cwd=str(OUT))
    m = re.search(r"\{.*\}", r.stdout, re.S)
    if not m:
        print(f"listen run: the dreamer gave no JSON (exit {r.returncode}): {r.stdout[:300]} {r.stderr[:300]}")
        return 1
    kept, thrown = verified(json.loads(m.group(0)).get("proposals", []), P)
    stamp = P["made"]
    for i, p in enumerate(kept, 1):
        p["id"] = f"{stamp}-{i}"
        p["answer"] = None
    out = {"made": stamp, "by": "claude -p --model opus, no tools", "sessions": [s["session"] for s in P["sessions"]], "proposals": kept,
           "thrown_away": [{"kind": p.get("kind"), "change": p.get("change"), "why": "a quote does not stand word for word in his messages, or the proposal is malformed"} for p in thrown]}
    (OUT / f"proposals-{stamp}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    (OUT / "last.json").write_text(json.dumps({"until": stamp}) + "\n")
    print(f"listen run: {len(kept)} proposals kept, {len(thrown)} thrown away → loop/state/dreams/proposals-{stamp}.json")
    return 0


def all_proposals():
    out = []
    for f in sorted(OUT.glob("proposals-*.json")):
        D = json.loads(f.read_text())
        out += [(f, D, p) for p in D["proposals"]]
    return out


def show():
    waiting = [(f, D, p) for f, D, p in all_proposals() if p.get("answer") is None]
    if not waiting:
        print("listen show: nothing waits for the owner")
        return 0
    for _, _, p in waiting:
        print(f"[{p['id']}] {p['kind']} · seen in {p.get('sessions_seen', '?')} session(s)\n  change: {p['change']}"
              + (f"\n  replaces: {p['replaces']}" if p.get("replaces") else "") + f"\n  why: {p['why']}\n  his words: "
              + " | ".join(f"\"{q['words']}\"" for q in p["quotes"]) + f"\n  my pick: {p.get('pick', '')}\n")
    print(f"{len(waiting)} waiting. Answer each: python3 -I loop/scripts/listen.py answer ID yes|no \"<your words>\"")
    return 0


def answer(pid, yn, words):
    for f, D, p in all_proposals():
        if p["id"] == pid:
            p["answer"] = {"yes": yn == "yes", "words": words, "at": now()}
            f.write_text(json.dumps(D, indent=1, ensure_ascii=False) + "\n")
            print(f"listen answer: {pid} {yn}. A yes is applied by the next session, in a commit you can read.")
            return 0
    print(f"listen answer: no proposal {pid}")
    return 1


def applied(pid, commit):
    """Marks a yes as applied, naming the commit that applied it; the index stops asking for it."""
    for f, D, p in all_proposals():
        if p["id"] == pid:
            if not (p.get("answer") or {}).get("yes"):
                print(f"listen applied: {pid} has no yes from the owner; refused")
                return 1
            p["applied"] = {"commit": commit, "at": now()}
            f.write_text(json.dumps(D, indent=1, ensure_ascii=False) + "\n")
            print(f"listen applied: {pid} in {commit}")
            return 0
    print(f"listen applied: no proposal {pid}")
    return 1


def selftest():
    bad = []
    must = lambda ok, what: ok or bad.append(what)  # noqa: E731
    lines = [json.dumps(x) for x in [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Shall I ask you about the stake?"}]}},
        {"type": "user", "origin": {"kind": "human"}, "message": {"content": "we literally have this built"}, "timestamp": "t1"},
        {"type": "user", "isMeta": True, "message": {"content": "Stop hook feedback: rewrite"}},
        {"type": "user", "origin": {"kind": "task-notification"}, "message": {"content": "<task-notification>x"}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "user", "message": {"content": "a helper's brief with no mark of who typed it"}},
        {"type": "user", "message": {"content": "<system-reminder>not his</system-reminder>"}},
    ]]
    T = session_turns(lines)
    must([t["owner"] for t in T] == ["we literally have this built"], f"his words were not told apart from the rest: {[t['owner'] for t in T]}")
    must(T[0]["claude_before"] == "Shall I ask you about the stake?", "what Claude said before his message was lost")
    packet = {"sessions": [{"session": "s1", "turns": T}]}
    good = {"kind": "correction", "change": "read first", "quotes": [{"session": "s1", "words": "we literally have  this built"}]}
    invented = {"kind": "correction", "change": "x", "quotes": [{"session": "s1", "words": "you are always right"}]}
    wrong_session = {"kind": "correction", "change": "x", "quotes": [{"session": "s2", "words": "we literally have this built"}]}
    no_kind = {"kind": "rewrite everything", "change": "x", "quotes": [{"session": "s1", "words": "we literally have this built"}]}
    kept, thrown = verified([good, invented, wrong_session, no_kind], packet)
    must(kept == [good], "a proposal with words he never typed, or the wrong session, or no kind, was kept; or the true one was thrown")
    must(len(thrown) == 3, "the thrown-away proposals were not all counted")
    src = Path(__file__).read_text()
    writes = re.findall(r"\(OUT / [^)]*\)\.write_text|f\.write_text|OUT\.mkdir", src)
    into_git = re.findall(r"(?m)^\s*\(?(?:INDEX|RULES|ROOT)\b[^\n]*\.write_text\(", src)
    must(len(writes) >= 3 and not into_git, f"the program writes somewhere other than loop/state/dreams/: {into_git}")
    if bad:
        print("listen selftest: FAIL\n  - " + "\n  - ".join(bad))
        return 1
    print("listen selftest: every planted truth held")
    return 0


def main(a):
    if not a:
        print(__doc__ or "usage: listen.py gather [--sessions N] | run | show | answer ID yes|no \"words\" | selftest")
        return 2
    if a[0] == "gather":
        gather(int(a[a.index("--sessions") + 1]) if "--sessions" in a else None)
        return 0
    if a[0] == "run":
        return run()
    if a[0] == "show":
        return show()
    if a[0] == "answer" and len(a) >= 4:
        return answer(a[1], a[2], a[3])
    if a[0] == "applied" and len(a) >= 3:
        return applied(a[1], a[2])
    if a[0] == "selftest":
        return selftest()
    print("usage: listen.py gather [--sessions N] | run | show | answer ID yes|no \"words\" | applied ID <commit> | selftest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
