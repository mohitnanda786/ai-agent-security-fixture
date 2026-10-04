"""Every tracked file must be governed by some layer, or be explicitly accepted.

Three categories, reported separately:

  governed   protected_paths or trusted_test_paths. Permanent.
  scope-only covered by nothing but the current task's allowed scope. Not
             governance: it becomes uncovered the moment the task closes, so it
             is declared in SCOPE_ONLY and must be re-decided then.
  uncovered  covered by nothing. Fails unless listed in UNCOVERED.

Enumerated lists go stale as files are added; this test makes staleness a
failure. Run against the real policy and the real tracked files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from orchestrator.checks import path_matches
from orchestrator.repo import load_policy

ROOT = Path(__file__).resolve().parents[2]

# Tracked files deliberately outside every layer. One line of reason each.
# Adding to this list is a privileged change: it widens the attack surface.
UNCOVERED = {
    ".gitignore": "ignore rules only; no executable or graded effect",
    "README.md": "documentation only",
    "RUNBOOK.md": "operator instructions; agents read it, so review changes by hand",
    "pipeline/probe_agy.sh": "operator probe script, run by a human after sign-in",
}

# Covered only by the allowed scope of the current task (TASK-0042). These are
# not governed once the task closes; re-decide them then.
SCOPE_ONLY = {
    "src/scoring.py": "TASK-0042 implements clamp_score here",
    "src/__init__.py": "TASK-0042 package marker; imported by every test run",
    "tests/worker/.gitkeep": "worker-writable test directory",
    "tests/worker/__init__.py": "worker-writable test directory",
}


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def _categorise(policy) -> dict[str, list[str]]:
    cats: dict[str, list[str]] = {"governed": [], "scope_only": [], "uncovered": []}
    for f in _tracked():
        if path_matches(f, policy.protected_paths) or path_matches(f, policy.trusted_test_paths):
            cats["governed"].append(f)
        elif path_matches(f, policy.scope_allowed):
            cats["scope_only"].append(f)
        else:
            cats["uncovered"].append(f)
    return cats


def test_no_tracked_file_is_uncovered_unless_declared():
    cats = _categorise(load_policy(ROOT / ".ai/POLICY.yaml"))
    orphans = [f for f in cats["uncovered"] if f not in UNCOVERED]
    assert not orphans, (
        "tracked files covered by none of protected_paths, trusted_test_paths or "
        "allowed scope (cover them in .ai/POLICY.yaml + CODEOWNERS, or add to "
        f"UNCOVERED with a reason): {orphans}"
    )


def test_scope_only_files_are_declared_not_silently_counted_as_covered():
    cats = _categorise(load_policy(ROOT / ".ai/POLICY.yaml"))
    undeclared = [f for f in cats["scope_only"] if f not in SCOPE_ONLY]
    assert not undeclared, (
        "files covered only by the current task's scope; declare them in "
        f"SCOPE_ONLY or govern them in protected_paths/trusted_test_paths: {undeclared}"
    )


def test_allowlists_are_not_stale():
    cats = _categorise(load_policy(ROOT / ".ai/POLICY.yaml"))
    gone_u = [f for f in UNCOVERED if f not in cats["uncovered"]]
    gone_s = [f for f in SCOPE_ONLY if f not in cats["scope_only"]]
    assert not gone_u, f"UNCOVERED entries that are gone or now covered: {gone_u}"
    assert not gone_s, f"SCOPE_ONLY entries that are gone or now governed/uncovered: {gone_s}"
    assert all(UNCOVERED.values()) and all(SCOPE_ONLY.values()), "every entry needs a reason"
