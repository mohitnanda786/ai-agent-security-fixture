"""Mutation testing — the control that sees what path rules cannot.

A worker that writes a test asserting nothing violates no path rule, touches
no protected file and stays inside its scope. Every deterministic check
passes. The only way to detect it is to ask whether the tests would notice if
the implementation were wrong.

So: break the implementation on purpose, re-run the trusted suites, and
require that they fail. A mutant that survives is a hole in the tests.

Written here rather than pulled from a library so the operators are
auditable and the run is deterministic. A real project may prefer mutmut or
cosmic-ray; the gate contract is the same.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Comparison flips: each maps to the operator that inverts the boundary.
_CMP_FLIP = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}


@dataclass(frozen=True)
class Mutant:
    path: str
    line: int
    description: str
    source: str


class _Mutator(ast.NodeTransformer):
    """Applies exactly one mutation, identified by index."""

    def __init__(self, target: int) -> None:
        self.target = target
        self.seen = 0
        self.applied: str | None = None
        self.line = 0

    def _take(self, description: str, line: int) -> bool:
        hit = self.seen == self.target
        if hit:
            self.applied = description
            self.line = line
        self.seen += 1
        return hit

    def visit_Compare(self, node: ast.Compare):  # noqa: N802
        self.generic_visit(node)
        if len(node.ops) == 1:
            op = type(node.ops[0])
            if op in _CMP_FLIP:
                new = _CMP_FLIP[op]
                if self._take(f"{op.__name__} -> {new.__name__}", node.lineno):
                    node.ops = [new()]
        return node

    def visit_Constant(self, node: ast.Constant):  # noqa: N802
        if isinstance(node.value, bool):
            if self._take(f"{node.value} -> {not node.value}", node.lineno):
                return ast.copy_location(ast.Constant(value=not node.value), node)
        elif isinstance(node.value, int):
            if self._take(f"{node.value} -> {node.value + 1}", node.lineno):
                return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node


def _count(tree: ast.AST) -> int:
    probe = _Mutator(-1)
    probe.visit(tree)
    return probe.seen


def generate(path: Path, source: str) -> list[Mutant]:
    tree = ast.parse(source)
    total = _count(tree)
    out: list[Mutant] = []
    for i in range(total):
        mutator = _Mutator(i)
        mutated = mutator.visit(ast.parse(source))
        ast.fix_missing_locations(mutated)
        if mutator.applied is None:
            continue
        out.append(
            Mutant(str(path), mutator.line, mutator.applied, ast.unparse(mutated))
        )
    return out


@dataclass(frozen=True)
class MutationResult:
    total: int
    killed: int
    survivors: tuple[Mutant, ...]

    @property
    def score(self) -> float:
        return self.killed / self.total if self.total else 0.0


def _run_suites(repo: Path, suites: list[str]) -> bool:
    """True when the suites pass."""
    proc = subprocess.run(
        ["python", "-m", "pytest", "-q", "-x", "--no-header", *suites],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return proc.returncode == 0


def evaluate(repo: Path, targets: list[str], suites: list[str]) -> MutationResult:
    """Mutate each target file in a scratch copy and see if the suites notice."""
    mutants: list[Mutant] = []
    for rel in targets:
        path = repo / rel
        if path.suffix == ".py" and path.exists():
            mutants.extend(generate(Path(rel), path.read_text()))

    killed, survivors = 0, []
    for mutant in mutants:
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "repo"
            shutil.copytree(repo, scratch, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            (scratch / mutant.path).write_text(mutant.source)
            if _run_suites(scratch, suites):
                survivors.append(mutant)  # tests did not notice
            else:
                killed += 1
    return MutationResult(len(mutants), killed, tuple(survivors))
