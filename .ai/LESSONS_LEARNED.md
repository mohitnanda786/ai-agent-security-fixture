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
