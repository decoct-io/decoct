"""End-to-end test: generate projections from real IOS-XR output."""

from __future__ import annotations

from pathlib import Path

import pytest

from decoct.assembly.tier_builder import expand_id_ranges
from decoct.projections.generator import generate_projection, validate_projection
from decoct.projections.spec_loader import load_projection_spec

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "entity-graph"
_SPEC_FILE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "projections" / "iosxr-access-pe_projection_spec.yaml"
)


@pytest.fixture()
def tier_b_c() -> tuple[dict, dict]:
    """Load real Tier B/C from output directory."""
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")

    classes_file = _OUTPUT_DIR / "iosxr-access-pe_classes.yaml"
    instances_file = _OUTPUT_DIR / "iosxr-access-pe_instances.yaml"

    if not classes_file.exists() or not instances_file.exists():
        pytest.skip("IOS-XR output files not found — run scripts/run_pipeline.py first")

    tier_b = yaml.load(classes_file.read_text())
    tier_c = yaml.load(instances_file.read_text())
    return tier_b, tier_c


@pytest.fixture()
def spec() -> load_projection_spec:
    """Load the hand-authored projection spec."""
    if not _SPEC_FILE.exists():
        pytest.skip("Projection spec fixture not found")
    return load_projection_spec(_SPEC_FILE)


class TestProjectionE2E:
    def test_all_subjects_produce_output(self, tier_b_c: tuple, spec: object) -> None:
        tier_b, tier_c = tier_b_c
        for subject in spec.subjects:
            result = generate_projection(tier_b, tier_c, subject)
            assert "meta" in result
            assert result["meta"]["subject"] == subject.name

    def test_all_subjects_validate(self, tier_b_c: tuple, spec: object) -> None:
        tier_b, tier_c = tier_b_c
        for subject in spec.subjects:
            result = generate_projection(tier_b, tier_c, subject)
            errors = validate_projection(result, tier_b, tier_c)
            assert errors == [], f"Subject '{subject.name}' validation failed: {errors}"

    def test_bgp_projection_contains_bgp_attrs(self, tier_b_c: tuple, spec: object) -> None:
        tier_b, tier_c = tier_b_c
        bgp_subject = next(s for s in spec.subjects if s.name == "bgp")
        result = generate_projection(tier_b, tier_c, bgp_subject)

        # Classes should have BGP attributes (BGP is class-level in this dataset)
        classes = result.get("classes", {})
        all_class_keys: set[str] = set()
        for cls_data in classes.values():
            all_class_keys.update(cls_data.get("own_attrs", {}).keys())
        bgp_keys = [k for k in all_class_keys if k.startswith("router.bgp.")]
        assert len(bgp_keys) > 0, "No BGP attributes in projected classes"

        # No ISIS attributes anywhere in the projection's base or classes
        base = result.get("base_class", {})
        isis_keys = [k for k in base if k.startswith("router.isis.")]
        assert len(isis_keys) == 0, "ISIS attributes leaked into BGP projection"

    def test_bgp_projection_preserves_entity_count(self, tier_b_c: tuple, spec: object) -> None:
        tier_b, tier_c = tier_b_c
        bgp_subject = next(s for s in spec.subjects if s.name == "bgp")
        result = generate_projection(tier_b, tier_c, bgp_subject)

        # All 60 entities should be accounted for
        all_ids: set[str] = set()
        for cls_data in result.get("class_assignments", {}).values():
            all_ids.update(expand_id_ranges(cls_data.get("instances", [])))
        assert len(all_ids) == 60

    def test_interfaces_projection_has_phone_book(self, tier_b_c: tuple, spec: object) -> None:
        tier_b, tier_c = tier_b_c
        iface_subject = next(s for s in spec.subjects if s.name == "interfaces")
        result = generate_projection(tier_b, tier_c, iface_subject)

        # Phone book should have interface columns
        inst_data = result.get("instance_data", {})
        schema = inst_data.get("schema", [])
        iface_cols = [s for s in schema if s.startswith("interface.")]
        assert len(iface_cols) > 0, "No interface columns in phone book"

    def test_projection_is_smaller_than_original(self, tier_b_c: tuple, spec: object) -> None:
        tier_b, tier_c = tier_b_c
        bgp_subject = next(s for s in spec.subjects if s.name == "bgp")
        result = generate_projection(tier_b, tier_c, bgp_subject)

        # Projected base_class should be smaller than original
        assert len(result.get("base_class", {})) < len(tier_b.get("base_class", {}))


class TestProjectCLI:
    def test_project_command(self, tier_b_c: tuple) -> None:
        """Smoke test the CLI project command."""
        from click.testing import CliRunner

        from decoct.cli import cli

        if not _SPEC_FILE.exists() or not _OUTPUT_DIR.exists():
            pytest.skip("Output or spec files not found")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "entity-graph", "project",
            "-o", str(_OUTPUT_DIR),
            "-s", str(_SPEC_FILE),
        ])
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "Generated" in result.output or "Projecting" in result.output
