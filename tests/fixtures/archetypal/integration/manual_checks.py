#!/usr/bin/env python3
"""
Manual checks for the integration fixture (10 hosts × 15 sections, 13 classes).

Maps 1:1 to sections in the archetypal-integration-manual-checks.md document.
Prints actual values with PASS/FAIL/FLAG markers for human review.

Usage (from repo root):
    python tests/fixtures/archetypal/integration/manual_checks.py
"""

import copy
import os
import sys
from pathlib import Path

import yaml

# ── Locate the repo ──────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # archetypal/

from helpers import (  # noqa: E402
    TestCase,
    deep_get,
    load_case,
    normalize,
    reconstruct_instances,
    reconstruct_section,
)

FIXTURE_DIR = Path(__file__).resolve().parent

# ── Utilities ─────────────────────────────────────────────────────────────

passes = 0
fails = 0
flags = 0


def hr(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def dump_yaml(data, indent=0):
    """Pretty-print YAML data with optional indent."""
    text = yaml.dump(data, default_flow_style=False, sort_keys=False, width=120)
    for line in text.splitlines():
        print(" " * indent + line)


def ok(msg):
    global passes
    passes += 1
    print(f"    {msg:68s} ok")


def fail(msg):
    global fails
    fails += 1
    print(f"    {msg:68s} FAIL")


def flag(msg):
    global flags
    flags += 1
    print(f"    {msg:68s} FLAG")


def check(condition, msg):
    if condition:
        ok(msg)
    else:
        fail(msg)


# ── Load fixture ──────────────────────────────────────────────────────────

case = load_case(str(FIXTURE_DIR))


# ═══════════════════════════════════════════════════════════════════════════
# §0: Generation — file counts, absent host report
# ═══════════════════════════════════════════════════════════════════════════
def check_00_generation():
    hr("§0: Generation — file counts, absent host report")

    n_hosts = len(case.hosts)
    n_inputs = len(case.inputs)
    n_tier_c = len(case.tier_c)
    n_classes = len(case.tier_b)

    print(f"  Hosts:    {n_hosts}")
    print(f"  Inputs:   {n_inputs}")
    print(f"  Tier C:   {n_tier_c}")
    print(f"  Classes:  {n_classes}")
    print()

    check(n_hosts == 10, f"Host count = {n_hosts} (expected 10)")
    check(n_inputs == 10, f"Input count = {n_inputs} (expected 10)")
    check(n_tier_c == 10, f"Tier C count = {n_tier_c} (expected 10)")
    check(n_classes == 13, f"Class count = {n_classes} (expected 13)")

    # Absent sections
    absent = case.expected.get("absent_sections", {})
    print()
    print("  Absent sections:")
    for section, hosts in absent.items():
        for h in hosts:
            present = section in case.tier_c.get(h, {})
            check(not present, f"{h}/{section} absent from tier_c")


# ═══════════════════════════════════════════════════════════════════════════
# §1: Global structure — input key counts, tier_b class list, round-trips
# ═══════════════════════════════════════════════════════════════════════════
def check_01_global_structure():
    hr("§1: Global Structure — round-trip validation")

    # Input section counts
    all_sections = case.positive_sections + case.negative_sections
    print(f"  Positive sections: {case.positive_sections}")
    print(f"  Negative sections: {case.negative_sections}")
    print(f"  Total section types: {len(all_sections)}")
    print()

    # Tier B class list
    class_names = sorted(case.tier_b.keys())
    print(f"  Tier B classes ({len(class_names)}): {class_names}")
    print()

    # Round-trip every host × section
    rt_total = 0
    rt_fail = 0
    for host in case.hosts:
        for section in all_sections:
            if section not in case.inputs.get(host, {}):
                continue
            if section not in case.tier_c.get(host, {}):
                continue

            rt_total += 1
            input_data = case.inputs[host][section]
            tc = case.tier_c[host][section]

            if isinstance(tc, dict) and "_class" in tc:
                if "instances" in tc:
                    recon = reconstruct_instances(case.tier_b, tc)
                else:
                    recon = reconstruct_section(case.tier_b, tc)
            else:
                recon = copy.deepcopy(tc)

            if normalize(recon) != normalize(input_data):
                rt_fail += 1
                print(f"    MISMATCH: {host}/{section}")

    check(rt_fail == 0, f"Round-trip: {rt_total} checks, {rt_fail} failures")
    print(f"    ({rt_total} host×section pairs validated)")

    # Verify input sections == tier_c sections per host
    print()
    for host in case.hosts:
        input_sections = set(case.inputs.get(host, {}).keys())
        tc_sections = set(case.tier_c.get(host, {}).keys())
        check(input_sections == tc_sections,
              f"{host}: input sections == tier_c sections ({len(input_sections)})")


# ═══════════════════════════════════════════════════════════════════════════
# §2: S1 — system_base (Overlap)
# ═══════════════════════════════════════════════════════════════════════════
def check_02_system_base():
    hr("§2: S1 — system_base (Overlap)")

    cls = case.tier_b.get("SystemBase", {})
    fields = [k for k in cls if k != "_identity"]
    identity = cls.get("_identity", [])

    print(f"  Tier B: SystemBase")
    print(f"    Fields ({len(fields)}): {', '.join(fields)}")
    print(f"    _identity: {identity}")
    print()

    check(len(fields) == 16, f"Static field count = {len(fields)} (expected 16)")
    check(identity == ["snmp_location"], f"_identity = {identity} (expected ['snmp_location'])")
    check("snmp_location" not in fields, "snmp_location NOT in static fields")

    print()
    print("  Tier C per host:")
    locations = []
    for host in case.hosts:
        tc = case.tier_c[host].get("system_base", {})
        loc = tc.get("snmp_location", "MISSING")
        cls_ref = tc.get("_class", "MISSING")
        extras = [k for k in tc if k not in ("_class", "snmp_location")]
        status = "ok" if cls_ref == "SystemBase" and len(extras) == 0 else "FAIL"
        print(f"    {host}: _class={cls_ref}  snmp_location={loc}  extras={len(extras)}  {status}")
        locations.append(loc)

    unique = len(set(locations)) == len(locations)
    check(unique, f"snmp_location values all unique ({len(set(locations))}/{len(locations)})")

    # Spot-check reconstruction
    print()
    print("  Reconstruction spot-check:")
    for host in ["rtr-00", "rtr-05"]:
        tc = case.tier_c[host]["system_base"]
        recon = reconstruct_section(case.tier_b, tc)
        n_fields = len(recon)
        check(n_fields == 17, f"{host}: {n_fields} fields (16 static + 1 identity)")


# ═══════════════════════════════════════════════════════════════════════════
# §3: S2 — access_control (Progressive removal)
# ═══════════════════════════════════════════════════════════════════════════
def check_03_access_control():
    hr("§3: S2 — access_control (Progressive Removal)")

    cls = case.tier_b.get("AccessPolicy", {})
    fields = [k for k in cls if k != "_identity"]
    expected_info = case.expected["classes"]["access_control"]
    progression = expected_info.get("removal_progression", [])
    ac_hosts = expected_info["hosts"]

    print(f"  Tier B: AccessPolicy")
    print(f"    Fields ({len(fields)}): {', '.join(fields)}")
    print()

    check(len(fields) == 14, f"Static field count = {len(fields)} (expected 14)")

    print("  Progressive _remove per host:")
    for i, host in enumerate(ac_hosts):
        tc = case.tier_c[host].get("access_control", {})
        removals = tc.get("_remove", [])
        expected_count = progression[i] if i < len(progression) else "?"
        match = len(removals) == expected_count
        marker = "ok" if match else "FAIL"
        print(f"    {host}: _remove count={len(removals):2d} (expected {expected_count})  "
              f"fields={removals}  {marker}")
        if match:
            ok(f"{host} removal count matches")
        else:
            fail(f"{host} removal count mismatch: {len(removals)} != {expected_count}")

    # Cumulative superset check
    print()
    all_removed = set()
    superset_ok = True
    for i, host in enumerate(ac_hosts):
        tc = case.tier_c[host].get("access_control", {})
        removals = set(tc.get("_remove", []))
        if i > 0 and not all_removed.issubset(removals):
            superset_ok = False
        all_removed = removals
    check(superset_ok, "Each host's _remove is superset of previous")


# ═══════════════════════════════════════════════════════════════════════════
# §4: S3 — alert_targets (Progressive addition)
# ═══════════════════════════════════════════════════════════════════════════
def check_04_alert_targets():
    hr("§4: S3 — alert_targets (Progressive Addition)")

    cls = case.tier_b.get("AlertTarget", {})
    fields = [k for k in cls if k != "_identity"]
    progression = case.expected["classes"]["alert_targets"]["addition_progression"]

    print(f"  Tier B: AlertTarget")
    print(f"    Fields ({len(fields)}): {', '.join(fields)}")
    print()

    check(len(fields) == 5, f"Static field count = {len(fields)} (expected 5)")

    # Check timeout value specifically
    timeout_val = cls.get("timeout")
    check(timeout_val == 10, f"AlertTarget.timeout = {timeout_val} (expected 10, NOT 30)")

    print()
    print("  Progressive additions per host:")
    for i, host in enumerate(case.hosts):
        tc = case.tier_c[host].get("alert_targets", {})
        override_keys = [k for k in tc if k not in ("_class", "_remove")]
        expected_count = progression[i] if i < len(progression) else "?"
        match = len(override_keys) == expected_count
        marker = "ok" if match else "FAIL"
        print(f"    {host}: additions={len(override_keys):2d} (expected {expected_count})  "
              f"keys={override_keys}  {marker}")
        if match:
            ok(f"{host} addition count matches")
        else:
            fail(f"{host} addition count mismatch: {len(override_keys)} != {expected_count}")


# ═══════════════════════════════════════════════════════════════════════════
# §5: S4 — loopback0 (Identity-only)
# ═══════════════════════════════════════════════════════════════════════════
def check_05_loopback0():
    hr("§5: S4 — loopback0 (Identity-Only)")

    cls = case.tier_b.get("Loopback0Config", {})
    fields = [k for k in cls if k != "_identity"]
    identity = cls.get("_identity", [])

    print(f"  Tier B: Loopback0Config")
    print(f"    Fields ({len(fields)}): {', '.join(fields)}")
    print(f"    _identity: {identity}")
    print()

    check(len(fields) == 10, f"Static field count = {len(fields)} (expected 10)")
    check(identity == ["ipv4_address"], f"_identity = {identity}")

    print("  Tier C per host:")
    addresses = []
    for host in case.hosts:
        tc = case.tier_c[host].get("loopback0", {})
        addr = tc.get("ipv4_address", "MISSING")
        extras = [k for k in tc if k not in ("_class", "ipv4_address")]
        status = "ok" if len(extras) == 0 else "FAIL"
        print(f"    {host}: ipv4_address={addr}  extras={extras}  {status}")
        addresses.append(addr)

    unique = len(set(addresses)) == len(addresses)
    check(unique, f"ipv4_address values all unique ({len(set(addresses))}/{len(addresses)})")


# ═══════════════════════════════════════════════════════════════════════════
# §6: S5 — change_procedures (Ordered list, 1 raw deviant, 2 absent)
# ═══════════════════════════════════════════════════════════════════════════
def check_06_change_procedures():
    hr("§6: S5 — change_procedures (Ordered List)")

    cls = case.tier_b.get("ChangeProcedure", {})
    cp_info = case.expected["classes"]["change_procedures"]
    matching = cp_info["hosts_matching"]
    raw_hosts = cp_info.get("hosts_raw", [])
    absent = case.expected.get("absent_sections", {}).get("change_procedures", [])

    print(f"  Tier B: ChangeProcedure")
    print(f"    Steps: {cls.get('steps', [])}")
    print()

    print(f"  Hosts matching class ({len(matching)}): {matching}")
    print(f"  Raw hosts ({len(raw_hosts)}): {raw_hosts}  reason: {cp_info.get('raw_reason')}")
    print(f"  Absent hosts ({len(absent)}): {absent}")
    print()

    # Verify classed hosts
    for host in matching:
        tc = case.tier_c[host].get("change_procedures", {})
        has_class = tc.get("_class") == "ChangeProcedure"
        marker = "ok" if has_class else "FAIL"
        print(f"    {host}: _class={tc.get('_class', 'NONE'):20s} {marker}")
        check(has_class, f"{host} uses ChangeProcedure class")

    # Verify raw host (rtr-05 has step reorder)
    print()
    for host in raw_hosts:
        tc = case.tier_c[host].get("change_procedures", {})
        is_raw = "_class" not in tc
        steps = tc.get("steps", [])
        print(f"    {host} (raw): _class absent={is_raw}")
        print(f"      steps: {steps}")
        check(is_raw, f"{host} is raw (no _class)")

        # Check the step swap
        class_steps = cls.get("steps", [])
        if steps != class_steps and sorted(steps) == sorted(class_steps):
            ok(f"{host} has same steps but different order (reorder)")
        elif steps == class_steps:
            flag(f"{host} steps match class — why raw?")

    # Verify absent hosts
    print()
    for host in absent:
        present = "change_procedures" in case.tier_c.get(host, {})
        check(not present, f"{host} absent from change_procedures")


# ═══════════════════════════════════════════════════════════════════════════
# §7: S6 — fabric_interfaces (Instances)
# ═══════════════════════════════════════════════════════════════════════════
def check_07_fabric_interfaces():
    hr("§7: S6 — fabric_interfaces (Instances)")

    cls = case.tier_b.get("FabricInterface", {})
    fields = [k for k in cls if k != "_identity"]
    identity = cls.get("_identity", [])
    fi_info = case.expected["classes"]["fabric_interfaces"]

    print(f"  Tier B: FabricInterface")
    print(f"    Fields ({len(fields)}): {', '.join(fields)}")
    print(f"    _identity: {identity}")
    print()

    check(len(fields) == 5, f"Static field count = {len(fields)} (expected 5)")

    fi_hosts = fi_info["hosts"]
    absent_hosts = case.expected.get("absent_sections", {}).get("fabric_interfaces", [])

    print(f"  Instance counts per host (expected {fi_info['instance_count_per_host']}):")
    for host in fi_hosts:
        tc = case.tier_c[host].get("fabric_interfaces", {})
        instances = tc.get("instances", [])
        n = len(instances)
        match = n == fi_info["instance_count_per_host"]
        marker = "ok" if match else "FAIL"
        print(f"    {host}: {n} instances  {marker}")
        check(match, f"{host} instance count = {n}")

    # Check specific overrides
    print()
    print("  Instance overrides:")
    for ovr in fi_info.get("overrides", []):
        host, idx, field, value = ovr["host"], ovr["instance"], ovr["field"], ovr["value"]
        tc = case.tier_c[host]["fabric_interfaces"]
        inst = tc["instances"][idx]
        actual = inst.get(field, "MISSING")
        match = actual == value
        marker = "ok" if match else "FAIL"
        print(f"    {host}[{idx}].{field} = {actual!r} (expected {value!r})  {marker}")
        check(match, f"{host}[{idx}].{field} override")

    # Check specific removals
    print()
    print("  Instance removals:")
    for rm in fi_info.get("removals", []):
        host, idx, field = rm["host"], rm["instance"], rm["field"]
        tc = case.tier_c[host]["fabric_interfaces"]
        inst = tc["instances"][idx]
        removals = inst.get("_remove", [])
        has_removal = field in removals
        marker = "ok" if has_removal else "FAIL"
        print(f"    {host}[{idx}]._remove contains '{field}': {has_removal}  {marker}")
        check(has_removal, f"{host}[{idx}] removal of {field}")

    # Absent hosts
    for host in absent_hosts:
        present = "fabric_interfaces" in case.tier_c.get(host, {})
        check(not present, f"{host} absent from fabric_interfaces")


# ═══════════════════════════════════════════════════════════════════════════
# §8: S7 — telemetry_stack (Dot notation)
# ═══════════════════════════════════════════════════════════════════════════
def check_08_telemetry_stack():
    hr("§8: S7 — telemetry_stack (Dot Notation)")

    cls = case.tier_b.get("TelemetryStack", {})
    print("  Tier B: TelemetryStack (nested structure):")
    dump_yaml(cls, indent=4)
    print()

    # Check each host's tier_c for dot-notation patterns
    dot_hosts = {
        "rtr-01": "scalar override (global_interval)",
        "rtr-02": "depth-3 dot (transport.tls.cipher)",
        "rtr-03": "subtree removal (logging)",
        "rtr-04": "combo (scalar + list + dot removal)",
    }

    for host, description in dot_hosts.items():
        tc = case.tier_c[host].get("telemetry_stack", {})
        dot_keys = [k for k in tc if "." in str(k)]
        flat_overrides = [k for k in tc if k not in ("_class", "_remove") and "." not in str(k)]
        removals = tc.get("_remove", [])

        print(f"  {host} — {description}:")
        print(f"    Dot-notation keys: {dot_keys}")
        print(f"    Flat overrides:    {flat_overrides}")
        print(f"    _remove:           {removals}")

        # Verify dot-notation keys are flat strings, not nested YAML
        for dk in dot_keys:
            check(isinstance(dk, str), f"{host}: '{dk}' is a flat string key")

        # Reconstruction check
        recon = reconstruct_section(case.tier_b, tc)
        input_data = case.inputs[host]["telemetry_stack"]
        match = normalize(recon) == normalize(input_data)
        check(match, f"{host}: reconstruction matches input")
        if not match:
            print("    Expected:")
            dump_yaml(input_data, indent=6)
            print("    Got:")
            dump_yaml(recon, indent=6)
        print()

    # Specific checks
    # rtr-02: transport.tls.cipher override
    tc02 = case.tier_c["rtr-02"].get("telemetry_stack", {})
    check("transport.tls.cipher" in tc02, "rtr-02 has 'transport.tls.cipher' dot key")

    # rtr-03: subtree removal
    tc03 = case.tier_c["rtr-03"].get("telemetry_stack", {})
    check("logging" in tc03.get("_remove", []), "rtr-03 removes 'logging' subtree")

    # rtr-04: combo
    tc04 = case.tier_c["rtr-04"].get("telemetry_stack", {})
    check("transport.tls.cipher" in tc04.get("_remove", []),
          "rtr-04 removes 'transport.tls.cipher' via dot-notation")


# ═══════════════════════════════════════════════════════════════════════════
# §9: S8 — routing_policy (Partial classification — 2 classes + 2 raw)
# ═══════════════════════════════════════════════════════════════════════════
def check_09_routing_policy():
    hr("§9: S8 — routing_policy (Partial Classification)")

    rp_info = case.expected["classes"]["routing_policy"]
    class_names = rp_info["class_names"]
    group_1 = rp_info["group_1"]
    group_2 = rp_info["group_2"]
    raw_hosts = rp_info["raw_hosts"]
    shared = rp_info.get("shared_fields_not_merged", [])

    print(f"  Classes: {class_names}")
    print(f"  Group 1 ({class_names[0]}): {group_1}")
    print(f"  Group 2 ({class_names[1]}): {group_2}")
    print(f"  Raw outliers: {raw_hosts}")
    print(f"  Shared fields (not merged): {shared}")
    print()

    # Verify group assignments
    for host in group_1:
        tc = case.tier_c[host].get("routing_policy", {})
        cls_ref = tc.get("_class", "NONE")
        check(cls_ref == class_names[0], f"{host}: _class={cls_ref} (expected {class_names[0]})")

    for host in group_2:
        tc = case.tier_c[host].get("routing_policy", {})
        cls_ref = tc.get("_class", "NONE")
        check(cls_ref == class_names[1], f"{host}: _class={cls_ref} (expected {class_names[1]})")

    for host in raw_hosts:
        tc = case.tier_c[host].get("routing_policy", {})
        is_raw = "_class" not in tc
        check(is_raw, f"{host}: raw (no _class)")
        if not is_raw:
            print(f"      _class={tc.get('_class')}")

    # Verify shared fields are independent in each class
    print()
    print("  Shared field independence:")
    for field in shared:
        vals = {}
        for cn in class_names:
            cls_def = case.tier_b.get(cn, {})
            vals[cn] = cls_def.get(field, "MISSING")
        print(f"    {field}: {vals}")
        check(all(v != "MISSING" for v in vals.values()),
              f"'{field}' present in both classes")


# ═══════════════════════════════════════════════════════════════════════════
# §10: S9 — isis_config (Compound operations)
# ═══════════════════════════════════════════════════════════════════════════
def check_10_isis_config():
    hr("§10: S9 — isis_config (Compound Operations)")

    cls = case.tier_b.get("IsisConfig", {})
    fields = [k for k in cls if k != "_identity"]
    identity = cls.get("_identity", [])
    isis_info = case.expected["classes"]["isis_config"]
    compound = isis_info.get("compound_operations", {})

    print(f"  Tier B: IsisConfig")
    print(f"    Fields ({len(fields)}): {', '.join(fields)}")
    print(f"    _identity: {identity}")
    print()

    check(len(fields) == 12, f"Static field count = {len(fields)} (expected 12)")
    check(identity == ["net_address"], f"_identity = {identity}")

    # All hosts have unique net_address
    addresses = []
    for host in case.hosts:
        tc = case.tier_c[host].get("isis_config", {})
        addr = tc.get("net_address", "MISSING")
        addresses.append(addr)
        print(f"    {host}: net_address={addr}")

    unique = len(set(addresses)) == len(addresses)
    check(unique, f"net_address values all unique ({len(set(addresses))}/{len(addresses)})")

    # Compound operations
    print()
    print("  Compound operations:")
    for host, desc in compound.items():
        tc = case.tier_c[host].get("isis_config", {})
        removals = tc.get("_remove", [])
        overrides = [k for k in tc if k not in ("_class", "_remove", "net_address")]
        print(f"    {host}: {desc}")
        print(f"      identity: net_address={tc.get('net_address', 'MISSING')}")
        print(f"      _remove: {removals}")
        print(f"      overrides: {overrides}")

        # Reconstruction round-trip
        recon = reconstruct_section(case.tier_b, tc)
        input_data = case.inputs[host]["isis_config"]
        match = normalize(recon) == normalize(input_data)
        check(match, f"{host} compound reconstruction matches")


# ═══════════════════════════════════════════════════════════════════════════
# §11: S10 — vrf_routing (Compound instances)
# ═══════════════════════════════════════════════════════════════════════════
def check_11_vrf_routing():
    hr("§11: S10 — vrf_routing (Compound Instances)")

    cls = case.tier_b.get("VrfConfig", {})
    fields = [k for k in cls if k != "_identity"]
    identity = cls.get("_identity", [])
    vrf_info = case.expected["classes"]["vrf_routing"]

    print(f"  Tier B: VrfConfig")
    print(f"    Fields ({len(fields)}): {', '.join(fields)}")
    print(f"    _identity: {identity}")
    print()

    check(len(fields) == 5, f"Static field count = {len(fields)} (expected 5)")

    # Instance counts
    expected_n = vrf_info["instance_count_per_host"]
    print(f"  Instance counts (expected {expected_n}):")
    for host in case.hosts:
        tc = case.tier_c[host].get("vrf_routing", {})
        instances = tc.get("instances", [])
        n = len(instances)
        check(n == expected_n, f"{host}: {n} instances")

    # Specific overrides
    print()
    print("  Instance overrides:")
    for ovr in vrf_info.get("overrides", []):
        host, idx, field, value = ovr["host"], ovr["instance"], ovr["field"], ovr["value"]
        tc = case.tier_c[host]["vrf_routing"]
        inst = tc["instances"][idx]
        actual = inst.get(field, "MISSING")
        match = actual == value
        marker = "ok" if match else "FAIL"
        print(f"    {host}[{idx}].{field} = {actual!r} (expected {value!r})  {marker}")
        check(match, f"{host}[{idx}].{field} override")

    # Specific removals
    print()
    print("  Instance removals:")
    for rm in vrf_info.get("removals", []):
        host, idx, field = rm["host"], rm["instance"], rm["field"]
        tc = case.tier_c[host]["vrf_routing"]
        inst = tc["instances"][idx]
        removals = inst.get("_remove", [])
        has_removal = field in removals
        marker = "ok" if has_removal else "FAIL"
        print(f"    {host}[{idx}]._remove contains '{field}': {has_removal}  {marker}")
        check(has_removal, f"{host}[{idx}] removal of {field}")


# ═══════════════════════════════════════════════════════════════════════════
# §12: S11 — policy_maps (Compound dot notation)
# ═══════════════════════════════════════════════════════════════════════════
def check_12_policy_maps():
    hr("§12: S11 — policy_maps (Compound Dot Notation)")

    cls = case.tier_b.get("PolicyMap", {})
    print("  Tier B: PolicyMap (nested structure):")
    dump_yaml(cls, indent=4)
    print()

    # Hosts with dot-notation operations
    dot_hosts = {}
    for host in case.hosts:
        tc = case.tier_c[host].get("policy_maps", {})
        dot_keys = [k for k in tc if "." in str(k)]
        removals = [r for r in tc.get("_remove", []) if "." in r]
        if dot_keys or removals:
            dot_hosts[host] = {"dot_overrides": dot_keys, "dot_removals": removals}

    print(f"  Hosts with dot-notation ops: {list(dot_hosts.keys())}")
    for host, ops in dot_hosts.items():
        tc = case.tier_c[host].get("policy_maps", {})
        print(f"\n    {host}:")
        print(f"      Dot overrides: {ops['dot_overrides']}")
        print(f"      Dot removals:  {ops['dot_removals']}")
        print(f"      All tier_c keys: {list(tc.keys())}")

    # Specific checks
    # rtr-04: policy.dampening.* are additions (not in class)
    tc04 = case.tier_c["rtr-04"].get("policy_maps", {})
    dampening_keys = [k for k in tc04 if "dampening" in str(k)]
    print(f"\n  rtr-04 dampening keys (additions, not in class): {dampening_keys}")
    for dk in dampening_keys:
        in_class = deep_get(cls, dk.replace("'", ""), None) is not None
        check(not in_class, f"rtr-04 '{dk}' is addition (not in class)")

    # rtr-07: 3 operation types in one entry
    tc07 = case.tier_c["rtr-07"].get("policy_maps", {})
    dot_overrides_07 = [k for k in tc07 if k not in ("_class", "_remove") and "." in str(k)]
    dot_removals_07 = [r for r in tc07.get("_remove", []) if "." in r]
    print(f"\n  rtr-07: dot overrides={dot_overrides_07}  dot removals={dot_removals_07}")
    check(len(dot_overrides_07) > 0 and len(dot_removals_07) > 0,
          "rtr-07 has both dot overrides and dot removals")

    # Reconstruction for all hosts
    print()
    for host in case.hosts:
        tc = case.tier_c[host].get("policy_maps", {})
        recon = reconstruct_section(case.tier_b, tc)
        input_data = case.inputs[host]["policy_maps"]
        match = normalize(recon) == normalize(input_data)
        check(match, f"{host} policy_maps reconstruction matches")


# ═══════════════════════════════════════════════════════════════════════════
# §13: S12 — bgp_neighbors (Compound instances with dot-notation)
# ═══════════════════════════════════════════════════════════════════════════
def check_13_bgp_neighbors():
    hr("§13: S12 — bgp_neighbors (Compound Instances + Dot Notation)")

    cls = case.tier_b.get("BgpNeighborConfig", {})
    fields = [k for k in cls if k != "_identity"]
    identity = cls.get("_identity", [])
    bgp_info = case.expected["classes"]["bgp_neighbors"]

    print(f"  Tier B: BgpNeighborConfig")
    print(f"    Fields ({len(fields)}): {', '.join(fields)}")
    print(f"    _identity: {identity}")
    print()

    expected_n = bgp_info["instance_count_per_host"]
    print(f"  Instance counts (expected {expected_n}):")
    for host in case.hosts:
        tc = case.tier_c[host].get("bgp_neighbors", {})
        instances = tc.get("instances", [])
        n = len(instances)
        check(n == expected_n, f"{host}: {n} instances")

    # Instance dot overrides
    print()
    print("  Instance dot-notation overrides:")
    for ovr in bgp_info.get("instance_dot_overrides", []):
        host, idx, path, value = ovr["host"], ovr["instance"], ovr["path"], ovr["value"]
        tc = case.tier_c[host]["bgp_neighbors"]
        inst = tc["instances"][idx]
        actual = inst.get(path, "MISSING")
        match = actual == value
        marker = "ok" if match else "FAIL"
        print(f"    {host}[{idx}].'{path}' = {actual!r} (expected {value!r})  {marker}")
        # Verify it's a flat dot-notation key in tier_c
        check(path in inst, f"{host}[{idx}] has flat dot key '{path}'")

    # Instance dot removals
    print()
    print("  Instance dot-notation removals:")
    for rm in bgp_info.get("instance_dot_removals", []):
        host, idx, path = rm["host"], rm["instance"], rm["path"]
        tc = case.tier_c[host]["bgp_neighbors"]
        inst = tc["instances"][idx]
        removals = inst.get("_remove", [])
        has_removal = path in removals
        marker = "ok" if has_removal else "FAIL"
        print(f"    {host}[{idx}]._remove contains '{path}': {has_removal}  {marker}")
        check(has_removal, f"{host}[{idx}] dot removal of '{path}'")

    # Reconstruction for all hosts
    print()
    for host in case.hosts:
        tc = case.tier_c[host].get("bgp_neighbors", {})
        recon = reconstruct_instances(case.tier_b, tc)
        input_data = case.inputs[host]["bgp_neighbors"]
        match = normalize(recon) == normalize(input_data)
        check(match, f"{host} bgp_neighbors reconstruction matches")


# ═══════════════════════════════════════════════════════════════════════════
# §14: T1 — auth_methods (Type coercion trap)
# ═══════════════════════════════════════════════════════════════════════════
def check_14_trap_auth():
    hr("§14: T1 — auth_methods (Type Coercion Trap)")

    trap_info = case.expected["traps"]["auth_methods"]
    print(f"  Expected classes: {trap_info['expected_classes']}")
    print(f"  Reason: {trap_info['reason']}")
    print()

    # Verify no _class in any host
    any_class = False
    for host in case.hosts:
        tc = case.tier_c[host].get("auth_methods", {})
        if "_class" in tc:
            any_class = True
    check(not any_class, "No host has _class in auth_methods (0 classes)")

    # Type preservation: print repr() and type().__name__ for each field
    print()
    print("  Type preservation per host:")
    type_fields = ["mfa_enabled", "timeout", "max_retries", "method"]
    for host in case.hosts:
        tc = case.tier_c[host].get("auth_methods", {})
        parts = []
        for field in type_fields:
            val = tc.get(field)
            parts.append(f"{field}={val!r}({type(val).__name__})")
        print(f"    {host}: {', '.join(parts)}")

    # False-positive check: rtr-00, rtr-06, rtr-08 should be identical
    print()
    print("  False-positive check (identical hosts should NOT trigger compression):")
    identical_hosts = ["rtr-00", "rtr-06", "rtr-08"]
    values = {}
    for host in identical_hosts:
        tc = case.tier_c[host].get("auth_methods", {})
        values[host] = {k: (repr(v), type(v).__name__) for k, v in tc.items()}

    all_same = all(values[h] == values[identical_hosts[0]] for h in identical_hosts)
    if all_same:
        ok(f"{identical_hosts} have identical values+types — correctly not compressed")
    else:
        print(f"    Values differ (expected identical):")
        for h in identical_hosts:
            print(f"      {h}: {values[h]}")
        flag(f"{identical_hosts} differ — check if this is intentional")


# ═══════════════════════════════════════════════════════════════════════════
# §15: T2 — vendor_extensions (Heterogeneous trap)
# ═══════════════════════════════════════════════════════════════════════════
def check_15_trap_vendor():
    hr("§15: T2 — vendor_extensions (Heterogeneous Trap)")

    trap_info = case.expected["traps"]["vendor_extensions"]
    overlap_fields = trap_info.get("incidental_overlap", [])

    print(f"  Expected classes: {trap_info['expected_classes']}")
    print(f"  Reason: {trap_info['reason']}")
    print(f"  Incidental overlap fields: {overlap_fields}")
    print()

    # Verify no _class in any host
    any_class = False
    for host in case.hosts:
        tc = case.tier_c[host].get("vendor_extensions", {})
        if "_class" in tc:
            any_class = True
    check(not any_class, "No host has _class in vendor_extensions (0 classes)")

    # Schema diversity
    print()
    print("  Key sets per host:")
    all_keys = {}
    for host in case.hosts:
        tc = case.tier_c[host].get("vendor_extensions", {})
        keys = sorted(tc.keys())
        all_keys[host] = set(keys)
        print(f"    {host}: {keys}")

    unique_schemas = len(set(frozenset(v) for v in all_keys.values()))
    print(f"\n  Unique schemas: {unique_schemas}")
    check(unique_schemas > 1, f"Schema diversity: {unique_schemas} unique schemas (>1)")

    # Incidental overlap: count how many hosts share each overlap field
    print()
    print("  Incidental overlap analysis:")
    for field in overlap_fields:
        hosts_with = [h for h in case.hosts if field in all_keys[h]]
        print(f"    '{field}': present in {len(hosts_with)} hosts: {hosts_with}")
        # Didn't trigger compression despite overlap
        ok(f"'{field}' shared by {len(hosts_with)} hosts, didn't trigger compression")


# ═══════════════════════════════════════════════════════════════════════════
# §16: T3 — path_export (Same children, different parents)
# ═══════════════════════════════════════════════════════════════════════════
def check_16_trap_path_export():
    hr("§16: T3 — path_export (Same Children, Different Parents)")

    trap_info = case.expected["traps"]["path_export"]

    print(f"  Expected classes: {trap_info['expected_classes']}")
    print(f"  Reason: {trap_info['reason']}")
    print()

    # Verify no _class
    any_class = False
    for host in case.hosts:
        tc = case.tier_c[host].get("path_export", {})
        if "_class" in tc:
            any_class = True
    check(not any_class, "No host has _class in path_export (0 classes)")

    # Show parent keys are unique, leaf values are identical
    parents = []
    leaf_values = []
    for host in case.hosts:
        tc = case.tier_c[host].get("path_export", {})
        ep = tc.get("export_policy", {})
        parent_key = list(ep.keys())[0] if ep else "MISSING"
        parents.append(parent_key)
        leaf = ep.get(parent_key, {}) if ep else {}
        leaf_values.append(normalize(leaf))
        print(f"    {host}: parent='{parent_key}'  leaves={leaf}")

    unique_parents = len(set(parents))
    check(unique_parents == 10, f"Unique parent keys: {unique_parents} (expected 10)")

    # Check all leaves are identical
    all_same_leaves = all(lv == leaf_values[0] for lv in leaf_values)
    check(all_same_leaves, "All leaf values are identical across hosts")


# ═══════════════════════════════════════════════════════════════════════════
# §17: Cross-section isolation
# ═══════════════════════════════════════════════════════════════════════════
def check_17_cross_section():
    hr("§17: Cross-Section Isolation")

    # Timeout collision: AccessPolicy.timeout vs AlertTarget.timeout
    ap_timeout = case.tier_b.get("AccessPolicy", {}).get("timeout")
    at_timeout = case.tier_b.get("AlertTarget", {}).get("timeout")

    print("  Timeout collision check:")
    print(f"    AccessPolicy.timeout = {ap_timeout}")
    print(f"    AlertTarget.timeout  = {at_timeout}")
    check(ap_timeout == 30, f"AccessPolicy.timeout = {ap_timeout} (expected 30)")
    check(at_timeout == 10, f"AlertTarget.timeout = {at_timeout} (expected 10)")
    check(ap_timeout != at_timeout, "Timeouts are different (no cross-contamination)")

    # Overlapping field names across classes: check 'timeout' appears in multiple
    print()
    print("  'timeout' field across all classes:")
    for cls_name, cls_def in case.tier_b.items():
        if "timeout" in cls_def:
            print(f"    {cls_name}.timeout = {cls_def['timeout']}")

    # Adjacent positive+negative: hosts with both access_control (positive) and auth_methods (negative)
    print()
    print("  Adjacent pos+neg sections on same hosts:")
    for host in case.hosts:
        has_ac = "access_control" in case.tier_c.get(host, {})
        has_am = "auth_methods" in case.tier_c.get(host, {})
        ac_classed = "_class" in case.tier_c.get(host, {}).get("access_control", {}) if has_ac else False
        am_raw = "_class" not in case.tier_c.get(host, {}).get("auth_methods", {}) if has_am else False
        if has_ac and has_am:
            both_ok = ac_classed and am_raw
            marker = "ok" if both_ok else "FAIL"
            print(f"    {host}: access_control=classed({ac_classed})  auth_methods=raw({am_raw})  {marker}")
            check(both_ok, f"{host} pos+neg isolation")

    # Absent neighbours: hosts absent from one section still present in adjacent sections
    print()
    print("  Absent neighbours (absent in one section, present in adjacent):")
    absent_sections = case.expected.get("absent_sections", {})
    for section, absent_hosts in absent_sections.items():
        for host in absent_hosts:
            other_sections = [s for s in case.tier_c.get(host, {}).keys() if s != section]
            print(f"    {host} absent from {section}, present in {len(other_sections)} other sections")
            check(len(other_sections) > 0, f"{host} has other sections despite missing {section}")


# ═══════════════════════════════════════════════════════════════════════════
# §18: Optimality
# ═══════════════════════════════════════════════════════════════════════════
def check_18_optimality():
    hr("§18: Optimality")

    # No tier_c redundancy: for classed sections, check no override field duplicates the class value
    print("  Tier C redundancy check (no override = class value):")
    redundant_count = 0
    for host in case.hosts:
        for section, tc in case.tier_c[host].items():
            if not isinstance(tc, dict) or "_class" not in tc:
                continue
            cls_name = tc["_class"]
            cls_def = case.tier_b.get(cls_name, {})
            identity_fields = cls_def.get("_identity", [])

            # Check flat overrides
            for key, value in tc.items():
                if key in ("_class", "_remove", "instances"):
                    continue
                if key in identity_fields:
                    continue
                if "." in str(key):
                    # Dot-notation: check if resolved value matches class
                    cls_val = deep_get(cls_def, key, None)
                    if cls_val is not None and cls_val == value and type(cls_val) is type(value):
                        print(f"    REDUNDANT: {host}/{section}.{key} = {value!r} (same as class)")
                        redundant_count += 1
                else:
                    if key in cls_def and cls_def[key] == value and type(cls_def[key]) is type(value):
                        print(f"    REDUNDANT: {host}/{section}.{key} = {value!r} (same as class)")
                        redundant_count += 1

            # Check instance overrides
            for i, inst in enumerate(tc.get("instances", [])):
                for key, value in inst.items():
                    if key in ("_remove",):
                        continue
                    if key in identity_fields:
                        continue
                    if "." in str(key):
                        cls_val = deep_get(cls_def, key, None)
                        if cls_val is not None and cls_val == value and type(cls_val) is type(value):
                            print(f"    REDUNDANT: {host}/{section}[{i}].{key} = {value!r}")
                            redundant_count += 1
                    else:
                        if key in cls_def and cls_def[key] == value and type(cls_def[key]) is type(value):
                            print(f"    REDUNDANT: {host}/{section}[{i}].{key} = {value!r}")
                            redundant_count += 1

    check(redundant_count == 0, f"Tier C redundant overrides: {redundant_count} (expected 0)")

    # No tier_b redundancy: check each class field appears in at least 2 hosts
    print()
    print("  Tier B redundancy check (each class field shared by 2+ hosts):")
    for cls_name, cls_def in case.tier_b.items():
        identity_fields = cls_def.get("_identity", [])
        static_fields = [k for k in cls_def if k != "_identity" and k not in identity_fields]

        for field in static_fields:
            # Count how many hosts retain this field (not removed)
            retained = 0
            total = 0
            for host in case.hosts:
                for section, tc in case.tier_c[host].items():
                    if not isinstance(tc, dict) or tc.get("_class") != cls_name:
                        continue
                    total += 1
                    removals = tc.get("_remove", [])
                    if field not in removals:
                        retained += 1

            if retained < 2:
                flag(f"{cls_name}.{field}: retained by only {retained}/{total} hosts")
            elif retained == total:
                pass  # All hosts retain — perfectly shared
            else:
                pass  # Partially shared — fine

    # No missed extraction: negative sections should have diverse schemas or types
    print()
    print("  Missed extraction check (negative sections stay raw):")
    for section in case.negative_sections:
        any_classed = False
        for host in case.hosts:
            tc = case.tier_c[host].get(section, {})
            if isinstance(tc, dict) and "_class" in tc:
                any_classed = True
        check(not any_classed, f"{section}: correctly raw (0 classes)")


# ═══════════════════════════════════════════════════════════════════════════
# §19: expected.yaml metadata matches actual fixture
# ═══════════════════════════════════════════════════════════════════════════
def check_19_expected_yaml():
    hr("§19: expected.yaml Metadata Verification")

    expected = case.expected

    # Positive section list matches actual tier_b coverage
    actual_classed_sections = set()
    for host in case.hosts:
        for section, tc in case.tier_c[host].items():
            if isinstance(tc, dict) and "_class" in tc:
                actual_classed_sections.add(section)

    expected_pos = set(expected.get("positive_sections", []))
    check(actual_classed_sections == expected_pos,
          f"Positive sections match: {actual_classed_sections == expected_pos}")
    if actual_classed_sections != expected_pos:
        print(f"    Expected: {sorted(expected_pos)}")
        print(f"    Actual:   {sorted(actual_classed_sections)}")

    # Negative section list
    expected_neg = set(expected.get("negative_sections", []))
    actual_raw_sections = set()
    for host in case.hosts:
        for section, tc in case.tier_c[host].items():
            if isinstance(tc, dict) and "_class" not in tc:
                actual_raw_sections.add(section)
            elif not isinstance(tc, dict):
                actual_raw_sections.add(section)

    # Negative sections should all appear as raw in some hosts
    for ns in expected_neg:
        found_raw = any(
            ns in case.tier_c[h] and "_class" not in case.tier_c[h].get(ns, {})
            for h in case.hosts
        )
        check(found_raw, f"Negative section '{ns}' found as raw")

    # Class names match
    print()
    print("  Class name verification:")
    for section, info in expected.get("classes", {}).items():
        if "class_name" in info:
            cls_name = info["class_name"]
            check(cls_name in case.tier_b, f"{section}: class '{cls_name}' exists in tier_b")
        elif "class_names" in info:
            for cn in info["class_names"]:
                check(cn in case.tier_b, f"{section}: class '{cn}' exists in tier_b")

    # Host lists
    print()
    print("  Host list verification:")
    for section, info in expected.get("classes", {}).items():
        if "hosts" not in info:
            continue
        expected_hosts = set(info["hosts"])
        actual_hosts = set(h for h in case.hosts if section in case.tier_c.get(h, {}))
        match = expected_hosts == actual_hosts
        check(match, f"{section}: host list matches ({len(expected_hosts)} hosts)")
        if not match:
            print(f"      Expected: {sorted(expected_hosts)}")
            print(f"      Actual:   {sorted(actual_hosts)}")


# ═══════════════════════════════════════════════════════════════════════════
# §20: Compression ratio
# ═══════════════════════════════════════════════════════════════════════════
def check_20_compression_ratio():
    hr("§20: Compression Ratio")

    # Count lines in input files
    input_dir = FIXTURE_DIR / "input"
    input_lines = 0
    input_files = 0
    for f in sorted(input_dir.glob("rtr-*.yaml")):
        with open(f) as fh:
            input_lines += sum(1 for _ in fh)
        input_files += 1

    # Count lines in tier_b
    tier_b_path = FIXTURE_DIR / "golden" / "tier_b.yaml"
    with open(tier_b_path) as fh:
        tier_b_lines = sum(1 for _ in fh)

    # Count lines in tier_c
    tier_c_dir = FIXTURE_DIR / "golden" / "tier_c"
    tier_c_lines = 0
    tier_c_files = 0
    for f in sorted(tier_c_dir.glob("rtr-*.yaml")):
        with open(f) as fh:
            tier_c_lines += sum(1 for _ in fh)
        tier_c_files += 1

    compressed_lines = tier_b_lines + tier_c_lines
    ratio = input_lines / compressed_lines if compressed_lines > 0 else 0

    print(f"  Input:      {input_files:3d} files, {input_lines:5d} lines")
    print(f"  Tier B:     {1:3d} file,  {tier_b_lines:5d} lines")
    print(f"  Tier C:     {tier_c_files:3d} files, {tier_c_lines:5d} lines")
    print(f"  Compressed: {tier_c_files + 1:3d} files, {compressed_lines:5d} lines")
    print(f"  Ratio:      {ratio:.2f}×")
    print()

    check(ratio > 1.0, f"Compression ratio {ratio:.2f}× > 1.0 (actually saves space)")


# ═══════════════════════════════════════════════════════════════════════════
# Summary table
# ═══════════════════════════════════════════════════════════════════════════

CHECKS = [
    ("00", "check_00_generation", "Generation clean", "10 files, 13 classes"),
    ("01", "check_01_global_structure", "Round-trip (all checks)", "0 failures"),
    ("02", "check_02_system_base", "S1 overlap", "1 class, 16 fields"),
    ("03", "check_03_access_control", "S2 subtraction", "progressive _remove [0..7]"),
    ("04", "check_04_alert_targets", "S3 addition", "progressive [0..9], timeout=10"),
    ("05", "check_05_loopback0", "S4 identity-only", "10 fields, all unique addr"),
    ("06", "check_06_change_procedures", "S5 ordered list", "7 classed, 1 raw, 2 absent"),
    ("07", "check_07_fabric_interfaces", "S6 instances", "4/host, override+removal"),
    ("08", "check_08_telemetry_stack", "S7 dot notation", "4 variant hosts"),
    ("09", "check_09_routing_policy", "S8 partial classify", "2 classes, 2 raw"),
    ("10", "check_10_isis_config", "S9 compound ops", "identity + rm/ovrd"),
    ("11", "check_11_vrf_routing", "S10 compound instances", "3/host, ovrd+rm"),
    ("12", "check_12_policy_maps", "S11 compound dot", "dot overrides+removals"),
    ("13", "check_13_bgp_neighbors", "S12 compound inst+dot", "3/host, dot ops"),
    ("14", "check_14_trap_auth", "T1 type coercion", "0 classes, types preserved"),
    ("15", "check_15_trap_vendor", "T2 heterogeneous", "0 classes, schema diversity"),
    ("16", "check_16_trap_path_export", "T3 same children", "0 classes, 10 parents"),
    ("17", "check_17_cross_section", "Cross-section isolation", "no contamination"),
    ("18", "check_18_optimality", "Optimality", "no redundancy"),
    ("19", "check_19_expected_yaml", "expected.yaml metadata", "matches fixture"),
    ("20", "check_20_compression_ratio", "Compression ratio", "> 1.0×"),
]


def run_all():
    global passes, fails, flags

    check_fns = [
        check_00_generation,
        check_01_global_structure,
        check_02_system_base,
        check_03_access_control,
        check_04_alert_targets,
        check_05_loopback0,
        check_06_change_procedures,
        check_07_fabric_interfaces,
        check_08_telemetry_stack,
        check_09_routing_policy,
        check_10_isis_config,
        check_11_vrf_routing,
        check_12_policy_maps,
        check_13_bgp_neighbors,
        check_14_trap_auth,
        check_15_trap_vendor,
        check_16_trap_path_export,
        check_17_cross_section,
        check_18_optimality,
        check_19_expected_yaml,
        check_20_compression_ratio,
    ]

    for fn in check_fns:
        try:
            fn()
        except Exception as e:
            hr(f"ERROR in {fn.__name__}")
            print(f"  {type(e).__name__}: {e}")
            fails += 1

    # ── Summary table ─────────────────────────────────────────────────
    hr("Summary")

    print(f"  {'S':>3s}  {'Check':<32s}  {'Expected':<26s}  Status")
    print(f"  {'──':>3s}  {'─'*32:<32s}  {'─'*26:<26s}  ──────")

    # (We don't track per-section pass/fail individually, so just report overall)
    for sect_num, _fn_name, label, expected_val in CHECKS:
        # All checks ran inline — we rely on the global counters
        print(f"  {sect_num:>3s}  {label:<32s}  {expected_val:<26s}  (see above)")

    print()
    print(f"  Total: {passes} ok, {fails} FAIL, {flags} FLAG")
    print()

    if fails > 0:
        print(f"  RESULT: {fails} FAILURES — review output above")
    elif flags > 0:
        print(f"  RESULT: ALL PASS ({flags} flagged for review)")
    else:
        print("  RESULT: ALL PASS")

    return fails


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Decoct Integration Fixture — Manual Checks")
    print(f"Fixture dir: {FIXTURE_DIR}")
    print(f"Hosts: {case.hosts}")
    print(f"Classes: {sorted(case.tier_b.keys())}")

    exit_code = run_all()
    sys.exit(1 if exit_code > 0 else 0)
