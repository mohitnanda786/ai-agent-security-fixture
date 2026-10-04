#!/usr/bin/env bash
# probe_agy.sh — register rows 1 and 2.
#
# Settles one question: can an orchestrator drive `agy` unattended on THIS
# machine? Community reports say -p drops stdout or hangs when stdout is not a
# TTY. This checks it rather than trusting the reports.
#
# Run from a directory you do not mind an agent reading. Writes probe_agy.log.
#
#   chmod +x probe_agy.sh && ./probe_agy.sh

set -uo pipefail

PROMPT="Reply with exactly the word: ALIVE"
TIMEOUT="${PROBE_TIMEOUT:-90}"
LOG="probe_agy.log"
: > "$LOG"

pass=0; fail=0

say()  { printf '%s\n' "$*" | tee -a "$LOG"; }
head() { say ""; say "── $* ────────────────────────────────"; }

verdict() { # name, exit code, captured output
  local name="$1" rc="$2" out="$3"
  if [ "$rc" -eq 124 ]; then
    say "FAIL  $name — timed out after ${TIMEOUT}s (the hang defect)"
    fail=$((fail+1))
  elif [ "$rc" -ne 0 ]; then
    say "FAIL  $name — exit $rc"
    say "      ${out:0:200}"
    fail=$((fail+1))
  elif [ -z "${out//[[:space:]]/}" ]; then
    say "FAIL  $name — exit 0 but no output (the silent-drop defect)"
    fail=$((fail+1))
  else
    say "PASS  $name — ${#out} bytes"
    pass=$((pass+1))
  fi
}

head "Environment"
command -v agy >/dev/null 2>&1 || { say "agy not on PATH — install it first, then re-run."; exit 2; }
say "agy:      $(agy --version 2>&1 | head -1)"
say "timeout:  $(command -v timeout >/dev/null && echo yes || echo 'MISSING — install coreutils')"
say "script:   $(command -v script >/dev/null && echo yes || echo 'MISSING — install util-linux')"
say "tty now:  $([ -t 1 ] && echo 'yes (interactive shell)' || echo 'no')"

# ---------------------------------------------------------------- row 1 -----
head "Row 1 — does -p produce output without a TTY?"

# A. command substitution — stdout is a pipe. This is what subprocess.run does.
out=$(timeout "$TIMEOUT" agy -p "$PROMPT" 2>&1); rc=$?
verdict "pipe (command substitution)" "$rc" "$out"

# B. redirect to a file — stdout is a regular file.
rc=0; timeout "$TIMEOUT" agy -p "$PROMPT" > .probe_b.txt 2>&1 || rc=$?
verdict "redirect to file" "$rc" "$(cat .probe_b.txt 2>/dev/null)"

# C. --output-format json — the shape an adapter actually wants.
out=$(timeout "$TIMEOUT" agy -p "$PROMPT" --output-format json 2>&1); rc=$?
verdict "pipe + --output-format json" "$rc" "$out"

# D. under a pseudo-terminal — the documented community workaround.
if command -v script >/dev/null 2>&1; then
  if script --version 2>&1 | grep -qi util-linux; then
    rc=0; timeout "$TIMEOUT" script -qec "agy -p '$PROMPT'" /dev/null > .probe_d.txt 2>&1 || rc=$?
  else
    # BSD/macOS script takes the command as trailing args, no -c
    rc=0; timeout "$TIMEOUT" script -q /dev/null agy -p "$PROMPT" > .probe_d.txt 2>&1 || rc=$?
  fi
  verdict "PTY via script" "$rc" "$(cat .probe_d.txt 2>/dev/null)"
else
  say "SKIP  PTY via script — script not installed"
fi

# ---------------------------------------------------------------- row 2 -----
head "Row 2 — does it authenticate without an interactive session?"
say "Running with HOME pointed at an empty directory, so no cached credentials."
TMPHOME=$(mktemp -d)
out=$(HOME="$TMPHOME" timeout "$TIMEOUT" agy -p "$PROMPT" 2>&1); rc=$?
if [ "$rc" -eq 124 ]; then
  say "HANGS — waits for interactive auth. Unattended runs need a pre-authenticated HOME."
elif [ "$rc" -ne 0 ]; then
  say "EXITS $rc — fails cleanly without cached credentials (better than hanging)."
  say "      ${out:0:200}"
else
  say "SUCCEEDS — credentials are reachable from outside HOME. Find out where before"
  say "           claiming the worker container is credential-free."
fi
rm -rf "$TMPHOME"

# ------------------------------------------------------------------ out -----
rm -f .probe_b.txt .probe_d.txt
head "Result"
say "row 1: $pass passed, $fail failed"
say ""
if [ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]; then
  say "The adapter can use plain subprocess. Build it that way."
elif [ "$pass" -gt 0 ]; then
  say "Some shapes work and some do not. The adapter must use whichever passed above."
  say "If only the PTY row passed, the adapter allocates a PTY (python: pty.openpty)."
else
  say "Nothing worked unattended. agy is not usable as the worker on this machine today."
  say "Options: the Antigravity SDK, a different worker CLI, or defer the worker and"
  say "build steps 2 and 3 against a scripted stub that fakes an implementation."
fi
say ""
say "Paste this log into .ai/VERIFIED.md with today's date."
