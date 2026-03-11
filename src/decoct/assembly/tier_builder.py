"""Build Tier A/B/C YAML output with ID range compression (§8)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from decoct.assembly.tier_a_models import TierASpec
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    ClassHierarchy,
    CompositeTemplate,
    TierC,
)


def compress_id_ranges(sorted_ids: list[str]) -> list[str]:
    """Compress sorted entity IDs into range notation (§7.4).

    Rules:
    - IDs sharing a common non-numeric prefix with contiguous same-width
      numeric suffixes are collapsed: [BNG-01, BNG-02, BNG-03] → [BNG-01..BNG-03]
    - Non-contiguous or non-numeric IDs listed individually.
    """
    if not sorted_ids:
        return []

    # Parse each ID into (prefix, numeric_suffix, width)
    parsed: list[tuple[str, int | None, int, str]] = []
    suffix_re = re.compile(r"^(.*?)(\d+)$")

    for id_str in sorted_ids:
        m = suffix_re.match(id_str)
        if m:
            prefix = m.group(1)
            num_str = m.group(2)
            parsed.append((prefix, int(num_str), len(num_str), id_str))
        else:
            parsed.append(("", None, 0, id_str))

    result: list[str] = []
    i = 0
    while i < len(parsed):
        prefix, num, width, raw = parsed[i]
        if num is None:
            result.append(raw)
            i += 1
            continue

        # Find contiguous run
        run_start = num
        run_end = num
        j = i + 1
        while j < len(parsed):
            p2, n2, w2, _ = parsed[j]
            if p2 == prefix and w2 == width and n2 is not None and n2 == run_end + 1:
                run_end = n2
                j += 1
            else:
                break

        if run_end > run_start:
            start_str = f"{prefix}{str(run_start).zfill(width)}"
            end_str = f"{prefix}{str(run_end).zfill(width)}"
            result.append(f"{start_str}..{end_str}")
        else:
            result.append(raw)

        i = j

    return result


def expand_id_ranges(compressed: list[str]) -> list[str]:
    """Expand range notation back to individual IDs (§7.4 inverse)."""
    result: list[str] = []
    range_re = re.compile(r"^(.+?)(\d+)\.\.(.+?)(\d+)$")

    for item in compressed:
        m = range_re.match(item)
        if m:
            prefix1 = m.group(1)
            start = int(m.group(2))
            width = len(m.group(2))
            prefix2 = m.group(3)
            end = int(m.group(4))
            if prefix1 == prefix2:
                for n in range(start, end + 1):
                    result.append(f"{prefix1}{str(n).zfill(width)}")
            else:
                result.append(item)
        else:
            result.append(item)

    return result


def build_tier_a(
    graph: EntityGraph,
    type_map: dict[str, list[Any]],
    hierarchies: dict[str, ClassHierarchy],
) -> dict[str, Any]:
    """Build Tier A orientation data (§8.1)."""
    tier_a: dict[str, Any] = {
        "types": {},
        "assertions": {},
    }

    for type_id in sorted(type_map.keys()):
        entities = type_map[type_id]
        hierarchy = hierarchies[type_id]

        # base_only_ratio
        base_only_count = 0
        if "_base_only" in hierarchy.classes:
            base_only_count = len(hierarchy.classes["_base_only"].entity_ids)
        base_only_ratio = base_only_count / len(entities) if entities else 0.0

        tier_a["types"][type_id] = {
            "count": len(entities),
            "classes": len(hierarchy.classes),
            "subclasses": len(hierarchy.subclasses),
            "tier_b_ref": f"{type_id}_classes.yaml",
            "tier_c_ref": f"{type_id}_instances.yaml",
        }

        tier_a["assertions"][type_id] = {
            "base_only_ratio": round(base_only_ratio, 4),
            "max_inheritance_depth": 2,
        }

    # Topology
    tier_a["topology"] = {}
    for type_id in sorted(type_map.keys()):
        entities = type_map[type_id]
        connected_types: set[str] = set()
        for e in entities:
            for label, target in graph.relationships_from(e.id):
                if graph.has_entity(target):
                    target_entity = graph.get_entity(target)
                    if target_entity.discovered_type and target_entity.discovered_type != type_id:
                        connected_types.add(target_entity.discovered_type)
        if connected_types:
            tier_a["topology"][type_id] = sorted(connected_types)

    return tier_a


def scan_projection_index(output_dir: Path) -> dict[str, list[str]]:
    """Scan projections/ subdirectory for available projection YAML files.

    Returns a dict mapping type_id → list of subject filenames (without extension).
    """
    proj_dir = output_dir / "projections"
    if not proj_dir.is_dir():
        return {}

    index: dict[str, list[str]] = {}
    for type_dir in sorted(proj_dir.iterdir()):
        if not type_dir.is_dir():
            continue
        subjects: list[str] = []
        for f in sorted(type_dir.iterdir()):
            if f.suffix in (".yaml", ".yml") and f.stem != "projection_spec":
                subjects.append(f.stem)
        if subjects:
            index[type_dir.name] = subjects

    return index


def merge_tier_a_spec(
    tier_a: dict[str, Any],
    spec: TierASpec,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Merge a TierASpec into an existing tier_a dict, adding LLM-generated guide content.

    This is a separate function from build_tier_a() to keep the pipeline backward-compatible.
    The merge adds:
    - ``guide`` section (corpus_description, how_to_use, reconstruction instructions)
    - Per-type ``summary`` and ``key_differentiators`` into existing ``types[type_id]``
    - ``projections`` index (if output_dir provided, scanned from projections/ subdir)
    """
    merged = dict(tier_a)

    # Guide section at the top
    guide: dict[str, Any] = {
        "corpus_description": spec.corpus_description,
    }
    if spec.how_to_use:
        guide["how_to_use"] = spec.how_to_use

    guide["reconstruction"] = (
        "To reconstruct any entity: start with base_class attributes from Tier B, "
        "overlay class own_attrs, then overlay subclass own_attrs (if assigned), "
        "then apply Tier C instance-specific overrides and instance_attrs."
    )
    merged["guide"] = guide

    # Merge type descriptions into existing types
    types_section = merged.get("types", {})
    for type_id, desc in spec.type_descriptions.items():
        if type_id in types_section:
            types_section[type_id]["summary"] = desc.summary
            if desc.key_differentiators:
                types_section[type_id]["key_differentiators"] = desc.key_differentiators

    # Projection index
    if output_dir is not None:
        proj_index = scan_projection_index(output_dir)
        if proj_index:
            merged["projections"] = proj_index

    return merged


