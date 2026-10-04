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

## 2026-10-04 — Lessons learned: audit gap and example-vs-directive (PR #5)

**What changed.** Two entries added to `.ai/LESSONS_LEARNED.md`. Merged by the
owner via the `pull_request` bypass, following the new convention (watch the
checks complete, then `--admin`).

**Actual verdict, quoted (run 37201589789, first push of this branch):**
- `deterministic-checks`: FAIL — "blocked by base_binding, scope".
  - BLOCKING scope: paths outside the approved scope changed [.ai/LESSONS_LEARNED.md]
  - BLOCKING base_binding: main advanced since approval and touched files this
    task depends on; the plan needs re-approval [.github/workflows/ci.yml]
  - `protected_paths` did **not** fire: `.ai/LESSONS_LEARNED.md` is not on the
    protected list, unlike `.ai/POLICY.yaml`. Possible gap in `POLICY.yaml`
    coverage of `.ai/`; not changed here.
- `trusted-suites`: FAIL — 4 failed (acceptance suite vs. unimplemented
  `clamp_score`, by design).
- `adversarial-replay`, `pipeline-unit-tests`: pass.

Overridden knowingly, not skipped: the verdicts above exist and were read
before merging.

## 2026-10-04 — Protect the .ai/ namespace in protected_paths (PR #6)

**What changed.** `protected_paths` in `.ai/POLICY.yaml` (and the replay
fixture's copy) now lists `.ai/**` instead of enumerated `.ai/` files. New test
`test_new_file_under_ai_is_caught_by_protected_paths_not_only_scope` loads the
real policy and was confirmed to fail against the old one. `validate_policy`
ok, 36 unit tests pass, replay 15/15 (`edit_acceptance` now additionally fires
`protected_paths`; still matches its expectation). Lessons entry added.

**Actual verdict, quoted (run 37201760516, first push):**
- `deterministic-checks`: FAIL — "blocked by base_binding, protected_paths, scope".
  - BLOCKING protected_paths [.ai/LESSONS_LEARNED.md, .ai/POLICY.yaml] —
    `LESSONS_LEARNED.md` is caught now; before this change only `scope` caught it.
  - BLOCKING scope [.ai/LESSONS_LEARNED.md, .ai/POLICY.yaml,
    pipeline/harness/fixture.py, pipeline/tests/test_checks.py]
  - BLOCKING base_binding: main advanced since approval and touched
    [.ai/DECISIONS.md, .ai/LESSONS_LEARNED.md, .ai/VERIFIED.md, .github/workflows/ci.yml]
- `trusted-suites`: FAIL — 4 failed (acceptance vs unimplemented `clamp_score`, by design).
- `adversarial-replay`, `pipeline-unit-tests`: pass.

**New finding.** `ci_check` loads `.ai/POLICY.yaml` from the checked-out head,
not from the base commit, so a PR's own policy edit is applied to itself (the
verdict above used the new `.ai/**` rule, proving it). Today `POLICY.yaml` is
itself protected and under CODEOWNERS, which contains this, but the policy
that grades a change should come from the base. Not fixed here; open.

Overridden knowingly: verdicts read before merging.
