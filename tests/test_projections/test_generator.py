"""Unit tests for projection generator using synthetic Tier B/C data."""

from __future__ import annotations

import pytest

from decoct.projections.generator import generate_projection, validate_projection
from decoct.projections.models import RelatedPath, SubjectSpec


@pytest.fixture()
def tier_b() -> dict:
    """Synthetic Tier B data with BGP, ISIS, and interface attributes."""
    return {
        "meta": {
            "entity_type": "test-router",
            "total_instances": 4,
            "max_inheritance_depth": 2,
            "tier_c_ref": "test-router_instances.yaml",
        },
        "base_class": {
            "hostname": "router",
            "router.bgp.65002.address-family": "l2vpn-evpn",
            "router.bgp.65002.bgp": "log neighbor changes detail",
            "router.isis.CORE.is-type": "level-2-only",
            "router.isis.CORE.log": "adjacency changes",
            "interface.Loopback0.shutdown": "false",
            "interface.TenGigE0/0/0/0.mtu": "9216",
            "mpls.ldp": "true",
        },
        "classes": {
            "bgp_timers_60": {
                "inherits": "base",
                "own_attrs": {
                    "router.bgp.65002.timers": "bgp 60 180",
                    "router.bgp.65002.distance": "bgp 20 200 200",
                },
                "instance_count_inclusive": 2,
            },
            "bgp_timers_30": {
                "inherits": "base",
                "own_attrs": {
                    "router.bgp.65002.timers": "bgp 30 90",
                },
                "instance_count_inclusive": 2,
            },
        },
        "subclasses": {
            "bgp_timers_60_graceful": {
                "parent": "bgp_timers_60",
                "own_attrs": {
                    "router.bgp.65002.graceful-restart": "true",
                },
                "instance_count": 1,
            },
        },
        "assertions": {
            "base_only_ratio": 0.0,
        },
    }


@pytest.fixture()
def tier_c() -> dict:
    """Synthetic Tier C data."""
    return {
        "meta": {
            "entity_type": "test-router",
            "tier_b_ref": "test-router_classes.yaml",
            "total_instances": 4,
        },
        "class_assignments": {
            "bgp_timers_60": {
                "instances": ["R-01", "R-02"],
            },
            "bgp_timers_30": {
                "instances": ["R-03", "R-04"],
            },
        },
        "subclass_assignments": {
            "bgp_timers_60_graceful": {
                "parent": "bgp_timers_60",
                "instances": ["R-01"],
            },
        },
        "instance_data": {
            "schema": [
                "hostname",
                "interface.Loopback0.ipv4",
                "router.isis.CORE.net",
            ],
            "records": {
                "R-01": ["R-01", "10.0.0.1/32", "49.0001.0001.00"],
                "R-02": ["R-02", "10.0.0.2/32", "49.0001.0002.00"],
                "R-03": ["R-03", "10.0.0.3/32", "49.0001.0003.00"],
                "R-04": ["R-04", "10.0.0.4/32", "49.0001.0004.00"],
            },
        },
        "instance_attrs": {
            "R-01": {
                "interface.TenGigE0/0/0/0.description": "TO-CORE-01",
                "router.bgp.65002.neighbor": "10.0.0.100",
            },
        },
        "overrides": {
            "R-03": {
                "router.bgp.65002.bgp": "log neighbor changes",
                "interface.Loopback0.shutdown": "true",
            },
        },
        "foreign_keys": {},
    }


