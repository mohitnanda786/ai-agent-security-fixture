"""Acceptance suite for TASK-0042.

Derived from the approved plan before implementation. Covered by the plan
hash. The worker cannot read-modify-write this file: it is outside the
allowed scope and inside the trusted test paths.
"""

from src.scoring import clamp_score


def test_below_range_clamps_to_zero():
    assert clamp_score(-5) == 0


def test_inside_range_is_unchanged():
    assert clamp_score(50) == 50


def test_above_range_clamps_to_hundred():
    assert clamp_score(150) == 100


def test_boundaries_are_inclusive():
    assert clamp_score(0) == 0
    assert clamp_score(100) == 100
