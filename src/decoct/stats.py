"""Compression statistics for decoct pipeline output."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

from ruamel.yaml import YAML

from decoct.tokens import count_tokens

# ---------------------------------------------------------------------------
# Internal YAML helper (ruamel for consistency with pipeline output)
# ---------------------------------------------------------------------------

def _yaml_dump(data: Any) -> str:
    """Serialise *data* to a YAML string using ruamel.yaml."""
    yaml = YAML()
    yaml.default_flow_style = False
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Leaf counting
# ---------------------------------------------------------------------------

def count_leaves(obj: Any) -> int:
    """Count scalar leaf values recursively."""
    if isinstance(obj, dict):
        return sum(count_leaves(v) for v in obj.values())
    elif isinstance(obj, list):
        return sum(count_leaves(v) for v in obj)
    return 1


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HostStats:
    """Per-host compression statistics."""

    name: str
    input_bytes: int
    tier_c_bytes: int
    input_tokens: int = 0
    tier_c_tokens: int = 0

    @property
    def saving_pct(self) -> float:
        return (1 - self.tier_c_bytes / self.input_bytes) * 100 if self.input_bytes else 0.0

    @property
    def token_saving_pct(self) -> float:
        return (1 - self.tier_c_tokens / self.input_tokens) * 100 if self.input_tokens else 0.0


@dataclass
class SectionStats:
    """Aggregated byte statistics for one section across all hosts."""

    name: str
    input_bytes: int
    tier_c_bytes: int

    @property
    def saving_pct(self) -> float:
        return (1 - self.tier_c_bytes / self.input_bytes) * 100 if self.input_bytes else 0.0


@dataclass
class ClassStats:
    """Statistics for a single Tier B class."""

    name: str
    bytes: int
    leaves: int
    host_count: int


@dataclass
class CompressionStats:
    """Overall compression statistics."""

    entity_count: int
    class_count: int
    input_bytes: int
    tier_b_bytes: int
    tier_c_bytes: int
    input_leaves: int
    tier_b_leaves: int
    tier_c_leaves: int
    input_tokens: int = 0
    tier_b_tokens: int = 0
    tier_c_tokens: int = 0
    per_host: list[HostStats] = field(default_factory=list)
    per_section: list[SectionStats] = field(default_factory=list)
    per_class: list[ClassStats] = field(default_factory=list)
    round_trip_ok: list[str] = field(default_factory=list)
    round_trip_fail: list[str] = field(default_factory=list)

    @property
    def compressed_bytes(self) -> int:
        return self.tier_b_bytes + self.tier_c_bytes

    @property
    def compression_pct(self) -> float:
        return (1 - self.compressed_bytes / self.input_bytes) * 100 if self.input_bytes else 0.0

    @property
    def compression_ratio(self) -> float:
        return self.input_bytes / self.compressed_bytes if self.compressed_bytes else 0.0

    @property
    def compressed_leaves(self) -> int:
        return self.tier_b_leaves + self.tier_c_leaves

    @property
    def leaf_reduction_pct(self) -> float:
        return (1 - self.compressed_leaves / self.input_leaves) * 100 if self.input_leaves else 0.0

    @property
    def compressed_tokens(self) -> int:
        return self.tier_b_tokens + self.tier_c_tokens

    @property
    def token_reduction_pct(self) -> float:
        return (1 - self.compressed_tokens / self.input_tokens) * 100 if self.input_tokens else 0.0

    @property
    def token_ratio(self) -> float:
        return self.input_tokens / self.compressed_tokens if self.compressed_tokens else 0.0


# ---------------------------------------------------------------------------
# Compute statistics
# ---------------------------------------------------------------------------

def compute_stats(
    corpus: dict[str, dict[str, Any]],
    tier_b: dict[str, Any],
    tier_c: dict[str, dict[str, Any]],
    mismatched_hosts: list[str] | None = None,
) -> CompressionStats:
    """Compute compression statistics from corpus + tier_b + tier_c."""
    hosts = sorted(corpus)
    mismatched_set = set(mismatched_hosts or [])

    # Byte + token sizes
    tier_b_yaml = _yaml_dump(dict(tier_b))
    tier_b_bytes = len(tier_b_yaml.encode("utf-8"))
    tier_b_tokens = count_tokens(tier_b_yaml)

    input_bytes_total = 0
    tier_c_bytes_total = 0
    input_tokens_total = 0
    tier_c_tokens_total = 0
    per_host: list[HostStats] = []

    for host in hosts:
        inp_yaml = _yaml_dump(dict(corpus[host]))
        tc_yaml = _yaml_dump(dict(tier_c.get(host, {})))
        inp_b = len(inp_yaml.encode("utf-8"))
        tc_b = len(tc_yaml.encode("utf-8"))
        inp_t = count_tokens(inp_yaml)
        tc_t = count_tokens(tc_yaml)
        input_bytes_total += inp_b
        tier_c_bytes_total += tc_b
        input_tokens_total += inp_t
        tier_c_tokens_total += tc_t
        per_host.append(HostStats(
            name=host, input_bytes=inp_b, tier_c_bytes=tc_b,
            input_tokens=inp_t, tier_c_tokens=tc_t,
        ))

    # Leaf counts
    input_leaves = sum(count_leaves(corpus[h]) for h in hosts)
    tier_b_leaves = count_leaves(tier_b)
    tier_c_leaves = sum(count_leaves(tier_c.get(h, {})) for h in hosts)

    # Per-section aggregated stats
    all_sections = sorted({s for h in hosts for s in corpus[h]})
    per_section: list[SectionStats] = []
    for section in all_sections:
        s_inp = 0
        s_tc = 0
        for host in hosts:
            if section in corpus[host]:
                s_inp += len(_yaml_dump(corpus[host][section]).encode("utf-8"))
            if host in tier_c and section in tier_c[host]:
                s_tc += len(_yaml_dump(tier_c[host][section]).encode("utf-8"))
        per_section.append(SectionStats(name=section, input_bytes=s_inp, tier_c_bytes=s_tc))

    # Per-class stats
    per_class: list[ClassStats] = []
    for class_name in sorted(tier_b):
        cls = tier_b[class_name]
        cls_bytes = len(_yaml_dump(dict(cls) if isinstance(cls, dict) else cls).encode("utf-8"))
        cls_leaves = count_leaves(cls)
        host_count = 0
        for host in hosts:
            for section_data in tier_c.get(host, {}).values():
                if isinstance(section_data, dict) and section_data.get("_class") == class_name:
                    host_count += 1
        per_class.append(ClassStats(name=class_name, bytes=cls_bytes, leaves=cls_leaves, host_count=host_count))

    round_trip_ok = [h for h in hosts if h not in mismatched_set]
    round_trip_fail = [h for h in hosts if h in mismatched_set]

    return CompressionStats(
        entity_count=len(hosts),
        class_count=len(tier_b),
        input_bytes=input_bytes_total,
        tier_b_bytes=tier_b_bytes,
        tier_c_bytes=tier_c_bytes_total,
        input_leaves=input_leaves,
        tier_b_leaves=tier_b_leaves,
        tier_c_leaves=tier_c_leaves,
        input_tokens=input_tokens_total,
        tier_b_tokens=tier_b_tokens,
        tier_c_tokens=tier_c_tokens_total,
        per_host=per_host,
        per_section=per_section,
        per_class=per_class,
        round_trip_ok=round_trip_ok,
        round_trip_fail=round_trip_fail,
    )


# ---------------------------------------------------------------------------
# Format statistics for display
# ---------------------------------------------------------------------------

def format_stats(stats: CompressionStats) -> str:
    """Render compression statistics as a human-readable string."""
    lines: list[str] = []
    sep = "=" * 72

    # --- Round-trip validation ---
    total = len(stats.round_trip_ok) + len(stats.round_trip_fail)
    if total:
        lines.append(sep)
        lines.append("ROUND-TRIP VALIDATION")
        lines.append(sep)
        for host in stats.round_trip_ok:
            lines.append(f"  OK    {host}")
        for host in stats.round_trip_fail:
            lines.append(f"  FAIL  {host}")
        lines.append(f"\n{len(stats.round_trip_ok)}/{total} hosts match")
        if stats.round_trip_fail:
            lines.append(f"Mismatches: {', '.join(stats.round_trip_fail)}")
        else:
            lines.append("Round-trip: PASS")
        lines.append("")

    # --- Compression statistics ---
    lines.append(sep)
    lines.append("COMPRESSION STATISTICS")
    lines.append(sep)

    # Bytes
    lines.append(f"\nTier A (input):  {stats.input_bytes:>8,} bytes  ({stats.entity_count} files)")
    lines.append(f"Tier B (classes): {stats.tier_b_bytes:>7,} bytes  ({stats.class_count} classes)")
    lines.append(f"Tier C (deltas): {stats.tier_c_bytes:>8,} bytes  ({stats.entity_count} files)")
    lines.append(f"B + C combined:  {stats.compressed_bytes:>8,} bytes")
    lines.append(f"Compression:     {stats.compression_pct:>7.1f}%")
    if stats.compressed_bytes:
        lines.append(f"Ratio:           {stats.compression_ratio:>7.2f}x")

    # Tokens
    lines.append("\n--- Token counts ---")
    lines.append(f"Input tokens:     {stats.input_tokens:>8,}")
    lines.append(f"Tier B tokens:    {stats.tier_b_tokens:>8,}")
    lines.append(f"Tier C tokens:    {stats.tier_c_tokens:>8,}")
    lines.append(f"B + C tokens:     {stats.compressed_tokens:>8,}")
    lines.append(f"Token reduction:  {stats.token_reduction_pct:>7.1f}%")
    if stats.compressed_tokens:
        lines.append(f"Token ratio:      {stats.token_ratio:>7.2f}x")

    # Leaves
    lines.append("\n--- Leaf counts ---")
    lines.append(f"Input leaves:     {stats.input_leaves:>8,}")
    lines.append(f"Tier B leaves:    {stats.tier_b_leaves:>8,}")
    lines.append(f"Tier C leaves:    {stats.tier_c_leaves:>8,}")
    lines.append(f"B + C leaves:     {stats.compressed_leaves:>8,}")
    lines.append(f"Leaf reduction:   {stats.leaf_reduction_pct:>7.1f}%")

    # Per-host table
    if stats.per_host:
        lines.append("\n--- Per-host ---")
        lines.append(
            f"{'Host':<20} {'Input':>8} {'Tier C':>8} {'Saving':>7}"
            f"  {'Tokens In':>9} {'Tokens Out':>10} {'Saving':>7}"
        )
        lines.append(
            f"{'-' * 20} {'-' * 8} {'-' * 8} {'-' * 7}"
            f"  {'-' * 9} {'-' * 10} {'-' * 7}"
        )
        for h in stats.per_host:
            lines.append(
                f"{h.name:<20} {h.input_bytes:>8,} {h.tier_c_bytes:>8,} {h.saving_pct:>6.1f}%"
                f"  {h.input_tokens:>9,} {h.tier_c_tokens:>10,} {h.token_saving_pct:>6.1f}%"
            )

    # Per-section table
    if stats.per_section:
        lines.append("\n--- Per-section (aggregated across hosts) ---")
        lines.append(f"{'Section':<22} {'Input':>8} {'Tier C':>8} {'Saving':>7}")
        lines.append(f"{'-' * 22} {'-' * 8} {'-' * 8} {'-' * 7}")
        for s in stats.per_section:
            lines.append(f"{s.name:<22} {s.input_bytes:>8,} {s.tier_c_bytes:>8,} {s.saving_pct:>6.1f}%")

    # Class utilisation
    if stats.per_class:
        lines.append("\n--- Class utilisation ---")
        lines.append(f"{'Class':<22} {'Bytes':>7} {'Leaves':>7} {'Hosts':>6}")
        lines.append(f"{'-' * 22} {'-' * 7} {'-' * 7} {'-' * 6}")
        for c in stats.per_class:
            lines.append(f"{c.name:<22} {c.bytes:>7,} {c.leaves:>7,} {c.host_count:>6}")

    lines.append("")
    return "\n".join(lines)