def build_tier_b(
    type_id: str,
    hierarchy: ClassHierarchy,
    tier_c: TierC,
    template_index: dict[str, CompositeTemplate],
) -> dict[str, Any]:
    """Build Tier B class data for a type (§8.2)."""
    tier_b: dict[str, Any] = {}

    # Meta
    total_instances = sum(
        len(data.get("instances", []))
        for data in tier_c.class_assignments.values()
    )
    tier_b["meta"] = {
        "entity_type": type_id,
        "total_instances": total_instances,
        "max_inheritance_depth": 2,
        "tier_c_ref": f"{type_id}_instances.yaml",
    }

    # Base class
    tier_b["base_class"] = dict(hierarchy.base_class.attrs)

    # Classes
    tier_b["classes"] = {}
    for class_name, class_def in sorted(hierarchy.classes.items()):
        cls_data: dict[str, Any] = {
            "inherits": class_def.inherits,
            "own_attrs": dict(class_def.own_attrs),
            "instance_count_inclusive": len(class_def.entity_ids),
        }
        tier_b["classes"][class_name] = cls_data

    # Subclasses
    tier_b["subclasses"] = {}
    for subclass_name, subclass_def in sorted(hierarchy.subclasses.items()):
        sub_data: dict[str, Any] = {
            "parent": subclass_def.parent_class,
            "own_attrs": dict(subclass_def.own_attrs),
            "instance_count": len(subclass_def.entity_ids),
        }
        tier_b["subclasses"][subclass_name] = sub_data

    # Composite templates (grouped by path)
    composite_templates: dict[str, dict[str, Any]] = {}
    for tid, tmpl in sorted(template_index.items()):
        if tid.startswith(type_id + "."):
            # Extract path
            remainder = tid[len(type_id) + 1:]
            path = remainder.rsplit(".", 1)[0]
            composite_templates.setdefault(path, {})[tid] = {
                "elements": tmpl.content.data if hasattr(tmpl.content, "data") else tmpl.content,
            }

    if composite_templates:
        tier_b["composite_templates"] = composite_templates

    # Assertions
    base_only = hierarchy.classes.get("_base_only")
    base_only_ratio = len(base_only.entity_ids) / total_instances if base_only and total_instances else 0.0
    tier_b["assertions"] = {
        "base_only_ratio": round(base_only_ratio, 4),
    }

    return tier_b


def build_tier_c_yaml(
    type_id: str,
    tier_c: TierC,
) -> dict[str, Any]:
    """Build Tier C YAML output for a type (§8.3)."""
    output: dict[str, Any] = {
        "meta": {
            "entity_type": type_id,
            "tier_b_ref": f"{type_id}_classes.yaml",
            "total_instances": sum(
                len(data.get("instances", []))
                for data in tier_c.class_assignments.values()
            ),
        },
    }

    # Class assignments with compressed ID ranges
    output["class_assignments"] = {}
    for name, data in sorted(tier_c.class_assignments.items()):
        output["class_assignments"][name] = {
            "instances": compress_id_ranges(sorted(data["instances"])),
        }

    # Subclass assignments with compressed ID ranges
    if tier_c.subclass_assignments:
        output["subclass_assignments"] = {}
        for name, data in sorted(tier_c.subclass_assignments.items()):
            output["subclass_assignments"][name] = {
                "parent": data["parent"],
                "instances": compress_id_ranges(sorted(data["instances"])),
            }

    # Instance data (phone book)
    if tier_c.instance_data.schema:
        output["instance_data"] = {
            "schema": tier_c.instance_data.schema,
            "records": tier_c.instance_data.records,
        }

    # Instance attrs
    if tier_c.instance_attrs:
        output["instance_attrs"] = tier_c.instance_attrs

    # Relationship store
    if tier_c.relationship_store:
        output["relationship_store"] = tier_c.relationship_store

    # Overrides
    if tier_c.overrides:
        output["overrides"] = tier_c.overrides

    # B composite deltas
    if tier_c.b_composite_deltas:
        output["b_composite_deltas"] = tier_c.b_composite_deltas

    # Foreign keys
    output["foreign_keys"] = tier_c.foreign_keys

    return output
