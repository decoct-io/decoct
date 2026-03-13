"""Greedy-bundle compression engine.

Wraps the existing ``extract_classes()`` (Phase 4) and ``delta_compress()``
(Phase 5) functions as a :class:`CompressionEngine`.
"""

from __future__ import annotations

from decoct.compression.class_extractor import extract_classes
from decoct.compression.delta import delta_compress
from decoct.compression.engine import CompressionEngine, registry
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import AttributeProfile, ClassHierarchy, Entity


class GreedyBundleEngine(CompressionEngine):
    """Default compression engine using greedy frequent-bundle extraction."""

    def compress(
        self,
        type_map: dict[str, list[Entity]],
        graph: EntityGraph,
        profiles: dict[str, dict[str, AttributeProfile]],
        config: EntityGraphConfig,
    ) -> dict[str, ClassHierarchy]:
        """Run Phase 4 (class extraction) then Phase 5 (delta compression)."""
        hierarchies = extract_classes(type_map, graph, profiles, config)
        return delta_compress(hierarchies, graph, profiles, config)

    def name(self) -> str:
        return "greedy-bundle"


registry.register(GreedyBundleEngine)
