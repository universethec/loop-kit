# The plain-words check: text the owner reads stays plain and speaks to the owner as "you".
# It refuses: a borrowed persona name ("Maria"); "he", "his", "him", "himself" (the owner is "you", or "the owner");
# and codespeak, text that looks plain but is made of the program's own names and shapes. The test for codespeak:
# would a friend who never saw the project understand it on first read? A program name inside `backticks` is marked
# as code and passes; the same name loose in a sentence is codespeak.
#
#   plain.py check [FILES...]   exit 1 on any hit (default: CLAUDE.md, loop/HANDOFF.md, loop/qa/memory.json)
#   plain.py selftest           planted text: each kind of hit is caught, the clean text passes
import json
import re
import sys
from pathlib import Path

DEFAULT = ["CLAUDE.md", "loop/HANDOFF.md", "loop/qa/memory.json"]
PERSONA = re.compile(r"\bMaria\b", re.I)
PRONOUN = re.compile(r"\b(he|his|him|himself)\b", re.I)
# Program names that read like words but are not: a session may write them only inside backticks.
CODESPEAK = ["needs_owner", "waits_on", "done_when", "next-agent", "done-rules", "handoff_check", "review_check",
             "build_donemap"]
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def prose(path, text):
    """The words a reader sees: the string values of a JSON file, else the text itself."""
    if path.endswith(".json"):
        try:
            out = []

            def walk(x):
                if isinstance(x, str):
                    out.append(x)
                elif isinstance(x, dict):
                    [walk(v) for v in x.values()]
                elif isinstance(x, list):
                    [walk(v) for v in x]
            walk(json.loads(text))
            return "\n".join(out)
        except ValueError:
            return text
    return text


def scan(path, text, codespeak=True):
    """[(line number, what)] for every hit in one file."""
    hits = []
    for i, line in enumerate(prose(path, text).splitlines(), 1):
        if PERSONA.search(line):
            hits.append((i, "a persona name: " + PERSONA.search(line).group(0)))
        for m in PRONOUN.finditer(line):
            hits.append((i, f"'{m.group(0)}' for the owner: say 'you' (or 'the owner')"))
    if codespeak and path.endswith((".md", ".json")):  # prose only; code and its comments may name code
        for i, line in enumerate(CODE.sub("", prose(path, text)).splitlines(), 1):
            for w in CODESPEAK:
                if re.search(r"(?<![\w./-])" + re.escape(w) + r"(?![\w-])", line):
                    hits.append((i, f"codespeak '{w}' outside backticks: say what it does"))
    return hits


def check(files, codespeak=True):
    bad = []
    for f in files:
        p = Path(f)
        if p.is_file():
            bad += [f"{f}:{i}: {w}" for i, w in scan(str(p), p.read_text(errors="replace"), codespeak)]
    return bad


def selftest():
    n, bad = 0, []

    def must(ok, what):
        nonlocal n
        n += 1
        if not ok:
            bad.append(what)
    must(scan("a.md", "Explain it as a Maria story."), "a persona name got through")
    must(scan("a.md", "Ask the owner what he wants."), "a bare 'he' for the owner got through")
    must(scan("a.json", json.dumps({"rule": "measure his claims"})), "'his' inside a JSON rule got through")
    must(scan("a.md", "The step has needs_owner set."), "codespeak outside backticks got through")
    must(scan("a.md", "The step has `needs_owner` set.") == [], "a program name in backticks was refused")
    must(scan("a.md", "Ask the owner what they want; the theme and the helmet stay.") == [], "clean text was refused")
    must(scan("a.sh", "# needs_owner") == [], "codespeak was looked for in code")
    print(f"plain selftest: {'ok' if not bad else 'FAILED'} · {n} planted texts (persona, he/his, codespeak, clean)")
    for b in bad:
        print("  BAD", b)
    return 0 if not bad else 1


def main(argv):
    if argv[:1] == ["selftest"]:
        return selftest()
    if argv[:1] != ["check"]:
        print("usage: plain.py check [FILES...] | plain.py selftest")
        return 2
    bad = check(argv[1:] or DEFAULT)
    print("\n".join(bad) if bad else "plain: ok · no persona name, the owner is you, no codespeak")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
