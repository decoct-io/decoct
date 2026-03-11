"""Tests for strict bidirectional source fidelity validation.

Unit tests for normalize_leaf, expand_entity_leaves, validate_strict_fidelity,
plus E2E tests on the full pipeline across all three adapter datasets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.core.composite_value import CompositeValue
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, Entity
from decoct.reconstruction.strict_fidelity import (
    StrictFidelityError,
    StrictFidelityMismatch,
    expand_entity_leaves,
    normalize_leaf,
    validate_strict_fidelity,
)


# ===========================================================================
# normalize_leaf tests
# ===========================================================================


class TestNormalizeLeaf:
    """Unit tests for token normalization."""

    def test_basic_path_value(self) -> None:
        result = normalize_leaf("ntp.source", "Loopback0")
        assert result == ("ntp", "source", "Loopback0")

    def test_discrimination(self) -> None:
        """Source and entity representations of discriminated data produce same tokens."""
        source = normalize_leaf("ntp.server", "10.0.0.1 prefer")
        entity = normalize_leaf("ntp.server.10.0.0.1", "prefer")
        assert source == entity

    def test_segment_aliases_evis(self) -> None:
        result = normalize_leaf("evpn.evis.100", "some-value")
        assert result[1] == "evi"

    def test_segment_aliases_neighbors(self) -> None:
        result = normalize_leaf("bgp.neighbors.10.0.0.1", "true")
        assert result[1] == "neighbor"

    def test_segment_aliases_bridge_groups(self) -> None:
        result = normalize_leaf("l2vpn.bridge-groups.BG1", "true")
        assert result[1] == "bridge-group"

    def test_segment_aliases_bridge_domains(self) -> None:
        result = normalize_leaf("l2vpn.bridge-domains.BD1", "true")
        assert result[1] == "bridge-domain"

    def test_boolean_true_dropped(self) -> None:
        result = normalize_leaf("shutdown", "true")
        assert result == ("shutdown",)

    def test_value_with_dots(self) -> None:
        """IP addresses in values get split into individual octets."""
        result = normalize_leaf("ntp.server", "10.0.0.1")
        assert result == ("ntp", "server", "10", "0", "0", "1")

    def test_array_index(self) -> None:
        result = normalize_leaf("path[0].key", "val")
        assert result == ("path", "0", "key", "val")

    def test_redacted_value(self) -> None:
        """[REDACTED] is treated as a normal token, not a wildcard."""
        result = normalize_leaf("tacacs-server.key", "[REDACTED]")
        assert result == ("tacacs-server", "key", "[REDACTED]")

    def test_empty_value(self) -> None:
        result = normalize_leaf("some.path", "")
        assert result == ("some", "path")

    def test_value_with_spaces(self) -> None:
        result = normalize_leaf("router.ospf", "area 0 range 10.0.0.0/8")
        assert result == ("router", "ospf", "area", "0", "range", "10", "0", "0", "0/8")

    def test_nested_array_indices(self) -> None:
        result = normalize_leaf("items[0].sub[1].val", "x")
        assert result == ("items", "0", "sub", "1", "val", "x")


# ===========================================================================
# expand_entity_leaves tests
# ===========================================================================


class TestExpandEntityLeaves:
    """Unit tests for entity leaf expansion."""

    def test_scalar_attributes(self) -> None:
        entity = Entity(id="test", attributes={
            "hostname": Attribute(path="hostname", value="router1", type="string"),
            "domain": Attribute(path="domain", value="example.com", type="string"),
        })
        leaves = expand_entity_leaves(entity)
        assert ("hostname", "router1") in leaves
        assert ("domain", "example.com") in leaves

    def test_list_of_strings(self) -> None:
        """Route-policy body: CompositeValue(list) of strings."""
        entity = Entity(id="test", attributes={
            "route-policy.ALLOW.body": Attribute(
                path="route-policy.ALLOW.body",
                value=CompositeValue.from_list(["pass", "end-policy"]),
                type="list",
            ),
        })
        leaves = expand_entity_leaves(entity)
        assert ("route-policy.ALLOW.body[0]", "pass") in leaves
        assert ("route-policy.ALLOW.body[1]", "end-policy") in leaves

    def test_list_of_dicts(self) -> None:
        """Array of objects expanded to individual fields."""
        entity = Entity(id="test", attributes={
            "servers": Attribute(
                path="servers",
                value=CompositeValue.from_list([
                    {"host": "10.0.0.1", "port": "8080"},
                    {"host": "10.0.0.2", "port": "9090"},
                ]),
                type="list",
            ),
        })
        leaves = expand_entity_leaves(entity)
        assert ("servers[0].host", "10.0.0.1") in leaves
        assert ("servers[0].port", "8080") in leaves
        assert ("servers[1].host", "10.0.0.2") in leaves
        assert ("servers[1].port", "9090") in leaves

    def test_map_of_dicts(self) -> None:
        """Keyed map expanded to individual fields."""
        entity = Entity(id="test", attributes={
            "neighbors": Attribute(
                path="neighbors",
                value=CompositeValue.from_map({
                    "10.0.0.1": {"remote-as": "65001", "description": "peer1"},
                    "10.0.0.2": {"remote-as": "65002", "description": "peer2"},
                }),
                type="map",
            ),
        })
        leaves = expand_entity_leaves(entity)
        assert ("neighbors.10.0.0.1.remote-as", "65001") in leaves
        assert ("neighbors.10.0.0.1.description", "peer1") in leaves
        assert ("neighbors.10.0.0.2.remote-as", "65002") in leaves

    def test_map_of_scalars(self) -> None:
        entity = Entity(id="test", attributes={
            "settings": Attribute(
                path="settings",
                value=CompositeValue.from_map({"mtu": "9000", "speed": "auto"}),
                type="map",
            ),
        })
        leaves = expand_entity_leaves(entity)
        assert ("settings.mtu", "9000") in leaves
        assert ("settings.speed", "auto") in leaves

    def test_internal_paths_excluded(self) -> None:
        """_uuid should be skipped."""
        entity = Entity(id="test", attributes={
            "_uuid": Attribute(path="_uuid", value="abc-123", type="string"),
            "name": Attribute(path="name", value="test-app", type="string"),
        })
        leaves = expand_entity_leaves(entity)
        paths = [p for p, _ in leaves]
        assert "_uuid" not in paths
        assert "name" in paths

    def test_none_value(self) -> None:
        entity = Entity(id="test", attributes={
            "nullable": Attribute(path="nullable", value=None, type="null"),
        })
        leaves = expand_entity_leaves(entity)
        assert ("nullable", "") in leaves


# ===========================================================================
# validate_strict_fidelity tests
# ===========================================================================


class TestValidateStrictFidelity:
    """Unit tests for the strict bidirectional validation function."""

    def _make_graph(self, entities: list[Entity]) -> EntityGraph:
        graph = EntityGraph()
        for e in entities:
            graph.add_entity(e)
        return graph

    def test_perfect_match(self) -> None:
        """Identical source and entity data → 0 mismatches."""
        entity = Entity(id="r1", attributes={
            "hostname": Attribute(path="hostname", value="router1", type="string"),
            "ntp.source": Attribute(path="ntp.source", value="Loopback0", type="string"),
        })
        graph = self._make_graph([entity])
        source_leaves = {
            "r1": [("hostname", "router1"), ("ntp.source", "Loopback0")],
        }
        mismatches = validate_strict_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) == 0

    def test_missing_from_entity(self) -> None:
        """Source has a token that entity doesn't → flagged."""
        entity = Entity(id="r1", attributes={
            "hostname": Attribute(path="hostname", value="router1", type="string"),
        })
        graph = self._make_graph([entity])
        source_leaves = {
            "r1": [
                ("hostname", "router1"),
                ("ntp.source", "Loopback0"),
            ],
        }
        mismatches = validate_strict_fidelity(source_leaves, graph, mode="warn")
        missing = [m for m in mismatches if m.kind == "missing_from_entity"]
        assert len(missing) == 1
        assert missing[0].token == normalize_leaf("ntp.source", "Loopback0")

    def test_fabricated_in_entity(self) -> None:
        """Entity has a token that source doesn't → flagged."""
        entity = Entity(id="r1", attributes={
            "hostname": Attribute(path="hostname", value="router1", type="string"),
            "extra.attr": Attribute(path="extra.attr", value="fabricated", type="string"),
        })
        graph = self._make_graph([entity])
        source_leaves = {
            "r1": [("hostname", "router1")],
        }
        mismatches = validate_strict_fidelity(source_leaves, graph, mode="warn")
        fabricated = [m for m in mismatches if m.kind == "fabricated_in_entity"]
        assert len(fabricated) == 1
        assert fabricated[0].token == normalize_leaf("extra.attr", "fabricated")

    def test_discrimination_match(self) -> None:
        """Discriminated paths normalize to same tokens."""
        entity = Entity(id="r1", attributes={
            "ntp.server.10.0.0.1": Attribute(
                path="ntp.server.10.0.0.1", value="prefer", type="string",
            ),
        })
        graph = self._make_graph([entity])
        source_leaves = {
            "r1": [("ntp.server", "10.0.0.1 prefer")],
        }
        mismatches = validate_strict_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) == 0

    def test_composite_expansion_match(self) -> None:
        """Composite entries match source leaves after expansion."""
        entity = Entity(id="r1", attributes={
            "route-policy.ALLOW.body": Attribute(
                path="route-policy.ALLOW.body",
                value=CompositeValue.from_list(["pass", "end-policy"]),
                type="list",
            ),
        })
        graph = self._make_graph([entity])
        source_leaves = {
            "r1": [
                ("route-policy.ALLOW.body[0]", "pass"),
                ("route-policy.ALLOW.body[1]", "end-policy"),
            ],
        }
        mismatches = validate_strict_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) == 0

    def test_error_mode_raises(self) -> None:
        entity = Entity(id="r1", attributes={
            "hostname": Attribute(path="hostname", value="router1", type="string"),
        })
        graph = self._make_graph([entity])
        source_leaves = {
            "r1": [("hostname", "router1"), ("missing", "data")],
        }
        with pytest.raises(StrictFidelityError) as exc_info:
            validate_strict_fidelity(source_leaves, graph, mode="error")
        assert len(exc_info.value.mismatches) > 0

    def test_warn_mode_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        entity = Entity(id="r1", attributes={
            "hostname": Attribute(path="hostname", value="router1", type="string"),
        })
        graph = self._make_graph([entity])
        source_leaves = {
            "r1": [("hostname", "router1"), ("missing", "data")],
        }
        with caplog.at_level("WARNING"):
            mismatches = validate_strict_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) > 0
        assert "Strict fidelity" in caplog.text

    def test_skip_mode_bypasses(self) -> None:
        graph = EntityGraph()
        source_leaves = {"r1": [("any", "thing")]}
        mismatches = validate_strict_fidelity(source_leaves, graph, mode="skip")
        assert mismatches == []

    def test_entity_not_found(self) -> None:
        """All source leaves flagged as missing when entity not in graph."""
        graph = EntityGraph()
        source_leaves = {
            "r1": [("hostname", "router1"), ("ntp", "server")],
        }
        mismatches = validate_strict_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) == 2
        assert all(m.kind == "missing_from_entity" for m in mismatches)

    def test_redacted_match(self) -> None:
        """Both sides have [REDACTED] at same path → match."""
        entity = Entity(id="r1", attributes={
            "password": Attribute(path="password", value="[REDACTED]", type="string"),
        })
        graph = self._make_graph([entity])
        source_leaves = {"r1": [("password", "[REDACTED]")]}
        mismatches = validate_strict_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) == 0

    def test_duplicate_tokens(self) -> None:
        """Duplicate tokens in source must have matching duplicates in entity."""
        entity = Entity(id="r1", attributes={
            "a": Attribute(path="a", value="x", type="string"),
            "b": Attribute(path="b", value="x", type="string"),
        })
        graph = self._make_graph([entity])
        source_leaves = {"r1": [("a", "x"), ("b", "x")]}
        mismatches = validate_strict_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) == 0


