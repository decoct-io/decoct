"""Top-level orchestrator for the entity-graph compression pipeline.

Chains all phases:
1. Canonicalise (adapter parsing + entity extraction)
2+3. Bootstrap loop (type seeding → profiling → refinement → convergence)
3.5. Composite decomposition
4. Class extraction
5. Delta compression
6. Normalisation (Tier C construction)
7. Assembly + structural validation
8. Reconstruction validation (the gate test)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from decoct.adapters.base import BaseAdapter
from decoct.assembly.tier_builder import build_tier_a, build_tier_b, build_tier_c_yaml
from decoct.compression.class_extractor import extract_classes
from decoct.compression.delta import delta_compress
from decoct.compression.normalisation import build_tier_c
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    ClassHierarchy,
    CompositeTemplate,
    Entity,
    TierC,
)
from decoct.discovery.bootstrap import run_bootstrap_loop
from decoct.discovery.composite_decomp import decompose_composites
from decoct.reconstruction.validator import validate_reconstruction


@dataclass
class EntityGraphResult:
    """Result of the entity-graph pipeline."""
    graph: EntityGraph
    type_map: dict[str, list[Entity]]
    hierarchies: dict[str, ClassHierarchy]
    tier_c_files: dict[str, TierC]
    template_index: dict[str, CompositeTemplate]
    tier_a: dict[str, Any]
    tier_b_files: dict[str, dict[str, Any]]
    tier_c_yaml: dict[str, dict[str, Any]]
    original_composite_values: dict[tuple[str, str], Any] = field(default_factory=dict)


def run_entity_graph_pipeline(
    sources: list[str],
    adapter: BaseAdapter,
    config: EntityGraphConfig | None = None,
) -> EntityGraphResult:
    """Run the full entity-graph compression pipeline.

    Args:
        sources: list of file paths to process
        adapter: adapter for parsing + entity extraction
        config: pipeline configuration (defaults used if None)

    Returns:
        EntityGraphResult with all tier data and the entity graph

    Raises:
        ReconstructionError: if any entity fails reconstruction validation
        StructuralInvariantError: if structural invariants fail
    """
    if config is None:
        config = EntityGraphConfig()

    # Phase 1: Canonicalise
    graph = EntityGraph()
    for source in sources:
        parsed = adapter.parse(source)
        adapter.extract_entities(parsed, graph)

    # Phase 2+3: Bootstrap loop
    type_map, profiles = run_bootstrap_loop(graph, config)

    # Phase 3.5: Composite decomposition
    (
        graph,
        template_index,
        templates_by_type_path,
        composite_deltas,
        original_composite_values,
        profiles,
    ) = decompose_composites(graph, type_map, profiles, config)

    # Phase 4: Class extraction
    hierarchies = extract_classes(type_map, graph, profiles, config)

    # Phase 5: Delta compression
    hierarchies = delta_compress(hierarchies, graph, profiles, config)

    # Phase 6: Normalisation (Tier C construction)
    tier_c_files: dict[str, TierC] = {}
    for type_id in sorted(type_map.keys()):
        # Filter composite_deltas for this type
        type_entities = {e.id for e in type_map[type_id]}
        type_composite_deltas = {
            k: v for k, v in composite_deltas.items()
            if k[0] in type_entities
        }
        tier_c_files[type_id] = build_tier_c(
            type_id=type_id,
            hierarchy=hierarchies[type_id],
            graph=graph,
            profiles=profiles[type_id],
            composite_deltas=type_composite_deltas,
            config=config,
        )

    # Phase 7: Reconstruction validation (THE gate test)
    validate_reconstruction(
        graph=graph,
        hierarchies=hierarchies,
        tier_c_files=tier_c_files,
        template_index=template_index,
        original_composite_values=original_composite_values,
    )

    # Assembly: build output YAML
    tier_a = build_tier_a(graph, type_map, hierarchies)
    tier_b_files: dict[str, dict[str, Any]] = {}
    tier_c_yaml: dict[str, dict[str, Any]] = {}

    for type_id in sorted(type_map.keys()):
        tier_b_files[type_id] = build_tier_b(
            type_id, hierarchies[type_id], tier_c_files[type_id], template_index,
        )
        tier_c_yaml[type_id] = build_tier_c_yaml(type_id, tier_c_files[type_id])

    return EntityGraphResult(
        graph=graph,
        type_map=type_map,
        hierarchies=hierarchies,
        tier_c_files=tier_c_files,
        template_index=template_index,
        tier_a=tier_a,
        tier_b_files=tier_b_files,
        tier_c_yaml=tier_c_yaml,
        original_composite_values=original_composite_values,
    )
