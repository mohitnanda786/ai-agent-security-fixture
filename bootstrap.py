#!/usr/bin/env python3
"""One-time setup. Runs anywhere Python does — no bash, no heredocs.

Creates the two commits the approval model needs. APPROVAL.json records the
commit its plan was reviewed against, so it cannot contain its own hash: the
scaffold is committed first, its SHA becomes base_commit, and the approval is
committed on top.

The plan hash is taken from the committed blob, not from the file on disk.
On a machine with core.autocrlf=true the working tree holds CRLF while git
stores LF, so hashing the file would bind the approval to bytes that CI never
sees — and plan_binding would reject every honest branch for a line ending.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

TASK = "TASK-0042"


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc.stdout


def git_bytes(*args: str) -> bytes:
    proc = subprocess.run(["git", *args], capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{proc.stderr.decode().strip()}")
    return proc.stdout


def main() -> int:
    worker_model = os.environ.get("WORKER_MODEL", "").strip()
    if not worker_model:
        raise SystemExit(
            "WORKER_MODEL is required (e.g. WORKER_MODEL=gemini-3.8-flash-high): "
            "the approval records what will produce the implementation"
        )
    if not Path(".ai/tasks", TASK, "PLAN.md").exists():
        raise SystemExit("run this from the repository root")

    if not Path(".git").exists():
        git("init", "-q", "-b", "main")
    subprocess.run(["git", "branch", "-M", "main"], capture_output=True, timeout=30)

    approval_path = Path(".ai/tasks", TASK, "APPROVAL.json")
    approval_path.unlink(missing_ok=True)

    git("add", "-A")
    subprocess.run(
        ["git", "commit", "-qm", "scaffold: pipeline, fixture layout, policy"],
        capture_output=True, timeout=60,
    )
    base = git("rev-parse", "HEAD").strip()

    plan = git_bytes("show", f"{base}:.ai/tasks/{TASK}/PLAN.md")
    approval = {
        "task_id": TASK,
        "plan_hash": "sha256:" + hashlib.sha256(plan).hexdigest(),
        "base_commit": base,
        "approval": "APPROVED",
        "plan_reviewer_model": "manual/human",
        "worker_model": worker_model,
        "approved_at": "2026-10-04",
    }
    approval_path.write_bytes(
        (json.dumps(approval, indent=2) + "\n").encode("utf-8")
    )

    git("add", "-A")
    git("commit", "-qm", f"approve {TASK}")

    print(f"scaffold   {base[:12]}")
    print(f"approval   {git('rev-parse', 'HEAD').strip()[:12]}")
    print(f"plan hash  {approval['plan_hash'][:26]}…")
    print()
    print("Next:")
    print("  git remote add origin "
          "https://github.com/mohitnanda786/ai-agent-security-fixture.git")
    print("  git push -u origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
