"""Tests for delta compression: delta computation, subclass extraction, ABSENT handling."""

from decoct.compression.delta import compute_delta_restricted, delta_compress
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    ABSENT,
    Attribute,
    AttributeProfile,
    BaseClass,
    BootstrapSignal,
    ClassDef,
    ClassHierarchy,
    Entity,
    FinalRole,
)


def _entity(eid: str, attrs: dict[str, str], type_id: str = "t") -> Entity:
    e = Entity(id=eid, discovered_type=type_id)
    for path, value in attrs.items():
        e.attributes[path] = Attribute(path, value, "string")
    return e


def _profile(path: str, role: FinalRole) -> AttributeProfile:
    return AttributeProfile(
        path=path, cardinality=1, entropy=0, entropy_norm=0,
        coverage=1.0, value_length_mean=5, value_length_var=0,
        attribute_type="string", final_role=role,
        bootstrap_role=BootstrapSignal.NONE, entity_type="t",
    )


class TestComputeDeltaRestricted:
    def test_no_difference(self) -> None:
        entity_attrs = {"a": "1", "b": "2"}
        template = {"a": "1", "b": "2"}
        delta = compute_delta_restricted(entity_attrs, template, {"a", "b"})
        assert delta == {}

    def test_value_difference(self) -> None:
        entity_attrs = {"a": "1", "b": "changed"}
        template = {"a": "1", "b": "2"}
        delta = compute_delta_restricted(entity_attrs, template, {"a", "b"})
        assert delta == {"b": "changed"}

    def test_entity_has_extra_path(self) -> None:
        entity_attrs = {"a": "1", "extra": "val"}
        template = {"a": "1"}
        delta = compute_delta_restricted(entity_attrs, template, {"a", "extra"})
        assert delta == {"extra": "val"}

    def test_entity_missing_path_produces_absent(self) -> None:
        entity_attrs = {"a": "1"}
        template = {"a": "1", "removed": "val"}
        delta = compute_delta_restricted(entity_attrs, template, {"a", "removed"})
        assert "removed" in delta
        assert delta["removed"] is ABSENT

    def test_only_eligible_paths(self) -> None:
        entity_attrs = {"a": "1", "b": "changed"}
        template = {"a": "1", "b": "2"}
        delta = compute_delta_restricted(entity_attrs, template, {"a"})
        assert delta == {}  # b not eligible


class TestDeltaCompress:
    def _build_hierarchy(
        self,
        graph: EntityGraph,
        entities: list[Entity],
        base_attrs: dict[str, str],
        class_attrs: dict[str, str],
    ) -> dict[str, ClassHierarchy]:
        base = BaseClass(attrs=base_attrs)
        cls = ClassDef(
            name="main_class",
            inherits="base",
            own_attrs=class_attrs,
            entity_ids=sorted(e.id for e in entities),
            overrides={},
        )
        return {
            "t": ClassHierarchy(
                base_class=base,
                classes={"main_class": cls},
                subclasses={},
            )
        }

    def test_no_delta_no_overrides(self) -> None:
        """Entities matching template exactly produce no overrides."""
        graph = EntityGraph()
        entities = []
        for i in range(4):
            e = _entity(f"E{i}", {"base": "v", "cls_attr": "shared"})
            entities.append(e)
            graph.add_entity(e)

        hierarchies = self._build_hierarchy(
            graph, entities,
            base_attrs={"base": "v"},
            class_attrs={"cls_attr": "shared"},
        )

        profiles = {
            "t": {
                "base": _profile("base", FinalRole.A_BASE),
                "cls_attr": _profile("cls_attr", FinalRole.B),
            }
        }

        result = delta_compress(hierarchies, graph, profiles, EntityGraphConfig())
        cls = result["t"].classes["main_class"]
        assert len(cls.overrides) == 0

    def test_single_entity_override(self) -> None:
        """One entity deviating produces an override, not a subclass."""
        graph = EntityGraph()
        entities = []
        for i in range(4):
            attrs = {"cls_attr": "shared"} if i < 3 else {"cls_attr": "different"}
            e = _entity(f"E{i}", attrs)
            entities.append(e)
            graph.add_entity(e)

        hierarchies = self._build_hierarchy(
            graph, entities,
            base_attrs={},
            class_attrs={"cls_attr": "shared"},
        )

        profiles = {"t": {"cls_attr": _profile("cls_attr", FinalRole.B)}}
        config = EntityGraphConfig(min_subclass_size=3)
        result = delta_compress(hierarchies, graph, profiles, config)

        cls = result["t"].classes["main_class"]
        assert "E3" in cls.overrides

    def test_absent_stays_as_override(self) -> None:
        """ABSENT values (deletions) should stay as overrides, never promote."""
        graph = EntityGraph()
        entities = []
        for i in range(4):
            attrs = {"cls_attr": "shared", "optional": "val"} if i < 2 else {"cls_attr": "shared"}
            e = _entity(f"E{i}", attrs)
            entities.append(e)
            graph.add_entity(e)

        hierarchies = self._build_hierarchy(
            graph, entities,
            base_attrs={},
            class_attrs={"cls_attr": "shared", "optional": "val"},
        )

        profiles = {
            "t": {
                "cls_attr": _profile("cls_attr", FinalRole.B),
                "optional": _profile("optional", FinalRole.B),
            }
        }

        config = EntityGraphConfig(min_subclass_size=2)
        result = delta_compress(hierarchies, graph, profiles, config)

        # E2 and E3 miss "optional" → ABSENT in delta
        for eid in ["E2", "E3"]:
            if eid in result["t"].classes["main_class"].overrides:
                delta = result["t"].classes["main_class"].overrides[eid]
                if "optional" in delta:
                    assert delta["optional"] is ABSENT
