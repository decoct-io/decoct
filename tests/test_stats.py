"""Tests for decoct.stats module."""

from __future__ import annotations

from typing import Any

from decoct.stats import CompressionStats, compute_stats, count_leaves, format_stats

# ---------------------------------------------------------------------------
# count_leaves
# ---------------------------------------------------------------------------


def test_count_leaves_scalar() -> None:
    assert count_leaves(42) == 1
    assert count_leaves("hello") == 1
    assert count_leaves(True) == 1


def test_count_leaves_nested_dict() -> None:
    data: dict[str, Any] = {"a": 1, "b": {"c": 2, "d": 3}}
    assert count_leaves(data) == 3


def test_count_leaves_list() -> None:
    data: list[Any] = [1, 2, {"a": 3}]
    assert count_leaves(data) == 3


def test_count_leaves_empty_containers() -> None:
    assert count_leaves({}) == 0
    assert count_leaves([]) == 0


# ---------------------------------------------------------------------------
# CompressionStats properties
# ---------------------------------------------------------------------------


def test_compression_stats_computed_properties() -> None:
    stats = CompressionStats(
        entity_count=3,
        class_count=2,
        input_bytes=1000,
        tier_b_bytes=200,
        tier_c_bytes=300,
        input_leaves=100,
        tier_b_leaves=20,
        tier_c_leaves=50,
    )
    assert stats.compressed_bytes == 500
    assert stats.compression_pct == 50.0
    assert stats.compression_ratio == 2.0
    assert stats.compressed_leaves == 70
    assert abs(stats.leaf_reduction_pct - 30.0) < 1e-10


def test_compression_stats_zero_input() -> None:
    stats = CompressionStats(
        entity_count=0,
        class_count=0,
        input_bytes=0,
        tier_b_bytes=0,
        tier_c_bytes=0,
        input_leaves=0,
        tier_b_leaves=0,
        tier_c_leaves=0,
    )
    assert stats.compression_pct == 0.0
    assert stats.compression_ratio == 0.0
    assert stats.leaf_reduction_pct == 0.0


# ---------------------------------------------------------------------------
# compute_stats
# ---------------------------------------------------------------------------


def _make_corpus() -> dict[str, dict[str, Any]]:
    """Three hosts with overlapping network config."""
    return {
        "host-a": {
            "network": {"ip": "10.0.0.1", "mask": "255.255.255.0", "gateway": "10.0.0.254", "mtu": 1500},
            "dns": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
        },
        "host-b": {
            "network": {"ip": "10.0.0.2", "mask": "255.255.255.0", "gateway": "10.0.0.254", "mtu": 1500},
            "dns": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
        },
        "host-c": {
            "network": {"ip": "10.0.0.3", "mask": "255.255.255.0", "gateway": "10.0.0.254", "mtu": 9000},
            "dns": {"primary": "8.8.8.8", "secondary": "8.8.4.4"},
        },
    }


def test_compute_stats_entity_count() -> None:
    from decoct.archetypal import archetypal_compress

    corpus = _make_corpus()
    tier_b, tier_c = archetypal_compress(corpus)
    stats = compute_stats(corpus, tier_b, tier_c)

    assert stats.entity_count == 3
    assert stats.class_count == len(tier_b)
    assert stats.input_bytes > 0
    assert stats.compressed_bytes > 0
    assert stats.input_leaves > 0
    assert stats.input_tokens > 0
    assert stats.compressed_tokens > 0
    assert stats.token_reduction_pct > 0
    assert len(stats.per_host) == 3
    assert all(h.input_tokens > 0 for h in stats.per_host)
    assert len(stats.per_section) == 2  # network, dns
    assert len(stats.round_trip_ok) == 3
    assert len(stats.round_trip_fail) == 0


# ---------------------------------------------------------------------------
# format_stats
# ---------------------------------------------------------------------------


def test_format_stats_contains_expected_sections() -> None:
    stats = CompressionStats(
        entity_count=3,
        class_count=2,
        input_bytes=1000,
        tier_b_bytes=200,
        tier_c_bytes=300,
        input_leaves=100,
        tier_b_leaves=20,
        tier_c_leaves=50,
        input_tokens=500,
        tier_b_tokens=100,
        tier_c_tokens=150,
        round_trip_ok=["host-a", "host-b", "host-c"],
    )
    output = format_stats(stats)
    assert "COMPRESSION STATISTICS" in output
    assert "Tier A (input):" in output
    assert "Tier B (classes):" in output
    assert "Compression:" in output
    assert "Token counts" in output
    assert "Token reduction:" in output
    assert "Leaf counts" in output
    assert "ROUND-TRIP VALIDATION" in output
    assert "Round-trip: PASS" in output


def test_format_stats_shows_failures() -> None:
    stats = CompressionStats(
        entity_count=2,
        class_count=1,
        input_bytes=500,
        tier_b_bytes=100,
        tier_c_bytes=200,
        input_leaves=50,
        tier_b_leaves=10,
        tier_c_leaves=25,
        round_trip_ok=["host-a"],
        round_trip_fail=["host-b"],
    )
    output = format_stats(stats)
    assert "FAIL  host-b" in output
    assert "OK    host-a" in output
    assert "Mismatches: host-b" in output
