"""Build Tier C: phone book, instance_attrs, relationships, overrides (§7)."""

from __future__ import annotations

import copy
from typing import Any

from decoct.analysis.tier_classifier import select_tier_c_storage
from decoct.compression.inversion import detect_foreign_keys_on_scalar_attrs
from decoct.compression.phone_book import build_phone_book_dense
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    AttributeProfile,
    ClassHierarchy,
    FinalRole,
    TierC,
    TierCStorage,
)


def _encode_c_instance_value(
    eid: str,
    path: str,
    entity_attrs: dict[str, Any],
    composite_deltas: dict[tuple[str, str], Any],
    attr_type: str,
) -> Any:
    """Encode a Tier C instance value (§7.3)."""
    value = entity_attrs.get(path)
    if value is None:
        return None

    if attr_type == "composite_template_ref" and isinstance(value, str):
        out: dict[str, Any] = {"template": value}
        if (eid, path) in composite_deltas:
            out["delta"] = copy.deepcopy(composite_deltas[(eid, path)])
        return out

    return copy.deepcopy(value)


def build_tier_c(
    type_id: str,
    hierarchy: ClassHierarchy,
    graph: EntityGraph,
    profiles: dict[str, AttributeProfile],
    composite_deltas: dict[tuple[str, str], Any],
    config: EntityGraphConfig,
) -> TierC:
    """Build complete Tier C data for a type (§7.3)."""
    type_profiles = profiles
    entities = sorted(
        [e for e in graph.entities if e.discovered_type == type_id],
        key=lambda x: x.id,
    )

    # 1. Inclusive parent class assignments
    class_assignments: dict[str, dict[str, Any]] = {}
    for class_def in sorted(hierarchy.classes.values(), key=lambda c: c.name):
        class_assignments[class_def.name] = {
            "instances": sorted(class_def.entity_ids),
        }

    # 2. Subclass assignments
    subclass_assignments: dict[str, dict[str, Any]] = {}
    for subclass_def in sorted(hierarchy.subclasses.values(), key=lambda s: s.name):
        subclass_assignments[subclass_def.name] = {
            "parent": subclass_def.parent_class,
            "instances": sorted(subclass_def.entity_ids),
        }

    # 3. Tier C storage split
    phone_book_paths = sorted([
        p for p, prof in type_profiles.items()
        if select_tier_c_storage(prof) == TierCStorage.PHONE_BOOK
    ])

    instance_attr_paths = sorted([
        p for p, prof in type_profiles.items()
        if select_tier_c_storage(prof) == TierCStorage.INSTANCE_ATTRS
    ])

    phone_book = build_phone_book_dense(entities, phone_book_paths)

    instance_attrs: dict[str, dict[str, Any]] = {}
    for e in entities:
        row: dict[str, Any] = {}
        for path in instance_attr_paths:
            if path not in e.attributes:
                continue
            attr_type = type_profiles[path].attribute_type if path in type_profiles else "string"
            row[path] = _encode_c_instance_value(
                e.id, path, {p: a.value for p, a in e.attributes.items()},
                composite_deltas, attr_type,
            )
        if row:
            instance_attrs[e.id] = row

    # 4. Relationship store
    relationship_store: dict[str, list[dict[str, str]]] = {}
    for e in entities:
        rels = sorted(
            [{"label": label, "target": target_id}
             for label, target_id in graph.relationships_from(e.id)],
            key=lambda r: (r["label"], r["target"]),
        )
        if rels:
            relationship_store[e.id] = rels

    # 5. Flatten B overrides from parents and subclasses
    overrides: dict[str, dict[str, Any]] = {}
    for class_def in sorted(hierarchy.classes.values(), key=lambda c: c.name):
        for eid in sorted(class_def.overrides.keys()):
            delta = class_def.overrides[eid]
            overrides[eid] = {"owner": class_def.name, "delta": delta}

    for subclass_def in sorted(hierarchy.subclasses.values(), key=lambda s: s.name):
        for eid in sorted(subclass_def.overrides.keys()):
            delta = subclass_def.overrides[eid]
            overrides[eid] = {"owner": subclass_def.name, "delta": delta}

    # 6. B-layer composite deltas only
    b_composite_deltas: dict[str, dict[str, Any]] = {}
    for (eid, path) in sorted(composite_deltas.keys()):
        if path in type_profiles and type_profiles[path].final_role == FinalRole.B:
            delta_val = composite_deltas[(eid, path)]
            b_composite_deltas.setdefault(eid, {})[path] = {"delta": copy.deepcopy(delta_val)}

    # 7. FK detection
    fk_map = detect_foreign_keys_on_scalar_attrs(graph, type_profiles, type_id)

    return TierC(
        class_assignments=class_assignments,
        subclass_assignments=subclass_assignments,
        instance_data=phone_book,
        instance_attrs=instance_attrs,
        relationship_store=relationship_store,
        overrides=overrides,
        b_composite_deltas=b_composite_deltas,
        foreign_keys=fk_map,
    )
