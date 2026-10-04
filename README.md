# ai-agent-security-fixture

A test bed for one question:

> Can an AI implementation agent operate on a repository while remaining
> unable to influence the rules, the tests, or the decision that determine
> whether its work is accepted?

The repository is both the thing under test and the harness that attacks it.

## Layout

| Path | What it is | Worker may write |
| --- | --- | --- |
| `src/` | implementation under test | yes, within the task's scope |
| `tests/regression/` | graded suite, pre-existing | no |
| `tests/worker/` | the worker's own tests, not graded | yes |
| `.ai/tasks/*/acceptance/` | acceptance suite, approved with the plan | no |
| `.ai/POLICY.yaml` | scope, protected paths, budgets | no |
| `.github/` | the grading environment | no |
| `pipeline/` | orchestrator, checks, attack harness | no |

`tests/regression/` and `tests/worker/` are separate trees on purpose. The
worker writes in one and is graded by the other. `validate_policy()` refuses
any policy where the two overlap, because a scope that reaches the graded
tests would trigger no runtime check — the worker would simply be permitted.

## Setting it up

`RUNBOOK.md` is the full procedure, from a bare machine through verified
branch protection. It is written to be handed to an agent, and marks the two
steps that need a human: the `gh` device-code login and the Antigravity OAuth
sign-in.

## Run it

```bash
pip install pytest pyyaml
cd pipeline
pytest tests                 # unit tests for the check layer
python -m harness.replay     # every attack scenario against a real git repo
```

`replay` builds a throwaway repository in `/tmp`, runs fifteen scenarios as
real branches, and reports which control stopped each one. Two scenarios are
expected to merge; the reasons are in `.ai/VERIFIED.md`.

## Enforcement is two-layered

`pipeline/orchestrator/checks.py` is the second layer. The first is branch
protection, CODEOWNERS and required status checks in GitHub — those hold even
if the orchestrator is bypassed by anything with repository write. If the
first layer is not active, the second one is all there is.
