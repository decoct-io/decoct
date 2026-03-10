"""Anti-unification for type refinement (§3.6).

v1 stub: compare non-reference attributes path-by-path.
Matching canonical values kept, mismatches → Variable sentinel.

For type refinement, a restricted mode compares only signal paths
to avoid counting instance-level differences as type-level variables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from decoct.core.canonical import CANONICAL_EQUAL
from decoct.core.types import Entity


@dataclass
class Variable:
    """Sentinel for a position where two entities differ."""
    path: str


@dataclass
class AntiUnificationResult:
    """Result of anti-unifying two entities."""
    common: dict[str, Any]
    variables: list[Variable]


def anti_unify(
    e1: Entity,
    e2: Entity,
    restrict_paths: set[str] | None = None,
) -> AntiUnificationResult:
    """Anti-unify two entities by comparing attributes path-by-path.

    Args:
        e1, e2: entities to compare
        restrict_paths: if provided, only compare these paths (for type refinement).
            This avoids counting instance-level differences (like per-device IPs)
            as type-level structural variables.
    """
    common: dict[str, Any] = {}
    variables: list[Variable] = []

    if restrict_paths is not None:
        all_paths = sorted(restrict_paths)
    else:
        all_paths = sorted(set(e1.attributes.keys()) | set(e2.attributes.keys()))

    for path in all_paths:
        a1 = e1.attributes.get(path)
        a2 = e2.attributes.get(path)

        if a1 is not None and a2 is not None:
            if CANONICAL_EQUAL(a1.value, a2.value):
                common[path] = a1.value
            else:
                variables.append(Variable(path=path))
        else:
            variables.append(Variable(path=path))

    return AntiUnificationResult(common=common, variables=variables)


def count_variables(result: AntiUnificationResult) -> int:
    """Count the number of variable positions in an anti-unification result."""
    return len(result.variables)
