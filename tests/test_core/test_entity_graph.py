"""Tests for EntityGraph: entity add/get, relationship deduplication."""

from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, Entity


class TestEntityGraph:
    def test_add_and_get_entity(self) -> None:
        g = EntityGraph()
        e = Entity(id="R1")
        g.add_entity(e)
        assert g.get_entity("R1") is e

    def test_entities_sorted(self) -> None:
        g = EntityGraph()
        g.add_entity(Entity(id="C"))
        g.add_entity(Entity(id="A"))
        g.add_entity(Entity(id="B"))
        assert [e.id for e in g.entities] == ["A", "B", "C"]

    def test_len(self) -> None:
        g = EntityGraph()
        g.add_entity(Entity(id="A"))
        g.add_entity(Entity(id="B"))
        assert len(g) == 2


class TestRelationshipDedup:
    def test_deduplication(self) -> None:
        g = EntityGraph()
        g.add_relationship("A", "link", "B")
        g.add_relationship("A", "link", "B")  # duplicate
        assert len(g.all_relationships) == 1

    def test_different_labels_not_deduped(self) -> None:
        g = EntityGraph()
        g.add_relationship("A", "p2p_link", "B")
        g.add_relationship("A", "bgp_peer", "B")
        assert len(g.all_relationships) == 2

    def test_relationships_from(self) -> None:
        g = EntityGraph()
        g.add_relationship("A", "link", "B")
        g.add_relationship("A", "peer", "C")
        rels = g.relationships_from("A")
        assert ("link", "B") in rels
        assert ("peer", "C") in rels

    def test_has_relationship_from(self) -> None:
        g = EntityGraph()
        g.add_relationship("A", "link", "B")
        assert g.has_relationship_from("A", "link") is True
        assert g.has_relationship_from("A", "peer") is False
