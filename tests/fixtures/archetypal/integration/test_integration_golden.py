"""
Integration golden reference tests for archetypal compression.

10 hosts x 15 sections covering all compression patterns:
  - 12 positive sections (compressed via _class)
  - 3 negative sections (traps — raw passthrough)
  - 3 absent sections (some hosts miss certain sections)
  - 3 list-of-dicts sections with instances
  - 2-class routing_policy (multi-group)
  - Dot-notation overrides/removals within instances
  - Progressive removal/addition patterns
  - Compound operations (identity + removal/override)

Structural assertions beyond round-trip: optimality, cross-section
isolation, absent section verification.
"""

import pytest

from helpers import deep_get, normalize, reconstruct_instances, reconstruct_section

_ABSENT = object()


def _count_leaves(d, exclude=frozenset()):
    """Count leaf fields in a (possibly nested) dict, skipping excludes."""
    count = 0
    for k, v in d.items():
        if k in exclude:
            continue
        if isinstance(v, dict):
            count += _count_leaves(v)
        else:
            count += 1
    return count


# ═══════════════════════════════════════════════════════════════════════
# ROUND-TRIP — B + C = A
# ═══════════════════════════════════════════════════════════════════════


class TestRoundTrip:
    """B + C = A for every host x present section."""

    def test_all_hosts_present(self, case):
        assert len(case.hosts) == 10
        for host in case.hosts:
            assert host in case.tier_c

    def test_section_sets_match(self, case):
        """Each host's tier_c sections == input sections."""
        for host in case.hosts:
            assert set(case.tier_c[host]) == set(case.inputs[host]), (
                f"{host}: tier_c has {set(case.tier_c[host])}, "
                f"input has {set(case.inputs[host])}"
            )

    def test_dict_sections_reconstruct(self, case):
        """Dict sections reconstruct from B + C."""
        for host in case.hosts:
            for section, raw in case.inputs[host].items():
                if isinstance(raw, list):
                    continue
                tc = case.tier_c[host][section]
                if "_class" not in tc:
                    recon = tc
                else:
                    recon = reconstruct_section(case.tier_b, tc)
                assert normalize(recon) == normalize(raw), (
                    f"{host}/{section}"
                )

    def test_list_sections_reconstruct(self, case):
        """List-of-dicts sections reconstruct from B + C."""
        for host in case.hosts:
            for section, raw in case.inputs[host].items():
                if not isinstance(raw, list):
                    continue
                tc = case.tier_c[host][section]
                if "_class" not in tc:
                    recon = tc
                else:
                    recon = reconstruct_instances(case.tier_b, tc)
                assert len(recon) == len(raw), (
                    f"{host}/{section}: {len(recon)} vs {len(raw)} instances"
                )
                for idx, (r, o) in enumerate(zip(recon, raw)):
                    assert normalize(r) == normalize(o), (
                        f"{host}/{section}[{idx}]"
                    )

    def test_total_roundtrip_count(self, case):
        """Exactly 144 host x section pairs."""
        total = sum(len(case.inputs[h]) for h in case.hosts)
        assert total == 144


# ═══════════════════════════════════════════════════════════════════════
# ABSENT SECTIONS
# ═══════════════════════════════════════════════════════════════════════


class TestAbsentSections:
    """Some hosts are missing certain sections — no spillover."""

    def test_absent_not_in_input(self, case):
        absent = case.expected.get("absent_sections", {})
        for section, hosts in absent.items():
            for host in hosts:
                assert section not in case.inputs[host], (
                    f"{host}: absent section '{section}' found in input"
                )

    def test_absent_not_in_tier_c(self, case):
        absent = case.expected.get("absent_sections", {})
        for section, hosts in absent.items():
            for host in hosts:
                assert section not in case.tier_c[host], (
                    f"{host}: absent section '{section}' found in tier_c"
                )

    def test_present_hosts_have_section(self, case):
        """Non-absent hosts DO have the section."""
        absent = case.expected.get("absent_sections", {})
        for section, absent_hosts in absent.items():
            for host in case.hosts:
                if host not in absent_hosts:
                    assert section in case.tier_c[host], (
                        f"{host}: should have '{section}'"
                    )

    def test_host_section_counts(self, case):
        """Per-host section counts match full_count minus absent."""
        absent = case.expected.get("absent_sections", {})
        full_count = len(case.positive_sections) + len(case.negative_sections)
        for host in case.hosts:
            absent_count = sum(
                1 for hosts in absent.values() if host in hosts
            )
            expected = full_count - absent_count
            assert len(case.inputs[host]) == expected, (
                f"{host}: expected {expected} sections, "
                f"got {len(case.inputs[host])}"
            )


