# ADR-009: Topological Sort for Pass Ordering

## Status
Accepted

## Context
Pipeline passes have ordering dependencies. strip-secrets must run first. strip-defaults must run after strip-comments. annotate-deviations must run after strip-conformant. Users and profiles specify which passes to include but shouldn't need to manually order them.

## Decision
Passes declare ordering constraints via `run_after` and `run_before` lists. The pipeline constructor uses Kahn's algorithm (topological sort) to determine execution order automatically.

## Rationale
1. **Declarative ordering** — Pass authors declare dependencies, not positions. This is robust to pass additions and removals.
2. **Automatic resolution** — Users list passes in any order in profiles; the pipeline sorts them correctly.
3. **Cycle detection** — The topological sort detects circular dependencies and raises `ValueError`, preventing invalid configurations.
4. **Graceful degradation** — Constraints referencing absent passes are silently ignored. A pipeline with only strip-secrets and strip-comments doesn't fail because strip-defaults is missing.

## Implementation
- `BasePass.run_after: list[str]` — names of passes that must run before this one.
- `BasePass.run_before: list[str]` — names of passes that must run after this one.
- `_topological_sort()` in `pipeline.py` implements Kahn's algorithm.
- Constraint edges are only added for passes present in the current pipeline.

## Consequences
- Pass order in profiles and CLI doesn't matter — the sort determines order.
- New passes only need to declare their constraints, not update every existing pass.
- Stable sort: passes with no ordering relationship maintain their original list order.
