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

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decoct.adapters.base import BaseAdapter
from decoct.adapters.iosxr import IosxrConfigTree
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
from decoct.reconstruction.parser_validation import validate_parser_structure
from decoct.reconstruction.strict_fidelity import validate_strict_fidelity
from decoct.reconstruction.validator import validate_reconstruction
from decoct.secrets.attribute_masker import mask_entity_attributes
from decoct.secrets.detection import DEFAULT_SECRET_PATHS, REDACTED, AuditEntry, detect_secret
from decoct.secrets.document_masker import mask_document


def _mask_leaf_values(
    leaves: list[tuple[str, str]],
    entity_id: str,
    secret_paths: list[str],
    extra_value_patterns: list[tuple[str, re.Pattern[str]]],
    entropy_threshold_b64: float = 4.5,
    entropy_threshold_hex: float = 3.0,
    min_entropy_length: int = 16,
) -> list[tuple[str, str]]:
    """Apply post-flatten secret masking to source leaf values.

    Uses the same detection logic as mask_entity_attributes() so that
    source leaves and entity attributes have identical [REDACTED] values.
    Prefixes entity_id to paths for pattern matching consistency with
    mask_entity_attributes().
    """
    result: list[tuple[str, str]] = []
    for path, value in leaves:
        # Prefix entity_id like mask_entity_attributes does
        full_path = f"{entity_id}.{path}"
        method = detect_secret(
            value, full_path, secret_paths,
            entropy_threshold_b64, entropy_threshold_hex, min_entropy_length,
        )
        if not method and extra_value_patterns:
            for name, pattern in extra_value_patterns:
                if pattern.search(value):
                    method = f"value_pattern:{name}"
                    break
        if method:
            result.append((path, REDACTED))
        else:
            result.append((path, value))
    return result


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
    secrets_audit: list[AuditEntry] = field(default_factory=list)
    source_leaves: dict[str, list[tuple[str, str]]] = field(default_factory=dict)


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

    # Build secret config from adapter
    secret_paths = list(DEFAULT_SECRET_PATHS) + adapter.secret_paths()
    extra_value_patterns = adapter.secret_value_patterns()

    all_audit: list[AuditEntry] = []
    all_source_leaves: dict[str, list[tuple[str, str]]] = {}

    # Phase 0 + Phase 1: Canonicalise with secrets masking
    graph = EntityGraph()
    for source in sources:
        parsed = adapter.parse(source)

        # Layer 1: Parser structure validation (IOS-XR only)
        if isinstance(parsed, IosxrConfigTree) and config.source_fidelity_mode != "skip":
            raw_text = Path(source).read_text(encoding="utf-8")
            validate_parser_structure(raw_text, parsed, source, config.source_fidelity_mode)

        # Phase 0a: Pre-flatten document masking (hybrid-infra, entra-intune)
        # IOS-XR returns IosxrConfigTree (not a dict) — skip pre-flatten
        if isinstance(parsed, tuple):
            # hybrid-infra: (doc, path) tuple
            doc = parsed[0]
            if isinstance(doc, dict):
                all_audit.extend(mask_document(
                    doc,
                    secret_paths=secret_paths,
                    entropy_threshold_b64=config.secrets_entropy_threshold_b64,
                    entropy_threshold_hex=config.secrets_entropy_threshold_hex,
                    min_entropy_length=config.secrets_min_entropy_length,
                ))
        elif isinstance(parsed, dict):
            # entra-intune: plain dict
            all_audit.extend(mask_document(
                parsed,
                secret_paths=secret_paths,
                entropy_threshold_b64=config.secrets_entropy_threshold_b64,
                entropy_threshold_hex=config.secrets_entropy_threshold_hex,
                min_entropy_length=config.secrets_min_entropy_length,
            ))

        # Layer 2: Collect source leaves AFTER pre-flatten masking
        # so source leaves have same [REDACTED] values as entity attributes
        if config.source_fidelity_mode != "skip":
            entity_leaves = adapter.collect_source_leaves(parsed)
            all_source_leaves.update(entity_leaves)

        adapter.extract_entities(parsed, graph)

    # Phase 0b: Post-flatten masking on all entity attributes
    for entity in graph.entities:
        all_audit.extend(mask_entity_attributes(
            entity,
            secret_paths=secret_paths,
            extra_value_patterns=extra_value_patterns,
            entropy_threshold_b64=config.secrets_entropy_threshold_b64,
            entropy_threshold_hex=config.secrets_entropy_threshold_hex,
            min_entropy_length=config.secrets_min_entropy_length,
        ))

    # Phase 0b': Post-flatten masking on source leaves (same patterns as entity attrs)
    if config.source_fidelity_mode != "skip":
        for entity_id in all_source_leaves:
            all_source_leaves[entity_id] = _mask_leaf_values(
                all_source_leaves[entity_id],
                entity_id=entity_id,
                secret_paths=secret_paths,
                extra_value_patterns=extra_value_patterns,
                entropy_threshold_b64=config.secrets_entropy_threshold_b64,
                entropy_threshold_hex=config.secrets_entropy_threshold_hex,
                min_entropy_length=config.secrets_min_entropy_length,
            )

    # Phase 1.5: Strict source fidelity validation (replaces fuzzy Layer 2)
    if config.source_fidelity_mode != "skip":
        validate_strict_fidelity(
            source_leaves_map=all_source_leaves,
            graph=graph,
            mode=config.source_fidelity_mode,
        )

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
        secrets_audit=all_audit,
        source_leaves=all_source_leaves,
    )
