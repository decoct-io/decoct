"""OutputStore: reads pre-computed entity-graph output and builds indexes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.assembly.tier_builder import expand_id_ranges
from decoct.core.types import (
    BaseClass,
    ClassDef,
    ClassHierarchy,
    CompositeTemplate,
    PhoneBook,
    SubclassDef,
    TierC,
)


def _hydrate_hierarchy(
    classes_data: dict[str, Any], type_id: str,
) -> tuple[ClassHierarchy, dict[str, CompositeTemplate]]:
    """Convert a classes YAML dict into ClassHierarchy + template index."""
    base_attrs = classes_data.get("base_class", {}) or {}
    base_class = BaseClass(attrs=dict(base_attrs))

    classes: dict[str, ClassDef] = {}
    for name, cdata in (classes_data.get("classes", {}) or {}).items():
        classes[name] = ClassDef(
            name=name,
            inherits=cdata.get("inherits", "base"),
            own_attrs=dict(cdata.get("own_attrs", {}) or {}),
            entity_ids=[],  # populated from Tier C
        )

    subclasses: dict[str, SubclassDef] = {}
    for name, sdata in (classes_data.get("subclasses", {}) or {}).items():
        subclasses[name] = SubclassDef(
            name=name,
            parent_class=sdata.get("parent", ""),
            own_attrs=dict(sdata.get("own_attrs", {}) or {}),
            entity_ids=[],  # populated from Tier C
        )

    template_index: dict[str, CompositeTemplate] = {}
    for path, templates in (classes_data.get("composite_templates", {}) or {}).items():
        if not isinstance(templates, dict):
            continue
        for tid, tdata in templates.items():
            content = tdata.get("elements", tdata.get("content"))
            decomp_kind = tdata.get("decomp_kind", "")
            # Detect map_inner: if elements is a flat dict of strings (base template)
            # and the template ID naming suggests inner decomposition
            if isinstance(content, dict) and all(isinstance(v, str) for v in content.values()):
                decomp_kind = "map_inner"
            template_index[tid] = CompositeTemplate(
                id=tid,
                content=content,
                decomp_kind=decomp_kind,
            )

    hierarchy = ClassHierarchy(
        base_class=base_class,
        classes=classes,
        subclasses=subclasses,
    )
    return hierarchy, template_index


def _hydrate_tier_c(instances_data: dict[str, Any]) -> TierC:
    """Convert an instances YAML dict into a TierC dataclass."""
    # Expand compressed ID ranges in class_assignments
    class_assignments: dict[str, dict[str, Any]] = {}
    for name, cdata in (instances_data.get("class_assignments", {}) or {}).items():
        raw_instances = cdata.get("instances", [])
        class_assignments[name] = {
            "instances": expand_id_ranges(raw_instances),
        }

    # Expand compressed ID ranges in subclass_assignments
    subclass_assignments: dict[str, dict[str, Any]] = {}
    for name, sdata in (instances_data.get("subclass_assignments", {}) or {}).items():
        raw_instances = sdata.get("instances", [])
        subclass_assignments[name] = {
            "parent": sdata.get("parent", ""),
            "instances": expand_id_ranges(raw_instances),
        }

    # Phone book
    idata = instances_data.get("instance_data", {}) or {}
    phone_book = PhoneBook(
        schema=idata.get("schema", []) or [],
        records=idata.get("records", {}) or {},
    )

    return TierC(
        class_assignments=class_assignments,
        subclass_assignments=subclass_assignments,
        instance_data=phone_book,
        instance_attrs=instances_data.get("instance_attrs", {}) or {},
        relationship_store=instances_data.get("relationship_store", {}) or {},
        overrides=instances_data.get("overrides", {}) or {},
        b_composite_deltas=instances_data.get("b_composite_deltas", {}) or {},
        foreign_keys=instances_data.get("foreign_keys", {}) or {},
    )


def _build_entity_index(
    tier_c: TierC,
) -> dict[str, tuple[str | None, str | None]]:
    """Build entity_id → (class_name, subclass_name) index from TierC."""
    index: dict[str, tuple[str | None, str | None]] = {}

    for class_name, cdata in tier_c.class_assignments.items():
        for eid in cdata.get("instances", []):
            index[eid] = (class_name, None)

    for subclass_name, sdata in tier_c.subclass_assignments.items():
        for eid in sdata.get("instances", []):
            prev = index.get(eid, (None, None))
            index[eid] = (prev[0], subclass_name)

    return index


class OutputStore:
    """Reads and caches pre-computed entity-graph output for the API."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.tier_a: dict[str, Any] = {}
        self.type_ids: list[str] = []

        # Per-type caches
        self.classes_raw: dict[str, dict[str, Any]] = {}
        self.instances_raw: dict[str, dict[str, Any]] = {}
        self.hierarchies: dict[str, ClassHierarchy] = {}
        self.tier_c_data: dict[str, TierC] = {}
        self.template_indexes: dict[str, dict[str, CompositeTemplate]] = {}
        self.entity_indexes: dict[str, dict[str, tuple[str | None, str | None]]] = {}

        # Projections index: type_id → list of subject names
        self.projection_index: dict[str, list[str]] = {}

    def load(self) -> None:
        """Load all output files and build indexes."""
        yaml = YAML(typ="safe")

        # Load Tier A
        tier_a_path = self.output_dir / "tier_a.yaml"
        if not tier_a_path.exists():
            msg = f"tier_a.yaml not found in {self.output_dir}"
            raise FileNotFoundError(msg)

        self.tier_a = yaml.load(tier_a_path.read_text()) or {}
        types_section = self.tier_a.get("types", {})
        self.type_ids = sorted(types_section.keys())

        # Load per-type data
        for type_id in self.type_ids:
            type_info = types_section[type_id]
            classes_file = self.output_dir / type_info.get("tier_b_ref", f"{type_id}_classes.yaml")
            instances_file = self.output_dir / type_info.get("tier_c_ref", f"{type_id}_instances.yaml")

            if classes_file.exists():
                classes_data = yaml.load(classes_file.read_text()) or {}
                self.classes_raw[type_id] = classes_data
                hierarchy, templates = _hydrate_hierarchy(classes_data, type_id)
                self.hierarchies[type_id] = hierarchy
                self.template_indexes[type_id] = templates
            else:
                self.classes_raw[type_id] = {}
                self.hierarchies[type_id] = ClassHierarchy()
                self.template_indexes[type_id] = {}

            if instances_file.exists():
                instances_data = yaml.load(instances_file.read_text()) or {}
                self.instances_raw[type_id] = instances_data
                tier_c = _hydrate_tier_c(instances_data)
                self.tier_c_data[type_id] = tier_c

                # Populate entity_ids on ClassDef/SubclassDef
                hierarchy = self.hierarchies[type_id]
                for class_name, cdata in tier_c.class_assignments.items():
                    if class_name in hierarchy.classes:
                        hierarchy.classes[class_name].entity_ids = cdata["instances"]
                for subclass_name, sdata in tier_c.subclass_assignments.items():
                    if subclass_name in hierarchy.subclasses:
                        hierarchy.subclasses[subclass_name].entity_ids = sdata["instances"]

                self.entity_indexes[type_id] = _build_entity_index(tier_c)
            else:
                self.instances_raw[type_id] = {}
                self.tier_c_data[type_id] = TierC()
                self.entity_indexes[type_id] = {}

        # Scan projections
        self._scan_projections()

    def _scan_projections(self) -> None:
        """Scan projections/ subdirectory for available projection YAML files."""
        proj_dir = self.output_dir / "projections"
        if not proj_dir.is_dir():
            return
        for type_dir in sorted(proj_dir.iterdir()):
            if not type_dir.is_dir():
                continue
            subjects: list[str] = []
            for f in sorted(type_dir.iterdir()):
                if f.suffix in (".yaml", ".yml") and f.stem != "projection_spec":
                    subjects.append(f.stem)
            if subjects:
                self.projection_index[type_dir.name] = subjects

    def load_projection(self, type_id: str, subject: str) -> dict[str, Any] | None:
        """Load a specific projection YAML file."""
        proj_file = self.output_dir / "projections" / type_id / f"{subject}.yaml"
        if not proj_file.exists():
            return None
        yaml = YAML(typ="safe")
        return yaml.load(proj_file.read_text()) or {}  # type: ignore[return-value]

    def has_type(self, type_id: str) -> bool:
        return type_id in self.tier_a.get("types", {})

    def has_entity(self, type_id: str, entity_id: str) -> bool:
        return entity_id in self.entity_indexes.get(type_id, {})
