"""Integration tests for HybridInfraAdapter with k8s-fleet ingestion spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.adapters.ingestion_spec import load_ingestion_spec
from decoct.core.entity_graph import EntityGraph

FIXTURES = Path("tests/fixtures/k8s-fleet/configs")
SPEC_PATH = Path("specs/ingestion/k8s-fleet/ingestion_spec.yaml")


def _parse_one(
    filename: str,
    adapter: HybridInfraAdapter,
) -> tuple[EntityGraph, str]:
    graph = EntityGraph()
    parsed = adapter.parse(str(FIXTURES / filename))
    adapter.extract_entities(parsed, graph)
    entity_id = graph.entity_ids[0]
    return graph, entity_id


class TestK8sFleetAdapterWithSpec:
    """Spec overrides schema_type_hint for k8s-fleet files."""

    @pytest.fixture()
    def spec_adapter(self) -> HybridInfraAdapter:
        spec = load_ingestion_spec(SPEC_PATH)
        return HybridInfraAdapter(ingestion_spec=spec)

    def test_deployment_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("deploy-payment-api-prod.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "k8s-deployment"

    def test_service_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("svc-payment-api-prod.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "k8s-service"

    def test_configmap_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("cm-db-config-prod.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "k8s-configmap"

    def test_ingress_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("ingress-gateway-prod.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "k8s-ingress"

    def test_hpa_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("hpa-payment-api-prod.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "k8s-hpa"

    def test_networkpolicy_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("netpol-default-deny-prod.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "k8s-networkpolicy"

    def test_serviceaccount_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sa-payment-api-prod.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "k8s-serviceaccount"


class TestK8sFleetFullCorpus:
    """All 125 fixtures get a non-None schema_type_hint with spec loaded."""

    def test_full_corpus_no_unknowns(self) -> None:
        spec = load_ingestion_spec(SPEC_PATH)
        adapter = HybridInfraAdapter(ingestion_spec=spec)

        all_files = sorted(FIXTURES.iterdir())
        assert len(all_files) == 125

        missing_hints: list[str] = []
        for f in all_files:
            graph = EntityGraph()
            parsed = adapter.parse(str(f))
            adapter.extract_entities(parsed, graph)
            entity = graph.get_entity(f.stem)
            if entity.schema_type_hint is None:
                missing_hints.append(f.name)

        assert missing_hints == [], f"Files without schema_type_hint: {missing_hints}"
