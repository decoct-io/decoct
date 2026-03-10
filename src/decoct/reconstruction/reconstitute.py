"""Entity reconstitution from Tier B + Tier C (§9)."""

from __future__ import annotations

import copy
from typing import Any

from decoct.core.types import (
    ABSENT,
    ClassHierarchy,
    CompositeTemplate,
    ReconstructedEntity,
    TierC,
)


def _find_parent_class(entity_id: str, class_assignments: dict[str, dict[str, Any]]) -> str | None:
    """Find the primary class for an entity."""
    for class_name, data in class_assignments.items():
        instances = data.get("instances", [])
        if entity_id in instances:
            return class_name
    return None


def _find_subclass(entity_id: str, subclass_assignments: dict[str, dict[str, Any]]) -> str | None:
    """Find the subclass for an entity, if any."""
    for subclass_name, data in subclass_assignments.items():
        instances = data.get("instances", [])
        if entity_id in instances:
            return subclass_name
    return None


def _is_encoded_c_template_value(
    path: str,
    encoded_value: Any,
    path_template_ids: dict[str, set[str]],
) -> bool:
    """Check if a value is a reserved-form encoded composite template ref (§9.1)."""
    return (
        path in path_template_ids
        and isinstance(encoded_value, dict)
        and "template" in encoded_value
        and set(encoded_value.keys()).issubset({"template", "delta"})
        and encoded_value["template"] in path_template_ids[path]
    )


def _apply_composite_delta(base: Any, delta: Any) -> None:
    """Apply a composite delta to a base value.

    v1 stub: positional replacement on list/dict structures.
    """
    if isinstance(delta, dict) and isinstance(base, dict):
        for key, val in delta.items():
            base[key] = val
    elif isinstance(delta, dict) and isinstance(base, list):
        for key, val in delta.items():
            # key like "position_0" → index 0
            if isinstance(key, str) and key.startswith("position_"):
                idx = int(key.split("_", 1)[1])
                if idx < len(base):
                    base[idx] = val


def _materialize_c_instance_value(
    path: str,
    encoded_value: Any,
    path_template_ids: dict[str, set[str]],
    template_index: dict[str, CompositeTemplate],
) -> Any:
    """Materialize a Tier C instance value (§9.1)."""
    if _is_encoded_c_template_value(path, encoded_value, path_template_ids):
        template = template_index[encoded_value["template"]]
        out = copy.deepcopy(template.content)
        if "delta" in encoded_value:
            _apply_composite_delta(out, encoded_value["delta"])
        return out
    return copy.deepcopy(encoded_value)


def reconstitute_entity(
    entity_type: str,
    entity_id: str,
    hierarchy: ClassHierarchy,
    tier_c: TierC,
    template_index: dict[str, CompositeTemplate],
) -> ReconstructedEntity:
    """Reconstruct an entity from Tier B + Tier C (§9.1).

    Attribute precedence:
    1. base_class
    2. primary class own_attrs
    3. subclass own_attrs (if any)
    4. per-instance B overrides
    5. B-layer composite template expansion + delta application
    6. C-layer instance_attrs
    7. C-layer dense phone-book attributes
    """
    attrs: dict[str, Any] = {}

    # Build path→template_ids mapping from composite_templates
    # In our implementation, composite_templates are stored in template_index
    # We need to build this from the template IDs
    path_template_ids: dict[str, set[str]] = {}
    for tid, tmpl in template_index.items():
        # Extract path from template ID: "type.path.T0" → path
        parts = tid.split(".")
        # type_id.path.T0 — find everything between type_id and T{n}
        # Template IDs: "{type_id}.{path}.T{index}"
        if len(parts) >= 3 and parts[-1].startswith("T"):
            # path is everything between type_id and T{n}
            # But type_id itself may contain dots, so we need another approach
            # Use the discovered_type to strip the prefix
            if tid.startswith(entity_type + "."):
                remainder = tid[len(entity_type) + 1:]
                # remainder is "path.T{n}"
                path = remainder.rsplit(".", 1)[0]
                path_template_ids.setdefault(path, set()).add(tid)

    # 1. Base class
    for p, v in hierarchy.base_class.attrs.items():
        attrs[p] = copy.deepcopy(v)

    # 2. Primary class
    class_name = _find_parent_class(entity_id, tier_c.class_assignments)
    if class_name and class_name in hierarchy.classes:
        class_def = hierarchy.classes[class_name]
        for p, v in class_def.own_attrs.items():
            attrs[p] = copy.deepcopy(v)

    # 3. Subclass, if any
    subclass_name = _find_subclass(entity_id, tier_c.subclass_assignments)
    if subclass_name and subclass_name in hierarchy.subclasses:
        subclass_def = hierarchy.subclasses[subclass_name]
        for p, v in subclass_def.own_attrs.items():
            attrs[p] = copy.deepcopy(v)

    # 4. Per-instance B overrides
    if entity_id in tier_c.overrides:
        override_data = tier_c.overrides[entity_id]
        delta = override_data.get("delta", {})
        for path in sorted(delta.keys()):
            value = delta[path]
            if value is ABSENT:
                attrs.pop(path, None)
            else:
                attrs[path] = copy.deepcopy(value)

    # 5. Expand B-layer template refs
    for path in sorted(path_template_ids.keys()):
        if path not in attrs:
            continue
        value = attrs[path]
        if isinstance(value, str) and value in path_template_ids[path]:
            template = template_index[value]
            attrs[path] = copy.deepcopy(template.content)

            if (entity_id in tier_c.b_composite_deltas
                    and path in tier_c.b_composite_deltas[entity_id]):
                delta_data = tier_c.b_composite_deltas[entity_id][path]
                _apply_composite_delta(attrs[path], delta_data.get("delta", {}))

    # 6. C-layer instance_attrs
    if entity_id in tier_c.instance_attrs:
        for path in sorted(tier_c.instance_attrs[entity_id].keys()):
            encoded_value = tier_c.instance_attrs[entity_id][path]
            attrs[path] = _materialize_c_instance_value(
                path, encoded_value, path_template_ids, template_index,
            )

    # 7. C-layer phone book
    if entity_id in tier_c.instance_data.records:
        record = tier_c.instance_data.records[entity_id]
        for i, path in enumerate(tier_c.instance_data.schema):
            attrs[path] = copy.deepcopy(record[i])

    # Relationships
    relationships: list[tuple[str, str]] = []
    if entity_id in tier_c.relationship_store:
        relationships = [
            (edge["label"], edge["target"])
            for edge in tier_c.relationship_store[entity_id]
        ]

    return ReconstructedEntity(
        id=entity_id,
        entity_type=entity_type,
        attributes=attrs,
        relationships=sorted(relationships),
    )
