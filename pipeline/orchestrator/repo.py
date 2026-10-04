"""Policy loading and git facts.

The only module that shells out. Keeping it separate means the checks stay
testable without a repository, and means there is exactly one place to audit
for command injection.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .checks import Budget, Policy

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def changed_paths(repo: Path, base: str, head: str = "HEAD") -> list[str]:
    out = _git(repo, "diff", "--name-only", f"{base}...{head}")
    return [line for line in out.splitlines() if line.strip()]


def diff_line_count(repo: Path, base: str, head: str = "HEAD") -> int:
    out = _git(repo, "diff", "--numstat", f"{base}...{head}")
    total = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            added, removed = parts[0], parts[1]
            # "-" marks a binary file; count it as zero lines, flag by path.
            total += int(added) if added.isdigit() else 0
            total += int(removed) if removed.isdigit() else 0
    return total


def merge_base(repo: Path, branch: str, onto: str = "main") -> str:
    return _git(repo, "merge-base", onto, branch).strip()


def worktree_is_clean(repo: Path) -> bool:
    return not _git(repo, "status", "--porcelain").strip()


def load_policy(path: Path) -> Policy:
    """Read .ai/POLICY.yaml. Language-specific paths live here, not in code."""
    if yaml is None:  # pragma: no cover
        raise RuntimeError("PyYAML is required: pip install pyyaml")
    raw = yaml.safe_load(path.read_text()) or {}
    budget_raw = raw.get("budget") or {}
    known = {f for f in Budget.__dataclass_fields__}
    unknown = set(budget_raw) - known
    if unknown:
        raise ValueError(f"unknown budget keys in {path}: {sorted(unknown)}")
    return Policy(
        scope_allowed=tuple(raw.get("scope", {}).get("allowed", ())),
        scope_forbidden=tuple(raw.get("scope", {}).get("forbidden", ())),
        protected_paths=tuple(raw.get("protected_paths", ())),
        trusted_test_paths=tuple(raw.get("trusted_test_paths", ())),
        budget=Budget(**budget_raw),
        required_approval_fields=tuple(
            raw.get("required_approval_fields", Policy().required_approval_fields)
        ),
    )


def load_approval(path: Path) -> dict:
    return json.loads(path.read_text())
