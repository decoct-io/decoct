"""Tests for IOS-XR adapter: one config per role validation."""

from pathlib import Path

import pytest

from decoct.adapters.iosxr import IosxrAdapter
from decoct.core.entity_graph import EntityGraph


FIXTURES = Path("tests/fixtures/iosxr/configs")


class TestIosxrAdapterPerRole:
    def _parse_one(self, filename: str) -> tuple[EntityGraph, str]:
        adapter = IosxrAdapter()
        graph = EntityGraph()
        adapter.parse_and_extract(str(FIXTURES / filename), graph)
        entity_id = graph.entity_ids[0]
        return graph, entity_id

    def test_p_core_entity(self) -> None:
        graph, eid = self._parse_one("P-CORE-01.cfg")
        e = graph.get_entity(eid)
        assert eid == "P-CORE-01"
        assert e.schema_type_hint == "iosxr-p-core"
        assert "hostname" in e.attributes
        assert len(e.attributes) > 50

    def test_rr_entity(self) -> None:
        graph, eid = self._parse_one("RR-01.cfg")
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "iosxr-rr"
        assert "hostname" in e.attributes

    def test_access_pe_entity(self) -> None:
        graph, eid = self._parse_one("APE-R1-01.cfg")
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "iosxr-access-pe"
        assert "hostname" in e.attributes
        # Should have composite values for EVIs
        evpn_attrs = [p for p in e.attributes if p.startswith("evpn")]
        assert len(evpn_attrs) > 0

    def test_bng_entity(self) -> None:
        graph, eid = self._parse_one("BNG-01.cfg")
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "iosxr-bng"

    def test_services_pe_entity(self) -> None:
        graph, eid = self._parse_one("SVC-PE-01.cfg")
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "iosxr-services-pe"

    def test_p2p_link_relationships(self) -> None:
        graph, eid = self._parse_one("P-CORE-01.cfg")
        rels = graph.relationships_from(eid)
        p2p_links = [(l, t) for l, t in rels if l == "p2p_link"]
        assert len(p2p_links) > 0


class TestIosxrAdapterCorpus:
    def test_all_86_configs_parse(self) -> None:
        adapter = IosxrAdapter()
        graph = EntityGraph()
        files = sorted(FIXTURES.glob("*.cfg"))
        assert len(files) == 86

        for f in files:
            adapter.parse_and_extract(str(f), graph)

        assert len(graph) == 86

    def test_type_distribution(self) -> None:
        adapter = IosxrAdapter()
        graph = EntityGraph()
        for f in sorted(FIXTURES.glob("*.cfg")):
            adapter.parse_and_extract(str(f), graph)

        from collections import Counter
        types = Counter(e.schema_type_hint for e in graph.entities)
        assert types["iosxr-access-pe"] == 60
        assert types["iosxr-bng"] == 8
        assert types["iosxr-p-core"] == 6
        assert types["iosxr-rr"] == 4
        assert types["iosxr-services-pe"] == 8
