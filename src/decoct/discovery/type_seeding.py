"""Coarse type seeding from schema hints and fingerprints (§3.2)."""

from __future__ import annotations

from decoct.core.config import EntityGraphConfig
from decoct.core.types import Entity


def _jaccard_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _cluster_unhinted_jaccard(
    entities: list[Entity],
    threshold: float,
) -> list[list[Entity]]:
    """Greedy agglomerative clustering by Jaccard similarity of attribute key sets.

    Entities sorted by attribute count (descending) to seed clusters with the
    most representative entities first.
    """
    sorted_entities = sorted(entities, key=lambda e: len(e.attributes), reverse=True)

    clusters: list[tuple[frozenset[str], list[Entity]]] = []

    for entity in sorted_entities:
        key_set = frozenset(entity.attributes.keys())
        best_idx = -1
        best_sim = -1.0

        for i, (centroid, _members) in enumerate(clusters):
            sim = _jaccard_similarity(key_set, centroid)
            if sim >= threshold and sim > best_sim:
                best_sim = sim
                best_idx = i

        if best_idx >= 0:
            # Add to existing cluster and update centroid (union of key sets)
            old_centroid, members = clusters[best_idx]
            members.append(entity)
            clusters[best_idx] = (old_centroid | key_set, members)
        else:
            clusters.append((key_set, [entity]))

    return [members for _centroid, members in clusters]


def seed_types_from_hints(
    entities: list[Entity],
    config: EntityGraphConfig | None = None,
) -> dict[str, list[Entity]]:
    """Seed types using adapter-provided schema_type_hint.

    Entities with the same hint go to the same type.
    Entities without hints get a fallback type from Jaccard clustering.
    """
    type_map: dict[str, list[Entity]] = {}
    unhinted: list[Entity] = []

    for entity in sorted(entities, key=lambda e: e.id):
        if entity.schema_type_hint:
            type_map.setdefault(entity.schema_type_hint, []).append(entity)
        else:
            unhinted.append(entity)

    if unhinted:
        threshold = config.unhinted_jaccard_threshold if config else 0.4
        clusters = _cluster_unhinted_jaccard(unhinted, threshold)
        for i, group in enumerate(clusters):
            type_name = f"unknown-{i}"
            type_map[type_name] = sorted(group, key=lambda e: e.id)

    return type_map
