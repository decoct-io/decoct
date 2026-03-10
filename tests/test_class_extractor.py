"""Tests for class extraction: base class, bundle generation, greedy selection."""

from decoct.compression.class_extractor import extract_classes
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    Attribute,
    AttributeProfile,
    BootstrapSignal,
    Entity,
    FinalRole,
)


def _entity(eid: str, attrs: dict[str, str]) -> Entity:
    e = Entity(id=eid, discovered_type="t")
    for path, value in attrs.items():
        e.attributes[path] = Attribute(path, value, "string")
    return e


def _profile(path: str, role: FinalRole, card: int = 1, cov: float = 1.0) -> AttributeProfile:
    return AttributeProfile(
        path=path, cardinality=card, entropy=0, entropy_norm=0,
        coverage=cov, value_length_mean=5, value_length_var=0,
        attribute_type="string", final_role=role,
        bootstrap_role=BootstrapSignal.NONE, entity_type="t",
    )


class TestBaseClassExtraction:
    def test_a_base_in_base_class(self) -> None:
        graph = EntityGraph()
        entities = [
            _entity("E1", {"hostname": "shared", "x": "1"}),
            _entity("E2", {"hostname": "shared", "x": "2"}),
            _entity("E3", {"hostname": "shared", "x": "3"}),
        ]
        for e in entities:
            graph.add_entity(e)

        profiles = {
            "t": {
                "hostname": _profile("hostname", FinalRole.A_BASE),
                "x": _profile("x", FinalRole.C, card=3),
            }
        }

        hierarchies = extract_classes({"t": entities}, graph, profiles, EntityGraphConfig())
        assert "hostname" in hierarchies["t"].base_class.attrs
        assert hierarchies["t"].base_class.attrs["hostname"] == "shared"

    def test_universal_b_promoted_to_base(self) -> None:
        graph = EntityGraph()
        entities = [
            _entity("E1", {"shared_b": "same", "diff_b": "a"}),
            _entity("E2", {"shared_b": "same", "diff_b": "b"}),
            _entity("E3", {"shared_b": "same", "diff_b": "c"}),
        ]
        for e in entities:
            graph.add_entity(e)

        profiles = {
            "t": {
                "shared_b": _profile("shared_b", FinalRole.B, card=1),
                "diff_b": _profile("diff_b", FinalRole.B, card=3),
            }
        }

        hierarchies = extract_classes({"t": entities}, graph, profiles, EntityGraphConfig())
        assert "shared_b" in hierarchies["t"].base_class.attrs

    def test_base_only_catchall(self) -> None:
        """Entities not assigned to any class go to _base_only."""
        graph = EntityGraph()
        # Only 2 entities with same residual B — below min_class_support=3
        entities = [
            _entity("E1", {"b_path": "same"}),
            _entity("E2", {"b_path": "same"}),
        ]
        for e in entities:
            graph.add_entity(e)

        profiles = {
            "t": {
                "b_path": _profile("b_path", FinalRole.B, card=1),
            }
        }

        config = EntityGraphConfig(min_class_support=3)
        hierarchies = extract_classes({"t": entities}, graph, profiles, config)
        # b_path is universal B → promoted to base_class
        # All entities unassigned from residual classes → _base_only
        assert "_base_only" in hierarchies["t"].classes
        assert sorted(hierarchies["t"].classes["_base_only"].entity_ids) == ["E1", "E2"]


class TestGreedyBundleSelection:
    def test_frequent_bundle_creates_class(self) -> None:
        graph = EntityGraph()
        entities = []
        # 10 entities share {"role": "leaf-switch-node-type-xxxx"}, 10 share {"role": "spine-switch-node-type-xxxx"}
        # Use long values so the token savings outweigh class overhead
        for i in range(10):
            entities.append(_entity(f"L{i:02d}", {"role": "leaf-switch-node-type-xxxx"}))
        for i in range(10):
            entities.append(_entity(f"S{i:02d}", {"role": "spine-switch-node-type-xxxx"}))
        for e in entities:
            graph.add_entity(e)

        profiles = {
            "t": {
                "role": _profile("role", FinalRole.B, card=2),
            }
        }

        config = EntityGraphConfig(min_class_support=3)
        hierarchies = extract_classes({"t": entities}, graph, profiles, config)
        # Should have 2 classes (leaf + spine) since both have support >= 3
        real_classes = {k: v for k, v in hierarchies["t"].classes.items() if k != "_base_only"}
        assert len(real_classes) >= 2

    def test_no_class_below_min_support(self) -> None:
        graph = EntityGraph()
        entities = [
            _entity("E1", {"x": "a"}),
            _entity("E2", {"x": "b"}),
            _entity("E3", {"x": "c"}),
        ]
        for e in entities:
            graph.add_entity(e)

        profiles = {
            "t": {
                "x": _profile("x", FinalRole.B, card=3),
            }
        }

        config = EntityGraphConfig(min_class_support=3)
        hierarchies = extract_classes({"t": entities}, graph, profiles, config)
        # Each value has support=1, below min_support=3
        real_classes = {k: v for k, v in hierarchies["t"].classes.items() if k != "_base_only"}
        assert len(real_classes) == 0

    def test_class_entities_are_correct(self) -> None:
        graph = EntityGraph()
        entities = []
        for i in range(5):
            entities.append(_entity(f"A{i}", {"region": "east"}))
        for i in range(3):
            entities.append(_entity(f"B{i}", {"region": "west"}))
        for e in entities:
            graph.add_entity(e)

        profiles = {
            "t": {
                "region": _profile("region", FinalRole.B, card=2),
            }
        }

        config = EntityGraphConfig(min_class_support=3)
        hierarchies = extract_classes({"t": entities}, graph, profiles, config)

        # Verify all entities assigned
        all_assigned: set[str] = set()
        for cls in hierarchies["t"].classes.values():
            all_assigned.update(cls.entity_ids)
        expected = {e.id for e in entities}
        assert all_assigned == expected
