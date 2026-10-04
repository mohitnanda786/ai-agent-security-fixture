"""Run the deterministic checks against a pull request. Entry point for CI.

This is the half of the control that lives outside the orchestrator. The
orchestrator can be bypassed by anything with repo write; a required status
check cannot, as long as branch protection holds.

    python -m orchestrator.ci_check --repo . --base origin/main --head HEAD
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from orchestrator.checks import (
    PolicyConflict,
    validate_policy,
    verify_implementation,
)
from orchestrator.repo import changed_paths, diff_line_count, load_approval, load_policy


def _show(repo: Path, ref: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{ref}:{path}"],
        capture_output=True,
        timeout=30,
    )
    return proc.stdout if proc.returncode == 0 else b""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--task", default=None, help="TASK-XXXX; inferred when omitted")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    policy = load_policy(repo / ".ai/POLICY.yaml")
    try:
        validate_policy(policy)
    except PolicyConflict as exc:
        print(f"BLOCKED  policy: {exc}")
        return 1

    changed = changed_paths(repo, args.base, args.head)
    if not changed:
        print("no changes against base; nothing to check")
        return 0

    task = args.task
    if task is None:
        tasks = sorted(p.name for p in (repo / ".ai/tasks").glob("TASK-*"))
        if not tasks:
            print("BLOCKED  no task directory under .ai/tasks")
            return 1
        task = tasks[-1]

    approval = load_approval(repo / f".ai/tasks/{task}/APPROVAL.json")
    merge_base = subprocess.run(
        ["git", "-C", str(repo), "merge-base", args.base, args.head],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()

    expected_base = approval.get("base_commit", "")
    is_ancestor = None
    drift: list[str] = []
    if expected_base:
        is_ancestor = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor",
             expected_base, merge_base],
            capture_output=True, timeout=30,
        ).returncode == 0
        if is_ancestor:
            # The approval record is committed on top of base_commit by
            # construction — it cannot contain its own hash — so its own
            # commit always appears as drift. That is not drift.
            own = f".ai/tasks/{task}/APPROVAL.json"
            drift = [
                path for path in changed_paths(repo, expected_base, merge_base)
                if path != own
            ]

    verdict = verify_implementation(
        changed=changed,
        policy=policy,
        approval=approval,
        plan_bytes=_show(repo, args.head, f".ai/tasks/{task}/PLAN.md"),
        actual_base=merge_base,
        diff_lines=diff_line_count(repo, args.base, args.head),
        approved_base_is_ancestor=is_ancestor,
        drift_paths=drift,
    )

    print(f"{task}: {len(changed)} files changed against {args.base}")
    for finding in verdict.findings:
        print(f"  {finding}")
    if verdict.ok:
        print("PASS  deterministic checks")
        return 0
    print(f"FAIL  blocked by {', '.join(sorted(verdict.checks_fired()))}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
