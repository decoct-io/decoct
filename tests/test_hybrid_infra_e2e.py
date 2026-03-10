"""End-to-end test: full pipeline on 100 hybrid-infra configs.

THE gate test: run_entity_graph_pipeline() on all 100 mixed-format configs
with 0 reconstruction mismatches.
"""

from pathlib import Path

import pytest

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.core.config import EntityGraphConfig
from decoct.entity_pipeline import run_entity_graph_pipeline

FIXTURES = Path("tests/fixtures/hybrid-infra/configs")


class TestHybridInfraE2E:
    """Full pipeline on 100 configs — the definitive correctness gate."""

    @pytest.fixture(scope="class")
    def pipeline_result(self):  # type: ignore[no-untyped-def]
        """Run pipeline once, share across all tests in this class."""
        sources = sorted(str(f) for f in FIXTURES.iterdir())
        assert len(sources) == 100
        adapter = HybridInfraAdapter()
        config = EntityGraphConfig()
        return run_entity_graph_pipeline(sources, adapter, config)

    def test_zero_reconstruction_mismatches(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Pipeline completed without raising ReconstructionError."""
        assert pipeline_result is not None

    def test_total_entity_count(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """All 100 entities are in the graph."""
        total = sum(len(entities) for entities in pipeline_result.type_map.values())
        assert total == 100

    def test_all_entities_assigned_to_class(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Every entity should be assigned to exactly one class."""
        for type_id, tier_c in pipeline_result.tier_c_files.items():
            all_assigned: set[str] = set()
            for class_data in tier_c.class_assignments.values():
                all_assigned.update(class_data["instances"])

            expected = {e.id for e in pipeline_result.type_map[type_id]}
            assert all_assigned == expected, f"{type_id}: assignment mismatch"

    def test_tier_a_covers_all_types(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Tier A has entries for all discovered types."""
        tier_a = pipeline_result.tier_a
        assert len(tier_a["types"]) == len(pipeline_result.type_map)

    def test_detected_platforms_represented(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """All 5 detectable platforms appear in the type map."""
        all_hints: set[str] = set()
        for entities in pipeline_result.type_map.values():
            for e in entities:
                if e.schema_type_hint:
                    all_hints.add(e.schema_type_hint)
        expected = {"docker-compose", "ansible-playbook", "cloud-init", "traefik", "prometheus"}
        assert expected <= all_hints

    def test_graph_entity_count(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        assert len(pipeline_result.graph) == 100
