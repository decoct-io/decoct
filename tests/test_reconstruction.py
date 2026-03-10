"""Tests for reconstitution: precedence chain, round-trip, null vs absent."""

from decoct.core.types import (
    ABSENT,
    BaseClass,
    ClassDef,
    ClassHierarchy,
    CompositeTemplate,
    PhoneBook,
    SubclassDef,
    TierC,
)
from decoct.reconstruction.reconstitute import reconstitute_entity


def _tier_c(
    class_assignments: dict[str, dict] | None = None,
    subclass_assignments: dict[str, dict] | None = None,
    instance_attrs: dict[str, dict] | None = None,
    phone_book: PhoneBook | None = None,
    overrides: dict[str, dict] | None = None,
    relationship_store: dict[str, list] | None = None,
    b_composite_deltas: dict[str, dict] | None = None,
) -> TierC:
    return TierC(
        class_assignments=class_assignments or {},
        subclass_assignments=subclass_assignments or {},
        instance_data=phone_book or PhoneBook(),
        instance_attrs=instance_attrs or {},
        relationship_store=relationship_store or {},
        overrides=overrides or {},
        b_composite_deltas=b_composite_deltas or {},
    )


class TestPrecedenceChain:
    def test_base_class_only(self) -> None:
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={"hostname": "shared"}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base", entity_ids=["E1"],
            )},
        )
        tier_c = _tier_c(class_assignments={"_base_only": {"instances": ["E1"]}})

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, {})
        assert result.attributes["hostname"] == "shared"

    def test_class_overrides_base(self) -> None:
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={"x": "base_val"}),
            classes={"cls_a": ClassDef(
                name="cls_a", inherits="base",
                own_attrs={"x": "class_val"},
                entity_ids=["E1"],
            )},
        )
        tier_c = _tier_c(class_assignments={"cls_a": {"instances": ["E1"]}})

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, {})
        assert result.attributes["x"] == "class_val"

    def test_subclass_overrides_class(self) -> None:
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"cls_a": ClassDef(
                name="cls_a", inherits="base",
                own_attrs={"x": "class_val"},
                entity_ids=["E1"],
            )},
            subclasses={"sub_a": SubclassDef(
                name="sub_a", parent_class="cls_a",
                own_attrs={"x": "sub_val"},
                entity_ids=["E1"],
            )},
        )
        tier_c = _tier_c(
            class_assignments={"cls_a": {"instances": ["E1"]}},
            subclass_assignments={"sub_a": {"parent": "cls_a", "instances": ["E1"]}},
        )

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, {})
        assert result.attributes["x"] == "sub_val"

    def test_override_overrides_subclass(self) -> None:
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"cls_a": ClassDef(
                name="cls_a", inherits="base",
                own_attrs={"x": "class_val"},
                entity_ids=["E1"],
            )},
            subclasses={"sub_a": SubclassDef(
                name="sub_a", parent_class="cls_a",
                own_attrs={"x": "sub_val"},
                entity_ids=["E1"],
            )},
        )
        tier_c = _tier_c(
            class_assignments={"cls_a": {"instances": ["E1"]}},
            subclass_assignments={"sub_a": {"parent": "cls_a", "instances": ["E1"]}},
            overrides={"E1": {"owner": "sub_a", "delta": {"x": "override_val"}}},
        )

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, {})
        assert result.attributes["x"] == "override_val"

    def test_phone_book_applied_last(self) -> None:
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={"base_a": "v"}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base", entity_ids=["E1"],
            )},
        )
        pb = PhoneBook(schema=["hostname"], records={"E1": ["device-01"]})
        tier_c = _tier_c(
            class_assignments={"_base_only": {"instances": ["E1"]}},
            phone_book=pb,
        )

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, {})
        assert result.attributes["hostname"] == "device-01"
        assert result.attributes["base_a"] == "v"

    def test_instance_attrs_applied(self) -> None:
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base", entity_ids=["E1"],
            )},
        )
        tier_c = _tier_c(
            class_assignments={"_base_only": {"instances": ["E1"]}},
            instance_attrs={"E1": {"sparse_attr": "val123"}},
        )

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, {})
        assert result.attributes["sparse_attr"] == "val123"


class TestAbsentHandling:
    def test_absent_removes_attribute(self) -> None:
        """ABSENT in override delta removes the attribute from result."""
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={"to_remove": "val"}),
            classes={"cls_a": ClassDef(
                name="cls_a", inherits="base", entity_ids=["E1"],
            )},
        )
        tier_c = _tier_c(
            class_assignments={"cls_a": {"instances": ["E1"]}},
            overrides={"E1": {"owner": "cls_a", "delta": {"to_remove": ABSENT}}},
        )

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, {})
        assert "to_remove" not in result.attributes


class TestCompositeTemplateExpansion:
    def test_c_layer_template_expansion(self) -> None:
        """Composite template ref in instance_attrs gets expanded."""
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base", entity_ids=["E1"],
            )},
        )

        template = CompositeTemplate(
            id="t.neighbors.T0",
            content={"peer": "10.0.0.1", "asn": "65000"},
        )
        template_index = {"t.neighbors.T0": template}

        tier_c = _tier_c(
            class_assignments={"_base_only": {"instances": ["E1"]}},
            instance_attrs={"E1": {"neighbors": {"template": "t.neighbors.T0"}}},
        )

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, template_index)
        assert result.attributes["neighbors"] == {"peer": "10.0.0.1", "asn": "65000"}


class TestRelationships:
    def test_relationships_reconstructed(self) -> None:
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base", entity_ids=["E1"],
            )},
        )
        tier_c = _tier_c(
            class_assignments={"_base_only": {"instances": ["E1"]}},
            relationship_store={"E1": [
                {"label": "bgp_peer", "target": "E2"},
                {"label": "p2p_link", "target": "E3"},
            ]},
        )

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, {})
        assert ("bgp_peer", "E2") in result.relationships
        assert ("p2p_link", "E3") in result.relationships

    def test_no_relationships(self) -> None:
        hierarchy = ClassHierarchy(
            base_class=BaseClass(attrs={}),
            classes={"_base_only": ClassDef(
                name="_base_only", inherits="base", entity_ids=["E1"],
            )},
        )
        tier_c = _tier_c(class_assignments={"_base_only": {"instances": ["E1"]}})

        result = reconstitute_entity("t", "E1", hierarchy, tier_c, {})
        assert result.relationships == []
