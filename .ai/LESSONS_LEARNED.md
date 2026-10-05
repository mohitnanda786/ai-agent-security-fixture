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

## 2026-10-04 — protected_paths enumerated members instead of the namespace

`protected_paths` listed individual `.ai/` files rather than guarding `.ai/**`.
Files added later (`VERIFIED.md`, `DECISIONS.md`, `LESSONS_LEARNED.md`) were
unguarded by that layer for five commits; only `scope` stopped them.
CODEOWNERS covered the whole directory and did not have the gap. Fixed by
`.ai/**` and a regression test that loads the real policy and asserts a new
file under `.ai/` is caught by `protected_paths` independent of scope. Found
because a verdict was read rather than assumed.

## 2026-10-04 — A file edit silently did not apply, and the report said it had

Data points, each caught by checking the artifact rather than trusting the
report:

1. **Owner-side.** The `ci_check` fix was believed to be on `main` and in the
   shipped zip. It was in neither: `parse_policy` and `show` appear in no
   archive, no loose file and no commit. Found by diffing `pipeline/
   orchestrator/` against both zips, not by reading the claim.
2. **Agent-side.** A scripted `str.replace` on `tests/test_ci_check.py` matched
   nothing and applied nothing; the script printed no error. The suite still
   passed (the new cases were simply absent). Caught because the diff stat
   listed two files, not three.
3. **Agent-side.** A `sed` substitution containing `\n` wrote a real newline
   into a Python string literal, which surfaced as a `SyntaxError`. This one
   failed loudly; it is listed because the cause is the same: the edit did not
   mean what the command said.

4. **Owner-side, container session.** A `str_replace` on `ci_check.py` reported
   success and did not apply. Caught by grepping for the new symbol: 5 hits in
   `checks.py`, 0 in `ci_check.py`.

Four data points recorded, **three distinct instances**. The owner has
confirmed that (1) and (4) are one event: a single failed container
`str_replace` on `ci_check.py`, which produced two symptoms. The first is the
broken file shipped in the original archive (the second archive contains no
`ci_check.py` at all); the second is a later false claim that
the fix was on `main`. Attribution as recorded: two data points the owner's,
two the agent's; the owner's two are the same event, so the distinct instances
are one owner-side and two agent-side.

Rule: after any edit, check the file (`git diff --stat`, a grep for the new
text), not the tool's exit status or the agent's summary.

## 2026-10-04 — The second symptom is its own lesson: a control cited from memory

The false claim that `ci_check` already read policy from the base ref was an
agent citing a control as present from its memory of having written it, while
evidence to the contrary was already in the session. Here the evidence was
`ci_check.py` itself, which loaded `.ai/POLICY.yaml` from disk (line 43), and
the CI log showing a PR graded by its own policy edit. The mitigation is the
same as for the silent edit — check the artifact, not the report — but this
failure is worse in one respect: it was not a single bad tool call but a
belief, and beliefs are not caught by a diff stat. The record supports this much: the broken
`ci_check.py` shipped in the original archive and remained on `main` until
PR #8 corrected it.

This correction is itself an instance of the entry's subject: an unsourced
quantity ("weeks and three merges") asserted in a file about unsourced
assertions, caught by the agent asking where it came from. The same pass found
a second one the agent had written without checking: "shipped in both
archives", repeated from the owner's wording into this file; the second archive
has no `ci_check.py`.

## 2026-10-04 — Positive: an approval was left for the owner to merge

The agent regenerated `APPROVAL.json` for TASK-0042 (PR #11) and did not merge
it, on the grounds that an approval is the owner's sign-off and `regenerate`
was not `merge`. An agent regenerating and merging its own approval record is
the pipeline's central failure mode. The control that held here was the
agent's own judgement, not a technical one: the owner bypass would have let it
through. Worth hardening, since it should not depend on judgement.

## 2026-10-05 — A flag recommended from one line of help text

`--print-timeout` was recommended as bounding the worker hang defect without a
PTY wrapper. Per the owner's account, that came from one line of help text
(`Optional time limit for print mode; 0 waits until the turn completes`),
without testing what happens on expiry. Tested: on expiry agy prints
`print timeout ... returning partial output` to stderr and exits **0** with
`status: "SUCCESS"`, an empty response and zero usage. A stalled worker is
indistinguishable from a completed one by exit code or status. Downstream, the
deterministic checks pass trivially on the resulting empty diff (`ci_check`
exits 0, "no changes against base; nothing to check", confirmed). The
backstop is the acceptance suite, which fails on an empty diff while the task
is unimplemented; the checks that do not look at the work do not catch it.

Second instance in the same message: `--add-dir` was read as a restriction
("workspace scoping, a layer under scope globs"). Help says it adds a directory
to the workspace; it widens access.

Both were caught by running the binary and reading what it said, which the
help text alone could not provide. The agent's own first probe misread the
timeout behaviour twice before the output settled it; the same rule applies to
the agent: test the behaviour, not the description.
