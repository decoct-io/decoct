"""Type refinement via fingerprint clustering (§3.6)."""

from __future__ import annotations

from statistics import mean
from typing import Any

from decoct.core.canonical import CANONICAL_KEY
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    AttributeProfile,
    BootstrapSignal,
    Entity,
)
from decoct.discovery.anti_unification import anti_unify, count_variables


def refine_types(
    graph: EntityGraph,
    type_map: dict[str, list[Entity]],
    profiles: dict[str, dict[str, AttributeProfile]],
    config: EntityGraphConfig,
) -> dict[str, list[Entity]]:
    """Refine types by sub-clustering on bootstrap signal fingerprints (§3.6)."""
    new_type_map: dict[str, list[Entity]] = {}

    for type_id in sorted(type_map.keys()):
        entities = type_map[type_id]
        type_profiles = profiles.get(type_id, {})

        # Collect signal paths
        signal_paths = sorted([
            p for p, prof in type_profiles.items()
            if prof.bootstrap_role != BootstrapSignal.NONE
        ])

        # Relationship labels
        rel_labels = graph.unique_relationship_labels_from_entities(entities)

        # Build fingerprints
        fingerprints: dict[str, tuple[tuple[str, str], ...]] = {}

        for entity in sorted(entities, key=lambda e: e.id):
            fp_parts: list[tuple[str, str]] = []

            for p in signal_paths:
                prof = type_profiles[p]
                if prof.bootstrap_role == BootstrapSignal.VALUE_SIGNAL:
                    if p in entity.attributes:
                        fp_parts.append((p, CANONICAL_KEY(entity.attributes[p].value)))
                elif prof.bootstrap_role == BootstrapSignal.PRESENCE_SIGNAL:
                    if p in entity.attributes:
                        fp_parts.append((p, "__EXISTS__"))

            for label in rel_labels:
                if graph.has_relationship_from(entity.id, label):
                    fp_parts.append((f"REL::{label}", "__EXISTS__"))

            fingerprints[entity.id] = tuple(fp_parts)

        # Group by fingerprint
        sub_clusters: dict[tuple[tuple[str, str], ...], list[Entity]] = {}
        for entity in sorted(entities, key=lambda e: e.id):
            fp = fingerprints[entity.id]
            sub_clusters.setdefault(fp, []).append(entity)

        if len(sub_clusters) == 1:
            new_type_map[type_id] = entities
            continue

        # Build the set of signal paths + relationship label pseudo-paths
        # for restricted anti-unification comparison
        signal_path_set = set(signal_paths)
        for label in rel_labels:
            signal_path_set.add(f"REL::{label}")

        # Attempt merging with anti-unification (restricted to signal paths)
        merged: list[_ClusterGroup] = []
        for cluster_entities in sub_clusters.values():
            reps = sorted(cluster_entities, key=lambda e: e.id)[:5]
            placed = False

            for group in merged:
                var_counts = []
                for r1 in reps:
                    for r2 in group.representatives:
                        result = anti_unify(r1, r2, restrict_paths=signal_path_set)
                        var_counts.append(count_variables(result))

                avg_var_count = mean(var_counts) if var_counts else float("inf")

                if avg_var_count <= config.max_anti_unify_variables:
                    group.entities.extend(cluster_entities)
                    group.representatives = sorted(group.entities, key=lambda e: e.id)[:5]
                    placed = True
                    break

            if not placed:
                merged.append(_ClusterGroup(
                    entities=list(cluster_entities),
                    representatives=list(reps),
                ))

        # Small-cluster guard: prevent shattering into near-singletons
        merged = _merge_small_clusters(merged, config, signal_path_set)

        if len(merged) == 1:
            new_type_map[type_id] = entities
        else:
            for i, group in enumerate(merged):
                refined_name = _derive_type_name(group, type_id, i, new_type_map)
                new_type_map[refined_name] = sorted(group.entities, key=lambda e: e.id)

    return new_type_map


def _merge_small_clusters(
    merged: list[_ClusterGroup],
    config: EntityGraphConfig,
    signal_path_set: set[str],
) -> list[_ClusterGroup]:
    """Merge clusters below min_refinement_cluster_size into larger ones.

    1. If ALL clusters are below the threshold → complete shatter: return one group.
    2. For each small cluster, try to merge into the group with lowest average
       anti-unification variable count (relaxed threshold: 2x max_anti_unify_variables).
    3. Fallback: merge into the largest group.
    """
    min_size = config.min_refinement_cluster_size
    if min_size <= 1:
        return merged

    large = [g for g in merged if len(g.entities) >= min_size]
    small = [g for g in merged if len(g.entities) < min_size]

    if not small:
        return merged

    # Complete shatter — ALL groups below threshold → don't split at all
    if not large:
        all_entities: list[Entity] = []
        for g in merged:
            all_entities.extend(g.entities)
        return [_ClusterGroup(
            entities=all_entities,
            representatives=sorted(all_entities, key=lambda e: e.id)[:5],
        )]

    relaxed_limit = 2 * config.max_anti_unify_variables

    for sg in small:
        best_target: _ClusterGroup | None = None
        best_avg = float("inf")

        for lg in large:
            var_counts = []
            for r1 in sg.representatives:
                for r2 in lg.representatives:
                    result = anti_unify(r1, r2, restrict_paths=signal_path_set)
                    var_counts.append(count_variables(result))

            avg = mean(var_counts) if var_counts else float("inf")
            if avg <= relaxed_limit and avg < best_avg:
                best_avg = avg
                best_target = lg

        if best_target is None:
            # Fallback: merge into largest group
            best_target = max(large, key=lambda g: len(g.entities))

        best_target.entities.extend(sg.entities)
        best_target.representatives = sorted(
            best_target.entities, key=lambda e: e.id,
        )[:5]

    return large


class _ClusterGroup:
    """Internal cluster group during type refinement."""

    def __init__(self, entities: list[Entity], representatives: list[Entity]) -> None:
        self.entities = entities
        self.representatives = representatives


def _derive_type_name(
    group: _ClusterGroup,
    base_name: str,
    ordinal: int,
    existing: dict[str, Any],
) -> str:
    """Derive a human-readable type name. Uses ordinal only on collision."""
    # Try using the type hint from first entity
    if group.entities and group.entities[0].schema_type_hint:
        candidate = group.entities[0].schema_type_hint
        if candidate not in existing:
            return candidate

    candidate = f"{base_name}_{ordinal}"
    if candidate not in existing:
        return candidate

    # Fallback with incrementing suffix
    counter = ordinal
    while candidate in existing:
        counter += 1
        candidate = f"{base_name}_{counter}"
    return candidate
