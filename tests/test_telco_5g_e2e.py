"""End-to-end test: full pipeline on 100 5G RAN configs.

Gate test: run_entity_graph_pipeline() on all configs
with 0 reconstruction mismatches.
"""

from pathlib import Path

import pytest

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.adapters.ingestion_spec import load_ingestion_spec
from decoct.core.config import EntityGraphConfig
from decoct.entity_pipeline import run_entity_graph_pipeline

FIXTURES = Path("tests/fixtures/telco-5g/configs")
SPEC_PATH = Path("specs/ingestion/telco-5g/ingestion_spec.yaml")


class TestTelco5gE2E:
    """Full pipeline on 100 5G RAN configs — gate test."""

    @pytest.fixture(scope="class")
    def pipeline_result(self):  # type: ignore[no-untyped-def]
        """Run pipeline once, share across all tests in this class."""
        sources = sorted(str(f) for f in FIXTURES.iterdir())
        assert len(sources) == 100
        spec = load_ingestion_spec(SPEC_PATH)
        adapter = HybridInfraAdapter(ingestion_spec=spec)
        config = EntityGraphConfig()
        return run_entity_graph_pipeline(sources, adapter, config)

    def test_zero_reconstruction_mismatches(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Pipeline completed without raising ReconstructionError."""
        assert pipeline_result is not None

    def test_discovers_types(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """100 configs -> multiple discovered types matching config categories."""
        type_names = sorted(pipeline_result.type_map.keys())
        assert len(type_names) >= 5  # at least 5 types from 9 config categories

    def test_total_entity_count(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """All 100 entities present in graph."""
        assert len(pipeline_result.graph) == 100

    def test_base_class_has_attributes(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Each type's base class should have attributes."""
        for type_id, h in pipeline_result.hierarchies.items():
            assert len(h.base_class.attrs) > 0, f"{type_id} has empty base class"

    def test_all_entities_assigned_to_class(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Every entity should be assigned to exactly one class."""
        for type_id, tier_c in pipeline_result.tier_c_files.items():
            all_assigned: set[str] = set()
            for class_data in tier_c.class_assignments.values():
                all_assigned.update(class_data["instances"])

            expected = {e.id for e in pipeline_result.type_map[type_id]}
            assert all_assigned == expected, f"{type_id}: assignment mismatch"

    def test_tier_a_has_all_types(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        tier_a = pipeline_result.tier_a
        assert len(tier_a["types"]) >= 5

    def test_graph_entity_count(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        assert len(pipeline_result.graph) == 100
