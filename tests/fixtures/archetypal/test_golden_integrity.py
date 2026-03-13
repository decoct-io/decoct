"""
Archetypal fixture unit tests.

Level 1: Golden reference integrity.
Proves that Tier B + C reconstructs Tier A exactly for every set.

These tests validate the test data itself. When decoct is implemented,
a parallel test module (test_decoct_output.py) will score decoct's
actual output against these same golden references.
"""

import pytest

from helpers import (
    normalize,
    reconstruct_instances,
    reconstruct_section,
)


# ═══════════════════════════════════════════════════════════════════════
# RECONSTRUCTION — B + C == A
# ═══════════════════════════════════════════════════════════════════════

class TestReconstruction:
    """Tier B + Tier C must reconstruct Tier A exactly."""

    def test_all_hosts_present(self, case):
        """Every input host has a golden Tier C file."""
        for host in case.hosts:
            assert host in case.tier_c, (
                f"{case.name}/{host}: missing from golden tier_c"
            )

    def test_all_sections_present(self, case):
        """Every section in input appears in Tier C."""
        for host in case.hosts:
            for section in case.all_sections:
                assert section in case.inputs[host], (
                    f"{case.name}/{host}: section '{section}' missing from input"
                )
                assert section in case.tier_c[host], (
                    f"{case.name}/{host}: section '{section}' missing from tier_c"
                )

    def test_positive_section_reconstruction(self, case):
        """Positive sections reconstruct from B + C."""
        for host in case.hosts:
            for section in case.positive_sections:
                tc_section = case.tier_c[host][section]
                raw = case.inputs[host][section]

                if "_class" not in tc_section:
                    # Raw passthrough (e.g. Set G rtr-03)
                    assert normalize(tc_section) == normalize(raw), (
                        f"{case.name}/{host}/{section}: raw passthrough mismatch"
                    )
                elif "instances" in tc_section:
                    # Repeating entities (Set L)
                    reconstructed = reconstruct_instances(case.tier_b, tc_section)
                    # Raw may be a list directly, or a dict with a list value
                    if isinstance(raw, list):
                        raw_list = raw
                    elif isinstance(raw, dict):
                        raw_list = None
                        for k, v in raw.items():
                            if isinstance(v, list):
                                raw_list = v
                                break
                    else:
                        raw_list = None
                    assert raw_list is not None, (
                        f"{case.name}/{host}/{section}: no list found in raw input"
                    )
                    assert len(reconstructed) == len(raw_list), (
                        f"{case.name}/{host}/{section}: instance count mismatch "
                        f"({len(reconstructed)} vs {len(raw_list)})"
                    )
                    for idx, (recon, orig) in enumerate(zip(reconstructed, raw_list)):
                        assert normalize(recon) == normalize(orig), (
                            f"{case.name}/{host}/{section}/instance[{idx}]: mismatch"
                        )
                else:
                    # Standard class reconstruction
                    reconstructed = reconstruct_section(case.tier_b, tc_section)
                    assert normalize(reconstructed) == normalize(raw), (
                        f"{case.name}/{host}/{section}: reconstruction mismatch"
                    )

    def test_negative_section_passthrough(self, case):
        """Negative sections (traps) pass through as raw data."""
        for host in case.hosts:
            for section in case.negative_sections:
                tc_section = case.tier_c[host][section]
                raw = case.inputs[host][section]
                assert normalize(tc_section) == normalize(raw), (
                    f"{case.name}/{host}/{section}: raw passthrough mismatch"
                )


# ═══════════════════════════════════════════════════════════════════════
# STRUCTURAL — expected.yaml criteria
# ═══════════════════════════════════════════════════════════════════════

