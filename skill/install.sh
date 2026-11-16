#!/usr/bin/env bash
# Install the boot skill and say what is missing, in one line:  bash loop-kit/skill/install.sh
#
# 1. Copies skill/new-project/SKILL.md to ~/.claude/skills/new-project/SKILL.md with this kit's real path filled in
#    (no hand edit). Run it again after you move the kit, or after a kit update.
# 2. Checks what the kit needs and lists what is missing, with how to get it:
#    needed: python3, git, claude (Claude Code); for the unattended loop: tmux, and on macOS caffeinate (keeps the
#    computer awake); optional: gh (GitHub).
# Exit 0 when the skill is in place and everything needed is there; 1 when something needed is missing.
here="${BASH_SOURCE[0]%/*}"
[ "$here" = "${BASH_SOURCE[0]}" ] && here=.
kit="$(cd "$here/.." && pwd)" || exit 1
src="$kit/skill/new-project/SKILL.md"
dest="${HOME:?HOME is not set}/.claude/skills/new-project"
[ -f "$src" ] || { echo "install: $src not found; run this from inside the loop-kit folder"; exit 1; }
mkdir -p "$dest" || exit 1
text="$(<"$src")"
shopt -u patsub_replacement 2>/dev/null  # bash 5.2: an '&' in the path stays an '&'
printf '%s\n' "${text//<path to loop-kit>/$kit}" > "$dest/SKILL.md" || exit 1
echo "install: the boot skill is in place: $dest/SKILL.md (kit: $kit)"
echo "         say \"boot loop-kit\" in Claude Code to start a project."

need=0
have() { command -v "$1" >/dev/null 2>&1; }
check() {  # check <tool> <needed|loop|optional> <what it is for> <how to get it>
  if have "$1"; then echo "  ok       $1"; return; fi
  case "$2" in
    needed) echo "  MISSING  $1: $3. Get it: $4"; need=1 ;;
    loop) echo "  MISSING  $1 (only for the unattended loop): $3. Get it: $4"; need=1 ;;
    optional) echo "  optional $1 is not installed: $3. Get it: $4" ;;
  esac
}
echo "install: what the kit needs"
check python3 needed "runs every check and tool" "https://www.python.org/downloads/ or: brew install python"
check git needed "keeps every piece of work as a commit" "xcode-select --install, or: brew install git"
check claude needed "Claude Code, the one who does the work" "https://claude.com/claude-code"
check tmux loop "keeps the unattended loop running in the background" "brew install tmux (Linux: apt install tmux)"
if [ "$(uname -s 2>/dev/null)" = Darwin ]; then
  check caffeinate loop "keeps the Mac awake while the loop runs" "it comes with macOS; check that /usr/bin is on your PATH"
fi
check gh optional "only if you want GitHub from the project" "brew install gh"
[ $need -eq 0 ] && echo "install: ok · everything needed is there" || echo "install: something needed is missing (above)"
exit $need
