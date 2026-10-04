# RUNBOOK — bring the pipeline online

For an agent to execute end to end. Starts from a machine with nothing set up.

Repository: `https://github.com/mohitnanda786/ai-agent-security-fixture`
Owner handle: `mohitnanda786`

## Rules for whoever executes this

1. **Never weaken a check to make a step pass.** If a check blocks you, that
   is the result. Report it and stop. Loosening `.ai/POLICY.yaml`, deleting a
   test, relaxing a ruleset or skipping a CI job to get green is the exact
   failure this project exists to detect.
2. **Do not use `--dangerously-skip-permissions`** or any equivalent.
3. **Steps marked `NEEDS THE HUMAN` cannot be done by an agent.** Stop, say
   precisely what you need, and wait.
4. **Verify by trying to break it, not by reading the settings page.** Several
   failures here are silent: GitHub accepts the configuration and enforces
   nothing.
5. **Record results in `.ai/VERIFIED.md` with today's date**, including
   failures. An honest negative result is the point.
6. After step 5, `main` is protected and you cannot push to it directly.
   Everything after that goes through a pull request.

---

## Step 0 — Preconditions

**Goal:** know what is on the machine before assuming anything.

```bash
git --version
python3 --version        # 3.10 or newer
gh --version             # GitHub CLI
gh auth status           # must show a token with the 'repo' scope
pwd && ls                # confirm you are in the unpacked repo directory
```

**Success:** all four tools report a version, and `gh auth status` shows a
logged-in account with `repo` scope.

**If `gh` is missing:** install it (`brew install gh`, `sudo apt install gh`,
or `winget install GitHub.cli`), then continue.

**If `gh auth status` fails — `NEEDS THE HUMAN`.** `gh auth login` is a
browser device-code flow. Stop and ask them to run it, choosing HTTPS and
granting the `repo` scope. Do not attempt to enter credentials yourself.

---

## Step 1 — Verify the code before pushing it

**Goal:** never push something you have not run.

```bash
pip install pytest pyyaml
cd pipeline && python -m pytest tests -q && cd ..
cd pipeline && python -m harness.replay && cd ..
```

**Success:** unit tests all pass, and the replay reports `15/15 as expected`.

**On failure:** stop. Report which scenario misbehaved and its output. Do not
adjust the expectations table in `harness/replay.py` to make it match — the
table is the specification, the code is what is wrong.

---

## Step 2 — Bootstrap the git history

**Goal:** create the two commits the approval model requires. `APPROVAL.json`
records the commit its plan was reviewed against, so it cannot contain its own
hash; the scaffold is committed first and the approval on top of it.

```bash
./bootstrap.sh
git log --oneline
```

**Success:** two commits, and `.ai/tasks/TASK-0042/APPROVAL.json` exists with
a `base_commit` matching the first commit's SHA.

---

## Step 3 — Push

```bash
git remote add origin https://github.com/mohitnanda786/ai-agent-security-fixture.git
git push -u origin main
```

**Success:** `main` exists on GitHub with both commits.

**If the push is rejected because the remote has commits** (a README created
at repo setup): `git pull --rebase origin main` then push again. Do not force
push.

---

## Step 4 — Confirm CI runs

**Goal:** status checks must have run at least once before they can be
required. A check that has never run does not appear in the ruleset picker.

```bash
gh run list --limit 5
gh run watch
```

**Expected:** four jobs — `deterministic-checks`, `trusted-suites`,
`pipeline-unit-tests`, `adversarial-replay`.

On a push to `main`, `trusted-suites` runs only the regression suite; the
acceptance suite runs on pull requests, because `clamp_score` is deliberately
unimplemented on `main` and the acceptance suite is meant to fail until a task
implements it.

**On failure:** read the log and fix the cause. If the cause is a real check
firing correctly, that is not a failure to fix — report it.

---

## Step 5 — Protect the branch

**Goal:** enforcement that holds even if the orchestrator is bypassed.

Repository must be **public** — on GitHub Free, branch protection and rulesets
are unavailable on private repositories (`403 Upgrade to GitHub Pro`), and
CODEOWNERS parses but requests nothing. Both fail silently.

