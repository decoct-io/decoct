"""Tests for type seeding, refinement, convergence, and anti-unification."""

from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, AttributeProfile, BootstrapSignal, Entity
from decoct.discovery.anti_unification import anti_unify, count_variables
from decoct.discovery.type_discovery import refine_types
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

    def test_jaccard_clusters_similar_key_sets(self) -> None:
        """Entities with overlapping (not identical) key sets are grouped together."""
        # e1 and e2 share 3 of 4 keys (Jaccard = 3/5 = 0.6 > 0.4)
        e1 = Entity(id="A")
        for k in ("a", "b", "c", "d"):
            e1.attributes[k] = Attribute(k, "v", "string")
        e2 = Entity(id="B")
        for k in ("a", "b", "c", "e"):
            e2.attributes[k] = Attribute(k, "v", "string")
        # e3 is totally different
        e3 = Entity(id="C")
        for k in ("x", "y", "z"):
            e3.attributes[k] = Attribute(k, "v", "string")

        config = EntityGraphConfig(unhinted_jaccard_threshold=0.4)
        type_map = seed_types_from_hints([e1, e2, e3], config)
        # e1 and e2 should cluster together, e3 separate
        assert len(type_map) == 2
        groups = list(type_map.values())
        sizes = sorted(len(g) for g in groups)
        assert sizes == [1, 2]

    def test_jaccard_separates_dissimilar(self) -> None:
        """Entities with very different key sets stay in separate types."""
        entities = []
        for i in range(5):
            e = Entity(id=f"E{i}")
            # Each entity has unique keys
            for k in (f"k{i}_a", f"k{i}_b", f"k{i}_c"):
                e.attributes[k] = Attribute(k, "v", "string")
            entities.append(e)

        config = EntityGraphConfig(unhinted_jaccard_threshold=0.4)
        type_map = seed_types_from_hints(entities, config)
        # All should be separate since they share no keys
        assert len(type_map) == 5

    def test_jaccard_high_threshold_more_types(self) -> None:
        """Higher threshold requires more overlap, producing more types."""
        e1 = Entity(id="A")
        for k in ("a", "b", "c", "d"):
            e1.attributes[k] = Attribute(k, "v", "string")
        e2 = Entity(id="B")
        for k in ("a", "b", "e", "f"):
            e2.attributes[k] = Attribute(k, "v", "string")

        # Jaccard = 2/6 = 0.33 — below 0.5 threshold
        config = EntityGraphConfig(unhinted_jaccard_threshold=0.5)
        type_map = seed_types_from_hints([e1, e2], config)
        assert len(type_map) == 2  # Separate

        # With 0.3 threshold, they should group
        config = EntityGraphConfig(unhinted_jaccard_threshold=0.3)
        type_map = seed_types_from_hints([e1, e2], config)
        assert len(type_map) == 1


