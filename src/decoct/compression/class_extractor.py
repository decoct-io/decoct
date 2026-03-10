"""Greedy frequent-bundle class extraction (§5).

Extracts partial Tier B templates via frequent-bundle extraction:
- base_class = A_BASE + universal B
- classes = frequent B bundles from residual B itemsets
- unassigned entities → _base_only
"""

from __future__ import annotations

import copy
from collections import Counter
from itertools import combinations
from typing import Any

from decoct.core.canonical import CANONICAL_KEY, ITEM_KEY, VALUE_KEY
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    AttributeProfile,
    BaseClass,
    BundleCandidate,
    ClassDef,
    ClassHierarchy,
    Entity,
    FinalRole,
)


def _token_estimate_attrs(attrs: dict[str, Any]) -> float:
    """Estimate token cost of a set of attributes."""
    total = 0.0
    for path, value in attrs.items():
        total += len(path) / 4.0 + len(str(value)) / 4.0 + 2  # key + value + YAML overhead
    return total


def _token_estimate_class(attrs: dict[str, Any]) -> float:
    """Estimate token cost of a class definition."""
    return _token_estimate_attrs(attrs) + 8  # class overhead (name, inherits, etc.)


def _materialize_bundle(
    bundle_keys: frozenset[tuple[str, str]],
    item_lookup: dict[tuple[str, str], Any],
) -> dict[str, Any]:
    """Materialize bundle keys into attrs dict (§5.3)."""
    return {
        path: copy.deepcopy(item_lookup[(path, value_key)])
        for path, value_key in sorted(bundle_keys)
    }


def _bundle_gain(
    bundle_keys: frozenset[tuple[str, str]],
    support_count: int,
    item_lookup: dict[tuple[str, str], Any],
    token_cost_class_ref: int,
) -> float:
    """Compute compression gain of a bundle (§5.3)."""
    attrs = _materialize_bundle(bundle_keys, item_lookup)
    repeated_cost = support_count * _token_estimate_attrs(attrs)
    templated_cost = _token_estimate_class(attrs) + support_count * token_cost_class_ref
    return repeated_cost - templated_cost


def _generate_bundle_candidates(
    entity_ids: list[str],
    vectors: dict[str, frozenset[tuple[str, str]]],
    item_lookup: dict[tuple[str, str], Any],
    min_support: int,
    max_bundle_size: int,
    token_cost_class_ref: int,
) -> list[BundleCandidate]:
    """Generate frequent bundle candidates (§5.5)."""
    counts: Counter[frozenset[tuple[str, str]]] = Counter()

    for eid in entity_ids:
        items = sorted(vectors[eid], key=lambda kv: (kv[0], kv[1]))
        for size in range(1, min(max_bundle_size, len(items)) + 1):
            for subset in combinations(items, size):
                counts[frozenset(subset)] += 1

    candidates: list[BundleCandidate] = []
    for bundle, raw_support in counts.items():
        if raw_support < min_support:
            continue

        covered = sorted([eid for eid in entity_ids if bundle.issubset(vectors[eid])])
        support = len(covered)
        gain = _bundle_gain(bundle, support, item_lookup, token_cost_class_ref)

        if gain > 0:
            candidates.append(BundleCandidate(
                bundle=bundle,
                covered=covered,
                gain=gain,
            ))

    return candidates


def _derive_class_name(
    bundle_attrs: dict[str, Any],
    type_id: str,
    existing_names: set[str],
) -> str:
    """Derive human-readable class name from bundle attributes (§12)."""
    # Use first few path segments and short values
    tokens: list[str] = []
    for path, value in sorted(bundle_attrs.items()):
        # Use last segment of path
        parts = path.split(".")
        token = parts[-1].replace("-", "_")
        if isinstance(value, str) and len(value) < 30:
            val_token = value.replace("-", "_").replace(" ", "_").replace("/", "_")
            tokens.append(f"{token}_{val_token}")
        else:
            tokens.append(token)
        if len(tokens) >= 2:
            break

    base_name = "_".join(tokens) if tokens else "class"
    # Sanitize
    base_name = "".join(c if c.isalnum() or c == "_" else "_" for c in base_name)
    base_name = base_name.strip("_")[:50]

    if base_name not in existing_names:
        return base_name

    # Collision — add ordinal
    i = 1
    while f"{base_name}_{i}" in existing_names:
        i += 1
    return f"{base_name}_{i}"


