#!/usr/bin/env python3
"""
Reconstruct original input files from tier_b + tier_c and compare
against the actual inputs (YAML-to-YAML round-trip validation).

Usage:
    cd tests/fixtures/archetypal/integration
    python reconstruct_and_compare.py
"""
import os
import sys
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import (
    load_case,
    normalize,
    reconstruct_section,
    reconstruct_instances,
)

FIXTURE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(FIXTURE_DIR, "reconstructed")

POSITIVE_SECTIONS = {
    "system_base", "access_control", "alert_targets", "loopback0",
    "change_procedures", "fabric_interfaces", "telemetry_stack",
    "routing_policy", "isis_config", "vrf_routing", "policy_maps",
    "bgp_neighbors",
}


def reconstruct_host(tier_b, tier_c_host):
    """Rebuild all sections for one host from tier_b + tier_c."""
    result = {}
    for section, tc in tier_c_host.items():
        if isinstance(tc, dict) and "instances" in tc:
            result[section] = reconstruct_instances(tier_b, tc)
        elif isinstance(tc, dict) and "_class" in tc:
            result[section] = reconstruct_section(tier_b, tc)
        else:
            # Raw passthrough — tier_c IS the original
            result[section] = tc
    return result


def yaml_dump(data):
    """Consistent YAML serialisation for comparison."""
    return yaml.dump(
        data,
        default_flow_style=False,
        sort_keys=True,
        allow_unicode=True,
        width=120,
    )


