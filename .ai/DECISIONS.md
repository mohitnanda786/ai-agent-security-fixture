# Decisions

## 2026-10-04 — Record runbook execution results (PR #2)

**What changed.** `.ai/VERIFIED.md` gains a "Runbook execution" section:
steps 0–6 results, the Windows portability fixes, the CI failure and its fix,
and the ruleset history (pre-existing weak ruleset, `bypass_mode: always`
added at 22:58, narrowed to `pull_request` with 1 approval, code-owner review
and required checks `deterministic-checks` + `trusted-suites`). This file adds
the decision record itself.

**Why it needs the control plane.** `.ai/` is governance, not worker scope.
Documentation of what the controls did is a privileged change; a worker must
not be able to edit the record of its own verification. It is merged by the
owner, not by the pipeline.

**deterministic-checks fired correctly.** On this PR it reported
`scope` (`.ai/VERIFIED.md` is outside the approved task scope) and
`base_binding` (main advanced since approval and touched `.github/workflows/ci.yml`,
so the plan would need re-approval). `trusted-suites` also failed, because the
acceptance suite is meant to fail until `clamp_score` is implemented. Neither
was relaxed or skipped. Owner merge is the intended path for this class of
change.
