"""Per-type attribute profiling (§3.3)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from decoct.analysis.entropy import normalized_entropy, shannon_entropy
from decoct.analysis.tier_classifier import classify_bootstrap_role, classify_final_role
from decoct.core.canonical import VALUE_KEY
from decoct.core.composite_value import CompositeValue
from decoct.core.config import EntityGraphConfig
from decoct.core.types import AttributeProfile, BootstrapSignal, Entity


def _token_estimate_value(value: Any) -> float:
    """Rough token estimate for a value (char/4 approximation)."""
    if value is None:
        return 1.0
    if isinstance(value, CompositeValue):
        return len(str(value.data)) / 4.0
    return len(str(value)) / 4.0


def profile_attributes(
    entities: list[Entity],
    type_id: str,
    config: EntityGraphConfig,
) -> dict[str, AttributeProfile]:
    """Compute AttributeProfile for every attribute path across entities of a type.

    Profiles are computed over non-reference attributes only.
    """
    n_entities = len(entities)
    if n_entities == 0:
        return {}

    # Collect all paths and values
    path_values: dict[str, list[Any]] = {}
    path_types: dict[str, str] = {}

    for entity in entities:
        for path, attr in entity.attributes.items():
            if path not in path_values:
                path_values[path] = []
                path_types[path] = attr.type
            path_values[path].append(attr.value)

    profiles: dict[str, AttributeProfile] = {}

    for path in sorted(path_values.keys()):
        values = path_values[path]
        attr_type = path_types[path]

        # Frequency counter using canonical keys
        freq: Counter[str] = Counter()
        for v in values:
            freq[VALUE_KEY(v)] += 1

        cardinality = len(freq)
        coverage = len(values) / n_entities
        entropy = shannon_entropy(freq)
        entropy_norm = normalized_entropy(freq)

        lengths = [_token_estimate_value(v) for v in values]
        len_mean = sum(lengths) / len(lengths) if lengths else 0.0
        len_var = (
            sum((x - len_mean) ** 2 for x in lengths) / len(lengths)
            if lengths
            else 0.0
        )

        final_role, _confidence = classify_final_role(
            H_norm=entropy_norm,
            cardinality=cardinality,
            n_entities=n_entities,
            coverage=coverage,
            len_mean=len_mean,
            attribute_type=attr_type,
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
            attribute_type=attr_type,
            final_role=final_role,
            bootstrap_role=BootstrapSignal.NONE,  # computed below
            entity_type=type_id,
        )

        profile.bootstrap_role = classify_bootstrap_role(profile)

        profiles[path] = profile

    return profiles