def main():
    case = load_case(FIXTURE_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total = 0
    match = 0
    mismatches = []

    for host in sorted(case.hosts):
        reconstructed = reconstruct_host(case.tier_b, case.tier_c[host])
        original = case.inputs[host]

        # Write reconstructed YAML
        out_path = os.path.join(OUTPUT_DIR, f"{host}.yaml")
        with open(out_path, "w") as f:
            yaml.dump(
                reconstructed,
                f,
                default_flow_style=False,
                sort_keys=True,
                allow_unicode=True,
                width=120,
            )

        # Compare normalised structures
        total += 1
        if normalize(reconstructed) == normalize(original):
            match += 1
            print(f"  OK  {host}")
        else:
            mismatches.append(host)
            print(f"  FAIL  {host}")
            # Per-section breakdown
            all_sections = set(list(original.keys()) + list(reconstructed.keys()))
            for section in sorted(all_sections):
                orig_sec = original.get(section)
                recon_sec = reconstructed.get(section)
                if orig_sec is None:
                    print(f"        {section}: EXTRA in reconstructed")
                elif recon_sec is None:
                    print(f"        {section}: MISSING from reconstructed")
                elif normalize(orig_sec) != normalize(recon_sec):
                    print(f"        {section}: MISMATCH")
                    # Dump both for diffing
                    diff_dir = os.path.join(OUTPUT_DIR, "diffs", host)
                    os.makedirs(diff_dir, exist_ok=True)
                    with open(os.path.join(diff_dir, f"{section}_original.yaml"), "w") as f:
                        f.write(yaml_dump(orig_sec))
                    with open(os.path.join(diff_dir, f"{section}_reconstructed.yaml"), "w") as f:
                        f.write(yaml_dump(recon_sec))

    print(f"\n{match}/{total} hosts match")
    if mismatches:
        print(f"Mismatches: {', '.join(mismatches)}")
        print(f"Diff files written to {os.path.join(OUTPUT_DIR, 'diffs')}/")
        print("\nTo inspect:")
        for host in mismatches:
            diff_dir = os.path.join(OUTPUT_DIR, "diffs", host)
            if os.path.isdir(diff_dir):
                for f in sorted(os.listdir(diff_dir)):
                    if f.endswith("_original.yaml"):
                        sec = f.replace("_original.yaml", "")
                        print(f"  diff {diff_dir}/{sec}_original.yaml {diff_dir}/{sec}_reconstructed.yaml")
        sys.exit(1)

    print("Round-trip: PASS\n")

    # --- Compression Statistics ---
    print("=" * 72)
    print("COMPRESSION STATISTICS")
    print("=" * 72)

    # Byte sizes
    input_bytes_total = 0
    tier_c_bytes_total = 0
    tier_b_yaml = yaml_dump(case.tier_b)
    tier_b_bytes = len(tier_b_yaml.encode("utf-8"))

    per_host_stats = []
    for host in sorted(case.hosts):
        inp_yaml = yaml_dump(case.inputs[host])
        tc_yaml = yaml_dump(case.tier_c[host])
        inp_b = len(inp_yaml.encode("utf-8"))
        tc_b = len(tc_yaml.encode("utf-8"))
        input_bytes_total += inp_b
        tier_c_bytes_total += tc_b
        per_host_stats.append((host, inp_b, tc_b))

    compressed_total = tier_b_bytes + tier_c_bytes_total
    ratio = (1 - compressed_total / input_bytes_total) * 100 if input_bytes_total else 0

    print(f"\nTier A (input):  {input_bytes_total:>8,} bytes  ({len(case.hosts)} files)")
    print(f"Tier B (classes): {tier_b_bytes:>7,} bytes  ({len(case.tier_b)} classes)")
    print(f"Tier C (deltas): {tier_c_bytes_total:>8,} bytes  ({len(case.hosts)} files)")
    print(f"B + C combined:  {compressed_total:>8,} bytes")
    print(f"Compression:     {ratio:>7.1f}%")
    print(f"Ratio:           {input_bytes_total / compressed_total:.2f}x" if compressed_total else "")

    # Leaf counts
    def count_leaves(obj):
        """Count scalar leaf values recursively."""
        if isinstance(obj, dict):
            return sum(count_leaves(v) for v in obj.values())
        elif isinstance(obj, list):
            return sum(count_leaves(v) for v in obj)
        else:
            return 1

    input_leaves = sum(count_leaves(case.inputs[h]) for h in case.hosts)
    tier_b_leaves = count_leaves(case.tier_b)
    tier_c_leaves = sum(count_leaves(case.tier_c[h]) for h in case.hosts)
    compressed_leaves = tier_b_leaves + tier_c_leaves
    leaf_ratio = (1 - compressed_leaves / input_leaves) * 100 if input_leaves else 0

    print(f"\n--- Leaf counts ---")
    print(f"Input leaves:     {input_leaves:>6,}")
    print(f"Tier B leaves:    {tier_b_leaves:>6,}")
    print(f"Tier C leaves:    {tier_c_leaves:>6,}")
    print(f"B + C leaves:     {compressed_leaves:>6,}")
    print(f"Leaf reduction:   {leaf_ratio:>5.1f}%")

    # Per-host table
    print(f"\n--- Per-host bytes ---")
    print(f"{'Host':<10} {'Input':>8} {'Tier C':>8} {'Saving':>7}")
    print(f"{'-'*10} {'-'*8} {'-'*8} {'-'*7}")
    for host, inp_b, tc_b in per_host_stats:
        saving = (1 - tc_b / inp_b) * 100 if inp_b else 0
        print(f"{host:<10} {inp_b:>8,} {tc_b:>8,} {saving:>6.1f}%")

    # Per-section breakdown (positive vs negative)
    print(f"\n--- Per-section (aggregated across hosts) ---")
    print(f"{'Section':<22} {'Type':<5} {'Input':>8} {'Tier C':>8} {'Saving':>7}")
    print(f"{'-'*22} {'-'*5} {'-'*8} {'-'*8} {'-'*7}")

    all_sections = sorted(set(
        s for h in case.hosts for s in case.inputs.get(h, {})
    ))
    for section in all_sections:
        s_type = "+" if section in POSITIVE_SECTIONS else "-"
        s_inp = 0
        s_tc = 0
        for host in case.hosts:
            if section in case.inputs.get(host, {}):
                s_inp += len(yaml_dump(case.inputs[host][section]).encode("utf-8"))
            if section in case.tier_c.get(host, {}):
                s_tc += len(yaml_dump(case.tier_c[host][section]).encode("utf-8"))
        saving = (1 - s_tc / s_inp) * 100 if s_inp else 0
        print(f"{section:<22} {s_type:<5} {s_inp:>8,} {s_tc:>8,} {saving:>6.1f}%")

    # Class utilisation
    print(f"\n--- Class utilisation ---")
    print(f"{'Class':<22} {'Bytes':>7} {'Leaves':>7} {'Hosts':>6}")
    print(f"{'-'*22} {'-'*7} {'-'*7} {'-'*6}")
    for class_name in sorted(case.tier_b):
        cls = case.tier_b[class_name]
        cls_bytes = len(yaml_dump(cls).encode("utf-8"))
        cls_leaves = count_leaves(cls)
        # Count hosts referencing this class
        host_count = 0
        for host in case.hosts:
            for section in case.tier_c.get(host, {}):
                tc = case.tier_c[host][section]
                if isinstance(tc, dict):
                    if tc.get("_class") == class_name:
                        host_count += 1
        print(f"{class_name:<22} {cls_bytes:>7,} {cls_leaves:>7,} {host_count:>6}")

    print()


if __name__ == "__main__":
    main()
