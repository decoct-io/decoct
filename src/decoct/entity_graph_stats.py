"""Entity-graph compression statistics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.tokens import count_tokens

_INPUT_EXTENSIONS = {".yaml", ".yml", ".json", ".ini", ".conf", ".cfg", ".cnf", ".properties"}


@dataclass
class InputStats:
    """Statistics for the input corpus."""

    file_count: int = 0
    total_bytes: int = 0
    total_lines: int = 0
    total_tokens: int = 0


@dataclass
class TierStats:
    """Statistics for a single output tier."""

    file_count: int = 0
    total_bytes: int = 0
    total_lines: int = 0
    total_tokens: int = 0


@dataclass
class TypeStats:
    """Per-type statistics from entity-graph output."""

    type_id: str
    entity_count: int = 0
    class_count: int = 0
    subclass_count: int = 0
    base_attr_count: int = 0
    base_only_ratio: float = 0.0
    phone_book_width: int = 0
    override_count: int = 0
    relationship_count: int = 0
    max_inheritance_depth: int = 0
    tier_b_bytes: int = 0
    tier_b_tokens: int = 0
    tier_c_bytes: int = 0
    tier_c_tokens: int = 0


@dataclass
class EntityGraphStatsReport:
    """Aggregate entity-graph compression statistics."""

    timestamp: str = ""
    encoding: str = "cl100k_base"
    input_stats: InputStats = field(default_factory=InputStats)
    tier_a: TierStats = field(default_factory=TierStats)
    tier_b: TierStats = field(default_factory=TierStats)
    tier_c: TierStats = field(default_factory=TierStats)
    type_stats: list[TypeStats] = field(default_factory=list)

    @property
    def output_total_bytes(self) -> int:
        return self.tier_a.total_bytes + self.tier_b.total_bytes + self.tier_c.total_bytes

    @property
    def output_total_tokens(self) -> int:
        return self.tier_a.total_tokens + self.tier_b.total_tokens + self.tier_c.total_tokens

    @property
    def output_total_files(self) -> int:
        return self.tier_a.file_count + self.tier_b.file_count + self.tier_c.file_count

    @property
    def compression_ratio_bytes(self) -> float:
        if self.input_stats.total_bytes == 0:
            return 0.0
        return self.output_total_bytes / self.input_stats.total_bytes

    @property
    def compression_ratio_tokens(self) -> float:
        if self.input_stats.total_tokens == 0:
            return 0.0
        return self.output_total_tokens / self.input_stats.total_tokens

    @property
    def savings_pct_bytes(self) -> float:
        if self.input_stats.total_bytes == 0:
            return 0.0
        return (1 - self.compression_ratio_bytes) * 100

    @property
    def savings_pct_tokens(self) -> float:
        if self.input_stats.total_tokens == 0:
            return 0.0
        return (1 - self.compression_ratio_tokens) * 100


def _count_file_stats(path: Path, encoding: str) -> tuple[int, int, int]:
    """Return (bytes, lines, tokens) for a file."""
    text = path.read_text(encoding="utf-8")
    return len(text.encode("utf-8")), text.count("\n"), count_tokens(text, encoding)


def _count_overrides(instances_data: dict[str, Any]) -> int:
    """Count instance-level overrides in an instances file."""
    count = 0
    # Overrides in instance_attrs
    instance_attrs = instances_data.get("instance_attrs", {})
    if isinstance(instance_attrs, dict):
        for entity_data in instance_attrs.values():
            if isinstance(entity_data, dict):
                count += len(entity_data)
    # Overrides in the overrides section
    overrides = instances_data.get("overrides", {})
    if isinstance(overrides, dict):
        for entity_data in overrides.values():
            if isinstance(entity_data, dict):
                count += len(entity_data)
    return count


def _count_relationships(instances_data: dict[str, Any]) -> int:
    """Count relationships stored in an instances file."""
    store = instances_data.get("relationship_store", {})
    if not isinstance(store, dict):
        return 0
    count = 0
    for rels in store.values():
        if isinstance(rels, list):
            count += len(rels)
    return count


def compute_stats(
    input_dir: Path,
    output_dir: Path,
    encoding: str = "cl100k_base",
) -> EntityGraphStatsReport:
    """Compute entity-graph compression statistics.

    Args:
        input_dir: Directory containing raw input config files.
        output_dir: Directory containing entity-graph output files.
        encoding: Tiktoken encoding name for token counting.

    Returns:
        EntityGraphStatsReport with input, output, and per-type statistics.
    """
    yaml = YAML(typ="safe")

    report = EntityGraphStatsReport(
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        encoding=encoding,
    )

    # --- Input stats ---
    input_files = sorted(
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _INPUT_EXTENSIONS
    )
    report.input_stats.file_count = len(input_files)
    for f in input_files:
        byt, lin, tok = _count_file_stats(f, encoding)
        report.input_stats.total_bytes += byt
        report.input_stats.total_lines += lin
        report.input_stats.total_tokens += tok

    # --- Tier A ---
    tier_a_path = output_dir / "tier_a.yaml"
    if tier_a_path.exists():
        report.tier_a.file_count = 1
        byt, lin, tok = _count_file_stats(tier_a_path, encoding)
        report.tier_a.total_bytes = byt
        report.tier_a.total_lines = lin
        report.tier_a.total_tokens = tok

        tier_a_data = yaml.load(tier_a_path)
    else:
        tier_a_data = {}

    types_section = tier_a_data.get("types", {}) if tier_a_data else {}
    assertions_section = tier_a_data.get("assertions", {}) if tier_a_data else {}

    # --- Per-type stats (Tier B + C) ---
    for type_id, type_info in sorted(types_section.items()):
        ts = TypeStats(type_id=type_id)
        ts.entity_count = type_info.get("count", 0)
        ts.class_count = type_info.get("classes", 0)
        ts.subclass_count = type_info.get("subclasses", 0)

        # Tier A assertions
        type_assertions = assertions_section.get(type_id, {})
        if isinstance(type_assertions, dict):
            ts.base_only_ratio = type_assertions.get("base_only_ratio", 0.0)
            ts.max_inheritance_depth = type_assertions.get("max_inheritance_depth", 0)

        # Tier B (classes file)
        classes_path = output_dir / f"{type_id}_classes.yaml"
        if classes_path.exists():
            byt, lin, tok = _count_file_stats(classes_path, encoding)
            ts.tier_b_bytes = byt
            ts.tier_b_tokens = tok
            report.tier_b.file_count += 1
            report.tier_b.total_bytes += byt
            report.tier_b.total_lines += lin
            report.tier_b.total_tokens += tok

            classes_data = yaml.load(classes_path)
            if classes_data:
                base_class = classes_data.get("base_class", {})
                if isinstance(base_class, dict):
                    ts.base_attr_count = len(base_class)

        # Tier C (instances file)
        instances_path = output_dir / f"{type_id}_instances.yaml"
        if instances_path.exists():
            byt, lin, tok = _count_file_stats(instances_path, encoding)
            ts.tier_c_bytes = byt
            ts.tier_c_tokens = tok
            report.tier_c.file_count += 1
            report.tier_c.total_bytes += byt
            report.tier_c.total_lines += lin
            report.tier_c.total_tokens += tok

            instances_data = yaml.load(instances_path)
            if instances_data:
                # Phone book width
                instance_data_section = instances_data.get("instance_data", {})
                if isinstance(instance_data_section, dict):
                    schema = instance_data_section.get("schema", [])
                    ts.phone_book_width = len(schema) if isinstance(schema, list) else 0

                ts.override_count = _count_overrides(instances_data)
                ts.relationship_count = _count_relationships(instances_data)

        report.type_stats.append(ts)

    return report


def format_stats_markdown(report: EntityGraphStatsReport) -> str:
    """Format an EntityGraphStatsReport as markdown text."""
    lines: list[str] = []
    lines.append(f"# Entity-Graph Compression Statistics — {report.timestamp}")
    lines.append(f"Encoding: {report.encoding}")
    lines.append("")

    # Input corpus
    lines.append("## Input Corpus")
    lines.append("")
    inp = report.input_stats
    lines.append("| Metric | Value |")
    lines.append("|--------|------:|")
    lines.append(f"| Files | {inp.file_count} |")
    lines.append(f"| Bytes | {inp.total_bytes:,} |")
    lines.append(f"| Lines | {inp.total_lines:,} |")
    lines.append(f"| Tokens | {inp.total_tokens:,} |")
    lines.append("")

    # Output summary by tier
    lines.append("## Output Summary")
    lines.append("")
    lines.append("| Tier | Files | Bytes | Tokens |")
    lines.append("|------|------:|------:|-------:|")
    tier_pairs = [
        ("A (global)", report.tier_a), ("B (classes)", report.tier_b), ("C (instances)", report.tier_c),
    ]
    for tier_name, tier in tier_pairs:
        lines.append(f"| {tier_name} | {tier.file_count} | {tier.total_bytes:,} | {tier.total_tokens:,} |")
    total_line = (
        f"| **Total** | {report.output_total_files} "
        f"| {report.output_total_bytes:,} | {report.output_total_tokens:,} |"
    )
    lines.append(total_line)
    lines.append("")

    # Compression ratios
    lines.append("## Compression Ratios")
    lines.append("")
    lines.append("| Metric | Input | Output | Saved | Savings % |")
    lines.append("|--------|------:|-------:|------:|----------:|")
    lines.append(
        f"| Bytes | {inp.total_bytes:,} | {report.output_total_bytes:,} "
        f"| {inp.total_bytes - report.output_total_bytes:,} | {report.savings_pct_bytes:.1f}% |"
    )
    lines.append(
        f"| Tokens | {inp.total_tokens:,} | {report.output_total_tokens:,} "
        f"| {inp.total_tokens - report.output_total_tokens:,} | {report.savings_pct_tokens:.1f}% |"
    )
    lines.append("")

    # Per-type breakdown
    if report.type_stats:
        lines.append("## Per-Type Breakdown")
        lines.append("")
        lines.append("| Type | Entities | Classes | Subclasses | Base Attrs | Phone Book Width | B Tokens | C Tokens |")
        lines.append("|------|--------:|--------:|-----------:|-----------:|-----------------:|---------:|---------:|")
        for ts in report.type_stats:
            lines.append(
                f"| {ts.type_id} | {ts.entity_count} | {ts.class_count} | {ts.subclass_count} "
                f"| {ts.base_attr_count} | {ts.phone_book_width} | {ts.tier_b_tokens:,} | {ts.tier_c_tokens:,} |"
            )
        lines.append("")

        # Entity-graph structure summary
        lines.append("## Entity-Graph Structure")
        lines.append("")
        total_entities = sum(ts.entity_count for ts in report.type_stats)
        total_classes = sum(ts.class_count for ts in report.type_stats)
        total_subclasses = sum(ts.subclass_count for ts in report.type_stats)
        total_overrides = sum(ts.override_count for ts in report.type_stats)
        total_relationships = sum(ts.relationship_count for ts in report.type_stats)
        lines.append(f"- **Types**: {len(report.type_stats)}")
        lines.append(f"- **Total entities**: {total_entities}")
        lines.append(f"- **Total classes**: {total_classes}")
        lines.append(f"- **Total subclasses**: {total_subclasses}")
        lines.append(f"- **Total overrides**: {total_overrides}")
        lines.append(f"- **Total relationships**: {total_relationships}")
        lines.append("")

    return "\n".join(lines)


def format_stats_json(report: EntityGraphStatsReport) -> str:
    """Format an EntityGraphStatsReport as JSON."""
    data: dict[str, Any] = {
        "timestamp": report.timestamp,
        "encoding": report.encoding,
        "input_stats": {
            "file_count": report.input_stats.file_count,
            "total_bytes": report.input_stats.total_bytes,
            "total_lines": report.input_stats.total_lines,
            "total_tokens": report.input_stats.total_tokens,
        },
        "output": {
            "tier_a": _tier_stats_dict(report.tier_a),
            "tier_b": _tier_stats_dict(report.tier_b),
            "tier_c": _tier_stats_dict(report.tier_c),
            "total_bytes": report.output_total_bytes,
            "total_tokens": report.output_total_tokens,
            "total_files": report.output_total_files,
        },
        "compression": {
            "ratio_bytes": round(report.compression_ratio_bytes, 4),
            "ratio_tokens": round(report.compression_ratio_tokens, 4),
            "savings_pct_bytes": round(report.savings_pct_bytes, 1),
            "savings_pct_tokens": round(report.savings_pct_tokens, 1),
        },
        "type_stats": [_type_stats_dict(ts) for ts in report.type_stats],
    }
    return json.dumps(data, indent=2)


def _tier_stats_dict(ts: TierStats) -> dict[str, Any]:
    return {
        "file_count": ts.file_count,
        "total_bytes": ts.total_bytes,
        "total_lines": ts.total_lines,
        "total_tokens": ts.total_tokens,
    }


def _type_stats_dict(ts: TypeStats) -> dict[str, Any]:
    return {
        "type_id": ts.type_id,
        "entity_count": ts.entity_count,
        "class_count": ts.class_count,
        "subclass_count": ts.subclass_count,
        "base_attr_count": ts.base_attr_count,
        "base_only_ratio": ts.base_only_ratio,
        "phone_book_width": ts.phone_book_width,
        "override_count": ts.override_count,
        "relationship_count": ts.relationship_count,
        "max_inheritance_depth": ts.max_inheritance_depth,
        "tier_b_bytes": ts.tier_b_bytes,
        "tier_b_tokens": ts.tier_b_tokens,
        "tier_c_bytes": ts.tier_c_bytes,
        "tier_c_tokens": ts.tier_c_tokens,
    }
