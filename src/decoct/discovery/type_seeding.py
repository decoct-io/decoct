"""Coarse type seeding from schema hints and fingerprints (§3.2)."""

from __future__ import annotations

from decoct.core.types import Entity


def seed_types_from_hints(entities: list[Entity]) -> dict[str, list[Entity]]:
    """Seed types using adapter-provided schema_type_hint.

    Entities with the same hint go to the same type.
    Entities without hints get a fallback type from fingerprinting.
    """
    type_map: dict[str, list[Entity]] = {}
    unhinted: list[Entity] = []

    for entity in sorted(entities, key=lambda e: e.id):
        if entity.schema_type_hint:
            type_map.setdefault(entity.schema_type_hint, []).append(entity)
        else:
            unhinted.append(entity)

    if unhinted:
        # Fingerprint-based grouping for unhinted entities
        # Group by attribute-presence fingerprint
        fp_groups: dict[tuple[str, ...], list[Entity]] = {}
        for entity in unhinted:
            fp = tuple(sorted(entity.attributes.keys()))
            fp_groups.setdefault(fp, []).append(entity)

        for i, (fp, group) in enumerate(sorted(fp_groups.items(), key=lambda x: x[0])):
            type_name = f"unknown-{i}"
            type_map[type_name] = group

    return type_map
