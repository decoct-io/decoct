"""Projection generator — slice Tier B/C into per-subject views (R3).

Operates on assembled YAML dicts (output of ``build_tier_b``/``build_tier_c_yaml``),
so CLI can work from output directory without re-running the pipeline.
"""

from __future__ import annotations

from typing import Any

from decoct.assembly.tier_builder import compress_id_ranges, expand_id_ranges
from decoct.projections.models import SubjectSpec
from decoct.projections.path_matcher import collect_matching_paths


def _collect_all_paths(tier_b: dict[str, Any], tier_c: dict[str, Any]) -> set[str]:
    """Collect every attribute path from Tier B and Tier C."""
    paths: set[str] = set()

    # Base class keys
    for key in tier_b.get("base_class", {}):
        paths.add(key)

    # Class own_attrs
    for cls_data in tier_b.get("classes", {}).values():
        for key in cls_data.get("own_attrs", {}):
            paths.add(key)

    # Subclass own_attrs
    for sub_data in tier_b.get("subclasses", {}).values():
        for key in sub_data.get("own_attrs", {}):
            paths.add(key)

    # Composite templates
    for path_group in tier_b.get("composite_templates", {}).values():
        if isinstance(path_group, str):
            paths.add(path_group)
        elif isinstance(path_group, dict):
            for tmpl_data in path_group.values():
                if isinstance(tmpl_data, dict):
                    elements = tmpl_data.get("elements", [])
                    if isinstance(elements, list):
                        for elem in elements:
                            if isinstance(elem, dict):
                                for key in elem:
                                    paths.add(key)
                    elif isinstance(elements, dict):
                        for key in elements:
                            paths.add(key)

    # Phone book schema
    instance_data = tier_c.get("instance_data", {})
    for key in instance_data.get("schema", []):
        paths.add(key)

    # Instance attrs
    for entity_attrs in tier_c.get("instance_attrs", {}).values():
        if isinstance(entity_attrs, dict):
            for key in entity_attrs:
                paths.add(key)

    # Overrides
    for entity_overrides in tier_c.get("overrides", {}).values():
        if isinstance(entity_overrides, dict):
            for key in entity_overrides:
                paths.add(key)

    # B composite deltas
    for entity_deltas in tier_c.get("b_composite_deltas", {}).values():
        if isinstance(entity_deltas, dict):
            for key in entity_deltas:
                paths.add(key)

    return paths


def _filter_dict(d: dict[str, Any], matching: set[str]) -> dict[str, Any]:
    """Keep only keys present in ``matching``."""
    return {k: v for k, v in d.items() if k in matching}


def _expand_all_instances(tier_c: dict[str, Any]) -> set[str]:
    """Get all entity IDs from class and subclass assignments."""
    ids: set[str] = set()
    for cls_data in tier_c.get("class_assignments", {}).values():
        ids.update(expand_id_ranges(cls_data.get("instances", [])))
    return ids


