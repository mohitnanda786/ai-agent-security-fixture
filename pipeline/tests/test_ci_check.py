"""ci_check must judge a branch by the base ref's rules, never its own.

Regression for: policy, approval and plan read from the checked-out head, so a
PR that edited POLICY.yaml was graded by its own edit.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from orchestrator import ci_check
from orchestrator.checks import plan_hash

TASK = "TASK-0001"
PLAN = "# PLAN\n\nAdd a function.\n"

STRICT_POLICY = """\
scope:
  allowed:
    - src/**
protected_paths:
  - .ai/**
trusted_test_paths:
  - tests/regression/**
budget:
  max_files_changed: 10
  max_diff_lines: 400
"""

# What a worker would write to get its change through.
WEAK_POLICY = """\
scope:
  allowed:
    - src/**
    - .ai/**
protected_paths: []
trusted_test_paths: []
budget:
  max_files_changed: 10
  max_diff_lines: 400
"""


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    for k, v in (("user.name", "t"), ("user.email", "t@t"), ("core.autocrlf", "false")):
        git(tmp_path, "config", k, v)
    write(tmp_path, "src/a.py", "x = 1\n")
    write(tmp_path, ".ai/POLICY.yaml", STRICT_POLICY)
    write(tmp_path, f".ai/tasks/{TASK}/PLAN.md", PLAN)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "scaffold")
    base = git(tmp_path, "rev-parse", "HEAD")
    approval = {
        "task_id": TASK,
        "plan_hash": plan_hash(PLAN.encode()),
        "base_commit": base,
        "approval": "APPROVED",
        "plan_reviewer_model": "manual/human",
    }
    write(tmp_path, f".ai/tasks/{TASK}/APPROVAL.json", json.dumps(approval) + "\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "approve")
    return tmp_path


def run(repo: Path, branch: str, capsys) -> tuple[int, str]:
    code = ci_check.main(["--repo", str(repo), "--base", "main", "--head", branch])
    return code, capsys.readouterr().out


def test_honest_change_inside_scope_passes(repo, capsys):
    git(repo, "checkout", "-qb", "honest")
    write(repo, "src/a.py", "x = 2\n")
    git(repo, "commit", "-qam", "change")
    code, out = run(repo, "honest", capsys)
    assert code == 0, out


def test_branch_that_weakens_policy_is_judged_by_the_base_policy(repo, capsys):
    git(repo, "checkout", "-qb", "weaken")
    write(repo, ".ai/POLICY.yaml", WEAK_POLICY)
    git(repo, "commit", "-qam", "weaken the policy")
    # The branch's own policy would allow this and protect nothing.
    code, out = run(repo, "weaken", capsys)
    assert code != 0, f"weakened policy let the branch through:\n{out}"
    assert "protected_paths" in out, out


def test_branch_that_forges_the_approval_is_judged_by_the_base_approval(repo, capsys):
    git(repo, "checkout", "-qb", "forge")
    write(repo, ".ai/POLICY.yaml", WEAK_POLICY)
    forged = {
        "task_id": TASK,
        "plan_hash": plan_hash(b"# PLAN\n\nDo whatever.\n"),
        "base_commit": "0" * 40,
        "approval": "APPROVED",
        "plan_reviewer_model": "attacker",
    }
    write(repo, f".ai/tasks/{TASK}/APPROVAL.json", json.dumps(forged) + "\n")
    write(repo, f".ai/tasks/{TASK}/PLAN.md", "# PLAN\n\nDo whatever.\n")
    git(repo, "commit", "-qam", "forge approval and plan")
    code, out = run(repo, "forge", capsys)
    assert code != 0, out
    assert "protected_paths" in out, out


def test_working_tree_is_never_read(repo, capsys):
    """Checked out on a weakened branch, evaluating a different branch."""
    git(repo, "checkout", "-qb", "honest")
    write(repo, "src/a.py", "x = 3\n")
    git(repo, "commit", "-qam", "change")
    git(repo, "checkout", "-qb", "weak-tree", "main")
    write(repo, ".ai/POLICY.yaml", WEAK_POLICY)  # uncommitted, on disk only
    code, out = run(repo, "honest", capsys)
    assert code == 0, out
    git(repo, "checkout", "-q", "--", ".ai/POLICY.yaml")


def test_missing_policy_at_base_fails_closed(repo, capsys):
    git(repo, "checkout", "-qb", "feature")
    write(repo, "src/a.py", "x = 9\n")
    git(repo, "commit", "-qam", "change")
    code = ci_check.main(["--repo", str(repo), "--base", "no-such-ref", "--head", "feature"])
    out = capsys.readouterr().out
    assert code != 0 and "BLOCKED" in out, out


# ---- drift: which commits between base_commit and the branch point re-block

def _advance_main_then_branch(repo: Path, rel: str, text: str) -> None:
    """Commit `rel` to main after the approval, then branch an honest change."""
    write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"main advances: {rel}")
    git(repo, "checkout", "-qb", "honest")
    write(repo, "src/a.py", "x = 5\n")
    git(repo, "commit", "-qam", "honest change")


def test_audit_trail_write_between_base_and_branch_does_not_block(repo, capsys):
    _advance_main_then_branch(repo, ".ai/DECISIONS.md", "# decisions\n")
    code, out = run(repo, "honest", capsys)
    assert code == 0, out
    assert "WARNING" in out and "base_binding" in out, out


@pytest.mark.parametrize(
    "rel,text",
    [
        (".ai/POLICY.yaml", STRICT_POLICY + "# touched\n"),
        ("tests/regression/test_x.py", "def test_x():\n    assert True\n"),
    ],
)
def test_policy_or_graded_test_change_between_base_and_branch_blocks(repo, capsys, rel, text):
    _advance_main_then_branch(repo, rel, text)
    code, out = run(repo, "honest", capsys)
    assert code != 0, out
    assert "BLOCKING base_binding" in out, out