# ═══════════════════════════════════════════════════════════════════════
# CLASS STRUCTURE
# ═══════════════════════════════════════════════════════════════════════


class TestClassStructure:
    """Tier B matches expected class metadata."""

    def test_total_class_count(self, case):
        expected = sum(
            c.get("class_count", 1)
            for c in case.expected["classes"].values()
        )
        assert len(case.tier_b) == expected

    def test_class_names_present(self, case):
        for cls_info in case.expected["classes"].values():
            for name in cls_info.get("class_names", []):
                assert name in case.tier_b
            if "class_name" in cls_info:
                assert cls_info["class_name"] in case.tier_b

    def test_static_field_counts(self, case):
        for cls_info in case.expected["classes"].values():
            if "static_field_count" not in cls_info:
                continue
            name = cls_info["class_name"]
            count = _count_leaves(case.tier_b[name], exclude={"_identity"})
            assert count == cls_info["static_field_count"], (
                f"{name}: expected {cls_info['static_field_count']} "
                f"static fields, got {count}"
            )

    def test_identity_fields(self, case):
        for cls_info in case.expected["classes"].values():
            if "identity_fields" not in cls_info:
                continue
            name = cls_info["class_name"]
            assert case.tier_b[name].get("_identity") == cls_info["identity_fields"], (
                f"{name}: _identity mismatch"
            )


# ═══════════════════════════════════════════════════════════════════════
# TRAPS — negative sections
# ═══════════════════════════════════════════════════════════════════════


class TestTraps:
    """Negative sections produce no classes."""

    def test_no_class_in_traps(self, case):
        for host in case.hosts:
            for section in case.negative_sections:
                if section not in case.tier_c[host]:
                    continue
                assert "_class" not in case.tier_c[host][section], (
                    f"{host}/{section}: trap should not have _class"
                )

    def test_type_coercion_trap(self, case):
        """auth_methods: type diversity prevents compression."""
        sigs = set()
        for host in case.hosts:
            tc = case.tier_c[host]["auth_methods"]
            sig = tuple((k, type(v).__name__) for k, v in sorted(tc.items()))
            sigs.add(sig)
        assert len(sigs) >= 3, (
            f"Expected type diversity in auth_methods, got {len(sigs)}"
        )

    def test_heterogeneous_trap(self, case):
        """vendor_extensions: different key sets prevent compression."""
        key_sets = set()
        for host in case.hosts:
            tc = case.tier_c[host]["vendor_extensions"]
            key_sets.add(frozenset(tc.keys()))
        assert len(key_sets) >= 5, (
            f"Expected key diversity in vendor_extensions, got {len(key_sets)}"
        )

    def test_same_children_different_parents_trap(self, case):
        """path_export: identical leaves under unique parent keys."""
        parents = set()
        leaf_values = []
        for host in case.hosts:
            ep = case.tier_c[host]["path_export"]["export_policy"]
            child_key = list(ep.keys())[0]
            parents.add(child_key)
            leaf_values.append(normalize(ep[child_key]))
        assert len(parents) == 10, (
            f"Expected 10 distinct parent keys, got {len(parents)}"
        )
        assert all(v == leaf_values[0] for v in leaf_values), (
            "Leaf values should be identical across all hosts"
        )


# ═══════════════════════════════════════════════════════════════════════
# PROGRESSIVE REMOVAL — access_control
# ═══════════════════════════════════════════════════════════════════════


class TestProgressiveRemoval:
    """access_control: hosts progressively remove more fields."""

    def test_removal_counts(self, case):
        info = case.expected["classes"]["access_control"]
        for host, expected in zip(info["hosts"], info["removal_progression"]):
            tc = case.tier_c[host]["access_control"]
            actual = len(tc.get("_remove", []))
            assert actual == expected, (
                f"{host}: expected {expected} removals, got {actual}"
            )

    def test_removals_cumulative(self, case):
        info = case.expected["classes"]["access_control"]
        prev = set()
        for host in info["hosts"]:
            tc = case.tier_c[host]["access_control"]
            current = set(tc.get("_remove", []))
            assert prev <= current, (
                f"{host}: removals not cumulative"
            )
            prev = current


# ═══════════════════════════════════════════════════════════════════════
# PROGRESSIVE ADDITION — alert_targets
# ═══════════════════════════════════════════════════════════════════════


