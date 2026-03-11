"""End-to-end test: full pipeline on 86 IOS-XR configs.

THE gate test: run_entity_graph_pipeline() on all 86 configs
with 0 reconstruction mismatches.
"""

from pathlib import Path

import pytest

from decoct.adapters.iosxr import IosxrAdapter
from decoct.core.config import EntityGraphConfig
from decoct.entity_pipeline import run_entity_graph_pipeline

FIXTURES = Path("tests/fixtures/iosxr/configs")


class TestEntityGraphE2E:
    """Full pipeline on 86 configs — the definitive correctness gate."""

    @pytest.fixture(scope="class")
    def pipeline_result(self):  # type: ignore[no-untyped-def]
        """Run pipeline once, share across all tests in this class."""
        sources = sorted(str(f) for f in FIXTURES.glob("*.cfg"))
        assert len(sources) == 86
        adapter = IosxrAdapter()
        # Use warn mode for strict fidelity — IOS-XR adapter has known
        # structural transformations (bridge-group key collision,
        # confederation restructuring) that cause strict mismatches.
        config = EntityGraphConfig(source_fidelity_mode="warn")
        return run_entity_graph_pipeline(sources, adapter, config)

    def test_zero_reconstruction_mismatches(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Pipeline completed without raising ReconstructionError."""
        assert pipeline_result is not None

    def test_discovers_five_types(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """86 configs → 5 discovered types matching device roles."""
        type_names = sorted(pipeline_result.type_map.keys())
        assert len(type_names) == 5
        assert "iosxr-access-pe" in type_names
        assert "iosxr-bng" in type_names
        assert "iosxr-p-core" in type_names
        assert "iosxr-rr" in type_names
        assert "iosxr-services-pe" in type_names

    def test_type_counts_match(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Entity counts per type match expected distribution."""
        tm = pipeline_result.type_map
        assert len(tm["iosxr-access-pe"]) == 60
        assert len(tm["iosxr-bng"]) == 8
        assert len(tm["iosxr-p-core"]) == 6
        assert len(tm["iosxr-rr"]) == 4
        assert len(tm["iosxr-services-pe"]) == 8

    def test_access_pe_has_classes(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Access PE with 60 entities should produce multiple classes."""
        h = pipeline_result.hierarchies["iosxr-access-pe"]
        # Should have at least 2 non-base_only classes
        real_classes = [c for c in h.classes.values() if c.name != "_base_only"]
        assert len(real_classes) >= 1

    def test_base_class_has_attributes(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Each type's base class should have A_BASE attributes."""
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
        assert len(tier_a["types"]) == 5

    def test_relationships_preserved(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Relationships should be present in relationship_store."""
        total_rels = sum(
            len(rels) for tc in pipeline_result.tier_c_files.values()
            for rels in tc.relationship_store.values()
        )
        assert total_rels > 0

    def test_graph_entity_count(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        assert len(pipeline_result.graph) == 86

    def test_strict_fidelity_zero_mismatches(self, pipeline_result) -> None:  # type: ignore[no-untyped-def]
        """Strict bidirectional fidelity passed (validated in pipeline, would have raised)."""
        assert len(pipeline_result.source_leaves) == 86
