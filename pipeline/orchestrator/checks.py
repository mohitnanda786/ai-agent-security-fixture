"""Deterministic checks. Step 2 of the V1 build plan.

Every function here is pure: it takes facts and returns findings. Nothing in
this module calls git, touches the network, or asks a model. That is the
point. These are the controls a worker must not be able to influence, so they
must not depend on anything a worker can reach.

Nothing here is language-specific. The language-specific paths (test
directories, coverage config, build manifests) live in POLICY.yaml, which is
a protected file.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

BLOCKING = "blocking"
WARNING = "warning"
INFO = "info"


# --------------------------------------------------------------------- types


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    message: str
    paths: tuple[str, ...] = ()

    def __str__(self) -> str:  # pragma: no cover - display only
        where = f" [{', '.join(self.paths)}]" if self.paths else ""
        return f"{self.severity.upper():8} {self.check}: {self.message}{where}"


@dataclass(frozen=True)
class Verdict:
    findings: tuple[Finding, ...] = ()

    @property
    def blocking(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == BLOCKING)

    @property
    def ok(self) -> bool:
        return not self.blocking

    def checks_fired(self) -> set[str]:
        return {f.check for f in self.blocking}


@dataclass(frozen=True)
class Budget:
    max_files_changed: int = 50
    max_diff_lines: int = 1000
    max_worker_attempts: int = 3
    max_plan_revisions: int = 2
    max_ci_failures: int = 3


@dataclass(frozen=True)
class Policy:
    """Loaded from .ai/POLICY.yaml. Protected; a worker may not edit it."""

    scope_allowed: tuple[str, ...] = ()
    scope_forbidden: tuple[str, ...] = ()
    protected_paths: tuple[str, ...] = ()
    trusted_test_paths: tuple[str, ...] = ()
    budget: Budget = field(default_factory=Budget)
    required_approval_fields: tuple[str, ...] = (
        "task_id",
        "plan_hash",
        "base_commit",
        "approval",
        "plan_reviewer_model",
    )


# ------------------------------------------------------------ glob matching


def _compile(pattern: str) -> re.Pattern[str]:
    """Translate a gitignore-style glob to a regex.

    Supports ``**`` across directory separators, ``*`` and ``?`` within a
    segment, and character classes. A pattern ending in ``/`` matches
    everything beneath it.
    """
    if pattern.endswith("/"):
        pattern += "**"
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        elif pattern[i] == "[":
            close = pattern.find("]", i)
            if close == -1:
                out.append(re.escape("["))
                i += 1
            else:
                out.append(pattern[i : close + 1])
                i = close + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def _norm(path: str) -> str:
    # Only a leading "./" is removed. lstrip("./") would eat the dot on
    # .github/ and .ai/, which is exactly the set of protected paths.
    while path.startswith("./"):
        path = path[2:]
    return path


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    norm = _norm(path)
    return any(_compile(p).match(norm) for p in patterns)


def _matching(paths: Iterable[str], patterns: Iterable[str]) -> tuple[str, ...]:
    pats = tuple(patterns)
    return tuple(p for p in paths if path_matches(p, pats))


def _probe(pattern: str) -> str:
    """A concrete path that the pattern would match, for overlap testing."""
    return (
        pattern.replace("**", "_seg/_leaf").replace("*", "_seg").replace("?", "z")
    ).rstrip("/")


class PolicyConflict(ValueError):
    """The policy itself would let a worker edit what grades it."""


def validate_policy(policy: Policy) -> None:
    """Refuse a policy whose allowed scope reaches graded or governance files.

    A misconfigured scope is not a runtime attack, so no check would ever
    fire on it — the worker would simply be permitted. It has to be caught
    when the policy loads.
    """
    if not policy.scope_allowed:
        raise PolicyConflict("scope.allowed is empty; nothing would be in scope")

    conflicts: list[str] = []
    for pattern in policy.scope_allowed:
        probe = _probe(pattern)
        if path_matches(probe, policy.trusted_test_paths):
            conflicts.append(f"{pattern} reaches trusted test paths")
        if path_matches(probe, policy.protected_paths):
            conflicts.append(f"{pattern} reaches protected paths")
    if conflicts:
        raise PolicyConflict(
            "allowed scope overlaps files the worker must not control: "
            + "; ".join(conflicts)
        )


# ------------------------------------------------------------------- checks


def check_protected_paths(changed: Sequence[str], policy: Policy) -> list[Finding]:
    """A worker may never touch the rules that decide whether its work passes.

    This is a second line of defence. The first is branch protection and
    CODEOWNERS in the forge, which hold even if this orchestrator is bypassed.
    """
    hits = _matching(changed, policy.protected_paths)
    if not hits:
        return []
    return [
        Finding(
            "protected_paths",
            BLOCKING,
            "governance or approval files were modified",
            hits,
        )
    ]


def check_test_integrity(changed: Sequence[str], policy: Policy) -> list[Finding]:
    """The worker may write tests. It may not edit the ones that grade it."""
    hits = _matching(changed, policy.trusted_test_paths)
    if not hits:
        return []
    return [
        Finding(
            "test_integrity",
            BLOCKING,
            "trusted test definitions, discovery or CI config were modified",
            hits,
        )
    ]


def check_scope(changed: Sequence[str], policy: Policy) -> list[Finding]:
    """Fail closed: with no allowed globs, nothing is in scope."""
    findings: list[Finding] = []

    forbidden = _matching(changed, policy.scope_forbidden)
    if forbidden:
        findings.append(
            Finding("scope", BLOCKING, "explicitly forbidden paths changed", forbidden)
        )

    outside = tuple(
        p
        for p in changed
        if p not in forbidden and not path_matches(p, policy.scope_allowed)
    )
    if outside:
        findings.append(
            Finding("scope", BLOCKING, "paths outside the approved scope changed", outside)
        )
    return findings


def plan_hash(plan_bytes: bytes) -> str:
    return "sha256:" + hashlib.sha256(plan_bytes).hexdigest()


def check_plan_binding(plan_bytes: bytes, approval: dict) -> list[Finding]:
    """A changed byte in PLAN.md voids the approval. No model judges this."""
    expected = approval.get("plan_hash")
    if not expected:
        return [Finding("plan_binding", BLOCKING, "approval records no plan hash")]
    actual = plan_hash(plan_bytes)
    if actual != expected:
        return [
            Finding(
                "plan_binding",
                BLOCKING,
                f"PLAN.md changed since approval (approved {expected[:19]}…, "
                f"found {actual[:19]}…)",
            )
        ]
    return []


# Governance files whose change invalidates an approved plan (they define scope).
DRIFT_POLICY_FILES: tuple[str, ...] = (".ai/POLICY.yaml",)


def check_base_binding(
    actual_base: str,
    approval: dict,
    *,
    approved_base_is_ancestor: bool | None = None,
    drift_paths: Sequence[str] = (),
    policy: Policy | None = None,
) -> list[Finding]:
    """Is this branch built on the commit the plan was approved against?

    Exact match is the clean case. But main advances between approval and
    implementation, and treating every advance as a violation turns the check
    into noise that gets switched off. So:

      - branch point is the approved base       -> fine
      - approved base is not an ancestor        -> blocking, histories diverged
      - approved base is an ancestor and the    -> blocking, re-approve
        intervening commits touched this task's
        scope or a graded or governance file
      - approved base is an ancestor, drift is  -> warning
        elsewhere

    That is the plan's "re-verify rather than silently rebasing", made
    specific about what re-verification is for.
    """
    expected = approval.get("base_commit")
    if not expected:
        return [Finding("base_binding", BLOCKING, "approval records no base commit")]
    if actual_base.startswith(expected) or expected.startswith(actual_base):
        return []
    if approved_base_is_ancestor is None:
        return [Finding("base_binding", BLOCKING,
                        f"branch is based on {actual_base[:12]}, approval assumed "
                        f"{expected[:12]}, and ancestry was not established")]
    if not approved_base_is_ancestor:
        return [Finding("base_binding", BLOCKING,
                        f"branch point {actual_base[:12]} does not descend from "
                        f"the approved base {expected[:12]}")]
    relevant: tuple[str, ...] = ()
    if policy is not None and drift_paths:
        # Drift asks "does a change here invalidate the plan", which is a
        # different question from protected_paths' "may the worker write this".
        # Using one list for both made every audit-trail write invalidate the
        # approval. POLICY.yaml stays because it defines scope; records such as
        # DECISIONS.md are not inputs to correctness.
        guarded = (policy.scope_allowed + policy.trusted_test_paths
                   + DRIFT_POLICY_FILES)
        relevant = _matching(drift_paths, guarded)
    if relevant:
        return [Finding("base_binding", BLOCKING,
                        "main advanced since approval and touched files this task "
                        "depends on; the plan needs re-approval", relevant)]
    return [Finding("base_binding", WARNING,
                    f"main advanced from {expected[:12]} to {actual_base[:12]} "
                    f"since approval; no guarded file changed")]


def check_budgets(
    policy: Policy,
    *,
    files_changed: int,
    diff_lines: int,
    attempts: int = 0,
    ci_failures: int = 0,
    plan_revisions: int = 0,
) -> list[Finding]:
    b = policy.budget
    limits = [
        ("files changed", files_changed, b.max_files_changed),
        ("diff lines", diff_lines, b.max_diff_lines),
        ("worker attempts", attempts, b.max_worker_attempts),
        ("CI failures", ci_failures, b.max_ci_failures),
        ("plan revisions", plan_revisions, b.max_plan_revisions),
    ]
    return [
        Finding("budget", BLOCKING, f"{name} {value} exceeds limit {limit}")
        for name, value, limit in limits
        if value > limit
    ]


def failure_fingerprint(text: str) -> str:
    """Normalise a failure so two runs of the same error compare equal."""
    t = text.lower()
    t = re.sub(r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}\S*", "<ts>", t)
    t = re.sub(r"\b[0-9a-f]{7,40}\b", "<sha>", t)
    t = re.sub(r":\d+(:\d+)?\b", ":<pos>", t)
    t = re.sub(r"\b\d+(\.\d+)?\s*(s|ms|sec|seconds)\b", "<dur>", t)
    t = re.sub(r"0x[0-9a-f]+", "<addr>", t)
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def check_repeated_failure(fingerprints: Sequence[str], window: int = 2) -> list[Finding]:
    """Stop a stalled loop before it spends the last attempt."""
    if len(fingerprints) < window:
        return []
    recent = fingerprints[-window:]
    if len(set(recent)) == 1:
        return [
            Finding(
                "repeated_failure",
                BLOCKING,
                f"the same failure {recent[0]} repeated {window} times; not retrying",
            )
        ]
    return []


def check_provenance(approval: dict, policy: Policy) -> list[Finding]:
    missing = tuple(
        f for f in policy.required_approval_fields if not str(approval.get(f, "")).strip()
    )
    if missing:
        return [
            Finding(
                "provenance",
                BLOCKING,
                f"approval record incomplete: missing {', '.join(missing)}",
            )
        ]
    return []


# ---------------------------------------------------------------- composite


def verify_implementation(
    *,
    changed: Sequence[str],
    policy: Policy,
    approval: dict,
    plan_bytes: bytes,
    actual_base: str,
    diff_lines: int,
    attempts: int = 0,
    ci_failures: int = 0,
    failure_history: Sequence[str] = (),
    approved_base_is_ancestor: bool | None = None,
    drift_paths: Sequence[str] = (),
) -> Verdict:
    """Every pre-merge check that needs no model and no network.

    Deliberately NOT covered here: whether the tests actually test anything.
    That is the mutation gate in step 3, and it is the attack this layer
    cannot see.
    """
    findings: list[Finding] = []
    findings += check_protected_paths(changed, policy)
    findings += check_test_integrity(changed, policy)
    findings += check_scope(changed, policy)
    findings += check_plan_binding(plan_bytes, approval)
    findings += check_base_binding(
        actual_base, approval,
        approved_base_is_ancestor=approved_base_is_ancestor,
        drift_paths=drift_paths, policy=policy,
    )
    findings += check_provenance(approval, policy)
    findings += check_budgets(
        policy,
        files_changed=len(changed),
        diff_lines=diff_lines,
        attempts=attempts,
        ci_failures=ci_failures,
    )
    findings += check_repeated_failure(failure_history)
    return Verdict(tuple(findings))
