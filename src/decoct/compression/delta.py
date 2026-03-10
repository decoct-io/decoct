"""Delta compression and subclass extraction (§6).

Compresses residual Tier B differences within each primary class.
Promotes positive-gain shared concrete additions into direct subclasses.
"""

from __future__ import annotations

import copy
from collections import Counter
from itertools import combinations
from typing import Any

from decoct.core.canonical import CANONICAL_EQUAL, CANONICAL_KEY, ITEM_KEY
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    ABSENT,
    AttributeProfile,
    ClassHierarchy,
    FinalRole,
    SubclassDef,
)


def _token_estimate_attrs(attrs: dict[str, Any]) -> float:
    """Estimate token cost of a set of attributes."""
    total = 0.0
    for path, value in attrs.items():
        total += len(path) / 4.0 + len(str(value)) / 4.0 + 2
    return total


def _token_estimate_override(delta: dict[str, Any]) -> float:
    """Estimate token cost of an override delta."""
    if not delta:
        return 0.0
    return _token_estimate_attrs(delta) + 4  # override header


def _token_estimate_subclass(
    template_attrs: dict[str, Any],
    covered_entity_ids: list[str],
    subclass_overhead_tokens: int,
) -> float:
    """Estimate token cost of a subclass (§6.3)."""
    return (
        subclass_overhead_tokens
        + _token_estimate_attrs(template_attrs) + 8  # class overhead
        + len(str(covered_entity_ids)) / 4.0  # ID set
    )


def _token_estimate_id_set(entity_ids: list[str]) -> float:
    """Estimate token cost of an ID set."""
    return len(str(entity_ids)) / 4.0


def compute_delta_restricted(
    entity_attrs: dict[str, Any],
    template: dict[str, Any],
    eligible_paths: set[str],
) -> dict[str, Any]:
    """Compute restricted delta between entity attrs and template (§6.4).

    Only considers eligible (Tier B) paths.
    """
    delta: dict[str, Any] = {}
    for path in sorted(eligible_paths):
        entity_val = entity_attrs.get(path)
        template_val = template.get(path)

        if entity_val is not None and template_val is not None:
            if not CANONICAL_EQUAL(entity_val, template_val):
                delta[path] = copy.deepcopy(entity_val)
        elif entity_val is not None and template_val is None:
            delta[path] = copy.deepcopy(entity_val)
        elif entity_val is None and template_val is not None:
            delta[path] = ABSENT

    return delta


def _materialize_bundle(
    bundle_keys: frozenset[tuple[str, str]],
    item_lookup: dict[tuple[str, str], Any],
) -> dict[str, Any]:
    return {
        path: copy.deepcopy(item_lookup[(path, value_key)])
        for path, value_key in sorted(bundle_keys)
    }


def _generate_subclass_candidates(
    entity_ids: list[str],
    vectors: dict[str, frozenset[tuple[str, str]]],
    item_lookup: dict[tuple[str, str], Any],
    min_support: int,
    max_bundle_size: int,
) -> list[tuple[frozenset[tuple[str, str]], list[str]]]:
    """Generate frequent bundle candidates for subclass extraction."""
    counts: Counter[frozenset[tuple[str, str]]] = Counter()

    for eid in entity_ids:
        v = vectors.get(eid, frozenset())
        items = sorted(v, key=lambda kv: (kv[0], kv[1]))
        for size in range(1, min(max_bundle_size, len(items)) + 1):
            for subset in combinations(items, size):
                counts[frozenset(subset)] += 1

    candidates: list[tuple[frozenset[tuple[str, str]], list[str]]] = []
    for bundle, raw_support in counts.items():
        if raw_support < min_support:
            continue
        covered = sorted([eid for eid in entity_ids if bundle.issubset(vectors.get(eid, frozenset()))])
        candidates.append((bundle, covered))

    return candidates


def _derive_subclass_name(
    parent_name: str,
    template_attrs: dict[str, Any],
    existing_names: set[str],
) -> str:
    """Derive subclass name from parent and template attrs (§12)."""
    tokens: list[str] = []
    for path, value in sorted(template_attrs.items()):
        parts = path.split(".")
        token = parts[-1].replace("-", "_")
        if isinstance(value, str) and len(value) < 20:
            val_token = value.replace("-", "_").replace(" ", "_")
            tokens.append(f"{token}_{val_token}")
        else:
            tokens.append(token)
        if len(tokens) >= 2:
            break

    suffix = "_".join(tokens) if tokens else "sub"
    suffix = "".join(c if c.isalnum() or c == "_" else "_" for c in suffix)[:30]
    base_name = f"{parent_name}_{suffix}"

    if base_name not in existing_names:
        return base_name
    i = 1
    while f"{base_name}_{i}" in existing_names:
        i += 1
    return f"{base_name}_{i}"


