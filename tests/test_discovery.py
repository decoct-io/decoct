"""Tests for type seeding, refinement, convergence, and anti-unification."""

from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, Entity
from decoct.discovery.anti_unification import anti_unify, count_variables
from decoct.discovery.type_seeding import seed_types_from_hints


class TestTypeSeeding:
    def test_groups_by_hint(self) -> None:
        entities = [
            Entity(id="A", schema_type_hint="type-a"),
            Entity(id="B", schema_type_hint="type-a"),
            Entity(id="C", schema_type_hint="type-b"),
        ]
        type_map = seed_types_from_hints(entities)
        assert len(type_map) == 2
        assert len(type_map["type-a"]) == 2
        assert len(type_map["type-b"]) == 1

    def test_unhinted_entities_grouped_by_fingerprint(self) -> None:
        e1 = Entity(id="X")
        e1.attributes["a"] = Attribute("a", "1", "string")
        e2 = Entity(id="Y")
        e2.attributes["a"] = Attribute("a", "2", "string")
        e3 = Entity(id="Z")
        e3.attributes["b"] = Attribute("b", "3", "string")
        type_map = seed_types_from_hints([e1, e2, e3])
        assert len(type_map) == 2  # X,Y grouped; Z separate


class TestAntiUnification:
    def test_identical_entities(self) -> None:
        e1 = Entity(id="A")
        e1.attributes["x"] = Attribute("x", "1", "string")
        e2 = Entity(id="B")
        e2.attributes["x"] = Attribute("x", "1", "string")
        result = anti_unify(e1, e2)
        assert count_variables(result) == 0

    def test_different_values(self) -> None:
        e1 = Entity(id="A")
        e1.attributes["x"] = Attribute("x", "1", "string")
        e2 = Entity(id="B")
        e2.attributes["x"] = Attribute("x", "2", "string")
        result = anti_unify(e1, e2)
        assert count_variables(result) == 1

    def test_missing_path(self) -> None:
        e1 = Entity(id="A")
        e1.attributes["x"] = Attribute("x", "1", "string")
        e2 = Entity(id="B")
        result = anti_unify(e1, e2)
        assert count_variables(result) == 1

    def test_restrict_paths(self) -> None:
        e1 = Entity(id="A")
        e1.attributes["x"] = Attribute("x", "1", "string")
        e1.attributes["y"] = Attribute("y", "2", "string")
        e2 = Entity(id="B")
        e2.attributes["x"] = Attribute("x", "1", "string")
        e2.attributes["y"] = Attribute("y", "999", "string")
        # Without restriction: 1 variable (y differs)
        result = anti_unify(e1, e2)
        assert count_variables(result) == 1
        # With restriction to only x: 0 variables
        result = anti_unify(e1, e2, restrict_paths={"x"})
        assert count_variables(result) == 0
