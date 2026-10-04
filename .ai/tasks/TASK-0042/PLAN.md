# PLAN — TASK-0042

## 1. Objective

`clamp_score` must map any numeric score into the inclusive range 0..100.

## 8. Test strategy

Acceptance cases, approved with this plan and stored outside worker scope:

- a value below the range returns 0
- a value inside the range is returned unchanged
- a value above the range returns 100
- the range boundaries are inclusive
