"""Bootstrap loop: seed types → profile → refine → converge (§3.7)."""

from __future__ import annotations

from decoct.analysis.profiler import profile_attributes
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import AttributeProfile, Entity
from decoct.discovery.type_discovery import refine_types
from decoct.discovery.type_seeding import seed_types_from_hints


def run_bootstrap_loop(
    graph: EntityGraph,
    config: EntityGraphConfig,
) -> tuple[dict[str, list[Entity]], dict[str, dict[str, AttributeProfile]]]:
    """Run the full bootstrap loop: seed → profile → refine until convergence.

    Returns (final_type_map, final_profiles).
    """
    # Phase 2a: Coarse type seeding
    type_map = seed_types_from_hints(graph.entities)

    # Set discovered_type on entities
    for type_id, entities in type_map.items():
        for entity in entities:
            entity.discovered_type = type_id

    prev_assignment: dict[str, str] = {}

    for iteration in range(config.max_bootstrap_iterations):
        # Phase 2b: Per-type profiling
        profiles: dict[str, dict[str, AttributeProfile]] = {}
        for type_id, entities in sorted(type_map.items()):
            profiles[type_id] = profile_attributes(entities, type_id, config)

        # Build current assignment map
        current_assignment: dict[str, str] = {}
        for type_id, entities in type_map.items():
            for entity in entities:
                current_assignment[entity.id] = type_id

        # Check convergence
        if current_assignment == prev_assignment:
            break

        prev_assignment = current_assignment

        # Phase 3: Type refinement
        new_type_map = refine_types(graph, type_map, profiles, config)

        # Update discovered_type on entities
        for type_id, entities in new_type_map.items():
            for entity in entities:
                entity.discovered_type = type_id

        type_map = new_type_map

    # Final re-profile on converged types
    final_profiles: dict[str, dict[str, AttributeProfile]] = {}
    for type_id, entities in sorted(type_map.items()):
        final_profiles[type_id] = profile_attributes(entities, type_id, config)

    return type_map, final_profiles
