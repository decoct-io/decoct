"""End-to-end test: full pipeline on ~185 enterprise campus configs.

Gate test: run_entity_graph_pipeline() on all configs
with 0 reconstruction mismatches.
"""

from pathlib import Path

import pytest

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.adapters.ingestion_spec import load_ingestion_spec
from decoct.core.config import EntityGraphConfig
from decoct.entity_pipeline import run_entity_graph_pipeline

FIXTURES = Path("tests/fixtures/enterprise-campus/configs")
SPEC_PATH = Path("specs/ingestion/enterprise-campus/ingestion_spec.yaml")


class TestEnterpriseCampusE2E:
    """Full pipeline on ~185 enterprise campus configs — gate test."""

    @pytest.fixture(scope="class")
    def pipeline_result(self):  # type: ignore[no-untyped-def]
        """Run pipeline once, share across all tests in this class."""
        sources = sorted(str(f) for f in FIXTURES.iterdir())
        assert len(sources) == 185
        spec = load_ingestion_spec(SPEC_PATH)
        adapter = HybridInfraAdapter(ingestion_spec=spec)
        config = EntityGraphConfig()
        return run_entity_graph_pipeline(sources, adapter, config)

    def test_zero_reconstruction_mismatches(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Pipeline completed without raising ReconstructionError."""
        assert pipeline_result is not None

    def test_discovers_types(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """185 configs across 5 domains should discover many types."""
        type_names = sorted(pipeline_result.type_map.keys())
        assert len(type_names) >= 10  # at least 10 types from 33 config categories

    def test_total_entity_count(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """All 185 entities present in graph."""
        assert len(pipeline_result.graph) == 185

    def test_base_class_has_attributes(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Most types' base class should have attributes.

        Exception: db-config mixes PostgreSQL (flat key=value) with MariaDB
        ([section] INI), which produces no shared base attributes.
        """
        empty_base: list[str] = []
        for type_id, h in pipeline_result.hierarchies.items():
            if len(h.base_class.attrs) == 0:
                empty_base.append(type_id)
        # At most 1 type may have an empty base (heterogeneous INI mix)
        assert len(empty_base) <= 1, f"Too many types with empty base class: {empty_base}"

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
        assert len(tier_a["types"]) >= 10

    def test_graph_entity_count(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        assert len(pipeline_result.graph) == 185
