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

## 2026-10-04 — ci_check reads everything from the base ref (PR #8)

**What changed.** `ci_check` loads policy, `APPROVAL.json`, `PLAN.md` and the
task list from `args.base` only (`parse_policy(show(...))`, `list_tree` =
`git ls-tree --name-only <base>:.ai/tasks`); nothing from disk, nothing from
`args.head` except to compute the diff. Local `_show` deleted. `repo.py` gains
`show`, `list_tree`, `parse_policy` (`load_policy` now wraps it). A missing
file at base fails closed (`BLOCKED`). The drift exclusion for the task's own
`APPROVAL.json` and the `approved_base_is_ancestor` / `drift_paths` arguments
were present and are unchanged. New `tests/test_ci_check.py` runs `ci_check`
on real git repos: a branch that weakens `POLICY.yaml` (and one that also
forges `APPROVAL.json`/`PLAN.md`) is still judged by the base policy; an
uncommitted weak policy on disk is ignored. Run against the old `ci_check`,
the weaken and forge tests fail and the missing-base test crashes; with the fix
41 unit tests pass and replay is 15/15.

**Item 5 — what did not survive.** Nothing was lost. `parse_policy` and `show`
never existed in `repo.py` on main, in `ai-agent-security-fixture.zip`, in
`pipeline-windows-fixes.zip`, or in the loose files under `E:\Multi AI`:
there was no fixed `ci_check` to lose, so it was written here. Diffs (CRLF
ignored): `ci_check.py`, `repo.py`, `checks.py` identical to the original zip;
`gate.py` and `mutate.py` differ only by the Windows patches (tarfile extract,
`force_rmtree`), which match `pipeline-windows-fixes.zip` exactly; `fixture.py`
differs from that zip only by the intended `.ai/**` change (PR #6). The loose
`checks.py` is an older copy (no drift-aware `check_base_binding`).
Unrelated: `mutate.force_rmtree` is defined but `replay.py` has its own
inline copy; not used from `mutate`.

**Trade-off.** With `PLAN.md` read from base, `plan_binding` no longer sees a
head-side plan swap; `protected_paths` (`.ai/**`) and `gate.py`'s
"PLAN.md differs on the branch" check cover it.

**Actual verdict, quoted (run 37202233989):**
- `deterministic-checks`: FAIL — "blocked by base_binding, scope".
  - BLOCKING scope [pipeline/orchestrator/ci_check.py, pipeline/orchestrator/repo.py,
    pipeline/tests/test_ci_check.py]
  - BLOCKING base_binding: main advanced since approval and touched
    [.ai/DECISIONS.md, .ai/LESSONS_LEARNED.md, .ai/POLICY.yaml,
    .ai/VERIFIED.md, .github/workflows/ci.yml]
  - `protected_paths` did **not** fire: `pipeline/orchestrator/` is under
    CODEOWNERS but not in `protected_paths`, and `pipeline/tests/` is in
    neither. Same class as the `.ai/` gap; open.
- `trusted-suites`: FAIL — 4 failed (acceptance vs unimplemented `clamp_score`, by design).
- `adversarial-replay`, `pipeline-unit-tests`: pass.

Overridden knowingly: verdict read before merging.

## 2026-10-04 — Protect pipeline code and tests; attack-surface audit (PR #9)

**What changed.** `protected_paths` += `pipeline/orchestrator/**`,
`pipeline/harness/**`; `trusted_test_paths` += `pipeline/tests/**` (in
`.ai/POLICY.yaml` and the replay fixture's copy). `CODEOWNERS` gains
`/pipeline/harness/` and `/pipeline/tests/` (orchestrator was already there) so
both layers match. `validate_policy` ok, 41 unit tests pass, replay 15/15.

**Audit — tracked paths outside protected_paths, trusted_test_paths and the
allowed scope (`src/scoring.py`, `tests/worker/**`): 9 of 38.** This is the
remaining attack surface of the policy layer. None is writable by a worker
under the current task, because `scope` is default-deny; each becomes
reachable the moment a task's allowed scope is widened to include it.

| Path | CODEOWNERS | Why it matters |
| --- | --- | --- |
| `.github/CODEOWNERS` | yes | Defines the forge-side layer; policy layer sees it only via `scope` (confirmed in this PR's verdict) |
| `.gitattributes` | no | Controls line endings, so it can change the bytes `plan_hash` is computed over |
| `RUNBOOK.md` | no | Instructions executed by agents: a prompt-injection target |
| `bootstrap.sh`, `bootstrap.py` | no | Run by a human with owner credentials; create the approval commit |
| `pipeline/probe_agy.sh` | no | Shell script run by a human after signing in to `agy` |
| `src/__init__.py` | no | Imported by every test run; a worker allowed `src/**` could execute code at import |
| `.gitignore` | no | Can hide files from `git add -A` in bootstrap |
| `README.md` | no | Low risk; documentation only |

Not changed here: these are reported, not fixed, as requested. Note that
CODEOWNERS covers only 1 of the 9.

**Actual verdict, quoted (run 37202423636, first push; the PR was merged on
run 37202471861, second push, which had the same three blocks with
`.ai/DECISIONS.md` added to `protected_paths` and `scope` by the entry
itself):**
- `deterministic-checks`: FAIL — "blocked by base_binding, protected_paths, scope".
  - BLOCKING protected_paths [.ai/POLICY.yaml]
  - BLOCKING scope [.ai/POLICY.yaml, .github/CODEOWNERS, pipeline/harness/fixture.py]
  - BLOCKING base_binding: main advanced since approval and touched
    [.ai/DECISIONS.md, .ai/LESSONS_LEARNED.md, .ai/POLICY.yaml,
    .ai/VERIFIED.md, .github/workflows/ci.yml]
- `trusted-suites`: FAIL — 4 failed (acceptance vs unimplemented `clamp_score`, by design).
- `adversarial-replay`, `pipeline-unit-tests`: pass.
- Under the base policy (not the new one) `pipeline/harness/fixture.py` was
  caught only by `scope` — the old gap this PR closes.

Overridden knowingly: verdict read before merging.

## 2026-10-04 — Close coverage gaps; coverage test (PR #10)

**What changed.** `protected_paths` += `.github/**`, `bootstrap.py`,
`bootstrap.sh`, `.gitattributes` (`.github/workflows/**` stays in
`trusted_test_paths`; overlap is accepted by `validate_policy`). CODEOWNERS
mirrors the three new files (`.github/` was already covered). `scope_allowed`
enumerates `src/scoring.py`, `src/__init__.py`, `tests/worker/**`. New
`pipeline/tests/test_coverage.py`: governed / scope-only / uncovered reported
as separate categories; fails on an undeclared uncovered file, an undeclared
scope-only file, or a stale allowlist entry. Seeded `UNCOVERED`: `.gitignore`,
`README.md`, `RUNBOOK.md`, `pipeline/probe_agy.sh`. 44 unit tests pass, replay
15/15; confirmed the test fails on a new `src/extra.py`.

**Why scope is not `src/**`.** A first attempt widened scope to `src/**`; the
replay dropped to 14/15 — `out_of_scope` (edits `src/auth/session.py`) became
mergeable. Scope comes from the approved plan; TASK-0042 does not touch
`src/auth/`. The replay table was not changed. Scope-only files are
uncovered once the task closes; the test now says so.

**Actual verdict, quoted (run 37203027096, first push):**
- `deterministic-checks`: FAIL — "blocked by base_binding, protected_paths, scope, test_integrity".
  - BLOCKING protected_paths [.ai/DECISIONS.md, .ai/POLICY.yaml, pipeline/harness/fixture.py]
  - BLOCKING test_integrity [pipeline/tests/test_coverage.py]
  - BLOCKING scope [.ai/DECISIONS.md, .ai/POLICY.yaml, .github/CODEOWNERS,
    pipeline/harness/fixture.py, pipeline/tests/test_coverage.py]
  - BLOCKING base_binding: main advanced since approval and touched 13 files
    including .ai/POLICY.yaml, .github/workflows/ci.yml,
    pipeline/orchestrator/{ci_check,gate,mutate,repo}.py
- `trusted-suites`: FAIL — 4 failed (acceptance vs unimplemented `clamp_score`, by design).
- `adversarial-replay`, `pipeline-unit-tests`: pass.

The run merged on is the one after this entry's push; its verdict is posted as
a comment on PR #10 (an entry cannot quote the run its own commit triggers).

## 2026-10-04 — Drift is not protected_paths (PR #12)

**What changed.** In `check_base_binding` the drift set (`guarded`) was
`scope_allowed + protected_paths + trusted_test_paths`; it is now
`scope_allowed + trusted_test_paths + (".ai/POLICY.yaml",)`
(`DRIFT_POLICY_FILES`). `protected_paths` is unchanged: those files stay
unwritable by a worker.

**Why.** `protected_paths` answers "may the worker write this"; drift answers
"does a change here invalidate the plan". One list for both meant every
audit-trail write invalidated the approval, including the write that records
the re-approval (observed: six consecutive PRs blocked, and the re-approval PR
could not leave a record without re-breaking itself). `POLICY.yaml` stays in
the drift set because it defines scope. `DECISIONS.md`, `LESSONS_LEARNED.md`
and `VERIFIED.md` leave it: they are records, not inputs to correctness.

**PLAN.md and APPROVAL.json also leave the drift set.** `plan_binding`
already compares the plan hash on every run, so a changed plan is caught
there (and by `protected_paths`). The approval commit lands after
`base_commit` by construction, so it would always drift against itself.

**Is the `own` APPROVAL.json exclusion in `ci_check` now dead code?** Yes,
under the current policy. `.ai/tasks/*/APPROVAL.json` matches none of
`scope_allowed`, `trusted_test_paths` or `POLICY.yaml`, so it can never be
drift. Checked: with the exclusion removed, all 53 tests still pass and a
probe branch against current main still gets only a `base_binding` warning —
no test covers the exclusion. It is not removed here (not asked). It would
become live again if a future policy put approval files in scope or
`trusted_test_paths`; either delete it or add a test that needs it.

**Test coverage.** The 53 tests now include `ci_check` running against real
git history (`tests/test_ci_check.py`: base-ref policy, forged approval,
drift between `base_commit` and the branch point). Unit tests on `gate.py`
passed throughout while `ci_check.py` was broken on main. The gap was
integration coverage, not test count. New drift tests fail against the old
`checks.py` (4 failures); the must-block cases pass before and after.

**This PR is its own test.** It is judged against the fresh approval from
#11 (`base_commit` d04ca23) and carries this `DECISIONS.md` write.
`base_binding` should warn, not block. The run's full verdict is posted as a
comment on PR #12 — an entry cannot quote the run its own commit triggers.

## 2026-10-04 — Drift is a named constant, narrower than trusted tests (PR #14)

**What changed.** `check_base_binding` now uses `policy.scope_allowed +
DRIFT_PATHS`, where `DRIFT_PATHS` is a constant in `checks.py`:
`.ai/tasks/*/acceptance/**`, `tests/regression/**`, `.ai/POLICY.yaml`.
Previously `scope_allowed + trusted_test_paths + POLICY.yaml` (PR #12), and
before that it also borrowed `protected_paths`.

**Why.** `trusted_test_paths` answers "may the worker write this"; drift
answers "does a change here invalidate the plan". Orchestrator tests under
`pipeline/tests/**` are trusted but are not an input to any task's
correctness, so every orchestrator test change was forcing a re-approval
(observed on PR #13 after #12 changed two test files). Same conflation as the
`protected_paths` case, one layer down. Drift had now been wrong twice by
borrowing another list, so it is stated outright and tested directly
(`test_drift_set_is_stated_not_borrowed`).

**Tests (60 pass, replay 15/15).** Unit and `ci_check`-on-real-git: commits to
`pipeline/tests/**`, `pipeline/orchestrator/**` and `.ai/DECISIONS.md` between
base and branch point warn; commits to `tests/regression/**`,
`.ai/tasks/*/acceptance/**` and `.ai/POLICY.yaml` block. Against the previous
`checks.py` three of these fail (unit pipeline/tests warn, constant import,
acceptance integration block).

**Known limitation.** `scope_allowed` stays policy-derived (it differs per
task), but `tests/regression/**` is now hard-coded in `DRIFT_PATHS` while the
policy still configures regression paths in `trusted_test_paths`. If the
policy renames the regression suite, drift will not follow until the constant
is edited; no test ties the two together.

**Next.** The clean data point is PR #13 (a DECISIONS.md-only write) rebased
onto this once merged. This PR's own run cannot test that; its verdict is in a
comment on PR #14.

## 2026-10-04 — Follow-up write after the drift fix (PR #13)

A small `DECISIONS.md`-only write on its own branch, made after #12 merged,
to observe how `base_binding` treats a later audit-trail write. Result is
posted as a comment on the PR.
