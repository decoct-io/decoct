"""Configuration dataclass for the entity-graph pipeline (§11.3)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EntityGraphConfig:
    """All configurable thresholds for the entity-graph pipeline."""

    # Composite decomposition
    composite_decompose_threshold: int = 5
    min_composite_template_members: int = 2

    # Class extraction
    min_class_support: int = 3
    max_class_bundle_size: int = 3

    # Subclass / delta compression
    min_subclass_size: int = 3
    subclass_overhead_tokens: int = 12

    # Type discovery
    max_anti_unify_variables: int = 3
    small_group_floor: int = 8
    min_refinement_cluster_size: int = 3
    unhinted_jaccard_threshold: float = 0.4

    # FK detection
    fk_overlap_threshold: float = 0.5
    fk_type_compat_threshold: float = 0.3

    # Bootstrap
    max_bootstrap_iterations: int = 5

    # Token estimation
    token_cost_class_ref: int = 4

    # Source fidelity validation (Phase 1)
    source_fidelity_mode: str = "error"  # "error", "warn", or "skip"

    # Secrets masking (Phase 0)
    secrets_entropy_threshold_b64: float = 4.5
    secrets_entropy_threshold_hex: float = 3.0
    secrets_min_entropy_length: int = 16
