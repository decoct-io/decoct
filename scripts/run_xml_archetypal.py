#!/usr/bin/env python3
"""Run archetypal compression on IOS-XR NETCONF XML fixtures.

Parses each XML file into sections (by YANG module + tag), runs
archetypal_compress(), reconstructs, and compares against originals.

Usage:
    python scripts/run_xml_archetypal.py
"""
import copy
import os
import sys
from pathlib import Path

import defusedxml.ElementTree as DefusedET
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from decoct.compression.archetypal import archetypal_compress

# Reconstruction helpers (same as tests/fixtures/archetypal/helpers.py)


def deep_set(d, dotpath, value):
    keys = dotpath.split(".")
    for key in keys[:-1]:
        if key not in d:
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value


def deep_delete(d, dotpath):
    keys = dotpath.split(".")
    for key in keys[:-1]:
        if key not in d:
            return False
        d = d[key]
    if keys[-1] in d:
        del d[keys[-1]]
        return True
    return False


def normalize(obj):
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [normalize(item) for item in obj]
    return obj


def reconstruct_section(tier_b_classes, tier_c_section):
    if "_class" not in tier_c_section:
        return copy.deepcopy(tier_c_section)
    class_name = tier_c_section["_class"]
    result = copy.deepcopy(tier_b_classes[class_name])
    result.pop("_identity", None)
    for field in tier_c_section.get("_remove", []):
        if "." in field:
            deep_delete(result, field)
        else:
            result.pop(field, None)
    for key, value in tier_c_section.items():
        if key in ("_class", "_remove", "instances"):
            continue
        if "." in key:
            deep_set(result, key, value)
        else:
            result[key] = value
    return result


def reconstruct_instances(tier_b_classes, tier_c_section):
    class_name = tier_c_section["_class"]
    class_def = copy.deepcopy(tier_b_classes[class_name])
    class_def.pop("_identity", None)
    instances = []
    for inst in tier_c_section.get("instances", []):
        record = copy.deepcopy(class_def)
        removals = inst.get("_remove", [])
        for k, v in inst.items():
            if k == "_remove":
                continue
            if "." in k:
                deep_set(record, k, v)
            else:
                record[k] = v
        for field in removals:
            if "." in field:
                deep_delete(record, field)
            else:
                record.pop(field, None)
        instances.append(record)
    return instances


def reconstruct_host(tier_b, tier_c_host):
    result = {}
    for section, tc in tier_c_host.items():
        if isinstance(tc, dict) and "instances" in tc:
            result[section] = reconstruct_instances(tier_b, tc)
        elif isinstance(tc, dict) and "_class" in tc:
            result[section] = reconstruct_section(tier_b, tc)
        else:
            result[section] = tc
    return result


def count_leaves(obj):
    if isinstance(obj, dict):
        return sum(count_leaves(v) for v in obj.values())
    elif isinstance(obj, list):
        return sum(count_leaves(v) for v in obj)
    return 1


def yaml_dump(data):
    return yaml.dump(data, default_flow_style=False, sort_keys=True,
                     allow_unicode=True, width=120)


# ---------------------------------------------------------------------------
# XML → sectioned dict
# ---------------------------------------------------------------------------

def _strip_ns(tag):
    """Strip XML namespace: {http://...}tag → tag"""
    return tag.split("}")[-1] if "}" in tag else tag


def _ns_module(tag):
    """Extract YANG module name from namespace URI."""
    if "}" not in tag:
        return ""
    ns = tag.split("}")[0].lstrip("{")
    return ns.split("/")[-1]