class TestStructure:
    """Golden references match expected structural properties."""

    def test_class_count(self, case):
        """Tier B has the expected number of classes."""
        expected_total = sum(
            cls.get("class_count", 1)
            for cls in case.expected.get("classes", {}).values()
        )
        actual = len(case.tier_b)
        assert actual == expected_total, (
            f"{case.name}: expected {expected_total} classes in tier_b, got {actual}"
        )

    def test_class_names(self, case):
        """Tier B class names match expected."""
        for section_key, cls_info in case.expected.get("classes", {}).items():
            if "class_name" in cls_info:
                assert cls_info["class_name"] in case.tier_b, (
                    f"{case.name}: expected class '{cls_info['class_name']}' not in tier_b"
                )
            if "class_names" in cls_info:
                for name in cls_info["class_names"]:
                    assert name in case.tier_b, (
                        f"{case.name}: expected class '{name}' not in tier_b"
                    )

    def test_negative_sections_no_class(self, case):
        """Negative sections have no _class in Tier C."""
        for host in case.hosts:
            for section in case.negative_sections:
                tc_section = case.tier_c[host][section]
                assert "_class" not in tc_section, (
                    f"{case.name}/{host}/{section}: trap should not have _class"
                )

    def test_identity_fields_declared(self, case):
        """Classes with identity fields have _identity in Tier B."""
        for section_key, cls_info in case.expected.get("classes", {}).items():
            if "identity_fields" in cls_info:
                class_name = cls_info.get("class_name")
                if class_name and class_name in case.tier_b:
                    cls_def = case.tier_b[class_name]
                    assert "_identity" in cls_def, (
                        f"{case.name}: class '{class_name}' missing _identity"
                    )
                    assert cls_def["_identity"] == cls_info["identity_fields"], (
                        f"{case.name}: class '{class_name}' _identity mismatch"
                    )

    def test_identity_fields_unique(self, case):
        """Identity field values are unique across hosts (or per-host for instances)."""
        for section_key, cls_info in case.expected.get("classes", {}).items():
            if "identity_fields" not in cls_info:
                continue
            class_name = cls_info.get("class_name")
            if not class_name:
                continue

            for id_field in cls_info["identity_fields"]:
                # For instance-based sections, check uniqueness per host
                has_instances = any(
                    "instances" in case.tier_c[h].get(section_key, {})
                    for h in case.hosts
                )
                if has_instances:
                    for host in case.hosts:
                        section = case.tier_c[host].get(section_key, {})
                        if "instances" not in section:
                            continue
                        host_values = [inst[id_field] for inst in section["instances"]
                                       if id_field in inst]
                        assert len(host_values) == len(set(str(v) for v in host_values)), (
                            f"{case.name}/{host}: identity field '{id_field}' "
                            f"has duplicates within host: {host_values}"
                        )
                else:
                    # Non-instance: check uniqueness across hosts
                    values = []
                    for host in case.hosts:
                        section = case.tier_c[host].get(section_key, {})
                        if "_class" in section and section["_class"] == class_name:
                            if id_field in section:
                                values.append(section[id_field])
                    if values:
                        assert len(values) == len(set(str(v) for v in values)), (
                            f"{case.name}: identity field '{id_field}' has duplicates: {values}"
                        )

    def test_static_field_count(self, case):
        """Classes have the expected number of static fields."""
        for section_key, cls_info in case.expected.get("classes", {}).items():
            if "static_field_count" not in cls_info:
                continue
            class_name = cls_info.get("class_name")
            if not class_name or class_name not in case.tier_b:
                continue
            cls_def = case.tier_b[class_name]
            # Count non-meta fields
            meta_keys = {"_identity", "_class", "_remove"}
            field_count = sum(1 for k in cls_def if k not in meta_keys)
            assert field_count == cls_info["static_field_count"], (
                f"{case.name}: class '{class_name}' expected "
                f"{cls_info['static_field_count']} static fields, got {field_count}"
            )


# ═══════════════════════════════════════════════════════════════════════
# SET-SPECIFIC — targeted checks per set
# ═══════════════════════════════════════════════════════════════════════

