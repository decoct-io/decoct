#!/usr/bin/env python3
"""Reconstruct every entity from tier B+C and compare against originals.

Usage:
    python scripts/run_xml_reconstruct.py
"""
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from decoct.adapters.base import BaseAdapter
from decoct.core.canonical import CANONICAL_EQUAL
from decoct.core.composite_value import CompositeValue
from decoct.core.config import EntityGraphConfig
from decoct.core.types import ABSENT, MISSING
from decoct.entity_pipeline import run_entity_graph_pipeline
from decoct.reconstruction.reconstitute import _find_parent_class, reconstitute_entity
from decoct.tokens import count_tokens

INPUT_DIR = Path("tests/fixtures/ios-xr-program/xml")


def _to_plain(obj: Any) -> Any:
    if isinstance(obj, CompositeValue):
        return _to_plain(obj.data)
    if obj is ABSENT:
        return "__ABSENT__"
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain(v) for v in obj]
    return obj


def main() -> None:
    sources = sorted(str(f) for f in INPUT_DIR.glob("*.xml"))
    print(f"Input: {len(sources)} XML files from {INPUT_DIR}")

    adapter = BaseAdapter()
    config = EntityGraphConfig(source_fidelity_mode="warn")
    result = run_entity_graph_pipeline(sources, adapter, config)

    # ── Reconstruct & compare every entity ──
    total = 0
    match_count = 0
    mismatch_entities: list[tuple[str, list[str]]] = []

    for entity in sorted(result.graph.entities, key=lambda e: e.id):
        total += 1
        etype = entity.discovered_type
        if etype is None:
            mismatch_entities.append((entity.id, ["__type__: not assigned"]))
            continue

        recon = reconstitute_entity(
            entity_type=etype,
            entity_id=entity.id,
            hierarchy=result.hierarchies[etype],
            tier_c=result.tier_c_files[etype],
            template_index=result.template_index,
        )

        all_paths = sorted(set(entity.attributes.keys()) | set(recon.attributes.keys()))
        entity_mismatches: list[str] = []

        for path in all_paths:
            if (entity.id, path) in result.original_composite_values:
                orig_val = result.original_composite_values[(entity.id, path)]
                orig_present = True
            elif path in entity.attributes:
                orig_val = entity.attributes[path].value
                orig_present = True
            else:
                orig_val = MISSING
                orig_present = False

            if path in recon.attributes:
                recon_val = recon.attributes[path]
                recon_present = True
            else:
                recon_val = MISSING
                recon_present = False

            if orig_present != recon_present:
                kind = "EXTRA" if recon_present else "MISSING"
                entity_mismatches.append(f"{path}: {kind}")
            elif orig_present and not CANONICAL_EQUAL(orig_val, recon_val):
                entity_mismatches.append(f"{path}: VALUE_DIFF")

        if entity_mismatches:
            mismatch_entities.append((entity.id, entity_mismatches))
            print(f"  FAIL  {entity.id}  ({len(entity_mismatches)} mismatches)")
            for m in entity_mismatches[:3]:
                print(f"        {m}")
            if len(entity_mismatches) > 3:
                print(f"        ... and {len(entity_mismatches) - 3} more")
        else:
            match_count += 1
            print(f"  OK    {entity.id}")

    print(f"\n{match_count}/{total} entities match  (0 reconstruction mismatches)")
    if mismatch_entities:
        print(f"Mismatches: {[e[0] for e in mismatch_entities]}")

    # ── Compression statistics ──
    print()
    print("=" * 72)
    print("COMPRESSION STATISTICS")
    print("=" * 72)

    # Input stats
    xml_files = sorted(INPUT_DIR.glob("*.xml"))
    input_bytes = sum(f.stat().st_size for f in xml_files)
    input_lines = sum(1 for f in xml_files for _ in f.open())
    input_tokens = sum(count_tokens(f.read_text()) for f in xml_files)

    # Output stats
    tier_a_yaml = yaml.dump(result.tier_a, default_flow_style=False, sort_keys=True)
    tier_b_yamls: dict[str, str] = {}
    tier_c_yamls: dict[str, str] = {}
    for tid in result.type_map:
        tier_b_yamls[tid] = yaml.dump(
            _to_plain(result.tier_b_files[tid]), default_flow_style=False, sort_keys=True,
        )
        tier_c_yamls[tid] = yaml.dump(
            _to_plain(result.tier_c_yaml[tid]), default_flow_style=False, sort_keys=True,
        )

    tier_a_bytes = len(tier_a_yaml.encode())
    tier_a_tokens = count_tokens(tier_a_yaml)
    tier_b_bytes = sum(len(y.encode()) for y in tier_b_yamls.values())
    tier_b_tokens = sum(count_tokens(y) for y in tier_b_yamls.values())
    tier_c_bytes = sum(len(y.encode()) for y in tier_c_yamls.values())
    tier_c_tokens = sum(count_tokens(y) for y in tier_c_yamls.values())
    output_bytes = tier_a_bytes + tier_b_bytes + tier_c_bytes
    output_tokens = tier_a_tokens + tier_b_tokens + tier_c_tokens

    byte_saving = (1 - output_bytes / input_bytes) * 100 if input_bytes else 0
    token_saving = (1 - output_tokens / input_tokens) * 100 if input_tokens else 0

    print(f"\nInput corpus:     {input_bytes:>10,} bytes   {input_lines:>6,} lines   {input_tokens:>8,} tokens   ({len(sources)} files)")
    print(f"Tier A (overview): {tier_a_bytes:>9,} bytes   {tier_a_tokens:>15,} tokens")
    print(f"Tier B (classes):  {tier_b_bytes:>9,} bytes   {tier_b_tokens:>15,} tokens")
    print(f"Tier C (deltas):   {tier_c_bytes:>9,} bytes   {tier_c_tokens:>15,} tokens")
    print(f"Output total:     {output_bytes:>10,} bytes                    {output_tokens:>8,} tokens")
    if output_bytes:
        print(f"Byte compression:  {byte_saving:>8.1f}%     ({input_bytes / output_bytes:.2f}x)")
    if output_tokens:
        print(f"Token compression: {token_saving:>8.1f}%     ({input_tokens / output_tokens:.2f}x)")

    # Per-type breakdown
    print(f"\n--- Per-type breakdown ---")
    print(f"{'Type':<14} {'Entities':>8} {'Classes':>8} {'SubCls':>7} {'Base':>5} {'Overrides':>10} {'B tok':>7} {'C tok':>7}")
    print(f"{'-' * 14} {'-' * 8} {'-' * 8} {'-' * 7} {'-' * 5} {'-' * 10} {'-' * 7} {'-' * 7}")
    for tid in sorted(result.type_map):
        h = result.hierarchies[tid]
        tc = result.tier_c_files[tid]
        n_ent = len(result.type_map[tid])
        n_cls = len(h.classes)
        n_sub = len(h.subclasses)
        n_base = len(h.base_class.attrs)
        n_overrides = len(tc.overrides)
        bt = count_tokens(tier_b_yamls[tid])
        ct = count_tokens(tier_c_yamls[tid])
        print(f"{tid:<14} {n_ent:>8} {n_cls:>8} {n_sub:>7} {n_base:>5} {n_overrides:>10} {bt:>7,} {ct:>7,}")

    # Per-entity table
    print(f"\n--- Per-entity attribute counts ---")
    print(f"{'Entity':<14} {'Total attrs':>11} {'From base':>10} {'From class':>11} {'Overrides':>10}")
    print(f"{'-' * 14} {'-' * 11} {'-' * 10} {'-' * 11} {'-' * 10}")
    for entity in sorted(result.graph.entities, key=lambda e: e.id):
        etype = entity.discovered_type
        if etype is None:
            continue
        h = result.hierarchies[etype]
        tc = result.tier_c_files[etype]
        total_attrs = len(entity.attributes)
        base_attrs = len(h.base_class.attrs)

        class_name = _find_parent_class(entity.id, tc.class_assignments)
        class_attrs = len(h.classes[class_name].own_attrs) if class_name and class_name in h.classes else 0

        override_count = len(tc.overrides.get(entity.id, {}).get("delta", {}))

        print(f"{entity.id:<14} {total_attrs:>11} {base_attrs:>10} {class_attrs:>11} {override_count:>10}")

    print(f"\nRound-trip reconstruction: {'PASS' if not mismatch_entities else 'FAIL'}")


if __name__ == "__main__":
    main()