class TestProgressiveAddition:
    """alert_targets: hosts progressively add more override fields."""

    def test_addition_counts(self, case):
        info = case.expected["classes"]["alert_targets"]
        meta = {"_class", "_remove"}
        for host, expected in zip(info["hosts"], info["addition_progression"]):
            tc = case.tier_c[host]["alert_targets"]
            extras = sum(1 for k in tc if k not in meta)
            assert extras == expected, (
                f"{host}: expected {expected} extra fields, "
                f"got {extras}"
            )

    def test_additions_cumulative(self, case):
        info = case.expected["classes"]["alert_targets"]
        meta = {"_class", "_remove"}
        prev = set()
        for host in info["hosts"]:
            tc = case.tier_c[host]["alert_targets"]
            current = {k for k in tc if k not in meta}
            assert prev <= current, (
                f"{host}: additions not cumulative"
            )
            prev = current


# ═══════════════════════════════════════════════════════════════════════
# MULTI-CLASS — routing_policy
# ═══════════════════════════════════════════════════════════════════════


class TestMultiClass:
    """routing_policy: 2 classes, 2 raw outliers."""

    def test_two_classes_exist(self, case):
        info = case.expected["classes"]["routing_policy"]
        for name in info["class_names"]:
            assert name in case.tier_b

    def test_group_1_assignments(self, case):
        info = case.expected["classes"]["routing_policy"]
        expected_class = info["class_names"][0]
        for host in info["group_1"]:
            assert case.tier_c[host]["routing_policy"]["_class"] == expected_class, (
                f"{host}: expected {expected_class}"
            )

    def test_group_2_assignments(self, case):
        info = case.expected["classes"]["routing_policy"]
        expected_class = info["class_names"][1]
        for host in info["group_2"]:
            assert case.tier_c[host]["routing_policy"]["_class"] == expected_class, (
                f"{host}: expected {expected_class}"
            )

    def test_raw_outliers(self, case):
        info = case.expected["classes"]["routing_policy"]
        for host in info["raw_hosts"]:
            assert "_class" not in case.tier_c[host]["routing_policy"], (
                f"{host}: raw outlier should not have _class"
            )

    def test_shared_fields_not_merged(self, case):
        """Both classes independently contain shared fields."""
        info = case.expected["classes"]["routing_policy"]
        c1 = case.tier_b[info["class_names"][0]]
        c2 = case.tier_b[info["class_names"][1]]
        for field in info.get("shared_fields_not_merged", []):
            assert field in c1, f"{info['class_names'][0]} missing {field}"
            assert field in c2, f"{info['class_names'][1]} missing {field}"


# ═══════════════════════════════════════════════════════════════════════
# INSTANCE SECTIONS — fabric_interfaces, vrf_routing, bgp_neighbors
# ═══════════════════════════════════════════════════════════════════════


class TestInstanceSections:
    """List-of-dicts sections with per-instance overrides/removals."""

    @pytest.mark.parametrize("section", [
        "fabric_interfaces", "vrf_routing", "bgp_neighbors",
    ])
    def test_instances_present(self, case, section):
        info = case.expected["classes"][section]
        for host in info["hosts"]:
            if section not in case.tier_c[host]:
                continue  # absent section
            tc = case.tier_c[host][section]
            assert "instances" in tc, f"{host}/{section}"

    @pytest.mark.parametrize("section", [
        "fabric_interfaces", "vrf_routing", "bgp_neighbors",
    ])
    def test_instance_counts(self, case, section):
        info = case.expected["classes"][section]
        expected = info.get("instance_count_per_host")
        if expected is None:
            pytest.skip("no fixed instance count")
        for host in info["hosts"]:
            if section not in case.tier_c[host]:
                continue
            actual = len(case.tier_c[host][section].get("instances", []))
            assert actual == expected, f"{host}/{section}"

    def test_fabric_override(self, case):
        """fabric_interfaces: specific instance field overrides."""
        for ov in case.expected["classes"]["fabric_interfaces"].get("overrides", []):
            inst = case.tier_c[ov["host"]]["fabric_interfaces"]["instances"][ov["instance"]]
            assert inst[ov["field"]] == ov["value"], (
                f"{ov['host']}[{ov['instance']}].{ov['field']}"
            )

    def test_fabric_removal(self, case):
        """fabric_interfaces: specific instance field removals."""
        for rm in case.expected["classes"]["fabric_interfaces"].get("removals", []):
            inst = case.tier_c[rm["host"]]["fabric_interfaces"]["instances"][rm["instance"]]
            assert rm["field"] in inst.get("_remove", []), (
                f"{rm['host']}[{rm['instance']}].{rm['field']}"
            )

    def test_vrf_override(self, case):
        """vrf_routing: specific instance field overrides."""
        for ov in case.expected["classes"]["vrf_routing"].get("overrides", []):
            inst = case.tier_c[ov["host"]]["vrf_routing"]["instances"][ov["instance"]]
            assert inst[ov["field"]] == ov["value"], (
                f"{ov['host']}[{ov['instance']}].{ov['field']}"
            )

    def test_vrf_removal(self, case):
        """vrf_routing: specific instance field removals."""
        for rm in case.expected["classes"]["vrf_routing"].get("removals", []):
            inst = case.tier_c[rm["host"]]["vrf_routing"]["instances"][rm["instance"]]
            assert rm["field"] in inst.get("_remove", []), (
                f"{rm['host']}[{rm['instance']}].{rm['field']}"
            )


