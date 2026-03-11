#!/usr/bin/env python3
"""Run the entity-graph pipeline on cdn-edge fixtures and dump Tier A/B/C YAML."""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.adapters.hybrid_infra import HybridInfraAdapter
from decoct.adapters.ingestion_spec import load_ingestion_spec
from decoct.core.composite_value import CompositeValue
from decoct.core.config import EntityGraphConfig
from decoct.core.types import ABSENT
from decoct.entity_pipeline import run_entity_graph_pipeline

yaml = YAML()
yaml.default_flow_style = False


def _to_plain(obj: Any) -> Any:
    """Recursively convert CompositeValue/ABSENT to plain Python types for YAML."""
    if isinstance(obj, CompositeValue):
        return _to_plain(obj.data)
    if obj is ABSENT:
        return "__ABSENT__"
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain(v) for v in obj]
    return obj


FIXTURES = Path("tests/fixtures/cdn-edge/configs")
OUT_DIR = Path("output/cdn-edge")


def main() -> None:
    sources = sorted(str(f) for f in FIXTURES.iterdir())
    print(f"Found {len(sources)} configs")

    spec = load_ingestion_spec("specs/ingestion/cdn-edge/ingestion_spec.yaml")
    adapter = HybridInfraAdapter(ingestion_spec=spec)
    config = EntityGraphConfig()

    print("Running pipeline...")
    result = run_entity_graph_pipeline(sources, adapter, config)
    print(f"  Types discovered: {len(result.type_map)}")
    for tid, entities in sorted(result.type_map.items()):
        h = result.hierarchies[tid]
        n_cls = len([c for c in h.classes if c != "_base_only"])
        n_sub = len(h.subclasses)
        base_n = len(h.base_class.attrs)
        print(f"  {tid}: {len(entities)} entities, {base_n} base attrs, {n_cls} classes, {n_sub} subclasses")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Tier A
    with open(OUT_DIR / "tier_a.yaml", "w") as f:
        yaml.dump(result.tier_a, f)
    print(f"\nWrote {OUT_DIR / 'tier_a.yaml'}")

    # Tier B + C per type
    for type_id in sorted(result.type_map.keys()):
        b_path = OUT_DIR / f"{type_id}_classes.yaml"
        c_path = OUT_DIR / f"{type_id}_instances.yaml"

        with open(b_path, "w") as f:
            yaml.dump(_to_plain(result.tier_b_files[type_id]), f)

        with open(c_path, "w") as f:
            yaml.dump(_to_plain(result.tier_c_yaml[type_id]), f)

        print(f"Wrote {b_path}")
        print(f"Wrote {c_path}")

    print(f"\nDone — all output in {OUT_DIR}/")


if __name__ == "__main__":
    main()
