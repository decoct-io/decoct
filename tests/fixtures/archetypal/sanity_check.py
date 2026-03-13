#!/usr/bin/env python3
"""
Sanity checks for archetypal_compress() — run AFTER the 36 unit tests pass.

These checks go beyond pass/fail: they dump actual output for human review
and verify properties the unit tests don't cover.

Usage (from repo root):
    python tests/fixtures/archetypal/sanity_check.py

Or ask Claude Code to run it and show you the output.
"""

import copy
import os
import sys
import yaml
from collections import OrderedDict
from pathlib import Path

# ── Locate the repo ──────────────────────────────────────────────────────
# Adjust this if your repo layout differs
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "fixtures" / "archetypal"))

from helpers import normalize, reconstruct_section, reconstruct_instances
from decoct.compression.archetypal import archetypal_compress

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "archetypal"

def load_set(set_name):
    """Load input data for a set, return {hostname: data}."""
    set_dir = FIXTURE_DIR / set_name
    inputs = {}
    for f in sorted((set_dir / "input").glob("rtr-*.yaml")):
        host = f.stem
        with open(f) as fh:
            inputs[host] = yaml.safe_load(fh)
    return inputs

def load_golden_b(set_name):
    with open(FIXTURE_DIR / set_name / "golden" / "tier_b.yaml") as f:
        return yaml.safe_load(f) or {}

def load_golden_c(set_name):
    tier_c = {}
    for f in sorted((FIXTURE_DIR / set_name / "golden" / "tier_c").glob("rtr-*.yaml")):
        host = f.stem
        with open(f) as fh:
            tier_c[host] = yaml.safe_load(fh)
    return tier_c

