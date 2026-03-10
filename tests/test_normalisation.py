"""Tests for Tier C normalisation: phone book routing, instance_attrs, relationship store."""

from decoct.compression.normalisation import build_tier_c
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import (
    Attribute,
    AttributeProfile,
    BaseClass,
    BootstrapSignal,
    ClassDef,
    ClassHierarchy,
    Entity,
    FinalRole,
    TierCStorage,
)


def _profile(
    path: str, role: FinalRole, card: int = 60, cov: float = 1.0,
    attr_type: str = "string", ent_norm: float = 0.95,
) -> AttributeProfile:
    return AttributeProfile(
        path=path, cardinality=card, entropy=5.0, entropy_norm=ent_norm,
        coverage=cov, value_length_mean=10, value_length_var=0,
        attribute_type=attr_type, final_role=role,
        bootstrap_role=BootstrapSignal.NONE, entity_type="t",
    )


class TestPhoneBookRouting:
    def test_scalar_c_full_coverage_to_phone_book(self) -> None:
        """C scalar with full coverage routes to phone book."""
        graph = EntityGraph()
        entities = []
        for i in range(4):
            e = Entity(id=f"E{i}", discovered_type="t")
            e.attributes["hostname"] = Attribute("hostname", f"host-{i}", "string")
            entities.append(e)
            graph.add_entity(e)

        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base",
                entity_ids=[f"E{i}" for i in range(4)],
            )},
        )

        profiles = {
            "hostname": _profile("hostname", FinalRole.C, card=4, cov=1.0),
        }

        tier_c = build_tier_c("t", hierarchy, graph, profiles, {}, EntityGraphConfig())
        assert "hostname" in tier_c.instance_data.schema
        assert len(tier_c.instance_data.records) == 4

    def test_composite_template_ref_never_phone_book(self) -> None:
        """composite_template_ref routes to instance_attrs, not phone book."""
        graph = EntityGraph()
        entities = []
        for i in range(4):
            e = Entity(id=f"E{i}", discovered_type="t")
            e.attributes["neighbors"] = Attribute("neighbors", f"t.neighbors.T{i}", "composite_template_ref")
            entities.append(e)
            graph.add_entity(e)

        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base",
                entity_ids=[f"E{i}" for i in range(4)],
            )},
        )

        profiles = {
            "neighbors": _profile(
                "neighbors", FinalRole.C, card=4, cov=1.0,
                attr_type="composite_template_ref",
            ),
        }

        tier_c = build_tier_c("t", hierarchy, graph, profiles, {}, EntityGraphConfig())
        assert "neighbors" not in tier_c.instance_data.schema
        # Should be in instance_attrs instead
        has_ia = any("neighbors" in row for row in tier_c.instance_attrs.values())
        assert has_ia


class TestInstanceAttrs:
    def test_sparse_c_to_instance_attrs(self) -> None:
        """Sparse C attributes go to instance_attrs."""
        graph = EntityGraph()
        entities = []
        for i in range(4):
            e = Entity(id=f"E{i}", discovered_type="t")
            if i < 2:  # Only 2 of 4 have this attr → coverage=0.5
                e.attributes["optional"] = Attribute("optional", f"val-{i}", "string")
            entities.append(e)
            graph.add_entity(e)

        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base",
                entity_ids=[f"E{i}" for i in range(4)],
            )},
        )

        profiles = {
            "optional": _profile("optional", FinalRole.C, card=2, cov=0.5),
        }

        tier_c = build_tier_c("t", hierarchy, graph, profiles, {}, EntityGraphConfig())
        assert "optional" not in tier_c.instance_data.schema
        assert "E0" in tier_c.instance_attrs
        assert "optional" in tier_c.instance_attrs["E0"]


class TestRelationshipStore:
    def test_relationships_stored(self) -> None:
        graph = EntityGraph()
        e1 = Entity(id="E1", discovered_type="t")
        e2 = Entity(id="E2", discovered_type="t")
        graph.add_entity(e1)
        graph.add_entity(e2)
        graph.add_relationship("E1", "p2p_link", "E2")

        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base",
                entity_ids=["E1", "E2"],
            )},
        )

        tier_c = build_tier_c("t", hierarchy, graph, {}, {}, EntityGraphConfig())
        assert "E1" in tier_c.relationship_store
        assert tier_c.relationship_store["E1"][0]["label"] == "p2p_link"
        assert tier_c.relationship_store["E1"][0]["target"] == "E2"

    def test_no_relationships_no_store(self) -> None:
        graph = EntityGraph()
        e1 = Entity(id="E1", discovered_type="t")
        graph.add_entity(e1)

        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base",
                entity_ids=["E1"],
            )},
        )

        tier_c = build_tier_c("t", hierarchy, graph, {}, {}, EntityGraphConfig())
        assert "E1" not in tier_c.relationship_store


class TestClassAssignments:
    def test_all_entities_assigned(self) -> None:
        graph = EntityGraph()
        for i in range(4):
            e = Entity(id=f"E{i}", discovered_type="t")
            graph.add_entity(e)

        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={
                "cls_a": ClassDef(name="cls_a", inherits="base", entity_ids=["E0", "E1"]),
                "cls_b": ClassDef(name="cls_b", inherits="base", entity_ids=["E2", "E3"]),
            },
        )

        tier_c = build_tier_c("t", hierarchy, graph, {}, {}, EntityGraphConfig())
        all_assigned: set[str] = set()
        for data in tier_c.class_assignments.values():
            all_assigned.update(data["instances"])
        assert all_assigned == {"E0", "E1", "E2", "E3"}


class TestNoCPathDuplication:
    def test_phone_book_and_instance_attrs_disjoint(self) -> None:
        """No path should appear in both phone book and instance_attrs."""
        graph = EntityGraph()
        entities = []
        for i in range(4):
            e = Entity(id=f"E{i}", discovered_type="t")
            e.attributes["dense"] = Attribute("dense", f"v-{i}", "string")
            if i < 2:
                e.attributes["sparse"] = Attribute("sparse", f"s-{i}", "string")
            entities.append(e)
            graph.add_entity(e)

        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base",
                entity_ids=[f"E{i}" for i in range(4)],
            )},
        )

        profiles = {
            "dense": _profile("dense", FinalRole.C, card=4, cov=1.0),
            "sparse": _profile("sparse", FinalRole.C, card=2, cov=0.5),
        }

        tier_c = build_tier_c("t", hierarchy, graph, profiles, {}, EntityGraphConfig())
        pb_paths = set(tier_c.instance_data.schema)
        for row in tier_c.instance_attrs.values():
            ia_paths = set(row.keys())
            assert pb_paths & ia_paths == set()