class TestMinRefinementClusterSize:
    """Tests for the small-cluster merge guard in type refinement."""

    def _make_entity_with_signal(self, eid: str, signal_val: str) -> Entity:
        """Create entity with a signal attribute for fingerprinting."""
        e = Entity(id=eid)
        e.attributes["role"] = Attribute("role", signal_val, "string")
        e.attributes["shared"] = Attribute("shared", "common", "string")
        return e

    def test_singletons_merged_back(self) -> None:
        """Refinement that would create singletons merges them back."""
        # 6 entities: 3 with role=web, 1 each with role=db, role=cache, role=queue
        entities = []
        for i in range(3):
            entities.append(self._make_entity_with_signal(f"web-{i}", "web"))
        entities.append(self._make_entity_with_signal("db-0", "db"))
        entities.append(self._make_entity_with_signal("cache-0", "cache"))
        entities.append(self._make_entity_with_signal("queue-0", "queue"))

        graph = EntityGraph()
        for e in entities:
            graph.add_entity(e)

        type_map = {"servers": entities}
        profiles = {
            "servers": {
                "role": AttributeProfile(
                    path="role",
                    cardinality=4,
                    entropy=1.5,
                    entropy_norm=0.8,
                    coverage=1.0,
                    value_length_mean=4.0,
                    value_length_var=1.0,
                    attribute_type="string",
                    final_role="A_SIGNAL",
                    bootstrap_role=BootstrapSignal.VALUE_SIGNAL,
                    entity_type="servers",
                ),
            },
        }
        config = EntityGraphConfig(
            max_anti_unify_variables=3,
            min_refinement_cluster_size=3,
        )

        result = refine_types(graph, type_map, profiles, config)
        # Singletons should be merged into the web cluster → 1 type
        assert len(result) == 1
        total = sum(len(v) for v in result.values())
        assert total == 6

    def test_large_clusters_not_affected(self) -> None:
        """Large clusters above the threshold are preserved as separate types."""

        def _make_divergent(eid: str, group: str) -> Entity:
            """Create entities with many signal differences to prevent merging."""
            e = Entity(id=eid)
            e.attributes["role"] = Attribute("role", group, "string")
            # Add group-specific presence signals so clusters diverge enough
            for k in (f"{group}_feat1", f"{group}_feat2", f"{group}_feat3", f"{group}_feat4"):
                e.attributes[k] = Attribute(k, "yes", "string")
            return e

        entities_a = [_make_divergent(f"a-{i}", "alpha") for i in range(5)]
        entities_b = [_make_divergent(f"b-{i}", "beta") for i in range(5)]

        graph = EntityGraph()
        all_entities = entities_a + entities_b
        for e in all_entities:
            graph.add_entity(e)

        type_map = {"mixed": all_entities}
        signal_paths = ["role", "alpha_feat1", "alpha_feat2", "alpha_feat3", "alpha_feat4",
                        "beta_feat1", "beta_feat2", "beta_feat3", "beta_feat4"]
        profiles = {
            "mixed": {
                p: AttributeProfile(
                    path=p,
                    cardinality=2,
                    entropy=1.0,
                    entropy_norm=1.0,
                    coverage=0.5,
                    value_length_mean=4.0,
                    value_length_var=0.0,
                    attribute_type="string",
                    final_role="A_SIGNAL",
                    bootstrap_role=BootstrapSignal.PRESENCE_SIGNAL,
                    entity_type="mixed",
                )
                for p in signal_paths
            },
        }
        config = EntityGraphConfig(
            max_anti_unify_variables=3,
            min_refinement_cluster_size=3,
        )

        result = refine_types(graph, type_map, profiles, config)
        # Both clusters have 5 entities (>= 3), so the small-cluster guard doesn't trigger
        assert len(result) == 2
        sizes = sorted(len(v) for v in result.values())
        assert sizes == [5, 5]

    def test_complete_shatter_returns_original(self) -> None:
        """If ALL clusters are below threshold, return original type unchanged."""
        entities = [self._make_entity_with_signal(f"e-{i}", f"unique-{i}") for i in range(4)]

        graph = EntityGraph()
        for e in entities:
            graph.add_entity(e)

        type_map = {"stuff": entities}
        profiles = {
            "stuff": {
                "role": AttributeProfile(
                    path="role",
                    cardinality=4,
                    entropy=2.0,
                    entropy_norm=1.0,
                    coverage=1.0,
                    value_length_mean=8.0,
                    value_length_var=0.0,
                    attribute_type="string",
                    final_role="A_SIGNAL",
                    bootstrap_role=BootstrapSignal.VALUE_SIGNAL,
                    entity_type="stuff",
                ),
            },
        }
        config = EntityGraphConfig(
            max_anti_unify_variables=0,  # Force max splitting
            min_refinement_cluster_size=3,
        )

        result = refine_types(graph, type_map, profiles, config)
        # Complete shatter → all singletons → return original
        assert len(result) == 1
        total = sum(len(v) for v in result.values())
        assert total == 4


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
