"""Reconstruction and layered view helpers for the API."""

from __future__ import annotations

import copy
from typing import Any

from decoct.core.composite_value import CompositeValue
from decoct.core.types import (
    ABSENT,
    ClassHierarchy,
    CompositeTemplate,
    TierC,
)
from decoct.reconstruction.reconstitute import reconstitute_entity


def _serialize_value(value: Any) -> Any:
    """Convert CompositeValue and other non-JSON types to plain dicts/lists."""
    if isinstance(value, CompositeValue):
        return value.data
    return value


def reconstruct_entity_json(
    type_id: str,
    entity_id: str,
    hierarchy: ClassHierarchy,
    tier_c: TierC,
    template_index: dict[str, CompositeTemplate],
) -> dict[str, Any]:
    """Reconstruct an entity and return JSON-serializable attributes."""
    result = reconstitute_entity(type_id, entity_id, hierarchy, tier_c, template_index)
    return {
        "entity_id": result.id,
        "entity_type": result.entity_type,
        "attributes": {k: _serialize_value(v) for k, v in result.attributes.items()},
        "relationships": [list(r) for r in result.relationships],
    }


def _build_path_template_ids(
    entity_type: str,
    template_index: dict[str, CompositeTemplate],
) -> dict[str, set[str]]:
    """Build path → template_ids mapping (same logic as reconstitute.py)."""
    path_template_ids: dict[str, set[str]] = {}
    for tid in template_index:
        parts = tid.split(".")
        if len(parts) >= 3 and parts[-1].startswith("T"):
            if tid.startswith(entity_type + "."):
                remainder = tid[len(entity_type) + 1:]
                path = remainder.rsplit(".", 1)[0]
                path_template_ids.setdefault(path, set()).add(tid)
    return path_template_ids


def build_layered_view(
    type_id: str,
    entity_id: str,
    hierarchy: ClassHierarchy,
    tier_c: TierC,
    template_index: dict[str, CompositeTemplate],
) -> dict[str, dict[str, Any]]:
    """Build a layered view of an entity's attributes showing the source of each.

    Returns a dict mapping attribute path → {value, source, class_name?}.
    Sources: base_class, class, subclass, override, composite_template,
             instance_attr, phone_book.
    """
    layers: dict[str, dict[str, Any]] = {}
    path_template_ids = _build_path_template_ids(type_id, template_index)

    # Track which paths come from which layer
    # 1. Base class
    for p, v in hierarchy.base_class.attrs.items():
        layers[p] = {"value": _serialize_value(copy.deepcopy(v)), "source": "base_class"}

    # 2. Primary class
    class_name: str | None = None
    for cn, cdata in tier_c.class_assignments.items():
        if entity_id in cdata.get("instances", []):
            class_name = cn
            break

    if class_name and class_name in hierarchy.classes:
        class_def = hierarchy.classes[class_name]
        for p, v in class_def.own_attrs.items():
            layers[p] = {
                "value": _serialize_value(copy.deepcopy(v)),
                "source": "class",
                "class_name": class_name,
            }

    # 3. Subclass
    subclass_name: str | None = None
    for sn, sdata in tier_c.subclass_assignments.items():
        if entity_id in sdata.get("instances", []):
            subclass_name = sn
            break

    if subclass_name and subclass_name in hierarchy.subclasses:
        subclass_def = hierarchy.subclasses[subclass_name]
        for p, v in subclass_def.own_attrs.items():
            layers[p] = {
                "value": _serialize_value(copy.deepcopy(v)),
                "source": "subclass",
                "class_name": subclass_name,
            }

    # 4. Per-instance B overrides
    if entity_id in tier_c.overrides:
        override_data = tier_c.overrides[entity_id]
        owner = override_data.get("owner", "")
        delta = override_data.get("delta", {})
        for path in sorted(delta.keys()):
            value = delta[path]
            if value is ABSENT:
                layers.pop(path, None)
            else:
                entry: dict[str, Any] = {
                    "value": _serialize_value(copy.deepcopy(value)),
                    "source": "override",
                }
                if owner:
                    entry["class_name"] = owner
                layers[path] = entry

    # 5. B-layer composite template expansion
    for path in sorted(path_template_ids.keys()):
        if path not in layers:
            continue
        value = layers[path]["value"]
        if isinstance(value, str) and value in path_template_ids[path]:
            template = template_index[value]
            layers[path] = {
                "value": _serialize_value(copy.deepcopy(template.content)),
                "source": "composite_template",
                "class_name": value,
            }

    # 6. C-layer instance_attrs
    if entity_id in tier_c.instance_attrs:
        for path in sorted(tier_c.instance_attrs[entity_id].keys()):
            value = tier_c.instance_attrs[entity_id][path]
            layers[path] = {
                "value": _serialize_value(copy.deepcopy(value)),
                "source": "instance_attr",
            }

    # 7. C-layer phone book
    if entity_id in tier_c.instance_data.records:
        record = tier_c.instance_data.records[entity_id]
        for i, path in enumerate(tier_c.instance_data.schema):
            layers[path] = {
                "value": copy.deepcopy(record[i]),
                "source": "phone_book",
            }

    return layers