# ═══════════════════════════════════════════════════════════════════════
# DOT-NOTATION WITHIN INSTANCES — bgp_neighbors
# ═══════════════════════════════════════════════════════════════════════


class TestDotNotationInstances:
    """bgp_neighbors: dot-notation overrides/removals within instances."""

    def test_dot_overrides_present(self, case):
        info = case.expected["classes"]["bgp_neighbors"]
        for ov in info.get("instance_dot_overrides", []):
            inst = case.tier_c[ov["host"]]["bgp_neighbors"]["instances"][ov["instance"]]
            assert ov["path"] in inst, (
                f"{ov['host']}[{ov['instance']}]: missing key '{ov['path']}'"
            )
            assert inst[ov["path"]] == ov["value"], (
                f"{ov['host']}[{ov['instance']}].{ov['path']}"
            )

    def test_dot_removals_present(self, case):
        info = case.expected["classes"]["bgp_neighbors"]
        for rm in info.get("instance_dot_removals", []):
            inst = case.tier_c[rm["host"]]["bgp_neighbors"]["instances"][rm["instance"]]
            assert rm["path"] in inst.get("_remove", []), (
                f"{rm['host']}[{rm['instance']}]: missing _remove '{rm['path']}'"
            )

    def test_dot_override_reconstructs(self, case):
        """Dot overrides reconstruct to correct nested values."""
        info = case.expected["classes"]["bgp_neighbors"]
        for ov in info.get("instance_dot_overrides", []):
            tc = case.tier_c[ov["host"]]["bgp_neighbors"]
            recon = reconstruct_instances(case.tier_b, tc)
            actual = deep_get(recon[ov["instance"]], ov["path"])
            assert actual == ov["value"], (
                f"{ov['host']}[{ov['instance']}].{ov['path']}: "
                f"reconstructed {actual!r}, expected {ov['value']!r}"
            )

    def test_dot_removal_reconstructs(self, case):
        """Dot removals produce absent nested keys after reconstruction."""
        info = case.expected["classes"]["bgp_neighbors"]
        for rm in info.get("instance_dot_removals", []):
            tc = case.tier_c[rm["host"]]["bgp_neighbors"]
            recon = reconstruct_instances(case.tier_b, tc)
            assert deep_get(recon[rm["instance"]], rm["path"], None) is None, (
                f"{rm['host']}[{rm['instance']}].{rm['path']}: "
                f"expected removed"
            )


# ═══════════════════════════════════════════════════════════════════════
# COMPOUND OPERATIONS — isis_config
# ═══════════════════════════════════════════════════════════════════════


class TestCompoundOperations:
    """isis_config: identity + removal/override combinations."""

    def test_compound_ops(self, case):
        info = case.expected["classes"]["isis_config"]
        for host, desc in info.get("compound_operations", {}).items():
            tc = case.tier_c[host]["isis_config"]
            assert "_class" in tc
            assert "net_address" in tc  # identity always present
            if "removal" in desc:
                assert "_remove" in tc, f"{host}: expected _remove for '{desc}'"
            if "override" in desc:
                meta = {"_class", "_remove", "net_address"}
                overrides = {k for k in tc if k not in meta}
                assert len(overrides) > 0, f"{host}: expected override for '{desc}'"


# ═══════════════════════════════════════════════════════════════════════
# CHANGE REORDER — change_procedures
# ═══════════════════════════════════════════════════════════════════════


class TestChangeReorder:
    """change_procedures: reordered list -> raw passthrough."""

    def test_reorder_host_raw(self, case):
        info = case.expected["classes"]["change_procedures"]
        for host in info.get("hosts_raw", []):
            tc = case.tier_c[host]["change_procedures"]
            assert "_class" not in tc, (
                f"{host}: reordered section should be raw"
            )

    def test_matching_hosts_classed(self, case):
        info = case.expected["classes"]["change_procedures"]
        for host in info.get("hosts_matching", []):
            tc = case.tier_c[host]["change_procedures"]
            assert tc.get("_class") == info["class_name"], (
                f"{host}: should use {info['class_name']}"
            )