def _element_to_dict(elem):
    """Convert an XML element to a plain dict/scalar.

    Rules:
    - Leaf elements (text only, no children, no attributes) → scalar string
    - Elements with children → dict
    - Repeated same-name children → list
    - Attributes → @attr keys
    - Empty elements (no text, no children) → ""
    """
    children = list(elem)
    has_attrs = bool(elem.attrib)
    text = (elem.text or "").strip()

    if not children and not has_attrs:
        return text  # leaf → scalar

    result = {}

    # Attributes
    for attr_name, attr_val in sorted(elem.attrib.items()):
        clean_name = _strip_ns(attr_name)
        result[f"@{clean_name}"] = attr_val

    # Children — collect by tag, detect repeats
    child_groups = {}
    for child in children:
        tag = _strip_ns(child.tag)
        child_groups.setdefault(tag, []).append(child)

    for tag, group in child_groups.items():
        if len(group) == 1:
            result[tag] = _element_to_dict(group[0])
        else:
            result[tag] = [_element_to_dict(c) for c in group]

    # If there's significant text alongside children, add it
    if text and children:
        result["_text"] = text

    return result


def parse_xml_to_sections(xml_path):
    """Parse an XML file into {section_name: section_data}.

    Section names are "{YANG-module}:{tag}" to disambiguate
    repeated tags with different namespaces.
    """
    tree = DefusedET.parse(str(xml_path))
    root = tree.getroot()

    sections = {}
    seen_keys = {}  # track duplicates within a single file

    for child in root:
        tag = _strip_ns(child.tag)
        module = _ns_module(child.tag)
        section_key = f"{module}:{tag}" if module else tag

        # Handle rare duplicate sections within one file
        if section_key in sections:
            count = seen_keys.get(section_key, 1)
            section_key = f"{section_key}[{count}]"
            seen_keys[section_key] = count + 1

        sections[section_key] = _element_to_dict(child)

    return sections


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

INPUT_DIR = Path("tests/fixtures/ios-xr-program/xml")
OUTPUT_DIR = Path("output/ios-xr-xml-archetypal")