def extract_classes(
    type_map: dict[str, list[Entity]],
    graph: EntityGraph,
    profiles: dict[str, dict[str, AttributeProfile]],
    config: EntityGraphConfig,
) -> dict[str, ClassHierarchy]:
    """Extract class hierarchies for all types (§5.4)."""
    hierarchies: dict[str, ClassHierarchy] = {}

    for type_id in sorted(type_map.keys()):
        entities = type_map[type_id]
        type_profiles = profiles[type_id]

        a_base_paths = sorted([p for p, prof in type_profiles.items() if prof.final_role == FinalRole.A_BASE])
        tier_b_paths = sorted([p for p, prof in type_profiles.items() if prof.final_role == FinalRole.B])

        # Base class = A_BASE + universal B
        base_attrs: dict[str, Any] = {}
        for p in a_base_paths:
            # All entities have this path with the same value
            base_attrs[p] = copy.deepcopy(entities[0].attributes[p].value)

        # Find universal B (all entities have this path with the same canonical value)
        for p in tier_b_paths:
            values = [e.attributes[p].value for e in entities if p in e.attributes]
            if len(values) == len(entities) and len(set(VALUE_KEY(v) for v in values)) == 1:
                base_attrs[p] = copy.deepcopy(values[0])

        residual_b_paths = [p for p in tier_b_paths if p not in base_attrs]

        # Build item lookup and vectors
        item_lookup: dict[tuple[str, str], Any] = {}
        vectors: dict[str, frozenset[tuple[str, str]]] = {}

        for e in sorted(entities, key=lambda x: x.id):
            items: list[tuple[str, str]] = []
            for p in residual_b_paths:
                if p in e.attributes:
                    k = ITEM_KEY(p, e.attributes[p].value)
                    if k not in item_lookup:
                        item_lookup[k] = copy.deepcopy(e.attributes[p].value)
                    items.append(k)
            vectors[e.id] = frozenset(items)

        unassigned = [e.id for e in sorted(entities, key=lambda x: x.id)]
        classes: dict[str, ClassDef] = {}
        existing_names: set[str] = set()

        while True:
            candidates = _generate_bundle_candidates(
                entity_ids=unassigned,
                vectors=vectors,
                item_lookup=item_lookup,
                min_support=config.min_class_support,
                max_bundle_size=config.max_class_bundle_size,
                token_cost_class_ref=config.token_cost_class_ref,
            )

            if not candidates:
                break

            candidates.sort(
                key=lambda c: (
                    -c.gain,
                    -len(c.bundle),
                    CANONICAL_KEY(sorted(c.bundle)),
                )
            )

            best = candidates[0]
            if best.gain <= 0:
                break

            covered = sorted(
                [eid for eid in unassigned if best.bundle.issubset(vectors[eid])]
            )

            bundle_attrs = _materialize_bundle(best.bundle, item_lookup)
            class_name = _derive_class_name(bundle_attrs, type_id, existing_names)
            existing_names.add(class_name)

            classes[class_name] = ClassDef(
                name=class_name,
                inherits="base",
                own_attrs=bundle_attrs,
                entity_ids=covered,
                overrides={},
            )

            covered_set = set(covered)
            unassigned = [eid for eid in unassigned if eid not in covered_set]

        if unassigned:
            classes["_base_only"] = ClassDef(
                name="_base_only",
                inherits="base",
                own_attrs={},
                entity_ids=sorted(unassigned),
                overrides={},
            )

        hierarchies[type_id] = ClassHierarchy(
            base_class=BaseClass(attrs=base_attrs),
            classes=classes,
            subclasses={},
        )

    return hierarchies
