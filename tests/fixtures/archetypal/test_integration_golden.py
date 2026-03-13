"""
Level 2a — Integration golden reference validation.

Proves the golden references (tier_b.yaml + tier_c/*.yaml) are internally
consistent AND optimal. Does NOT test decoct's output — that's Level 2b.
"""
import sys
import os
import pytest

# Import helpers from parent (archetypal/) directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import (
    normalize,
    reconstruct_section,
    reconstruct_instances,
    deep_get,
    deep_set,
    deep_delete,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POSITIVE_SECTIONS = [
    "system_base",
    "access_control",
    "alert_targets",
    "loopback0",
    "change_procedures",
    "fabric_interfaces",
    "telemetry_stack",
    "routing_policy",
    "isis_config",
    "vrf_routing",
    "policy_maps",
    "bgp_neighbors",
]

NEGATIVE_SECTIONS = [
    "auth_methods",
    "vendor_extensions",
    "path_export",
]

INSTANCE_SECTIONS = ["fabric_interfaces", "vrf_routing", "bgp_neighbors"]

EXPECTED_CLASSES = [
    "SystemBase",
    "AccessPolicy",
    "AlertTarget",
    "Loopback0Config",
    "ChangeProcedure",
    "FabricInterface",
    "TelemetryStack",
    "RoutingPolicyCore",
    "RoutingPolicyVpn",
    "IsisConfig",
    "VrfConfig",
    "PolicyMap",
    "BgpNeighborConfig",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_instance_section(tc_entry):
    """True if the tier_c entry uses the instances mechanic."""
    return isinstance(tc_entry, dict) and "instances" in tc_entry


def _has_dot_key(d, exclude=("_class", "_remove", "_identity")):
    """True if dict d has any key containing '.' outside reserved keys."""
    if not isinstance(d, dict):
        return False
    return any("." in str(k) for k in d if k not in exclude)


def _override_keys(d, exclude=("_class", "_remove", "_identity")):
    """Return set of keys in d that are overrides (not reserved)."""
    if not isinstance(d, dict):
        return set()
    return {k for k in d if k not in exclude}


def _identity_fields_for_class(tier_b, class_name):
    """Return the _identity list for a class, or empty list."""
    cls = tier_b.get(class_name, {})
    return cls.get("_identity", [])


def _positive_host_section_pairs(case):
    """Yield (host, section) for positive dict sections present on each host."""
    for host in case.hosts:
        for section in POSITIVE_SECTIONS:
            if section in case.inputs.get(host, {}):
                tc = case.tier_c[host][section]
                if not _is_instance_section(tc):
                    yield pytest.param(host, section, id=f"{host}/{section}")


def _instance_host_section_pairs(case):
    """Yield (host, section) for instance sections present on each host."""
    for host in case.hosts:
        for section in INSTANCE_SECTIONS:
            if section in case.inputs.get(host, {}):
                tc = case.tier_c[host][section]
                if _is_instance_section(tc):
                    yield pytest.param(host, section, id=f"{host}/{section}")


# ---------------------------------------------------------------------------
# TestReconstruction
# ---------------------------------------------------------------------------

class TestReconstruction:

    def test_all_hosts_present(self, case):
        for host in case.hosts:
            assert host in case.inputs, f"{host} missing from inputs"
            assert host in case.tier_c, f"{host} missing from tier_c"

    def test_all_sections_present(self, case):
        for host in case.hosts:
            for section in case.inputs[host]:
                assert section in case.tier_c[host], (
                    f"{host}/{section} in inputs but missing from tier_c"
                )

    def test_input_tier_c_section_match(self, case):
        for host in case.hosts:
            assert set(case.inputs[host].keys()) == set(case.tier_c[host].keys()), (
                f"{host}: input sections != tier_c sections"
            )

    def test_positive_section_reconstruction(self, case):
        for host in case.hosts:
            for section in POSITIVE_SECTIONS:
                if section not in case.inputs.get(host, {}):
                    continue
                tc = case.tier_c[host][section]
                if _is_instance_section(tc):
                    continue  # tested separately
                if not isinstance(tc, dict) or "_class" not in tc:
                    continue  # raw passthrough (e.g. routing_policy outliers)
                reconstructed = reconstruct_section(case.tier_b, tc)
                assert normalize(reconstructed) == normalize(case.inputs[host][section]), (
                    f"Reconstruction mismatch: {host}/{section}"
                )

    def test_negative_section_passthrough(self, case):
        for host in case.hosts:
            for section in NEGATIVE_SECTIONS:
                if section not in case.inputs.get(host, {}):
                    continue
                assert normalize(case.tier_c[host][section]) == normalize(
                    case.inputs[host][section]
                ), f"Negative section not raw passthrough: {host}/{section}"

    def test_instance_section_reconstruction(self, case):
        for host in case.hosts:
            for section in INSTANCE_SECTIONS:
                if section not in case.inputs.get(host, {}):
                    continue
                tc = case.tier_c[host][section]
                if not _is_instance_section(tc):
                    continue
                reconstructed = reconstruct_instances(case.tier_b, tc)
                assert normalize(reconstructed) == normalize(
                    case.inputs[host][section]
                ), f"Instance reconstruction mismatch: {host}/{section}"


# ---------------------------------------------------------------------------
# TestAbsentSections
# ---------------------------------------------------------------------------

class TestAbsentSections:

    def test_absent_not_in_input(self, case):
        absent = case.expected.get("absent_sections", {})
        for section, hosts in absent.items():
            for host in hosts:
                assert section not in case.inputs.get(host, {}), (
                    f"Absent section {section} found in inputs for {host}"
                )

    def test_absent_not_in_tier_c(self, case):
        absent = case.expected.get("absent_sections", {})
        for section, hosts in absent.items():
            for host in hosts:
                assert section not in case.tier_c.get(host, {}), (
                    f"Absent section {section} found in tier_c for {host}"
                )

    def test_absent_no_side_effects(self, case):
        absent = case.expected.get("absent_sections", {})
        hosts_with_absences = set()
        for section, hosts in absent.items():
            hosts_with_absences.update(hosts)

        for host in hosts_with_absences:
            for section in case.inputs.get(host, {}):
                tc = case.tier_c[host][section]
                inp = case.inputs[host][section]
                if _is_instance_section(tc):
                    reconstructed = reconstruct_instances(case.tier_b, tc)
                elif isinstance(tc, dict) and "_class" in tc:
                    reconstructed = reconstruct_section(case.tier_b, tc)
                else:
                    reconstructed = tc  # raw passthrough
                assert normalize(reconstructed) == normalize(inp), (
                    f"Side-effect on {host}/{section} from absent section"
                )


# ---------------------------------------------------------------------------
# TestStructure
# ---------------------------------------------------------------------------

class TestStructure:

    def test_class_count(self, case):
        assert len(case.tier_b) == 13, (
            f"Expected 13 classes, got {len(case.tier_b)}"
        )

    def test_class_names(self, case):
        for name in EXPECTED_CLASSES:
            assert name in case.tier_b, f"Missing class: {name}"

    def test_negative_sections_no_class(self, case):
        for host in case.hosts:
            for section in NEGATIVE_SECTIONS:
                if section not in case.tier_c.get(host, {}):
                    continue
                entry = case.tier_c[host][section]
                if isinstance(entry, dict):
                    assert "_class" not in entry, (
                        f"Negative section {host}/{section} has _class"
                    )

    def test_identity_fields_declared(self, case):
        classes_meta = case.expected.get("classes", {})
        for section_name, meta in classes_meta.items():
            if "identity_fields" not in meta:
                continue
            class_name = meta.get("class_name") or meta.get("class_names", [None])[0]
            if class_name is None:
                continue
            expected_identity = meta["identity_fields"]
            actual_identity = case.tier_b[class_name].get("_identity", [])
            assert actual_identity == expected_identity, (
                f"{class_name}: expected _identity {expected_identity}, "
                f"got {actual_identity}"
            )

    def test_identity_fields_unique(self, case):
        classes_meta = case.expected.get("classes", {})
        for section_name, meta in classes_meta.items():
            if "identity_fields" not in meta:
                continue
            identity_fields = meta["identity_fields"]
            class_name = meta.get("class_name") or meta.get("class_names", [None])[0]
            if class_name is None:
                continue

            values_seen = set()
            for host in case.hosts:
                if section_name not in case.tier_c.get(host, {}):
                    continue
                tc = case.tier_c[host][section_name]
                if _is_instance_section(tc):
                    for inst in tc["instances"]:
                        key = tuple(inst.get(f) for f in identity_fields)
                        assert key not in values_seen, (
                            f"Duplicate identity {key} in {section_name}"
                        )
                        values_seen.add(key)
                elif isinstance(tc, dict) and "_class" in tc:
                    key = tuple(tc.get(f) for f in identity_fields)
                    assert key not in values_seen, (
                        f"Duplicate identity {key} in {section_name} ({host})"
                    )
                    values_seen.add(key)

    def test_static_field_count(self, case):
        classes_meta = case.expected.get("classes", {})
        for section_name, meta in classes_meta.items():
            if "static_field_count" not in meta:
                continue
            class_name = meta.get("class_name") or meta.get("class_names", [None])[0]
            if class_name is None:
                continue
            cls = case.tier_b[class_name]
            count = len([k for k in cls if k != "_identity"])
            assert count == meta["static_field_count"], (
                f"{class_name}: expected {meta['static_field_count']} static "
                f"fields, got {count}"
            )


# ---------------------------------------------------------------------------
# TestProgressions
# ---------------------------------------------------------------------------

class TestProgressions:

    def test_access_control_progressive_removal(self, case):
        meta = case.expected["classes"]["access_control"]
        progression = meta["removal_progression"]
        hosts = [h for h in case.hosts if "access_control" in case.tier_c.get(h, {})]
        for i, host in enumerate(hosts):
            tc = case.tier_c[host]["access_control"]
            removals = len(tc.get("_remove", []))
            assert removals == progression[i], (
                f"{host}: expected {progression[i]} removals, got {removals}"
            )

    def test_alert_targets_progressive_addition(self, case):
        meta = case.expected["classes"]["alert_targets"]
        progression = meta["addition_progression"]
        hosts = [h for h in case.hosts if "alert_targets" in case.tier_c.get(h, {})]
        for i, host in enumerate(hosts):
            tc = case.tier_c[host]["alert_targets"]
            additions = len(_override_keys(tc))
            assert additions == progression[i], (
                f"{host}: expected {progression[i]} additions, got {additions}"
            )

    def test_removal_superset(self, case):
        hosts = [h for h in case.hosts if "access_control" in case.tier_c.get(h, {})]
        prev = set()
        for host in hosts:
            tc = case.tier_c[host]["access_control"]
            current = set(tc.get("_remove", []))
            assert current >= prev, (
                f"{host}: removal set {current} is not superset of previous {prev}"
            )
            prev = current

    def test_addition_superset(self, case):
        hosts = [h for h in case.hosts if "alert_targets" in case.tier_c.get(h, {})]
        prev = set()
        for host in hosts:
            tc = case.tier_c[host]["alert_targets"]
            current = _override_keys(tc)
            assert current >= prev, (
                f"{host}: addition set {current} is not superset of previous {prev}"
            )
            prev = current


# ---------------------------------------------------------------------------
# TestPartialClassification
# ---------------------------------------------------------------------------

class TestPartialClassification:

    def test_routing_policy_group_count(self, case):
        classes_seen = set()
        for host in case.hosts:
            if "routing_policy" not in case.tier_c.get(host, {}):
                continue
            tc = case.tier_c[host]["routing_policy"]
            if isinstance(tc, dict) and "_class" in tc:
                classes_seen.add(tc["_class"])
        assert len(classes_seen) == 2, (
            f"Expected 2 routing_policy classes, got {classes_seen}"
        )

    def test_routing_policy_group_assignment(self, case):
        meta = case.expected["classes"]["routing_policy"]
        for host in meta.get("group_1", []):
            tc = case.tier_c[host]["routing_policy"]
            assert tc["_class"] == "RoutingPolicyCore", (
                f"{host}: expected RoutingPolicyCore"
            )
        for host in meta.get("group_2", []):
            tc = case.tier_c[host]["routing_policy"]
            assert tc["_class"] == "RoutingPolicyVpn", (
                f"{host}: expected RoutingPolicyVpn"
            )

    def test_routing_policy_raw_outliers(self, case):
        meta = case.expected["classes"]["routing_policy"]
        for host in meta.get("raw_hosts", []):
            tc = case.tier_c[host]["routing_policy"]
            if isinstance(tc, dict):
                assert "_class" not in tc, (
                    f"{host}: raw outlier should not have _class"
                )

    def test_routing_policy_shared_fields_not_merged(self, case):
        assert "asn" in case.tier_b["RoutingPolicyCore"], (
            "RoutingPolicyCore missing asn"
        )
        assert "asn" in case.tier_b["RoutingPolicyVpn"], (
            "RoutingPolicyVpn missing asn"
        )
        assert "router_id_source" in case.tier_b["RoutingPolicyCore"], (
            "RoutingPolicyCore missing router_id_source"
        )
        assert "router_id_source" in case.tier_b["RoutingPolicyVpn"], (
            "RoutingPolicyVpn missing router_id_source"
        )


# ---------------------------------------------------------------------------
# TestOrderedList
# ---------------------------------------------------------------------------

class TestOrderedList:

    def test_change_procedures_matching_hosts(self, case):
        meta = case.expected["classes"]["change_procedures"]
        for host in meta.get("hosts_matching", []):
            tc = case.tier_c[host]["change_procedures"]
            assert isinstance(tc, dict) and tc.get("_class") == "ChangeProcedure", (
                f"{host}: expected _class: ChangeProcedure"
            )

    def test_change_procedures_deviant_raw(self, case):
        meta = case.expected["classes"]["change_procedures"]
        for host in meta.get("hosts_raw", []):
            tc = case.tier_c[host]["change_procedures"]
            if isinstance(tc, dict):
                assert "_class" not in tc, (
                    f"{host}: deviant should not have _class"
                )

    def test_change_procedures_deviant_content(self, case):
        meta = case.expected["classes"]["change_procedures"]
        deviant_hosts = meta.get("hosts_raw", [])
        class_data = case.tier_b["ChangeProcedure"]
        class_steps = class_data.get("steps", [])

        for host in deviant_hosts:
            tc = case.tier_c[host]["change_procedures"]
            # Handle both dict and raw formats
            if isinstance(tc, dict):
                deviant_steps = tc.get("steps", [])
            else:
                continue
            assert sorted(str(s) for s in deviant_steps) == sorted(
                str(s) for s in class_steps
            ), f"{host}: deviant steps don't contain same items as class"
            assert deviant_steps != class_steps, (
                f"{host}: deviant steps should differ in order"
            )


# ---------------------------------------------------------------------------
# TestInstances
# ---------------------------------------------------------------------------

class TestInstances:

    def test_instance_count_per_host(self, case):
        expected_counts = {
            "fabric_interfaces": 4,
            "vrf_routing": 3,
            "bgp_neighbors": 3,
        }
        for section, expected in expected_counts.items():
            for host in case.hosts:
                if section not in case.tier_c.get(host, {}):
                    continue
                tc = case.tier_c[host][section]
                if not _is_instance_section(tc):
                    continue
                actual = len(tc["instances"])
                assert actual == expected, (
                    f"{host}/{section}: expected {expected} instances, got {actual}"
                )

    def test_instance_identity_fields(self, case):
        classes_meta = case.expected.get("classes", {})
        for section in INSTANCE_SECTIONS:
            meta = classes_meta.get(section, {})
            identity_fields = meta.get("identity_fields", [])
            if not identity_fields:
                continue
            for host in case.hosts:
                if section not in case.tier_c.get(host, {}):
                    continue
                tc = case.tier_c[host][section]
                if not _is_instance_section(tc):
                    continue
                for i, inst in enumerate(tc["instances"]):
                    for field in identity_fields:
                        assert field in inst, (
                            f"{host}/{section} instance {i}: "
                            f"missing identity field '{field}'"
                        )

    def test_fabric_interfaces_override(self, case):
        tc = case.tier_c["rtr-02"]["fabric_interfaces"]
        inst = tc["instances"][2]
        assert inst.get("speed") == "10g", (
            "rtr-02 fabric_interfaces instance 2: expected speed='10g'"
        )

    def test_fabric_interfaces_removal(self, case):
        tc = case.tier_c["rtr-08"]["fabric_interfaces"]
        inst = tc["instances"][3]
        assert "isis_metric" in inst.get("_remove", []), (
            "rtr-08 fabric_interfaces instance 3: expected _remove containing 'isis_metric'"
        )

    def test_vrf_routing_override(self, case):
        tc = case.tier_c["rtr-03"]["vrf_routing"]
        inst = tc["instances"][1]
        assert inst.get("route_limit") == 5000, (
            "rtr-03 vrf_routing instance 1: expected route_limit=5000"
        )

    def test_vrf_routing_removal(self, case):
        tc = case.tier_c["rtr-04"]["vrf_routing"]
        inst = tc["instances"][2]
        assert "route_warning_pct" in inst.get("_remove", []), (
            "rtr-04 vrf_routing instance 2: expected _remove containing 'route_warning_pct'"
        )


# ---------------------------------------------------------------------------
# TestDotNotation
# ---------------------------------------------------------------------------

class TestDotNotation:

    def test_telemetry_dot_keys_present(self, case):
        tc = case.tier_c["rtr-01"]["telemetry_stack"]
        assert _has_dot_key(tc), (
            "rtr-01 telemetry_stack: expected at least one dot-notation key"
        )

    def test_telemetry_subtree_removal(self, case):
        tc = case.tier_c["rtr-03"]["telemetry_stack"]
        assert "logging" in tc.get("_remove", []), (
            "rtr-03 telemetry_stack: expected _remove containing 'logging'"
        )

    def test_telemetry_combo_host(self, case):
        tc = case.tier_c["rtr-04"]["telemetry_stack"]
        assert _has_dot_key(tc), (
            "rtr-04 telemetry_stack: expected dot-notation overrides"
        )
        assert "_remove" in tc, (
            "rtr-04 telemetry_stack: expected _remove present"
        )

    def test_policy_maps_dot_override(self, case):
        tc = case.tier_c["rtr-01"]["policy_maps"]
        assert "policy.match.as_path" in tc, (
            "rtr-01 policy_maps: expected 'policy.match.as_path' key"
        )

    def test_policy_maps_dot_removal_and_addition(self, case):
        tc = case.tier_c["rtr-02"]["policy_maps"]
        removes = tc.get("_remove", [])
        has_dot_removal = any("." in str(r) for r in removes)
        assert has_dot_removal, (
            "rtr-02 policy_maps: expected dot-path in _remove"
        )
        assert _has_dot_key(tc), (
            "rtr-02 policy_maps: expected dot-notation addition key"
        )

    def test_policy_maps_subtree_addition(self, case):
        tc = case.tier_c["rtr-04"]["policy_maps"]
        assert "policy.dampening.half_life" in tc, (
            "rtr-04 policy_maps: expected 'policy.dampening.half_life'"
        )
        assert "policy.dampening.reuse" in tc, (
            "rtr-04 policy_maps: expected 'policy.dampening.reuse'"
        )

    def test_policy_maps_triple_combo(self, case):
        tc = case.tier_c["rtr-07"]["policy_maps"]
        dot_overrides = [
            k for k in tc
            if k not in ("_class", "_remove", "_identity") and "." in str(k)
        ]
        assert len(dot_overrides) >= 2, (
            f"rtr-07 policy_maps: expected >=2 dot overrides, got {len(dot_overrides)}"
        )
        removes = tc.get("_remove", [])
        dot_removals = [r for r in removes if "." in str(r)]
        assert len(dot_removals) >= 1, (
            "rtr-07 policy_maps: expected >=1 dot-notation removal"
        )


# ---------------------------------------------------------------------------
# TestInstanceDotNotation
# ---------------------------------------------------------------------------

class TestInstanceDotNotation:

    def test_bgp_dot_override_in_instance(self, case):
        tc = case.tier_c["rtr-01"]["bgp_neighbors"]
        inst = tc["instances"][1]
        assert "transport.md5_auth" in inst, (
            "rtr-01 bgp_neighbors instance 1: expected 'transport.md5_auth' key"
        )
        assert inst["transport.md5_auth"] is False, (
            "rtr-01 bgp_neighbors instance 1: expected transport.md5_auth=False"
        )

        tc4 = case.tier_c["rtr-04"]["bgp_neighbors"]
        inst4 = tc4["instances"][0]
        assert "afi.vpnv4" in inst4, (
            "rtr-04 bgp_neighbors instance 0: expected 'afi.vpnv4' key"
        )
        assert inst4["afi.vpnv4"] is True, (
            "rtr-04 bgp_neighbors instance 0: expected afi.vpnv4=True"
        )

    def test_bgp_dot_removal_in_instance(self, case):
        tc2 = case.tier_c["rtr-02"]["bgp_neighbors"]
        inst2 = tc2["instances"][2]
        assert "timers.connect_retry" in inst2.get("_remove", []), (
            "rtr-02 bgp_neighbors instance 2: expected _remove containing 'timers.connect_retry'"
        )

        tc8 = case.tier_c["rtr-08"]["bgp_neighbors"]
        inst8 = tc8["instances"][1]
        assert "timers.hold" in inst8.get("_remove", []), (
            "rtr-08 bgp_neighbors instance 1: expected _remove containing 'timers.hold'"
        )

    def test_bgp_dot_keys_are_flat_strings(self, case):
        for host in case.hosts:
            if "bgp_neighbors" not in case.tier_c.get(host, {}):
                continue
            tc = case.tier_c[host]["bgp_neighbors"]
            if not _is_instance_section(tc):
                continue
            for i, inst in enumerate(tc["instances"]):
                for key in inst:
                    if key in ("_class", "_remove", "_identity"):
                        continue
                    if "." in str(key):
                        assert isinstance(key, str), (
                            f"{host} bgp instance {i}: dot key {key!r} "
                            f"is not a str"
                        )

    def test_bgp_identity_only_count(self, case):
        meta = case.expected["classes"]["bgp_neighbors"]
        identity_fields = set(meta.get("identity_fields", []))
        identity_only = 0
        total = 0
        for host in case.hosts:
            if "bgp_neighbors" not in case.tier_c.get(host, {}):
                continue
            tc = case.tier_c[host]["bgp_neighbors"]
            if not _is_instance_section(tc):
                continue
            for inst in tc["instances"]:
                total += 1
                non_reserved = {
                    k for k in inst if k not in ("_class", "_remove", "_identity")
                }
                if non_reserved == identity_fields:
                    identity_only += 1
        assert total == 30, f"Expected 30 total BGP instances, got {total}"
        assert identity_only == 26, (
            f"Expected 26 identity-only instances, got {identity_only}"
        )


# ---------------------------------------------------------------------------
# TestCompoundOperations
# ---------------------------------------------------------------------------

class TestCompoundOperations:

    def test_isis_identity_plus_removal(self, case):
        tc = case.tier_c["rtr-02"]["isis_config"]
        assert "net_address" in tc, "rtr-02 isis_config: missing net_address"
        assert "auth_password" in tc.get("_remove", []), (
            "rtr-02 isis_config: expected _remove containing 'auth_password'"
        )

    def test_isis_identity_plus_override(self, case):
        tc = case.tier_c["rtr-03"]["isis_config"]
        assert "net_address" in tc, "rtr-03 isis_config: missing net_address"
        assert tc.get("metric_style") == "narrow", (
            "rtr-03 isis_config: expected metric_style='narrow'"
        )

    def test_isis_identity_plus_two_removals(self, case):
        tc = case.tier_c["rtr-06"]["isis_config"]
        assert "net_address" in tc, "rtr-06 isis_config: missing net_address"
        removals = tc.get("_remove", [])
        assert len(removals) == 2, (
            f"rtr-06 isis_config: expected 2 removals, got {len(removals)}"
        )


# ---------------------------------------------------------------------------
# TestCrossSectionIsolation
# ---------------------------------------------------------------------------

class TestCrossSectionIsolation:

    def test_timeout_field_independent(self, case):
        assert case.tier_b["AccessPolicy"]["timeout"] == 30, (
            "AccessPolicy.timeout should be 30"
        )
        assert case.tier_b["AlertTarget"]["timeout"] == 10, (
            "AlertTarget.timeout should be 10"
        )

    def test_overlapping_group_membership(self, case):
        rp = case.tier_c["rtr-06"]["routing_policy"]
        if isinstance(rp, dict):
            assert "_class" not in rp, (
                "rtr-06 routing_policy should be raw"
            )
        isis = case.tier_c["rtr-06"]["isis_config"]
        assert isinstance(isis, dict) and isis.get("_class") == "IsisConfig", (
            "rtr-06 isis_config should have _class: IsisConfig"
        )
        telem = case.tier_c["rtr-06"]["telemetry_stack"]
        assert isinstance(telem, dict) and telem.get("_class") == "TelemetryStack", (
            "rtr-06 telemetry_stack should have _class: TelemetryStack"
        )

    def test_adjacent_positive_negative(self, case):
        for host in case.hosts:
            tc = case.tier_c.get(host, {})
            has_ac = "access_control" in tc
            has_am = "auth_methods" in tc
            if has_ac and has_am:
                ac = tc["access_control"]
                am = tc["auth_methods"]
                if isinstance(ac, dict):
                    assert "_class" in ac, (
                        f"{host}: access_control should have _class"
                    )
                if isinstance(am, dict):
                    assert "_class" not in am, (
                        f"{host}: auth_methods should NOT have _class"
                    )


# ---------------------------------------------------------------------------
# TestOptimality
# ---------------------------------------------------------------------------

class TestOptimality:

    def test_no_tier_c_redundancy(self, case):
        """No override in tier_c duplicates the class value (identity exempt)."""
        for host in case.hosts:
            for section in case.tier_c.get(host, {}):
                tc = case.tier_c[host][section]
                if not isinstance(tc, dict):
                    continue
                class_name = tc.get("_class")
                if not class_name:
                    continue
                cls = case.tier_b.get(class_name, {})
                identity = set(cls.get("_identity", []))

                if _is_instance_section(tc):
                    # Check within each instance
                    for i, inst in enumerate(tc["instances"]):
                        inst_class_name = inst.get("_class", class_name)
                        inst_cls = case.tier_b.get(inst_class_name, cls)
                        inst_identity = set(inst_cls.get("_identity", []))
                        for key in inst:
                            if key in ("_class", "_remove", "_identity"):
                                continue
                            if key in inst_identity:
                                continue
                            # Dot-notation: resolve against class
                            if "." in key:
                                try:
                                    class_val = deep_get(inst_cls, key)
                                except (KeyError, TypeError):
                                    continue  # new subtree, not redundant
                            else:
                                if key not in inst_cls:
                                    continue
                                class_val = inst_cls[key]
                            assert inst[key] != class_val or type(inst[key]) != type(class_val), (
                                f"Redundant override: {host}/{section} "
                                f"instance {i} key '{key}' = {inst[key]!r} "
                                f"matches class value"
                            )
                else:
                    for key in tc:
                        if key in ("_class", "_remove", "_identity"):
                            continue
                        if key in identity:
                            continue
                        if "." in key:
                            try:
                                class_val = deep_get(cls, key)
                            except (KeyError, TypeError):
                                continue  # new subtree
                        else:
                            if key not in cls:
                                continue
                            class_val = cls[key]
                        assert tc[key] != class_val or type(tc[key]) != type(class_val), (
                            f"Redundant override: {host}/{section} "
                            f"key '{key}' = {tc[key]!r} matches class value"
                        )

    def test_no_tier_b_redundancy(self, case):
        """
        Every class field should be retained by >=2 hosts.
        Flag (don't fail) if count < 2.
        Known flag: AccessPolicy.tacacs_allow retained by 1 of 8.
        """
        import warnings

        for class_name, cls in case.tier_b.items():
            identity = set(cls.get("_identity", []))
            # Find which section uses this class
            section_for_class = None
            for host in case.hosts:
                for section in case.tier_c.get(host, {}):
                    tc = case.tier_c[host][section]
                    if isinstance(tc, dict) and tc.get("_class") == class_name:
                        section_for_class = section
                        break
                    if _is_instance_section(tc) and isinstance(tc, dict):
                        if tc.get("_class") == class_name:
                            section_for_class = section
                            break
                if section_for_class:
                    break
            if not section_for_class:
                continue

            for field in cls:
                if field in ("_identity",):
                    continue
                if field in identity:
                    continue

                retained = 0
                for host in case.hosts:
                    if section_for_class not in case.tier_c.get(host, {}):
                        continue
                    tc = case.tier_c[host][section_for_class]
                    if not isinstance(tc, dict):
                        continue
                    if "_class" not in tc and not _is_instance_section(tc):
                        continue  # raw host

                    # Check if field is removed or overridden
                    if _is_instance_section(tc):
                        # For instance sections, field is "retained" if class
                        # value is used in at least one instance
                        for inst in tc.get("instances", []):
                            removed = field in inst.get("_remove", [])
                            overridden = field in inst and field not in (
                                set(inst.get("_remove", []))
                            )
                            if not removed and field not in inst:
                                retained += 1
                    else:
                        removed = field in tc.get("_remove", [])
                        overridden = field in tc and field not in identity
                        if not removed and not overridden:
                            retained += 1

                if retained < 2:
                    warnings.warn(
                        f"FLAG: {class_name}.{field} retained by only "
                        f"{retained} host(s) — verify design decision"
                    )

    def test_negative_sections_all_raw(self, case):
        for host in case.hosts:
            for section in NEGATIVE_SECTIONS:
                if section not in case.tier_c.get(host, {}):
                    continue
                entry = case.tier_c[host][section]
                if isinstance(entry, dict):
                    assert "_class" not in entry, (
                        f"Negative section {host}/{section} has _class"
                    )
