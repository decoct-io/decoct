"""Composite value decomposition (§4).

v1 stub: trivial clustering — one cluster per distinct value.
Template = value itself, no variable positions.
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any

from decoct.analysis.entropy import normalized_entropy, shannon_entropy
from decoct.analysis.tier_classifier import classify_bootstrap_role, classify_final_role
from decoct.core.canonical import CANONICAL_EQUAL, VALUE_KEY
from decoct.core.composite_value import CompositeValue, is_composite_type
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    Attribute,
    AttributeProfile,
    BootstrapSignal,
    CompositeTemplate,
    Entity,
)


def decompose_composites(
    graph: EntityGraph,
    type_map: dict[str, list[Entity]],
    profiles: dict[str, dict[str, AttributeProfile]],
    config: EntityGraphConfig,
) -> tuple[
    EntityGraph,
    dict[str, CompositeTemplate],
    dict[tuple[str, str], list[str]],
    dict[tuple[str, str], Any],
    dict[tuple[str, str], Any],
    dict[str, dict[str, AttributeProfile]],
]:
    """Decompose composite attributes above threshold (§4.3).

    Returns:
        graph, template_index, templates_by_type_path,
        composite_deltas, original_composite_values, updated_profiles
    """
    template_index: dict[str, CompositeTemplate] = {}
    templates_by_type_path: dict[tuple[str, str], list[str]] = {}
    composite_deltas: dict[tuple[str, str], Any] = {}
    original_composite_values: dict[tuple[str, str], Any] = {}

    for type_id in sorted(type_map.keys()):
        entities = type_map[type_id]
        type_profiles = profiles[type_id]

        # Find composite paths above threshold
        composite_paths = [
            p for p, prof in type_profiles.items()
            if is_composite_type(prof.attribute_type)
            and prof.cardinality > config.composite_decompose_threshold
        ]

        for path in sorted(composite_paths):
            # Preserve originals in shadow map
            for e in entities:
                if path in e.attributes and isinstance(e.attributes[path].value, CompositeValue):
                    original_composite_values[(e.id, path)] = copy.deepcopy(e.attributes[path].value)

            # Count value support
            value_support: Counter[str] = Counter()
            for e in entities:
                if path in e.attributes:
                    value_support[VALUE_KEY(e.attributes[path].value)] += 1

            # Build value lookup (first-seen representative)
            value_lookup: dict[str, Any] = {}
            for e in entities:
                if path in e.attributes:
                    k = VALUE_KEY(e.attributes[path].value)
                    if k not in value_lookup:
                        value_lookup[k] = copy.deepcopy(e.attributes[path].value)

            distinct_values = [value_lookup[k] for k in sorted(value_lookup.keys())]

            if len(distinct_values) <= 1:
                continue

            # v1 stub: trivial clustering — one cluster per distinct value
            # Template = value itself, no variable positions
            clusters = [(v, [v]) for v in distinct_values]

            local_ids: list[str] = []
            covered_value_keys: set[str] = set()
            next_template_idx = 0

            for template_val, members in clusters:
                member_keys = [VALUE_KEY(m) for m in members]
                covered_entity_count = sum(value_support[k] for k in member_keys)

                if covered_entity_count < config.min_composite_template_members:
                    continue

                template_id = f"{type_id}.{path}.T{next_template_idx}"
                next_template_idx += 1

                ct = CompositeTemplate(
                    id=template_id,
                    content=copy.deepcopy(template_val),
                    variable_positions=[],
                )
                template_index[template_id] = ct
                local_ids.append(template_id)
                covered_value_keys |= set(member_keys)

            templates_by_type_path[(type_id, path)] = local_ids

            if not local_ids:
                continue

            # Replace entity attribute values with template refs
            for e in entities:
                if path not in e.attributes:
                    continue

                value = e.attributes[path].value
                vk = VALUE_KEY(value)

                if vk not in covered_value_keys:
                    continue

                # v1 stub: exact match (trivial clustering = one value per cluster)
                best_template_id = None
                delta = None
                for tid in local_ids:
                    tmpl = template_index[tid]
                    if CANONICAL_EQUAL(value, tmpl.content):
                        best_template_id = tid
                        delta = None
                        break

                if best_template_id is None:
                    # Should not happen with trivial clustering
                    continue

                e.attributes[path] = Attribute(
                    path=path,
                    value=best_template_id,
                    type="composite_template_ref",
                    source=e.attributes[path].source if path in e.attributes else "",
                )

                if delta:
                    composite_deltas[(e.id, path)] = delta

            # Re-profile after decomposition
            type_profiles[path] = _reprofile_decomposed_attribute(
                entities=entities,
                path=path,
                old_profile=type_profiles[path],
                config=config,
            )

        profiles[type_id] = type_profiles

    return (
        graph,
        template_index,
        templates_by_type_path,
        composite_deltas,
        original_composite_values,
        profiles,
    )


def _reprofile_decomposed_attribute(
    entities: list[Entity],
    path: str,
    old_profile: AttributeProfile,
    config: EntityGraphConfig,
) -> AttributeProfile:
    """Re-profile a decomposed attribute with fresh statistics (§4.4)."""
    current_values = [e.attributes[path].value for e in entities if path in e.attributes]
    n_entities = len(entities)

    freq: Counter[str] = Counter(VALUE_KEY(v) for v in current_values)
    cardinality = len(freq)
    coverage = len(current_values) / n_entities if n_entities > 0 else 0.0
    entropy = shannon_entropy(freq)
    entropy_norm = normalized_entropy(freq)

    lengths = [len(str(v)) / 4.0 for v in current_values]
    len_mean = sum(lengths) / len(lengths) if lengths else 0.0
    len_var = sum((x - len_mean) ** 2 for x in lengths) / len(lengths) if lengths else 0.0

    final_role, confidence = classify_final_role(
        H_norm=entropy_norm,
        cardinality=cardinality,
        n_entities=n_entities,
        coverage=coverage,
        len_mean=len_mean,
        attribute_type="composite_template_ref",
        small_group_floor=config.small_group_floor,
    )

    profile = AttributeProfile(
        path=path,
        cardinality=cardinality,
        entropy=entropy,
        entropy_norm=entropy_norm,
        coverage=coverage,
        value_length_mean=len_mean,
        value_length_var=len_var,
        attribute_type="composite_template_ref",
        final_role=final_role,
        bootstrap_role=BootstrapSignal.NONE,
        entity_type=old_profile.entity_type,
    )

    profile.bootstrap_role = classify_bootstrap_role(profile)
    return profile
