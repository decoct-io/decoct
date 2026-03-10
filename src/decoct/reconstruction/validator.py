"""Reconstruction validation: structural invariants + per-entity fidelity (§10)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from decoct.core.canonical import CANONICAL_EQUAL
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    ABSENT,
    MISSING,
    ClassHierarchy,
    CompositeTemplate,
    TierC,
)
from decoct.reconstruction.reconstitute import (
    _find_parent_class,
    _find_subclass,
    reconstitute_entity,
)


@dataclass
class AttributeMismatch:
    entity_id: str
    path: str
    original: Any
    reconstructed: Any

    def __str__(self) -> str:
        return f"AttributeMismatch({self.entity_id}, {self.path})"


@dataclass
class RelationshipMismatch:
    entity_id: str
    original: list[tuple[str, str]]
    reconstructed: list[tuple[str, str]]

    def __str__(self) -> str:
        return f"RelationshipMismatch({self.entity_id})"


class ReconstructionError(Exception):
    """Raised when reconstruction validation fails."""

    def __init__(self, message: str, mismatches: list[Any]) -> None:
        self.mismatches = mismatches
        super().__init__(f"{message}: {[str(m) for m in mismatches[:10]]}")


class StructuralInvariantError(Exception):
    """Raised when structural invariant checks fail."""

    def __init__(self, message: str, errors: list[Any]) -> None:
        self.errors = errors
        super().__init__(f"{message}: {[str(e) for e in errors[:10]]}")


def _resolve_b_layer_value(
    eid: str,
    path: str,
    hierarchy: ClassHierarchy,
    tier_c: TierC,
) -> Any:
    """Walk B-layer precedence chain without template expansion (§10.2 helper)."""
    value = None

    # base_class
    if path in hierarchy.base_class.attrs:
        value = hierarchy.base_class.attrs[path]

    # primary class
    class_name = _find_parent_class(eid, tier_c.class_assignments)
    if class_name and class_name in hierarchy.classes:
        if path in hierarchy.classes[class_name].own_attrs:
            value = hierarchy.classes[class_name].own_attrs[path]

    # subclass
    subclass_name = _find_subclass(eid, tier_c.subclass_assignments)
    if subclass_name and subclass_name in hierarchy.subclasses:
        if path in hierarchy.subclasses[subclass_name].own_attrs:
            value = hierarchy.subclasses[subclass_name].own_attrs[path]

    # override
    if eid in tier_c.overrides:
        delta = tier_c.overrides[eid].get("delta", {})
        if path in delta:
            if delta[path] is ABSENT:
                value = None
            else:
                value = delta[path]

    return value


def validate_structural_invariants(
    graph: EntityGraph,
    hierarchies: dict[str, ClassHierarchy],
    tier_c_files: dict[str, TierC],
    template_index: dict[str, CompositeTemplate],
) -> None:
    """Validate structural invariants of Tier B/C (§10.2)."""
    errors: list[Any] = []

    for type_id in sorted(hierarchies.keys()):
        hierarchy = hierarchies[type_id]
        tier_c = tier_c_files[type_id]

        expected_ids = sorted([
            e.id for e in graph.entities
            if e.discovered_type == type_id
        ])
        expected_set = set(expected_ids)

        class_ids: dict[str, set[str]] = {}
        for name, data in sorted(tier_c.class_assignments.items()):
            class_ids[name] = set(data.get("instances", []))

        subclass_ids: dict[str, set[str]] = {}
        for name, data in sorted(tier_c.subclass_assignments.items()):
            subclass_ids[name] = set(data.get("instances", []))

        # 1. No entity in more than one primary class
        seen: set[str] = set()
        for class_name, ids in sorted(class_ids.items()):
            overlap = ids & seen
            if overlap:
                errors.append(f"MultiClassAssignment: {type_id}/{class_name}: {overlap}")
            seen |= ids

        # 2. Primary class coverage is exact
        if seen != expected_set:
            missing = expected_set - seen
            extra = seen - expected_set
            errors.append(f"ClassCoverageError: {type_id}: missing={missing}, extra={extra}")

        # 3. Subclass parent containment
        for subclass_name, ids in sorted(subclass_ids.items()):
            parent = tier_c.subclass_assignments[subclass_name].get("parent", "")
            if parent not in class_ids:
                errors.append(f"InvalidSubclassParent: {type_id}/{subclass_name} parent={parent}")
                continue
            orphans = ids - class_ids[parent]
            if orphans:
                errors.append(f"SubclassOrphan: {type_id}/{subclass_name}: {orphans}")

        # 4. No entity in more than one subclass
        seen_sub: set[str] = set()
        for subclass_name, ids in sorted(subclass_ids.items()):
            overlap = ids & seen_sub
            if overlap:
                errors.append(f"MultiSubclassAssignment: {type_id}/{subclass_name}: {overlap}")
            seen_sub |= ids

        # 5. Max inheritance depth = 2
        subclass_names = set(hierarchy.subclasses.keys())
        for subclass_name, subclass_def in sorted(hierarchy.subclasses.items()):
            if subclass_def.parent_class in subclass_names:
                errors.append(f"DepthViolation: {type_id}/{subclass_name}")

        # 6. Override owners are valid
        valid_owners = set(hierarchy.classes.keys()) | set(hierarchy.subclasses.keys())
        for eid, override_data in sorted(tier_c.overrides.items()):
            owner = override_data.get("owner", "")
            if owner not in valid_owners:
                errors.append(f"InvalidOverrideOwner: {type_id}/{eid} owner={owner}")

        # 7. Phone-book rectangular and dense
        schema = tier_c.instance_data.schema
        records = tier_c.instance_data.records

        for eid, row in sorted(records.items()):
            if len(row) != len(schema):
                errors.append(f"PhoneBookRowLength: {type_id}/{eid}: {len(schema)} vs {len(row)}")

        if schema and set(records.keys()) != expected_set:
            missing_pb = expected_set - set(records.keys())
            errors.append(f"PhoneBookCoverage: {type_id}: missing={missing_pb}")

        if not schema and records:
            errors.append(f"PhoneBookEmptySchemaWithRecords: {type_id}: {len(records)} records")

        # 8. No path in both phone book and instance_attrs
        schema_set = set(schema)
        for ia_eid in sorted(tier_c.instance_attrs.keys()):
            ia_row = tier_c.instance_attrs[ia_eid]
            overlap = set(ia_row.keys()) & schema_set
            if overlap:
                errors.append(f"DuplicateCPathEncoding: {type_id}/{ia_eid}: {overlap}")

    if errors:
        raise StructuralInvariantError(f"{len(errors)} structural errors", errors)


def validate_reconstruction(
    graph: EntityGraph,
    hierarchies: dict[str, ClassHierarchy],
    tier_c_files: dict[str, TierC],
    template_index: dict[str, CompositeTemplate],
    original_composite_values: dict[tuple[str, str], Any],
) -> None:
    """Validate reconstruction of all entities (§10.3)."""
    # Structural invariants first
    validate_structural_invariants(graph, hierarchies, tier_c_files, template_index)

    mismatches: list[Any] = []

    for entity in sorted(graph.entities, key=lambda x: x.id):
        entity_type = entity.discovered_type
        if entity_type is None:
            mismatches.append(AttributeMismatch(entity.id, "__type__", None, None))
            continue

        reconstructed = reconstitute_entity(
            entity_type=entity_type,
            entity_id=entity.id,
            hierarchy=hierarchies[entity_type],
            tier_c=tier_c_files[entity_type],
            template_index=template_index,
        )

        all_paths = sorted(set(entity.attributes.keys()) | set(reconstructed.attributes.keys()))

        for path in all_paths:
            # Check shadow map first for decomposed composites
            if (entity.id, path) in original_composite_values:
                original_val = original_composite_values[(entity.id, path)]
                original_present = True
            elif path in entity.attributes:
                original_val = entity.attributes[path].value
                original_present = True
            else:
                original_val = MISSING
                original_present = False

            if path in reconstructed.attributes:
                recon_val = reconstructed.attributes[path]
                recon_present = True
            else:
                recon_val = MISSING
                recon_present = False

            if original_present != recon_present:
                mismatches.append(AttributeMismatch(entity.id, path, original_val, recon_val))
                continue

            if original_present and not CANONICAL_EQUAL(original_val, recon_val):
                mismatches.append(AttributeMismatch(entity.id, path, original_val, recon_val))

        # Compare relationships
        original_rels = sorted(graph.relationships_from(entity.id))
        recon_rels = sorted(reconstructed.relationships)

        if original_rels != recon_rels:
            mismatches.append(RelationshipMismatch(entity.id, original_rels, recon_rels))

    if mismatches:
        raise ReconstructionError(
            f"{len(mismatches)} mismatches",
            mismatches,
        )
