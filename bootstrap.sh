#!/usr/bin/env bash
# One-time setup. Creates the two commits the approval model needs.
#
# APPROVAL.json records the commit its plan was reviewed against, so it cannot
# contain its own hash. The scaffold is committed first, its SHA becomes
# base_commit, and the approval is committed on top. A task branch then
# branches from base, not from latest main.
set -euo pipefail

TASK=TASK-0042

command -v python3 >/dev/null || { echo "python3 required"; exit 1; }
: "${WORKER_MODEL:?WORKER_MODEL is required, e.g. WORKER_MODEL=gemini-3.8-flash-high (the approval records what will produce the implementation)}"
export WORKER_MODEL
[ -d .git ] || git init -q
git branch -M main 2>/dev/null || true

rm -f ".ai/tasks/$TASK/APPROVAL.json"
git add -A
git commit -qm "scaffold: pipeline, fixture layout, policy" || true
BASE=$(git rev-parse HEAD)

python3 - "$TASK" "$BASE" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
task, base = sys.argv[1], sys.argv[2]
plan = Path(f".ai/tasks/{task}/PLAN.md").read_bytes()
approval = {
    "task_id": task,
    "plan_hash": "sha256:" + hashlib.sha256(plan).hexdigest(),
    "base_commit": base,
    "approval": "APPROVED",
    "plan_reviewer_model": "manual/human",
    "worker_model": os.environ["WORKER_MODEL"],
    "approved_at": "2026-10-04",
}
Path(f".ai/tasks/{task}/APPROVAL.json").write_text(json.dumps(approval, indent=2) + "\n")
print(f"approval bound to {base[:12]}")
PY

git add -A
git commit -qm "approve $TASK"
echo
echo "Done. Next:"
echo "  git remote add origin https://github.com/mohitnanda786/ai-agent-security-fixture.git"
echo "  git push -u origin main"
