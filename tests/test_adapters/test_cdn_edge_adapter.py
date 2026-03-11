"""Integration tests for HybridInfraAdapter with cdn-edge ingestion spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.adapters.ingestion_spec import load_ingestion_spec
from decoct.core.entity_graph import EntityGraph

FIXTURES = Path("tests/fixtures/cdn-edge/configs")
SPEC_PATH = Path("specs/ingestion/cdn-edge/ingestion_spec.yaml")


def _parse_one(
    filename: str,
    adapter: HybridInfraAdapter,
) -> tuple[EntityGraph, str]:
    graph = EntityGraph()
    parsed = adapter.parse(str(FIXTURES / filename))
    adapter.extract_entities(parsed, graph)
    entity_id = graph.entity_ids[0]
    return graph, entity_id


class TestCdnEdgeAdapterWithSpec:
    """Spec overrides schema_type_hint for cdn-edge files."""

    @pytest.fixture()
    def spec_adapter(self) -> HybridInfraAdapter:
        spec = load_ingestion_spec(SPEC_PATH)
        return HybridInfraAdapter(ingestion_spec=spec)

    def test_nginx_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("nginx-ams-static.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "nginx-site"

    def test_haproxy_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("haproxy-ams.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "haproxy"

    def test_varnish_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("varnish-ams.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "varnish-params"

    def test_dns_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("dns-ams.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "dns-zone"

    def test_ssl_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("ssl-ams.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "ssl-config"

    def test_prometheus_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("prometheus-ams.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "prometheus"

    def test_edge_compute_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("edge-compute-ams.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "edge-compute"

    def test_pop_metadata_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("pop-metadata-ams.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "pop-metadata"

    def test_keepalived_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("keepalived-ams.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "keepalived"


class TestCdnEdgeFullCorpus:
    """All 80 fixtures get a non-None schema_type_hint with spec loaded."""

    def test_full_corpus_no_unknowns(self) -> None:
        spec = load_ingestion_spec(SPEC_PATH)
        adapter = HybridInfraAdapter(ingestion_spec=spec)

        all_files = sorted(FIXTURES.iterdir())
        assert len(all_files) == 80

        missing_hints: list[str] = []
        for f in all_files:
            graph = EntityGraph()
            parsed = adapter.parse(str(f))
            adapter.extract_entities(parsed, graph)
            entity = graph.get_entity(f.stem)
            if entity.schema_type_hint is None:
                missing_hints.append(f.name)

        assert missing_hints == [], f"Files without schema_type_hint: {missing_hints}"