```bash
gh api repos/mohitnanda786/ai-agent-security-fixture --jq .visibility
```

If that prints anything but `public`, **stop and ask the human** before
changing visibility.

Then create the ruleset:

```bash
gh api -X POST repos/mohitnanda786/ai-agent-security-fixture/rulesets \
  --input - <<'JSON'
{
  "name": "protect-main",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "require_code_owner_review": true,
        "dismiss_stale_reviews_on_push": true,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false
      } },
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "deterministic-checks" },
          { "context": "trusted-suites" }
        ]
      } }
  ]
}
JSON
```

This payload shape is unverified. If the API rejects it, read the error, check
`gh api --help` and the current REST documentation for repository rulesets,
and correct it. Do not fall back to a weaker rule set to get a success.

**Success:** `gh api repos/mohitnanda786/ai-agent-security-fixture/rulesets`
lists the ruleset with `"enforcement": "active"` — not `"evaluate"`, which
logs violations and blocks nothing.

---

## Step 6 — Prove it enforces

**Goal:** the settings page is not evidence.

```bash
cd /tmp && git clone https://github.com/mohitnanda786/ai-agent-security-fixture.git check
cd check && echo "# probe" >> README.md
git commit -aqm "probe: direct push to main"
git push origin main          # MUST be rejected
```

**Success:** the push is refused.

**If it succeeds:** protection is not active. Delete the probe commit from
`main`, report this, and stop. Everything downstream depends on this step.

Then test the protected path:

```bash
git reset --hard origin/main
git checkout -b probe/protected-path
python3 - <<'PY'
from pathlib import Path
p = Path(".ai/POLICY.yaml")
p.write_text(p.read_text().replace("  - tests/regression/**\n", ""))
PY
git commit -aqm "probe: weaken the policy"
git push -u origin probe/protected-path
gh pr create --title "probe: weaken the policy" --body "Verification probe. Expected to be blocked."
gh pr checks --watch
```

**Success, all three:**

- `deterministic-checks` fails, reporting `protected_paths` and `scope`
- the PR requests review from a code owner
- the PR cannot merge

Note: as repository owner you can approve your own code-owner rule, so on a
solo repo that rule is a speed bump for you and a wall for a worker. That is
the correct reading — the worker will not have admin.

Then close it and clean up:

```bash
gh pr close --delete-branch
cd /tmp && rm -rf check
```

---

## Step 7 — Probe the Antigravity CLI

**Goal:** close register rows 1 and 2 with a local result instead of a
secondary source.

**`NEEDS THE HUMAN` first:** `agy` authenticates through an interactive OAuth
flow and the system keyring. Ask them to install it and sign in once:

```bash
curl -fsSL https://antigravity.google/cli/install.sh | bash
agy                 # sign in, then exit
```

That sign-in is itself a finding. If the probe only works after it, a
credential-free worker container is not possible with this CLI.

Then run the probe:

```bash
cd <repo>/pipeline && chmod +x probe_agy.sh && ./probe_agy.sh
```

Use `PROBE_TIMEOUT=180 ./probe_agy.sh` if runs are slow. It needs `timeout`
(coreutils) and `script` (util-linux).

**Record the full log in `.ai/VERIFIED.md` as rows 1 and 2**, whatever the
result. "Does not work unattended" is a valid and useful outcome.

---

## Step 8 — Record results

`main` is protected now, so this goes through a pull request.

```bash
git checkout -b chore/verification-results
# edit .ai/VERIFIED.md: rows 1, 2 and 9, plus the step 6 enforcement results
git commit -am "record verification results"
git push -u origin chore/verification-results
gh pr create --fill
gh pr checks --watch
```

`deterministic-checks` will block this PR — `.ai/` is a protected path, and
that is correct. Documentation changes to the control plane are a privileged
change, not worker work. Approve and merge it yourself as owner, and note in
the PR that the block fired as designed.

That block is itself the strongest evidence the controls work.

---

## Report back

- which steps passed, which failed, and the exact output of any failure
- anything you changed and why
- whether `main` genuinely rejects a direct push
- the probe result for rows 1 and 2
- anything in this runbook that was wrong or out of date
