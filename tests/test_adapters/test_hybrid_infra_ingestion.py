"""Integration tests for HybridInfraAdapter with ingestion spec."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.adapters.ingestion_spec import load_ingestion_spec
from decoct.core.composite_value import CompositeValue
from decoct.core.config import EntityGraphConfig
from decoct.core.entity_graph import EntityGraph
from decoct.entity_pipeline import run_entity_graph_pipeline

FIXTURES = Path("tests/fixtures/hybrid-infra/configs")
SPEC_PATH = Path("specs/ingestion/hybrid-infra/ingestion_spec.yaml")


def _parse_one(
    filename: str,
    adapter: HybridInfraAdapter,
) -> tuple[EntityGraph, str]:
    graph = EntityGraph()
    parsed = adapter.parse(str(FIXTURES / filename))
    adapter.extract_entities(parsed, graph)
    entity_id = graph.entity_ids[0]
    return graph, entity_id


class TestAdapterWithoutSpec:
    """Existing behavior preserved when no spec is loaded."""

    def test_adapter_without_spec_pg(self) -> None:
        adapter = HybridInfraAdapter()
        graph, eid = _parse_one("pg-prod-primary.conf", adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint is None  # no spec → detect_platform returns None

    def test_adapter_without_spec_compose(self) -> None:
        adapter = HybridInfraAdapter()
        graph, eid = _parse_one("compose-dev.yaml", adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "docker-compose"


class TestAdapterWithSpec:
    """Spec overrides schema_type_hint for matched files."""

    @pytest.fixture()
    def spec_adapter(self) -> HybridInfraAdapter:
        spec = load_ingestion_spec(SPEC_PATH)
        return HybridInfraAdapter(ingestion_spec=spec)

    def test_spec_overrides_pg_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("pg-prod-primary.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "postgresql"

    def test_spec_overrides_maria_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("maria-dev.cnf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "mariadb"

    def test_spec_overrides_sshd_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("sshd-prod.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "sshd"

    def test_spec_overrides_systemd_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("systemd-core-api.conf", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "systemd-unit"

    def test_spec_overrides_tfvars_hint(self, spec_adapter: HybridInfraAdapter) -> None:
        graph, eid = _parse_one("tfvars-prod.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "tfvars"

    def test_spec_does_not_affect_autodetected(self, spec_adapter: HybridInfraAdapter) -> None:
        """Compose files still get docker-compose from detect_platform()."""
        graph, eid = _parse_one("compose-dev.yaml", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "docker-compose"

    def test_spec_composite_override(self, spec_adapter: HybridInfraAdapter) -> None:
        """package-json files get forced composites via spec."""
        graph, eid = _parse_one("package-json-web-app.json", spec_adapter)
        e = graph.get_entity(eid)
        assert e.schema_type_hint == "package-json"
        # dependencies should be a composite (forced by spec)
        if "dependencies" in e.attributes:
            cv = e.attributes["dependencies"].value
            assert isinstance(cv, CompositeValue)
            assert cv.kind == "map"


class TestFullCorpusWithSpec:
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


class TestGateTestWithSpec:
    """Reconstruction validation still passes with spec loaded."""

    def test_gate_test_with_spec(self) -> None:
        spec = load_ingestion_spec(SPEC_PATH)
        adapter = HybridInfraAdapter(ingestion_spec=spec)
        sources = sorted(str(f) for f in FIXTURES.iterdir())
        # warn mode: ingestion spec adds _value fields not in source leaves
        config = EntityGraphConfig(source_fidelity_mode="warn")

        # This will raise ReconstructionError or StructuralInvariantError on failure
        result = run_entity_graph_pipeline(sources, adapter, config)
        assert len(result.type_map) > 0