def hr(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def dump_yaml(data, indent=0):
    """Pretty-print YAML data with optional indent."""
    text = yaml.dump(data, default_flow_style=False, sort_keys=False, width=120)
    for line in text.splitlines():
        print(" " * indent + line)


# ═══════════════════════════════════════════════════════════════════════
# CHECK 1: Inspect actual output for Set A (overlap) and Set M (dot notation)
# ═══════════════════════════════════════════════════════════════════════
def check_1_inspect_output():
    hr("CHECK 1: Actual output inspection — Set A (overlap)")

    inputs = load_set("set_a")
    tier_b, tier_c = archetypal_compress(inputs)

    print("── Tier B (classes extracted) ──")
    dump_yaml(tier_b)

    print("\n── Tier C (per-host, first 3 hosts) ──")
    for host in sorted(tier_c)[:3]:
        print(f"\n  {host}:")
        dump_yaml(tier_c[host], indent=4)

    print("\n── Golden Tier B for comparison ──")
    dump_yaml(load_golden_b("set_a"))

    # Key question: does the output look like something an LLM can read?
    print("\n── Readability check ──")
    if tier_b:
        class_names = list(tier_b.keys())
        print(f"  Classes found: {class_names}")
        for cn in class_names:
            fields = [k for k in tier_b[cn] if k != "_identity"]
            print(f"  {cn}: {len(fields)} fields")
    else:
        print("  No classes extracted (unexpected for Set A!)")

    # Now Set M
    hr("CHECK 1 (cont): Actual output inspection — Set M (dot notation)")

    inputs = load_set("set_m")
    tier_b, tier_c = archetypal_compress(inputs)

    print("── Tier B ──")
    dump_yaml(tier_b)

    print("\n── Tier C for rtr-04 (most complex — combo host) ──")
    if "rtr-04" in tier_c:
        dump_yaml(tier_c["rtr-04"])
    else:
        print("  rtr-04 not in output!")

    # Check: are dot-notation keys actually present?
    if "rtr-04" in tier_c:
        for section_name, section_data in tier_c["rtr-04"].items():
            if isinstance(section_data, dict):
                dot_keys = [k for k in section_data if "." in str(k)]
                if dot_keys:
                    print(f"\n  Dot-notation keys in {section_name}: {dot_keys}")
                else:
                    print(f"\n  WARNING: No dot-notation keys in {section_name}")
                    print(f"  Keys present: {list(section_data.keys())}")


# ═══════════════════════════════════════════════════════════════════════
# CHECK 2: Trap verification — are traps actually producing 0 classes?
# ═══════════════════════════════════════════════════════════════════════
def check_2_traps():
    hr("CHECK 2: Trap verification")

    trap_cases = [
        ("set_a", "snmp_security", "Trap 1 — Type Coercion"),
        ("set_c", "service_policy", "Trap 2 — Low Jaccard Disguised"),
        ("set_d", "dns_resolution", "Trap 3 — Structural Nesting"),
        ("set_m", "export_policy", "Trap 4 — Same Children Different Parents"),
        ("set_e", "config_block", "Set E — Heterogeneous"),
    ]

    all_pass = True
    for set_name, section, label in trap_cases:
        inputs = load_set(set_name)
        tier_b, tier_c = archetypal_compress(inputs)

        # Check: does any host in this section have a _class?
        classes_found = set()
        has_class = False
        for host, host_data in tier_c.items():
            if section in host_data:
                sec = host_data[section]
                if isinstance(sec, dict) and "_class" in sec:
                    has_class = True
                    classes_found.add(sec["_class"])

        # Check: are there classes in tier_b for this section?
        # (We need to check if any class is referenced by this section)

        status = "PASS" if not has_class else "FAIL"
        if has_class:
            all_pass = False

        print(f"  {label:50s}  classes={len(classes_found):d}  {status}")
        if has_class:
            print(f"    PROBLEM: Found _class references: {classes_found}")
            print(f"    Showing first host with _class:")
            for host, host_data in tier_c.items():
                if section in host_data:
                    sec = host_data[section]
                    if isinstance(sec, dict) and "_class" in sec:
                        dump_yaml({host: {section: sec}}, indent=6)
                        break

    if all_pass:
        print("\n  All traps correctly produced 0 classes.")
    else:
        print("\n  WARNING: Some traps were incorrectly compressed!")


# ═══════════════════════════════════════════════════════════════════════
# CHECK 3: Type preservation in Trap 1 specifically
# ═══════════════════════════════════════════════════════════════════════
def check_3_type_preservation():
    hr("CHECK 3: Type preservation — Trap 1 detail")

    inputs = load_set("set_a")
    tier_b, tier_c = archetypal_compress(inputs)

    print("  Checking snmp_security values are type-preserved:\n")

    expected_types = {
        "rtr-00": {"snmp_auth_enabled": bool, "snmp_encrypt": bool, "snmp_version": int},
        "rtr-01": {"snmp_auth_enabled": str, "snmp_encrypt": bool, "snmp_version": int},
        "rtr-02": {"snmp_auth_enabled": bool, "snmp_encrypt": str, "snmp_version": str},
        "rtr-03": {"snmp_auth_enabled": int, "snmp_encrypt": bool, "snmp_version": int},
        "rtr-04": {"snmp_auth_enabled": str, "snmp_encrypt": str, "snmp_version": int},
    }

    all_ok = True
    for host in sorted(tier_c):
        if "snmp_security" not in tier_c[host]:
            print(f"  {host}: snmp_security missing from output!")
            all_ok = False
            continue

        sec = tier_c[host]["snmp_security"]
        if host in expected_types:
            for field, expected_type in expected_types[host].items():
                if field in sec:
                    actual_type = type(sec[field])
                    match = actual_type == expected_type
                    marker = "ok" if match else "MISMATCH"
                    print(f"  {host}.{field}: value={sec[field]!r:12s} "
                          f"type={actual_type.__name__:5s} expected={expected_type.__name__:5s} {marker}")
                    if not match:
                        all_ok = False
                else:
                    print(f"  {host}.{field}: MISSING")
                    all_ok = False

    if all_ok:
        print("\n  All types preserved correctly.")
    else:
        print("\n  WARNING: Type preservation issues detected!")


# ═══════════════════════════════════════════════════════════════════════
# CHECK 4: Reconstruction round-trip for ALL sets
# ═══════════════════════════════════════════════════════════════════════
def check_4_roundtrip():
    hr("CHECK 4: Reconstruction round-trip (all sets)")

    set_dirs = sorted(FIXTURE_DIR.glob("set_*"))
    total_checks = 0
    total_fails = 0

    for set_dir in set_dirs:
        set_name = set_dir.name
        inputs = load_set(set_name)
        tier_b, tier_c = archetypal_compress(inputs)

        with open(set_dir / "expected.yaml") as f:
            expected = yaml.safe_load(f)

        pos_sections = expected.get("positive_sections", [])
        neg_sections = expected.get("negative_sections", [])

        fails = []
        for host in sorted(inputs):
            for section in inputs[host]:
                total_checks += 1
                input_data = inputs[host][section]

                if host not in tier_c or section not in tier_c[host]:
                    fails.append(f"{host}/{section}: missing from output")
                    total_fails += 1
                    continue

                tc_section = tier_c[host][section]

                # Reconstruct
                if isinstance(tc_section, dict) and "_class" in tc_section:
                    if "instances" in tc_section:
                        reconstructed = reconstruct_instances(tier_b, tc_section)
                    else:
                        reconstructed = reconstruct_section(tier_b, tc_section)
                else:
                    reconstructed = copy.deepcopy(tc_section)

                # Compare
                if isinstance(input_data, list):
                    match = normalize(reconstructed) == normalize(input_data)
                else:
                    match = normalize(reconstructed) == normalize(input_data)

                if not match:
                    fails.append(f"{host}/{section}")
                    total_fails += 1

        status = "PASS" if not fails else f"FAIL ({len(fails)} mismatches)"
        print(f"  {set_name:10s}  {len(inputs)} hosts × {len(list(inputs.values())[0])} sections  {status}")
        if fails and len(fails) <= 3:
            for f in fails:
                print(f"    - {f}")

    print(f"\n  Total: {total_checks} checks, {total_fails} failures")


# ═══════════════════════════════════════════════════════════════════════
# CHECK 5: Algorithm internals — what threshold / strategy is used?
# ═══════════════════════════════════════════════════════════════════════
def check_5_algorithm_review():
    hr("CHECK 5: Algorithm review prompts")

    archetypal_path = REPO_ROOT / "src" / "decoct" / "compression" / "archetypal.py"
    if not archetypal_path.exists():
        print(f"  Cannot find {archetypal_path}")
        print("  Ask Claude Code to show you the file.")
        return

    with open(archetypal_path) as f:
        source = f.read()

    print(f"  File: {archetypal_path}")
    print(f"  Lines: {len(source.splitlines())}")
    print()

    # Look for key patterns
    checks = [
        ("_values_equal", "Type-strict comparison function"),
        ("_find_groups", "Group discovery / Jaccard logic"),
        ("_identity", "Identity field detection"),
        ("_flatten", "Dot-path flattening"),
        ("jaccard", "Jaccard similarity mention"),
        ("threshold", "Threshold parameter"),
        ("≥3", "Minimum group size"),
        (">=3", "Minimum group size (alt)"),
        (">= 3", "Minimum group size (alt2)"),
        ("min_group", "Minimum group size parameter"),
    ]

    print("  Key patterns found in source:")
    for pattern, description in checks:
        count = source.lower().count(pattern.lower())
        if count > 0:
            print(f"    {description:40s} '{pattern}' appears {count}x")

    # Show the function signatures
    print("\n  Function signatures:")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("def ") and not stripped.startswith("def _"):
            print(f"    {stripped}")
        elif stripped.startswith("def _"):
            print(f"    {stripped}")

    print("\n  Review these functions manually for:")
    print("    1. What Jaccard threshold triggers class extraction?")
    print("    2. How does _values_equal handle bool vs int vs str?")
    print("    3. Does _find_groups use full-path or leaf-only comparison?")
    print("    4. How is the 'best' class reference selected?")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Decoct Archetypal Compress — Sanity Checks")
    print(f"Fixture dir: {FIXTURE_DIR}")
    print(f"Repo root: {REPO_ROOT}")

    check_1_inspect_output()
    check_2_traps()
    check_3_type_preservation()
    check_4_roundtrip()
    check_5_algorithm_review()

    hr("DONE")
    print("  Review the output above. Key things to look for:")
    print("  1. Does Tier B look like something an LLM can read directly?")
    print("  2. Are dot-notation keys present in Tier C (not nested YAML)?")
    print("  3. Did all 5 traps produce 0 classes?")
    print("  4. Are types preserved exactly in Trap 1?")
    print("  5. Does the round-trip reconstruct perfectly for all sets?")
    print("  6. What threshold / strategy is the algorithm using?")
    print()