def generate_projection(
    tier_b: dict[str, Any],
    tier_c: dict[str, Any],
    subject: SubjectSpec,
) -> dict[str, Any]:
    """Generate a single subject projection from Tier B/C data.

    Returns a YAML-ready dict containing only the paths matching
    the subject's ``include_paths`` and ``related_paths``.
    """
    # Collect matching paths
    all_paths = _collect_all_paths(tier_b, tier_c)
    related_patterns = [rp.path for rp in subject.related_paths]
    matching = collect_matching_paths(all_paths, subject.include_paths, related_patterns)

    result: dict[str, Any] = {}

    # Meta
    result["meta"] = {
        "subject": subject.name,
        "description": subject.description,
        "source_type": tier_b.get("meta", {}).get("entity_type", ""),
        "total_instances": tier_b.get("meta", {}).get("total_instances", 0),
    }

    # Filter base_class
    base_filtered = _filter_dict(tier_b.get("base_class", {}), matching)
    if base_filtered:
        result["base_class"] = base_filtered

    # Filter classes — keep only those with matching own_attrs
    visible_classes: set[str] = set()
    classes_out: dict[str, Any] = {}
    for cls_name, cls_data in tier_b.get("classes", {}).items():
        filtered_attrs = _filter_dict(cls_data.get("own_attrs", {}), matching)
        if filtered_attrs:
            classes_out[cls_name] = {
                "inherits": cls_data.get("inherits", "base"),
                "own_attrs": filtered_attrs,
                "instance_count_inclusive": cls_data.get("instance_count_inclusive", 0),
            }
            visible_classes.add(cls_name)

    if classes_out:
        result["classes"] = classes_out

    # Filter subclasses — drop if parent class invisible
    subclasses_out: dict[str, Any] = {}
    visible_subclasses: set[str] = set()
    for sub_name, sub_data in tier_b.get("subclasses", {}).items():
        parent = sub_data.get("parent", "")
        if parent not in visible_classes:
            continue
        filtered_attrs = _filter_dict(sub_data.get("own_attrs", {}), matching)
        if filtered_attrs:
            subclasses_out[sub_name] = {
                "parent": parent,
                "own_attrs": filtered_attrs,
                "instance_count": sub_data.get("instance_count", 0),
            }
            visible_subclasses.add(sub_name)

    if subclasses_out:
        result["subclasses"] = subclasses_out

    # Re-derive class assignments — entities from invisible classes → _base_only
    class_assignments = tier_c.get("class_assignments", {})
    assignments_out: dict[str, Any] = {}
    base_only_ids: list[str] = []

    for cls_name, cls_data in class_assignments.items():
        entity_ids = expand_id_ranges(cls_data.get("instances", []))
        if cls_name in visible_classes:
            assignments_out[cls_name] = {
                "instances": compress_id_ranges(sorted(entity_ids)),
            }
        else:
            base_only_ids.extend(entity_ids)

    if base_only_ids:
        existing_base_only = assignments_out.get("_base_only", {}).get("instances", [])
        all_base_only = expand_id_ranges(existing_base_only) + base_only_ids
        assignments_out["_base_only"] = {
            "instances": compress_id_ranges(sorted(all_base_only)),
        }

    if assignments_out:
        result["class_assignments"] = assignments_out

    # Subclass assignments
    subclass_assignments = tier_c.get("subclass_assignments", {})
    sub_assignments_out: dict[str, Any] = {}
    for sub_name, sub_data in subclass_assignments.items():
        if sub_name in visible_subclasses:
            sub_assignments_out[sub_name] = sub_data

    if sub_assignments_out:
        result["subclass_assignments"] = sub_assignments_out

    # Filter phone book — column-slice
    instance_data = tier_c.get("instance_data", {})
    schema = instance_data.get("schema", [])
    records = instance_data.get("records", {})
    if schema and records:
        # Find matching column indices
        col_indices = [i for i, col in enumerate(schema) if col in matching]
        if col_indices:
            result["instance_data"] = {
                "schema": [schema[i] for i in col_indices],
                "records": {
                    entity_id: [row[i] for i in col_indices]
                    for entity_id, row in records.items()
                },
            }

    # Filter instance_attrs
    instance_attrs = tier_c.get("instance_attrs", {})
    if instance_attrs:
        ia_out: dict[str, Any] = {}
        for entity_id, attrs in instance_attrs.items():
            if isinstance(attrs, dict):
                filtered = _filter_dict(attrs, matching)
                if filtered:
                    ia_out[entity_id] = filtered
        if ia_out:
            result["instance_attrs"] = ia_out

    # Filter overrides
    overrides = tier_c.get("overrides", {})
    if overrides:
        ov_out: dict[str, Any] = {}
        for entity_id, deltas in overrides.items():
            if isinstance(deltas, dict):
                filtered = _filter_dict(deltas, matching)
                if filtered:
                    ov_out[entity_id] = filtered
        if ov_out:
            result["overrides"] = ov_out

    # Filter b_composite_deltas
    b_composite_deltas = tier_c.get("b_composite_deltas", {})
    if b_composite_deltas:
        bcd_out: dict[str, Any] = {}
        for entity_id, deltas in b_composite_deltas.items():
            if isinstance(deltas, dict):
                filtered = _filter_dict(deltas, matching)
                if filtered:
                    bcd_out[entity_id] = filtered
        if bcd_out:
            result["b_composite_deltas"] = bcd_out

    # Filter composite_templates
    composite_templates = tier_b.get("composite_templates", {})
    if composite_templates:
        ct_out: dict[str, Any] = {}
        for path_key, templates in composite_templates.items():
            # path_key is the dotted path prefix — check if it matches
            if isinstance(templates, dict):
                # Check if any path in matching starts with this composite path prefix
                has_match = any(
                    p == path_key or p.startswith(path_key + ".")
                    for p in matching
                )
                if has_match:
                    ct_out[path_key] = templates
        if ct_out:
            result["composite_templates"] = ct_out

    return result


def validate_projection(
    projected: dict[str, Any],
    tier_b: dict[str, Any],
    tier_c: dict[str, Any],
) -> list[str]:
    """Validate a projection against source Tier B/C data.

    Returns a list of error strings (empty = valid).
    Checks:
    - Projected paths are a subset of original paths
    - Projected values match original values
    - Entity coverage is preserved (all entities appear somewhere)
    """
    errors: list[str] = []
    original_paths = _collect_all_paths(tier_b, tier_c)

    # Check base_class paths are subset
    for key in projected.get("base_class", {}):
        if key not in original_paths:
            errors.append(f"base_class key '{key}' not in original")

    # Check base_class values match
    orig_base = tier_b.get("base_class", {})
    for key, val in projected.get("base_class", {}).items():
        if key in orig_base and orig_base[key] != val:
            errors.append(f"base_class['{key}'] value mismatch: {val!r} != {orig_base[key]!r}")

    # Check class own_attrs are subset with matching values
    orig_classes = tier_b.get("classes", {})
    for cls_name, cls_data in projected.get("classes", {}).items():
        if cls_name not in orig_classes:
            errors.append(f"class '{cls_name}' not in original")
            continue
        for key, val in cls_data.get("own_attrs", {}).items():
            orig_val = orig_classes[cls_name].get("own_attrs", {}).get(key)
            if orig_val is None:
                errors.append(f"class '{cls_name}' own_attr '{key}' not in original")
            elif orig_val != val:
                errors.append(f"class '{cls_name}' own_attr '{key}' value mismatch")

    # Check entity coverage — all original entities appear in projected assignments
    original_entities = _expand_all_instances(tier_c)
    projected_entities: set[str] = set()
    for cls_data in projected.get("class_assignments", {}).values():
        projected_entities.update(expand_id_ranges(cls_data.get("instances", [])))

    missing = original_entities - projected_entities
    if missing:
        errors.append(f"{len(missing)} entities missing from projection: {sorted(missing)[:5]}...")

    return errors