class TestGenerateProjection:
    def test_bgp_projection_filters_base_class(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="bgp",
            include_paths=["router.bgp.**"],
        )
        result = generate_projection(tier_b, tier_c, subject)

        # Base class should only have BGP keys
        base = result.get("base_class", {})
        assert "router.bgp.65002.address-family" in base
        assert "router.bgp.65002.bgp" in base
        assert "router.isis.CORE.is-type" not in base
        assert "interface.Loopback0.shutdown" not in base

    def test_bgp_projection_keeps_classes(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="bgp",
            include_paths=["router.bgp.**"],
        )
        result = generate_projection(tier_b, tier_c, subject)

        # Both classes have BGP attrs
        assert "bgp_timers_60" in result.get("classes", {})
        assert "bgp_timers_30" in result.get("classes", {})

    def test_bgp_projection_keeps_subclasses(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="bgp",
            include_paths=["router.bgp.**"],
        )
        result = generate_projection(tier_b, tier_c, subject)
        assert "bgp_timers_60_graceful" in result.get("subclasses", {})

    def test_isis_projection_hides_bgp_classes(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="isis",
            include_paths=["router.isis.**"],
        )
        result = generate_projection(tier_b, tier_c, subject)

        # No BGP classes should be visible
        assert "bgp_timers_60" not in result.get("classes", {})
        assert "bgp_timers_30" not in result.get("classes", {})

        # All entities go to _base_only
        base_only = result.get("class_assignments", {}).get("_base_only", {})
        assert len(base_only.get("instances", [])) > 0

    def test_phone_book_column_slice(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="isis",
            include_paths=["router.isis.**"],
            related_paths=[RelatedPath(path="hostname")],
        )
        result = generate_projection(tier_b, tier_c, subject)

        # Phone book should only have hostname and isis.net columns
        inst_data = result.get("instance_data", {})
        schema = inst_data.get("schema", [])
        assert "hostname" in schema
        assert "router.isis.CORE.net" in schema
        assert "interface.Loopback0.ipv4" not in schema

        # Records should be sliced to matching columns
        records = inst_data.get("records", {})
        assert len(records["R-01"]) == len(schema)

    def test_related_paths_included(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="bgp",
            include_paths=["router.bgp.**"],
            related_paths=[RelatedPath(path="hostname", reason="identity")],
        )
        result = generate_projection(tier_b, tier_c, subject)

        # hostname should be in base class (from related_paths)
        base = result.get("base_class", {})
        assert "hostname" in base

    def test_instance_attrs_filtered(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="bgp",
            include_paths=["router.bgp.**"],
        )
        result = generate_projection(tier_b, tier_c, subject)

        ia = result.get("instance_attrs", {})
        assert "R-01" in ia
        assert "router.bgp.65002.neighbor" in ia["R-01"]
        assert "interface.TenGigE0/0/0/0.description" not in ia["R-01"]

    def test_overrides_filtered(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="bgp",
            include_paths=["router.bgp.**"],
        )
        result = generate_projection(tier_b, tier_c, subject)

        ov = result.get("overrides", {})
        assert "R-03" in ov
        assert "router.bgp.65002.bgp" in ov["R-03"]
        assert "interface.Loopback0.shutdown" not in ov["R-03"]

    def test_entity_coverage_preserved(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="bgp",
            include_paths=["router.bgp.**"],
        )
        result = generate_projection(tier_b, tier_c, subject)

        # All 4 entities should appear in class assignments
        from decoct.assembly.tier_builder import expand_id_ranges

        all_ids: set[str] = set()
        for cls_data in result.get("class_assignments", {}).values():
            all_ids.update(expand_id_ranges(cls_data.get("instances", [])))
        assert all_ids == {"R-01", "R-02", "R-03", "R-04"}

    def test_meta_section(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="bgp",
            description="BGP routing configuration",
            include_paths=["router.bgp.**"],
        )
        result = generate_projection(tier_b, tier_c, subject)

        meta = result["meta"]
        assert meta["subject"] == "bgp"
        assert meta["description"] == "BGP routing configuration"
        assert meta["source_type"] == "test-router"
        assert meta["total_instances"] == 4

    def test_wildcard_projection_includes_everything(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="all",
            include_paths=["**"],
        )
        result = generate_projection(tier_b, tier_c, subject)

        # Should include all base class keys
        assert len(result.get("base_class", {})) == len(tier_b["base_class"])
        # Should include both classes
        assert len(result.get("classes", {})) == len(tier_b["classes"])


class TestValidateProjection:
    def test_valid_projection(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="bgp",
            include_paths=["router.bgp.**"],
        )
        projected = generate_projection(tier_b, tier_c, subject)
        errors = validate_projection(projected, tier_b, tier_c)
        assert errors == []

    def test_valid_wildcard_projection(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(
            name="all",
            include_paths=["**"],
        )
        projected = generate_projection(tier_b, tier_c, subject)
        errors = validate_projection(projected, tier_b, tier_c)
        assert errors == []

    def test_detects_value_mismatch(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(name="bgp", include_paths=["router.bgp.**"])
        projected = generate_projection(tier_b, tier_c, subject)
        # Tamper with a value
        projected["base_class"]["router.bgp.65002.address-family"] = "WRONG"
        errors = validate_projection(projected, tier_b, tier_c)
        assert any("value mismatch" in e for e in errors)

    def test_detects_missing_entities(self, tier_b: dict, tier_c: dict) -> None:
        subject = SubjectSpec(name="bgp", include_paths=["router.bgp.**"])
        projected = generate_projection(tier_b, tier_c, subject)
        # Remove an assignment
        if "bgp_timers_30" in projected.get("class_assignments", {}):
            del projected["class_assignments"]["bgp_timers_30"]
        elif "_base_only" in projected.get("class_assignments", {}):
            del projected["class_assignments"]["_base_only"]
        errors = validate_projection(projected, tier_b, tier_c)
        assert any("missing from projection" in e for e in errors)
