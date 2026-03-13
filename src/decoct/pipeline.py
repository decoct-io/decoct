"""Simple pipeline: load -> compress -> write."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.adapter import BaseAdapter
from decoct.archetypal import archetypal_compress
from decoct.reconstruct import ReconstructionError, validate_round_trip
from decoct.stats import CompressionStats, compute_stats


def run_pipeline(sources: list[str], output_dir: str) -> dict[str, Any]:
    """Load files, compress, write YAML output, return stats."""
    adapter = BaseAdapter()
    corpus = adapter.load_corpus(sources)
    tier_b, tier_c = archetypal_compress(corpus)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    yaml = YAML()
    yaml.default_flow_style = False

    # Write tier_b.yaml
    with open(out / "tier_b.yaml", "w") as f:
        yaml.dump(tier_b, f)

    # Write tier_c/{hostname}.yaml
    tc_dir = out / "tier_c"
    tc_dir.mkdir(exist_ok=True)
    for hostname, data in sorted(tier_c.items()):
        with open(tc_dir / f"{hostname}.yaml", "w") as f:
            yaml.dump(data, f)

    # Round-trip validation
    mismatched = validate_round_trip(corpus, tier_b, tier_c)

    # Compression statistics (includes validation results)
    stats: CompressionStats = compute_stats(corpus, tier_b, tier_c, mismatched_hosts=mismatched)

    result: dict[str, Any] = {
        "entities": len(corpus),
        "classes": len(tier_b),
        "tier_b": tier_b,
        "tier_c": tier_c,
        "stats": stats,
    }

    if mismatched:
        raise ReconstructionError(mismatched, stats)

    return result
