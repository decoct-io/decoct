"""Pipeline builder and runner."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from decoct.passes.base import BasePass, PassResult


@dataclass
class PipelineStats:
    """Collected statistics from a pipeline run."""

    pass_results: list[PassResult] = field(default_factory=list)
    pass_timings: dict[str, float] = field(default_factory=dict)
    total_time: float = 0.0


def _topological_sort(passes: list[BasePass]) -> list[BasePass]:
    """Sort passes respecting run_after and run_before constraints.

    Raises ValueError on cycles or unsatisfiable constraints.
    """
    name_to_pass = {p.name: p for p in passes}
    names = {p.name for p in passes}

    # Build adjacency: edges[a] = {b} means a must run before b
    edges: dict[str, set[str]] = {n: set() for n in names}

    for p in passes:
        for dep in p.run_after:
            if dep in names:
                edges[dep].add(p.name)
        for before in p.run_before:
            if before in names:
                edges[p.name].add(before)

    # Kahn's algorithm
    in_degree: dict[str, int] = {n: 0 for n in names}
    for deps in edges.values():
        for d in deps:
            in_degree[d] += 1

    queue = sorted(n for n in names if in_degree[n] == 0)
    result: list[str] = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in sorted(edges[node]):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(names):
        remaining = names - set(result)
        msg = f"Cycle detected in pass ordering. Involved passes: {sorted(remaining)}"
        raise ValueError(msg)

    return [name_to_pass[n] for n in result]


class Pipeline:
    """Ordered sequence of passes to execute on a document."""

    def __init__(self, passes: list[BasePass]) -> None:
        self._passes = _topological_sort(passes)

    @property
    def pass_names(self) -> list[str]:
        """Ordered pass names after topological sort."""
        return [p.name for p in self._passes]

    def run(self, doc: Any, **kwargs: Any) -> PipelineStats:
        """Execute all passes in order on the document.

        The document is modified in-place. Returns collected statistics.
        """
        stats = PipelineStats()
        start = time.monotonic()

        for p in self._passes:
            t0 = time.monotonic()
            result = p.run(doc, **kwargs)
            elapsed = time.monotonic() - t0

            stats.pass_results.append(result)
            stats.pass_timings[p.name] = elapsed

        stats.total_time = time.monotonic() - start
        return stats