def main():
    xml_files = sorted(INPUT_DIR.glob("*.xml"))
    print(f"Input: {len(xml_files)} XML files from {INPUT_DIR}\n")

    # 1. Parse XML → sectioned dicts
    inputs = {}
    for xml_path in xml_files:
        host = xml_path.stem
        inputs[host] = parse_xml_to_sections(xml_path)
        print(f"  Parsed {host}: {len(inputs[host])} sections")

    # 2. Run archetypal compression
    print(f"\nRunning archetypal_compress() ...")
    tier_b, tier_c = archetypal_compress(inputs)
    print(f"  Tier B: {len(tier_b)} classes")
    print(f"  Tier C: {len(tier_c)} hosts")

    # 3. Write output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_DIR / "tier_b.yaml", "w") as f:
        yaml.dump(tier_b, f, default_flow_style=False, sort_keys=True,
                  allow_unicode=True, width=120)
    for host in sorted(tier_c):
        with open(OUTPUT_DIR / f"{host}.yaml", "w") as f:
            yaml.dump(tier_c[host], f, default_flow_style=False, sort_keys=True,
                      allow_unicode=True, width=120)

    # 4. Reconstruct & compare
    print(f"\n{'=' * 72}")
    print("RECONSTRUCTION VALIDATION")
    print(f"{'=' * 72}\n")

    total = 0
    match = 0
    mismatches = []

    for host in sorted(inputs):
        reconstructed = reconstruct_host(tier_b, tier_c[host])
        original = inputs[host]

        total += 1
        if normalize(reconstructed) == normalize(original):
            match += 1
            print(f"  OK    {host}")
        else:
            mismatches.append(host)
            print(f"  FAIL  {host}")
            all_sections = sorted(set(list(original.keys()) + list(reconstructed.keys())))
            for section in all_sections:
                orig_sec = original.get(section)
                recon_sec = reconstructed.get(section)
                if orig_sec is None:
                    print(f"        {section}: EXTRA in reconstructed")
                elif recon_sec is None:
                    print(f"        {section}: MISSING from reconstructed")
                elif normalize(orig_sec) != normalize(recon_sec):
                    print(f"        {section}: MISMATCH")

    print(f"\n{match}/{total} hosts match")
    if mismatches:
        print(f"Mismatches: {', '.join(mismatches)}")

    # 5. Compression statistics
    print(f"\n{'=' * 72}")
    print("COMPRESSION STATISTICS")
    print(f"{'=' * 72}")

    input_bytes_total = 0
    tier_c_bytes_total = 0
    tier_b_yaml = yaml_dump(tier_b)
    tier_b_bytes = len(tier_b_yaml.encode("utf-8"))

    per_host_stats = []
    for host in sorted(inputs):
        inp_yaml = yaml_dump(inputs[host])
        tc_yaml = yaml_dump(tier_c[host])
        inp_b = len(inp_yaml.encode("utf-8"))
        tc_b = len(tc_yaml.encode("utf-8"))
        input_bytes_total += inp_b
        tier_c_bytes_total += tc_b
        per_host_stats.append((host, inp_b, tc_b))

    compressed_total = tier_b_bytes + tier_c_bytes_total
    ratio = (1 - compressed_total / input_bytes_total) * 100 if input_bytes_total else 0

    print(f"\nInput (YAML'd):   {input_bytes_total:>8,} bytes  ({len(inputs)} hosts)")
    print(f"Tier B (classes): {tier_b_bytes:>8,} bytes  ({len(tier_b)} classes)")
    print(f"Tier C (deltas):  {tier_c_bytes_total:>8,} bytes  ({len(tier_c)} hosts)")
    print(f"B + C combined:   {compressed_total:>8,} bytes")
    print(f"Compression:      {ratio:>7.1f}%")
    if compressed_total:
        print(f"Ratio:            {input_bytes_total / compressed_total:.2f}x")

    # Raw XML input size
    raw_xml_bytes = sum(f.stat().st_size for f in xml_files)
    raw_compressed = tier_b_bytes + tier_c_bytes_total
    raw_ratio = (1 - raw_compressed / raw_xml_bytes) * 100 if raw_xml_bytes else 0
    print(f"\nRaw XML input:    {raw_xml_bytes:>8,} bytes")
    print(f"vs raw XML:       {raw_ratio:>7.1f}%  ({raw_xml_bytes / raw_compressed:.2f}x)")

    # Leaf counts
    input_leaves = sum(count_leaves(inputs[h]) for h in inputs)
    tier_b_leaves = count_leaves(tier_b)
    tier_c_leaves = sum(count_leaves(tier_c[h]) for h in tier_c)
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
    print(f"{'Host':<12} {'Input':>8} {'Tier C':>8} {'Saving':>7}")
    print(f"{'-' * 12} {'-' * 8} {'-' * 8} {'-' * 7}")
    for host, inp_b, tc_b in per_host_stats:
        saving = (1 - tc_b / inp_b) * 100 if inp_b else 0
        print(f"{host:<12} {inp_b:>8,} {tc_b:>8,} {saving:>6.1f}%")

    # Class utilisation
    print(f"\n--- Class utilisation ---")
    print(f"{'Class':<40} {'Bytes':>7} {'Leaves':>7} {'Hosts':>6}")
    print(f"{'-' * 40} {'-' * 7} {'-' * 7} {'-' * 6}")
    for class_name in sorted(tier_b):
        cls = tier_b[class_name]
        cls_bytes = len(yaml_dump(cls).encode("utf-8"))
        cls_leaves = count_leaves(cls)
        host_count = 0
        for host in tier_c:
            for section in tier_c[host]:
                tc = tier_c[host][section]
                if isinstance(tc, dict) and tc.get("_class") == class_name:
                    host_count += 1
        print(f"{class_name:<40} {cls_bytes:>7,} {cls_leaves:>7,} {host_count:>6}")

    print(f"\nRound-trip reconstruction: {'PASS' if not mismatches else 'FAIL'}")
    print()


if __name__ == "__main__":
    main()