# ═══════════════════════════════════════════════════════════════════════
# CROSS-SECTION ISOLATION
# ═══════════════════════════════════════════════════════════════════════


class TestCrossSectionIsolation:
    """No cross-contamination between sections."""

    def test_all_class_refs_valid(self, case):
        """Every _class in tier_c exists in tier_b."""
        for host in case.hosts:
            for section, tc in case.tier_c[host].items():
                if isinstance(tc, dict) and "_class" in tc:
                    assert tc["_class"] in case.tier_b, (
                        f"{host}/{section}: class '{tc['_class']}' not in tier_b"
                    )

    def test_no_class_shared_across_sections(self, case):
        """Each class is used by exactly one section."""
        class_to_section = {}
        for host in case.hosts:
            for section, tc in case.tier_c[host].items():
                if isinstance(tc, dict) and "_class" in tc:
                    cls = tc["_class"]
                    if cls in class_to_section:
                        assert class_to_section[cls] == section, (
                            f"Class '{cls}' used by both "
                            f"'{class_to_section[cls]}' and '{section}'"
                        )
                    class_to_section[cls] = section


# ═══════════════════════════════════════════════════════════════════════
# OPTIMALITY — compression quality
# ═══════════════════════════════════════════════════════════════════════


class TestOptimality:
    """No redundant data in tier_c."""

    def test_no_redundant_overrides(self, case):
        """Overrides in tier_c differ from the class value."""
        for host in case.hosts:
            for section, tc in case.tier_c[host].items():
                if not isinstance(tc, dict) or "_class" not in tc:
                    continue
                if "instances" in tc:
                    continue  # tested separately
                cls = case.tier_b[tc["_class"]]
                identity = set(cls.get("_identity", []))
                for key, value in tc.items():
                    if key in ("_class", "_remove"):
                        continue
                    if key in identity:
                        continue
                    if "." in key:
                        cls_val = deep_get(cls, key, _ABSENT)
                    else:
                        cls_val = cls.get(key, _ABSENT)
                    if cls_val is not _ABSENT:
                        assert normalize(value) != normalize(cls_val), (
                            f"{host}/{section}: override '{key}'={value!r} "
                            f"matches class — redundant"
                        )

    def test_removals_exist_in_class(self, case):
        """Every _remove path exists in the class definition."""
        for host in case.hosts:
            for section, tc in case.tier_c[host].items():
                if not isinstance(tc, dict) or "_class" not in tc:
                    continue
                if "instances" in tc:
                    continue  # tested separately
                cls = case.tier_b[tc["_class"]]
                for path in tc.get("_remove", []):
                    if "." in path:
                        assert deep_get(cls, path, _ABSENT) is not _ABSENT, (
                            f"{host}/{section}: _remove '{path}' not in class"
                        )
                    else:
                        assert path in cls, (
                            f"{host}/{section}: _remove '{path}' not in class"
                        )

    def test_instance_overrides_non_redundant(self, case):
        """Instance overrides differ from class values."""
        for host in case.hosts:
            for section, tc in case.tier_c[host].items():
                if not isinstance(tc, dict) or "instances" not in tc:
                    continue
                cls = case.tier_b[tc["_class"]]
                identity = set(cls.get("_identity", []))
                for idx, inst in enumerate(tc["instances"]):
                    for key, value in inst.items():
                        if key == "_remove":
                            continue
                        if key in identity:
                            continue
                        if "." in key:
                            cls_val = deep_get(cls, key, _ABSENT)
                        else:
                            cls_val = cls.get(key, _ABSENT)
                        if cls_val is not _ABSENT:
                            assert normalize(value) != normalize(cls_val), (
                                f"{host}/{section}[{idx}]: "
                                f"'{key}'={value!r} matches class — redundant"
                            )

    def test_instance_removals_exist_in_class(self, case):
        """Instance _remove paths exist in the class definition."""
        for host in case.hosts:
            for section, tc in case.tier_c[host].items():
                if not isinstance(tc, dict) or "instances" not in tc:
                    continue
                cls = case.tier_b[tc["_class"]]
                for idx, inst in enumerate(tc["instances"]):
                    for path in inst.get("_remove", []):
                        if "." in path:
                            assert deep_get(cls, path, _ABSENT) is not _ABSENT, (
                                f"{host}/{section}[{idx}]: "
                                f"_remove '{path}' not in class"
                            )
                        else:
                            assert path in cls, (
                                f"{host}/{section}[{idx}]: "
                                f"_remove '{path}' not in class"
                            )
