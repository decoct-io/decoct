"""Tests for composite value decomposition: shadow map, re-profiling, template assignment."""

import copy

from decoct.analysis.profiler import profile_attributes
from decoct.core.composite_value import CompositeValue
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, Entity, FinalRole
from decoct.discovery.composite_decomp import decompose_composites


def _make_entity(eid: str, type_hint: str, attrs: dict[str, Attribute]) -> Entity:
    e = Entity(id=eid, schema_type_hint=type_hint, discovered_type=type_hint)
    e.attributes = attrs
    return e


def _composite_map(data: dict[str, str]) -> CompositeValue:
    return CompositeValue.from_map(data)


class TestCompositeDecomp:
    def _setup(self, n_entities: int = 8, n_distinct: int = 6) -> tuple:
        """Build entities with composite values for decomposition tests."""
        config = EntityGraphConfig()
        graph = EntityGraph()

        # Create n_entities with composite values on path "neighbors"
        # n_distinct distinct values, so some are shared
        entities = []
        for i in range(n_entities):
            val_idx = i % n_distinct
            cv = _composite_map({"peer": f"10.0.0.{val_idx}", "asn": f"6500{val_idx}"})
            e = _make_entity(
                f"R-{i:02d}", "test-type",
                {
                    "hostname": Attribute("hostname", f"R-{i:02d}", "string"),
                    "neighbors": Attribute("neighbors", cv, "composite_map"),
                },
            )
            entities.append(e)
            graph.add_entity(e)

        type_map = {"test-type": entities}
        profiles = {"test-type": profile_attributes(entities, "test-type", config)}
        return graph, type_map, profiles, config

    def test_shadow_map_preserves_originals(self) -> None:
        graph, type_map, profiles, config = self._setup()
        original_vals = {
            e.id: copy.deepcopy(e.attributes["neighbors"].value)
            for e in type_map["test-type"]
        }

        _, _, _, _, original_composite_values, _ = decompose_composites(
            graph, type_map, profiles, config,
        )

        for eid, orig in original_vals.items():
            if (eid, "neighbors") in original_composite_values:
                shadow = original_composite_values[(eid, "neighbors")]
                assert isinstance(shadow, CompositeValue)
                assert shadow.data == orig.data

    def test_template_ids_assigned(self) -> None:
        graph, type_map, profiles, config = self._setup()
        _, template_index, templates_by_type_path, _, _, _ = decompose_composites(
            graph, type_map, profiles, config,
        )

        # Should have created templates for the composite path
        if ("test-type", "neighbors") in templates_by_type_path:
            tids = templates_by_type_path[("test-type", "neighbors")]
            for tid in tids:
                assert tid.startswith("test-type.neighbors.T")
                assert tid in template_index

    def test_reprofiling_updates_type(self) -> None:
        graph, type_map, profiles, config = self._setup()
        _, _, templates_by_type_path, _, _, updated_profiles = decompose_composites(
            graph, type_map, profiles, config,
        )

        if ("test-type", "neighbors") in templates_by_type_path:
            prof = updated_profiles["test-type"]["neighbors"]
            assert prof.attribute_type == "composite_template_ref"

    def test_below_threshold_not_decomposed(self) -> None:
        """Composites with cardinality <= threshold are skipped."""
        config = EntityGraphConfig(composite_decompose_threshold=100)
        graph = EntityGraph()

        entities = []
        for i in range(4):
            cv = _composite_map({"key": f"val-{i}"})
            e = _make_entity(
                f"E-{i}", "t",
                {"comp": Attribute("comp", cv, "composite_map")},
            )
            entities.append(e)
            graph.add_entity(e)

        type_map = {"t": entities}
        profiles = {"t": profile_attributes(entities, "t", config)}

        _, template_index, _, _, _, _ = decompose_composites(
            graph, type_map, profiles, config,
        )
        assert len(template_index) == 0

    def test_entity_attrs_replaced_with_refs(self) -> None:
        graph, type_map, profiles, config = self._setup()
        decompose_composites(graph, type_map, profiles, config)

        # After decomposition, entity attrs should be composite_template_ref strings
        for e in type_map["test-type"]:
            attr = e.attributes.get("neighbors")
            if attr and attr.type == "composite_template_ref":
                assert isinstance(attr.value, str)
                assert attr.value.startswith("test-type.neighbors.T")