class TestSetSpecific:
    """Set-specific invariants that go beyond generic structural checks."""

    def test_set_b_progressive_removal(self, case):
        """Set B: each host's _remove is a superset of the previous."""
        if case.name != "set_b":
            pytest.skip("set_b only")
        section = case.positive_sections[0]
        prev_remove = set()
        for host in case.hosts:
            tc = case.tier_c[host][section]
            current = set(tc.get("_remove", []))
            assert prev_remove.issubset(current), (
                f"{host}: _remove {current} is not a superset of previous {prev_remove}"
            )
            prev_remove = current

    def test_set_c_progressive_addition(self, case):
        """Set C: each host adds fields cumulatively."""
        if case.name != "set_c":
            pytest.skip("set_c only")
        section = case.positive_sections[0]
        meta_keys = {"_class", "_remove"}
        prev_extras = set()
        for host in case.hosts:
            tc = case.tier_c[host][section]
            current = {k for k in tc if k not in meta_keys}
            assert prev_extras.issubset(current), (
                f"{host}: extras {current} is not a superset of previous {prev_extras}"
            )
            prev_extras = current

    def test_set_g_one_deviant(self, case):
        """Set G: exactly one host is raw (no _class), the rest use the class."""
        if case.name != "set_g":
            pytest.skip("set_g only")
        section = case.positive_sections[0]
        raw_hosts = [h for h in case.hosts
                     if "_class" not in case.tier_c[h][section]]
        classed_hosts = [h for h in case.hosts
                         if "_class" in case.tier_c[h][section]]
        assert len(raw_hosts) == 1, f"Expected 1 raw host, got {raw_hosts}"
        assert raw_hosts == ["rtr-03"]
        assert len(classed_hosts) == 4

    def test_set_l_one_override_one_removal(self, case):
        """Set L: exactly one instance override and one instance removal across all hosts."""
        if case.name != "set_l":
            pytest.skip("set_l only")
        section = case.positive_sections[0]
        overrides = []
        removals = []
        for host in case.hosts:
            tc = case.tier_c[host][section]
            for idx, inst in enumerate(tc.get("instances", [])):
                non_id = {k for k in inst if k not in ("name", "ipv4_address", "_remove")}
                if non_id:
                    overrides.append((host, idx, non_id))
                if "_remove" in inst:
                    removals.append((host, idx, inst["_remove"]))
        assert len(overrides) == 1, f"Expected 1 override, got {overrides}"
        assert len(removals) == 1, f"Expected 1 removal, got {removals}"
        assert overrides[0][:2] == ("rtr-02", 6)
        assert removals[0][:2] == ("rtr-03", 7)

    def test_set_n_two_groups_one_outlier(self, case):
        """Set N: 2 classes, 2 hosts each, plus 1 raw outlier."""
        if case.name != "set_n":
            pytest.skip("set_n only")
        section = case.positive_sections[0]
        classes_used = {}
        raw_hosts = []
        for host in case.hosts:
            tc = case.tier_c[host][section]
            if "_class" in tc:
                cn = tc["_class"]
                classes_used.setdefault(cn, []).append(host)
            else:
                raw_hosts.append(host)
        assert len(classes_used) == 2, f"Expected 2 classes, got {classes_used}"
        for cn, hosts in classes_used.items():
            assert len(hosts) == 2, f"Class {cn} expected 2 hosts, got {hosts}"
        assert len(raw_hosts) == 1
        assert raw_hosts == ["rtr-04"]

    def test_set_m_dot_notation_present(self, case):
        """Set M: hosts with overrides use dot notation keys."""
        if case.name != "set_m":
            pytest.skip("set_m only")
        section = case.positive_sections[0]
        # rtr-01 through rtr-04 should have dot-notation or _remove
        for host in ["rtr-01", "rtr-02", "rtr-04"]:
            tc = case.tier_c[host][section]
            dot_keys = [k for k in tc if "." in str(k) and k != "_class"]
            assert len(dot_keys) > 0, (
                f"{host}: expected dot-notation keys, got none"
            )
        # rtr-03 uses _remove with dot notation
        tc3 = case.tier_c["rtr-03"][section]
        assert "_remove" in tc3
        assert any("." in r for r in tc3["_remove"]), (
            "rtr-03: expected dot-notation in _remove"
        )

    def test_trap1_type_diversity(self, case):
        """Trap 1 (in set_a): types vary across hosts."""
        if case.name != "set_a":
            pytest.skip("set_a only")
        section = case.negative_sections[0]
        type_signatures = set()
        for host in case.hosts:
            tc = case.tier_c[host][section]
            sig = tuple(type(v).__name__ for v in tc.values())
            type_signatures.add(sig)
        assert len(type_signatures) >= 4, (
            f"Expected at least 4 distinct type signatures, got {len(type_signatures)}"
        )

    def test_trap2_all_different_parents(self, case):
        """Trap 2 (in set_c): each host has a different child key under service_policy."""
        if case.name != "set_c":
            pytest.skip("set_c only")
        section = case.negative_sections[0]
        parents = set()
        for host in case.hosts:
            tc = case.tier_c[host][section]
            # tc is the service_policy content — keys are the child names
            parents.update(tc.keys())
        assert len(parents) == 5, f"Expected 5 distinct parent keys, got {parents}"

    def test_trap4_identical_leaves(self, case):
        """Trap 4 (in set_m): all hosts have identical leaf values despite different parents."""
        if case.name != "set_m":
            pytest.skip("set_m only")
        section = case.negative_sections[0]
        leaf_values = []
        for host in case.hosts:
            tc = case.tier_c[host][section]
            sp = tc.get("service_policy", {})
            # Get the single child's value
            child_val = list(sp.values())[0]
            leaf_values.append(normalize(child_val))
        assert all(v == leaf_values[0] for v in leaf_values), (
            "Trap 4: leaf values should be identical across all hosts"
        )
