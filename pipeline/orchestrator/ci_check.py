"""Run the deterministic checks against a pull request. Entry point for CI.

This is the half of the control that lives outside the orchestrator. The
orchestrator can be bypassed by anything with repo write; a required status
check cannot, as long as branch protection holds.

    python -m orchestrator.ci_check --repo . --base origin/main --head HEAD
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from orchestrator.checks import (
    PolicyConflict,
    validate_policy,
    verify_implementation,
)
from orchestrator.repo import (
    GitError,
    changed_paths,
    diff_line_count,
    list_tree,
    parse_policy,
    show,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--task", default=None, help="TASK-XXXX; inferred when omitted")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()

    # Everything that decides the verdict comes from the base ref. The head is
    # the thing being judged; it must never supply the rules, the approval or
    # the plan it is judged against.
    try:
        policy = parse_policy(
            show(repo, args.base, ".ai/POLICY.yaml").decode(),
            source=f"{args.base}:.ai/POLICY.yaml",
        )
        validate_policy(policy)
    except (GitError, PolicyConflict) as exc:
        print(f"BLOCKED  policy: {exc}")
        return 1

    changed = changed_paths(repo, args.base, args.head)
    if not changed:
        print("no changes against base; nothing to check")
        return 0

    task = args.task
    if task is None:
        try:
            names = list_tree(repo, args.base, ".ai/tasks")
        except GitError:
            names = []
        tasks = sorted(n for n in names if n.startswith("TASK-"))
        if not tasks:
            print("BLOCKED  no task directory under .ai/tasks")
            return 1
        task = tasks[-1]

    try:
        approval = json.loads(show(repo, args.base, f".ai/tasks/{task}/APPROVAL.json"))
        plan_bytes = show(repo, args.base, f".ai/tasks/{task}/PLAN.md")
    except (GitError, ValueError) as exc:
        print(f"BLOCKED  approval: {exc}")
        return 1
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
        plan_bytes=plan_bytes,
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
