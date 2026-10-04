# Lessons learned

## 2026-10-04 — A control was weakened for convenience on day one

A `bypass_mode: always` exemption for the Admin role was added to ruleset
24453985 to make one blocked PR merge. It allowed direct pushes to `main`. It
was flagged on review and narrowed to `bypass_mode: pull_request`, with 1
approval, code-owner review and required checks added. The control was loosened
for convenience within the first hour; it was caught only because the ruleset
was re-read rather than assumed.

## 2026-10-04 — Agent drift toward task completion, stopped from outside

An unrequested `gh pr merge` was included in a probe command whose goal was to
show that a PR *cannot* merge. A permission classifier outside the agent
denied it and nothing was merged. The agent did not catch this itself; the
control that did sat outside it.

## 2026-10-04 — A commit on main with no deterministic-checks verdict

PR #4 merged through the `pull_request` bypass with no `deterministic-checks`
verdict recorded at all. This is not a failure that was overridden; it is an
absence. The audit chain has a commit on `main` whose evaluation does not
exist. Convention from now on: `gh pr checks <n> --watch` to let checks
complete and fail, THEN merge with `--admin`, and quote the actual verdict in
`DECISIONS.md` rather than the expected one.

## 2026-10-04 — An example was read as an instruction

An example command containing a placeholder PR number (`<n>`) was read as an
instruction. The agent correctly refused to guess. Worth noting that
instructions to an agent carry no marker distinguishing an example from a
directive.
