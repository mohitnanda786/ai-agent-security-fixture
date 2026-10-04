"""The merge gate. Runs the controls in cost order and stops at the first wall.

Order matters. The deterministic checks are free and catch most attacks, so
they run first. The trusted suites need a clean checkout. The mutation gate is
the most expensive and runs last, on work that has already passed everything
else.

Nothing here consults a model. A model review sits after this gate, not
inside it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator import mutate
from orchestrator.checks import (
    BLOCKING,
    WARNING,
    Finding,
    Policy,
    Verdict,
    verify_implementation,
)
from orchestrator.repo import changed_paths, diff_line_count

MUTATION_THRESHOLD = 0.80


@dataclass(frozen=True)
class GateResult:
    stage: str
    verdict: Verdict
    mutation: mutate.MutationResult | None = None

    @property
    def ok(self) -> bool:
        return self.verdict.ok

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.verdict.findings if f.severity == WARNING)

    def summary(self) -> str:
        if self.ok:
            extra = f" (mutation {self.mutation.score:.0%})" if self.mutation else ""
            warn = f" +{len(self.warnings)} warning" if self.warnings else ""
            return f"MERGEABLE at {self.stage}{extra}{warn}"
        controls = ", ".join(sorted(self.verdict.checks_fired()))
        return f"BLOCKED at {self.stage} by {controls}"


def _export(repo: Path, commit: str, dest: Path) -> None:
    """A clean checkout of exactly one commit. No worker working tree."""
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", commit],
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True, timeout=60)


def _restore_trusted(repo: Path, base: str, dest: Path, trusted: list[str]) -> None:
    """Overwrite the graded files with their version from the approved base.

    This is the read-only mount, done with git rather than a mount. Even if a
    worker modified a graded file and the diff check somehow missed it, the
    version that runs is the approved one.
    """
    for rel in trusted:
        proc = subprocess.run(
            ["git", "-C", str(repo), "show", f"{base}:{rel}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(proc.stdout)


def _list_tree(repo: Path, commit: str, prefix: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", commit, prefix],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def run(
    repo: Path,
    *,
    head: str,
    policy: Policy,
    approval: dict,
    task: str,
    mutation_targets: list[str],
    failure_history: tuple[str, ...] = (),
) -> GateResult:
    base = approval["base_commit"]
    changed = changed_paths(repo, base, head)

    # --- stage 1: deterministic, free -------------------------------------
    plan_bytes = subprocess.run(
        ["git", "-C", str(repo), "show", f"{base}:.ai/tasks/{task}/PLAN.md"],
        capture_output=True, check=True, timeout=30,
    ).stdout
    merge_base = subprocess.run(
        ["git", "-C", str(repo), "merge-base", base, head],
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout.strip()

    verdict = verify_implementation(
        changed=changed,
        policy=policy,
        approval=approval,
        plan_bytes=plan_bytes,
        actual_base=merge_base,
        diff_lines=diff_line_count(repo, base, head),
        failure_history=failure_history,
    )
    # The plan on the branch, not just on main, must still match the approval.
    branch_plan = subprocess.run(
        ["git", "-C", str(repo), "show", f"{head}:.ai/tasks/{task}/PLAN.md"],
        capture_output=True, timeout=30,
    )
    if branch_plan.returncode == 0 and branch_plan.stdout != plan_bytes:
        verdict = Verdict(
            verdict.findings
            + (Finding("plan_binding", BLOCKING, "PLAN.md differs on the branch"),)
        )
    if not verdict.ok:
        return GateResult("deterministic checks", verdict)

    # --- stage 2 and 3: clean checkout, trusted suites, mutation ----------
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "clean"
        _export(repo, head, work)
        trusted = _list_tree(repo, base, "tests/regression") + _list_tree(
            repo, base, f".ai/tasks/{task}/acceptance"
        )
        _restore_trusted(repo, base, work, trusted)
        suites = ["tests/regression", f".ai/tasks/{task}/acceptance"]

        if not mutate._run_suites(work, suites):
            return GateResult(
                "trusted suites",
                Verdict((Finding("trusted_tests", BLOCKING, "graded suites failed"),)),
            )

        result = mutate.evaluate(work, mutation_targets, suites)
        findings = _adequacy_findings(result)

    return GateResult("mutation gate", Verdict(findings), result)


def _adequacy_findings(result: mutate.MutationResult) -> tuple[Finding, ...]:
    """Mutation is advisory here, and the measurements say why.

    On the fixture, an entirely correct implementation scores 33%, and every
    survivor is an equivalent mutant: `<` versus `<=` at a boundary, or a
    boundary constant off by one, both indistinguishable under integer-only
    test inputs. A threshold gate would therefore block correct work.

    More importantly, this control does not point at the worker. The suites it
    mutates are the regression and acceptance suites, neither of which the
    worker can write. A low score is evidence that the ACCEPTANCE CRITERIA are
    thin — a message for whoever approved the plan, not grounds to reject an
    implementation that satisfies them.

    The one case that is blocking is degenerate: mutants exist and none die.
    That proves the trusted suites do not exercise the code at all.
    """
    if not result.total:
        return ()
    detail = "; ".join(f"{m.path}:{m.line} {m.description}" for m in result.survivors[:4])
    if result.killed == 0:
        return (
            Finding(
                "test_adequacy",
                BLOCKING,
                f"no mutant of the implementation was detected by the trusted "
                f"suites ({result.total} tried); they do not exercise this code",
            ),
        )
    if result.score < MUTATION_THRESHOLD:
        return (
            Finding(
                "test_adequacy",
                WARNING,
                f"mutation score {result.score:.0%}; acceptance criteria may be "
                f"thin at: {detail}",
            ),
        )
    return ()
