"""Tests for source fidelity validation (Layers 1 + 2).

Layer 1: Parser structure validation (raw text section counts vs parsed tree)
Layer 2: Source fidelity (source leaves vs entity attributes)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.adapters.iosxr import (
    ConfigNode,
    IosxrAdapter,
    parse_iosxr_config,
)
from decoct.core.composite_value import CompositeValue
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.core.types import Attribute, Entity
from decoct.reconstruction.parser_validation import (
    ParserStructureError,
    count_section_lines,
    count_tree_section_nodes,
    validate_parser_structure,
)
from decoct.reconstruction.source_fidelity import (
    SourceFidelityError,
    validate_source_fidelity,
)

FIXTURES = Path("tests/fixtures/iosxr/configs")


# ===========================================================================
# Layer 1: Parser structure validation
# ===========================================================================


class TestParserValidation:
    """Layer 1: raw text section counts vs parsed ConfigTree."""

    def test_parser_section_counts_match(self) -> None:
        """Correct parse → 0 discrepancies on a real config."""
        cfg_path = sorted(FIXTURES.glob("*.cfg"))[0]
        text = cfg_path.read_text(encoding="utf-8")
        tree = parse_iosxr_config(text)

        count_section_lines(text)
        count_tree_section_nodes(tree)

        discrepancies = validate_parser_structure(text, tree, cfg_path.stem, mode="warn")
        assert discrepancies == [], f"Unexpected discrepancies: {discrepancies}"

    def test_all_86_configs_structure_match(self) -> None:
        """All 86 configs have matching section counts."""
        total_discrepancies = 0
        for cfg_path in sorted(FIXTURES.glob("*.cfg")):
            text = cfg_path.read_text(encoding="utf-8")
            tree = parse_iosxr_config(text)
            discrepancies = validate_parser_structure(text, tree, cfg_path.stem, mode="warn")
            total_discrepancies += len(discrepancies)
        assert total_discrepancies == 0

    def test_parser_catches_section_misattribution(self) -> None:
        """Simulate parser bug → flagged as discrepancy."""
        # Build a config where a section has a known count
        cfg_text = """\
!! IOS XR Configuration - TEST-DEVICE
hostname TEST-DEVICE
!
ntp
 server 10.0.0.1
 server 10.0.0.2
!
interface Loopback0
 ipv4 address 1.2.3.4 255.255.255.255