def delta_compress(
    hierarchies: dict[str, ClassHierarchy],
    graph: EntityGraph,
    profiles: dict[str, dict[str, AttributeProfile]],
    config: EntityGraphConfig,
) -> dict[str, ClassHierarchy]:
    """Apply delta compression to all types (§6.3)."""
    for type_id in sorted(hierarchies.keys()):
        hierarchy = hierarchies[type_id]
        type_profiles = profiles[type_id]
        eligible_paths = {
            p for p, prof in type_profiles.items()
            if prof.final_role == FinalRole.B
        }

        existing_subclass_names: set[str] = set()

        for class_def in sorted(hierarchy.classes.values(), key=lambda c: c.name):
            # Build parent template
            parent_template: dict[str, Any] = {}
            parent_template.update(hierarchy.base_class.attrs)
            parent_template.update(class_def.own_attrs)
            parent_template = {
                p: v for p, v in parent_template.items()
                if p in eligible_paths
            }

            raw_deltas: dict[str, dict[str, Any]] = {}
            vectors: dict[str, frozenset[tuple[str, str]]] = {}
            item_lookup: dict[tuple[str, str], Any] = {}

            for eid in sorted(class_def.entity_ids):
                e = graph.get_entity(eid)
                # Build entity attr values for eligible paths
                entity_b_values: dict[str, Any] = {}
                for p in eligible_paths:
                    if p in e.attributes:
                        entity_b_values[p] = e.attributes[p].value

                delta = compute_delta_restricted(entity_b_values, parent_template, eligible_paths)
                if not delta:
                    continue

                raw_deltas[eid] = delta

                items: list[tuple[str, str]] = []
                for path, value in sorted(delta.items()):
                    if value is ABSENT:
                        continue  # Deletions never become subclass own_attrs in v1
                    k = ITEM_KEY(path, value)
                    if k not in item_lookup:
                        item_lookup[k] = copy.deepcopy(value)
                    items.append(k)

                vectors[eid] = frozenset(items)

            remaining = sorted(raw_deltas.keys())
            class_def.overrides = {}

            while True:
                candidates = _generate_subclass_candidates(
                    entity_ids=remaining,
                    vectors=vectors,
                    item_lookup=item_lookup,
                    min_support=config.min_subclass_size,
                    max_bundle_size=config.max_class_bundle_size,
                )

                if not candidates:
                    break

                scored: list[Any] = []

                for bundle, covered in candidates:
                    template = _materialize_bundle(bundle, item_lookup)

                    residuals: dict[str, dict[str, Any]] = {}
                    for eid in covered:
                        residual: dict[str, Any] = {}
                        for path, value in sorted(raw_deltas[eid].items()):
                            if path in template and CANONICAL_EQUAL(value, template[path]):
                                continue
                            residual[path] = value
                        if residual:
                            residuals[eid] = residual

                    inline_cost = sum(
                        _token_estimate_override(raw_deltas[eid]) for eid in covered
                    )
                    templated_cost = (
                        _token_estimate_subclass(template, covered, config.subclass_overhead_tokens)
                        + sum(_token_estimate_override(d) for d in residuals.values())
                    )

                    gain = inline_cost - templated_cost
                    if gain > 0:
                        scored.append((gain, bundle, template, covered, residuals))

                if not scored:
                    break

                scored.sort(
                    key=lambda s: (
                        -s[0],  # gain
                        -len(s[1]),  # bundle size
                        CANONICAL_KEY(sorted(s[1])),
                    )
                )
                best_gain, best_bundle, best_template, best_covered, best_residuals = scored[0]

                subclass_name = _derive_subclass_name(
                    class_def.name, best_template, existing_subclass_names
                )
                existing_subclass_names.add(subclass_name)

                hierarchy.subclasses[subclass_name] = SubclassDef(
                    name=subclass_name,
                    parent_class=class_def.name,
                    own_attrs=best_template,
                    entity_ids=best_covered,
                    overrides=best_residuals,
                )

                covered_set = set(best_covered)
                remaining = [eid for eid in remaining if eid not in covered_set]

            # Parent overrides for members not lifted into a subclass
            for eid in remaining:
                class_def.overrides[eid] = raw_deltas[eid]

    return hierarchies
