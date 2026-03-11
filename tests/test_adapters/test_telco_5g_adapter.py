"""Integration tests for HybridInfraAdapter with telco-5g ingestion spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.adapters.ingestion_spec import load_ingestion_spec
from decoct.core.entity_graph import EntityGraph

FIXTURES = Path("tests/fixtures/telco-5g/configs")
SPEC_PATH = Path("specs/ingestion/telco-5g/ingestion_spec.yaml")


def _parse_one(
    filename: str,
    adapter: HybridInfraAdapter,
) -> tuple[EntityGraph, str]:
    graph = EntityGraph()
    parsed = adapter.parse(str(FIXTURES / filename))
    adapter.extract_entities(parsed, graph)
    entity_id = graph.entity_ids[0]
    return graph, entity_id


class TestTelco5gAdapterWithSpec:
    """Spec overrides schema_type_hint for telco-5g files."""

    @pytest.fixture()
    def spec_adapter(self) -> HybridInfraAdapter:
        spec = load_ingestion_spec(SPEC_PATH)
        return HybridInfraAdapter(ingestion_spec=spec)

    def test_gnodeb_cell_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("gnodeb-cell-macro-north-01-alpha.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "gnodeb-cell"

    def test_gnodeb_du_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("gnodeb-du-macro-north-01.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "gnodeb-du"

    def test_gnodeb_cu_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("gnodeb-cu-cu-pool-north.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "gnodeb-cu"

    def test_transport_link_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("transport-fronthaul-01.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "transport-link"

    def test_network_slice_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("slice-embb-default.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "network-slice"

    def test_ran_policy_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("ran-policy-handover-intra-freq.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "ran-policy"

    def test_core_amf_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("core-amf-01.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "core-amf"

    def test_core_smf_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("core-smf-01.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "core-smf"

    def test_site_metadata_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("site-macro-north-01.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "site-metadata"


class TestTelco5gFullCorpus:
    """All 100 fixtures get a non-None schema_type_hint with spec loaded."""

    def test_full_corpus_no_unknowns(self) -> None:
        spec = load_ingestion_spec(SPEC_PATH)
        adapter = HybridInfraAdapter(ingestion_spec=spec)

        all_files = sorted(FIXTURES.iterdir())
        assert len(all_files) == 100

        missing_hints: list[str] = []
        for f in all_files:
            graph = EntityGraph()
            parsed = adapter.parse(str(f))
            adapter.extract_entities(parsed, graph)
            entity = graph.get_entity(f.stem)
            if entity.schema_type_hint is None:
                missing_hints.append(f.name)

        assert missing_hints == [], f"Files without schema_type_hint: {missing_hints}"