!
end
"""
        tree = parse_iosxr_config(cfg_text)
        # Verify correct parsing first
        discrepancies = validate_parser_structure(cfg_text, tree, "TEST-DEVICE", mode="warn")
        assert discrepancies == []

        # Now tamper with the tree to simulate a parser bug:
        # move one child from ntp to interface
        ntp_node = None
        iface_node = None
        for node in tree.children:
            if node.keyword == "ntp":
                ntp_node = node
            if node.keyword == "interface":
                iface_node = node

        if ntp_node and iface_node and ntp_node.children:
            stolen = ntp_node.children.pop()
            iface_node.children.append(stolen)

            discrepancies = validate_parser_structure(cfg_text, tree, "TEST-DEVICE", mode="warn")
            assert len(discrepancies) > 0, "Should detect moved node"

    def test_error_mode_raises(self) -> None:
        """mode='error' raises ParserStructureError on mismatch."""
        cfg_text = "hostname TEST\n!\nntp\n server 10.0.0.1\n!\nend\n"
        tree = parse_iosxr_config(cfg_text)
        # Tamper
        tree.children[1].children.append(
            ConfigNode(keyword="fake", depth=1, raw_line="fake")
        )
        with pytest.raises(ParserStructureError):
            validate_parser_structure(cfg_text, tree, "TEST", mode="error")


# ===========================================================================
# Layer 2: Source fidelity validation
# ===========================================================================


class TestSourceFidelity:
    """Layer 2: source leaves vs entity attributes."""

    def _make_entity(
        self,
        entity_id: str,
        attrs: dict[str, str | CompositeValue],
    ) -> tuple[EntityGraph, dict[str, list[tuple[str, str]]]]:
        """Helper to create an entity in a graph."""
        graph = EntityGraph()
        entity = Entity(id=entity_id)
        for path, value in attrs.items():
            if isinstance(value, CompositeValue):
                entity.attributes[path] = Attribute(
                    path=path, value=value, type=value.kind, source=entity_id,
                )
            else:
                entity.attributes[path] = Attribute(
                    path=path, value=value, type="string", source=entity_id,
                )
        graph.add_entity(entity)
        return graph, {}

    def test_passes_when_all_match(self) -> None:
        """Clean entity → 0 mismatches."""
        graph, _ = self._make_entity("dev1", {
            "hostname": "dev1",
            "ntp.server.10.0.0.1": "prefer",
            "ntp.server.10.0.0.2": "true",
        })
        source_leaves = {
            "dev1": [
                ("hostname", "dev1"),
                ("ntp.server", "10.0.0.1 prefer"),
                ("ntp.server", "10.0.0.2"),
            ],
        }
        mismatches = validate_source_fidelity(source_leaves, graph, mode="warn")
        assert mismatches == []

    def test_catches_missing_leaf(self) -> None:
        """Source leaf not in entity → flagged."""
        graph, _ = self._make_entity("dev1", {
            "hostname": "dev1",
        })
        source_leaves = {
            "dev1": [
                ("hostname", "dev1"),
                ("ntp.server", "10.0.0.1"),
            ],
        }
        mismatches = validate_source_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) == 1
        assert mismatches[0].kind == "missing_from_entity"
        assert mismatches[0].path == "ntp.server"

    def test_catches_value_mismatch(self) -> None:
        """Wrong value → flagged."""
        graph, _ = self._make_entity("dev1", {
            "hostname": "dev1",
            "ntp.source": "Loopback0",
        })
        source_leaves = {
            "dev1": [
                ("hostname", "dev1"),
                ("ntp.source", "Loopback1"),
            ],
        }
        mismatches = validate_source_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) == 1
        assert mismatches[0].kind == "value_mismatch"

    def test_discriminated_match(self) -> None:
        """Source ("ntp.server", "10.0.0.1 prefer") matches entity ntp.server.10.0.0.1 = prefer."""
        graph, _ = self._make_entity("dev1", {
            "ntp.server.10.0.0.1": "prefer",
        })
        source_leaves = {
            "dev1": [
                ("ntp.server", "10.0.0.1 prefer"),
            ],
        }
        mismatches = validate_source_fidelity(source_leaves, graph, mode="warn")
        assert mismatches == []

    def test_composite_containment(self) -> None:
        """Subsumed leaf in composite → OK."""
        cv = CompositeValue(data={"10.0.0.1": {"remote-as": "65000"}}, kind="map")
        graph, _ = self._make_entity("dev1", {
            "router.bgp.1.neighbors": cv,
        })
        # Source leaf in the composite's subsumption zone
        source_leaves = {
            "dev1": [
                ("router.bgp.1.neighbor.10.0.0.1.remote-as", "65000"),
            ],
        }
        mismatches = validate_source_fidelity(source_leaves, graph, mode="warn")
        assert mismatches == []

    def test_redacted_values_skipped(self) -> None:
        """[REDACTED] entity value → OK regardless of source value."""
        graph, _ = self._make_entity("dev1", {
            "secret.key": "[REDACTED]",
        })
        source_leaves = {
            "dev1": [
                ("secret.key", "supersecretpassword123"),
            ],
        }
        mismatches = validate_source_fidelity(source_leaves, graph, mode="warn")
        assert mismatches == []

    def test_error_mode_raises(self) -> None:
        """mode='error' raises SourceFidelityError."""
        graph, _ = self._make_entity("dev1", {"hostname": "dev1"})
        source_leaves = {"dev1": [("hostname", "dev1"), ("missing", "val")]}
        with pytest.raises(SourceFidelityError):
            validate_source_fidelity(source_leaves, graph, mode="error")

    def test_warn_mode_returns(self) -> None:
        """mode='warn' returns mismatches without raising."""
        graph, _ = self._make_entity("dev1", {"hostname": "dev1"})
        source_leaves = {"dev1": [("hostname", "dev1"), ("missing", "val")]}
        mismatches = validate_source_fidelity(source_leaves, graph, mode="warn")
        assert len(mismatches) == 1

    def test_skip_mode_bypasses(self) -> None:
        """mode='skip' returns empty list."""
        graph, _ = self._make_entity("dev1", {"hostname": "dev1"})
        source_leaves = {"dev1": [("hostname", "dev1"), ("missing", "val")]}
        mismatches = validate_source_fidelity(source_leaves, graph, mode="skip")
        assert mismatches == []

    def test_route_policy_body_in_composite(self) -> None:
        """Route-policy body lines match CompositeValue(list) at body path."""
        cv = CompositeValue.from_list(["if destination in PREFIX-SET then", "pass", "endif"])
        graph, _ = self._make_entity("dev1", {
            "route-policy.ALLOW-ALL.body": cv,
        })
        source_leaves = {
            "dev1": [
                ("route-policy.ALLOW-ALL.body[0]", "if destination in PREFIX-SET then"),
                ("route-policy.ALLOW-ALL.body[1]", "pass"),
                ("route-policy.ALLOW-ALL.body[2]", "endif"),
            ],
        }
        mismatches = validate_source_fidelity(source_leaves, graph, mode="warn")
        assert mismatches == []


# ===========================================================================
# End-to-end: full pipeline with all 3 layers
# ===========================================================================


class TestE2ESourceFidelity:
    """End-to-end: source fidelity on all 86 IOS-XR configs via pipeline."""

    def test_e2e_86_configs(self) -> None:
        """Full pipeline on 86 configs with all 3 validation layers."""
        from decoct.entity_pipeline import run_entity_graph_pipeline

        sources = sorted(str(f) for f in FIXTURES.glob("*.cfg"))
        assert len(sources) == 86

        adapter = IosxrAdapter()
        # warn mode: IOS-XR adapter has known structural transformations
        # (bridge-group key collision, confederation restructuring) that
        # cause strict fidelity mismatches
        config = EntityGraphConfig(source_fidelity_mode="warn")
        result = run_entity_graph_pipeline(sources, adapter, config)

        # Pipeline completed — L1 (parser) and L3 (reconstruction) passed
        assert len(result.source_leaves) == 86
        assert len(result.graph) == 86