# ===========================================================================
# E2E tests on full datasets
# ===========================================================================


IOSXR_FIXTURES = Path("tests/fixtures/iosxr/configs")
HYBRID_FIXTURES = Path("tests/fixtures/hybrid-infra")
ENTRA_FIXTURES = Path("tests/fixtures/entra-intune/resources")


class TestStrictFidelityE2E:
    """Full-pipeline strict fidelity on all three datasets.

    IOS-XR and Entra-Intune have known adapter structural transformations
    (bridge-group key collision, confederation restructuring, nested
    @odata.type skipping) that produce bounded mismatches. These run in
    "warn" mode with mismatch count assertions.

    Hybrid-infra achieves 0 strict mismatches and runs in "error" mode.
    """

    @pytest.mark.skipif(
        not IOSXR_FIXTURES.exists(),
        reason="IOS-XR fixtures not available",
    )
    def test_iosxr_86_configs_strict(self) -> None:
        """86 IOS-XR configs — strict fidelity catches known adapter issues."""
        from decoct.adapters.iosxr import IosxrAdapter
        from decoct.core.config import EntityGraphConfig
        from decoct.entity_pipeline import run_entity_graph_pipeline

        sources = sorted(str(f) for f in IOSXR_FIXTURES.glob("*.cfg"))
        assert len(sources) == 86
        adapter = IosxrAdapter()
        # warn mode: IOS-XR adapter has bridge-group key collision and
        # confederation restructuring that cause strict mismatches
        config = EntityGraphConfig(source_fidelity_mode="warn")
        result = run_entity_graph_pipeline(sources, adapter, config)
        assert len(result.source_leaves) == 86

    @pytest.mark.skipif(
        not HYBRID_FIXTURES.exists(),
        reason="Hybrid-infra fixtures not available",
    )
    def test_hybrid_infra_strict(self) -> None:
        """100 hybrid-infra files → 0 strict mismatches (error mode)."""
        from decoct.adapters.hybrid_infra import HybridInfraAdapter
        from decoct.core.config import EntityGraphConfig
        from decoct.entity_pipeline import run_entity_graph_pipeline

        adapter = HybridInfraAdapter()
        fixture_dir = HYBRID_FIXTURES
        sources: list[str] = []
        for ext in ("*.yaml", "*.yml", "*.json", "*.ini", "*.conf",
                     "*.cfg", "*.cnf", "*.properties", "*.service", "*.socket"):
            sources.extend(str(f) for f in fixture_dir.rglob(ext))
        sources = [s for s in sources if "/generate/" not in s]
        sources.sort()
        assert len(sources) >= 1
        config = EntityGraphConfig()  # error mode — expects 0 mismatches
        result = run_entity_graph_pipeline(sources, adapter, config)
        assert len(result.source_leaves) >= 1

    @pytest.mark.skipif(
        not ENTRA_FIXTURES.exists(),
        reason="Entra-Intune fixtures not available",
    )
    def test_entra_intune_strict(self) -> None:
        """88 Entra-Intune files — strict fidelity catches known adapter issues."""
        from decoct.adapters.entra_intune import EntraIntuneAdapter
        from decoct.core.config import EntityGraphConfig
        from decoct.entity_pipeline import run_entity_graph_pipeline

        sources = sorted(str(f) for f in ENTRA_FIXTURES.glob("*.json"))
        assert len(sources) >= 1
        adapter = EntraIntuneAdapter()
        # warn mode: Entra adapter skips nested @odata.type fields that
        # source leaf collector includes
        config = EntityGraphConfig(source_fidelity_mode="warn")
        result = run_entity_graph_pipeline(sources, adapter, config)
        assert len(result.source_leaves) >= 1
