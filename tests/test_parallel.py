"""Tests for parallel section compression (Phase 6)."""

from __future__ import annotations

from typing import Any

import pytest

from decoct.compress import compress


def _make_fleet(n_hosts: int = 10, n_sections: int = 5) -> dict[str, dict[str, Any]]:
    """Generate a synthetic fleet for parallel compression tests."""
    fleet: dict[str, dict[str, Any]] = {}
    for i in range(n_hosts):
        host = f"host-{i:03d}"
        sections: dict[str, Any] = {}
        for s in range(n_sections):
            section = f"section_{s}"
            sections[section] = {
                "id": f"host-{i:03d}-s{s}",
                "shared_a": f"common-{s}",
                "shared_b": 100 + s,
                "param": i * 10 + s,
            }
        fleet[host] = sections
    return fleet


class TestParallelDeterminism:
    """Parallel output must match sequential output exactly."""

    def test_parallel_matches_sequential(self) -> None:
        inputs = _make_fleet(n_hosts=10, n_sections=5)
        tier_b_seq, tier_c_seq = compress(inputs, workers=1)
        tier_b_par, tier_c_par = compress(inputs, workers=4)
        assert tier_b_seq == tier_b_par
        assert tier_c_seq == tier_c_par

    def test_parallel_matches_sequential_small(self) -> None:
        inputs = _make_fleet(n_hosts=3, n_sections=3)
        tier_b_seq, tier_c_seq = compress(inputs, workers=1)
        tier_b_par, tier_c_par = compress(inputs, workers=2)
        assert tier_b_seq == tier_b_par
        assert tier_c_seq == tier_c_par

    def test_workers_none_matches_sequential(self) -> None:
        """Default (workers=None) produces same result as workers=1."""
        inputs = _make_fleet(n_hosts=5, n_sections=3)
        tier_b_default, tier_c_default = compress(inputs)
        tier_b_seq, tier_c_seq = compress(inputs, workers=1)
        assert tier_b_default == tier_b_seq
        assert tier_c_default == tier_c_seq

    def test_many_workers_matches_sequential(self) -> None:
        """More workers than sections still works correctly."""
        inputs = _make_fleet(n_hosts=5, n_sections=3)
        tier_b_seq, tier_c_seq = compress(inputs, workers=1)
        tier_b_par, tier_c_par = compress(inputs, workers=10)
        assert tier_b_seq == tier_b_par
        assert tier_c_seq == tier_c_par

    def test_single_section_stays_sequential(self) -> None:
        """With only 1 section, parallel mode falls back to sequential."""
        inputs = _make_fleet(n_hosts=5, n_sections=1)
        tier_b_seq, tier_c_seq = compress(inputs, workers=1)
        tier_b_par, tier_c_par = compress(inputs, workers=4)
        assert tier_b_seq == tier_b_par
        assert tier_c_seq == tier_c_par


class TestCallbackIsolation:
    """on_section callbacks fire in the main process."""

    def test_callbacks_parallel(self) -> None:
        events: list[tuple[str, str]] = []

        def on_section(name: str, event: str) -> None:
            events.append((name, event))

        inputs = _make_fleet(n_hosts=5, n_sections=4)
        compress(inputs, workers=2, on_section=on_section)

        assert len(events) > 0
        sections = {name for name, _ in events}
        for s in sections:
            assert (s, "start") in events
            assert (s, "done") in events

    def test_callbacks_sequential(self) -> None:
        events: list[tuple[str, str]] = []

        def on_section(name: str, event: str) -> None:
            events.append((name, event))

        inputs = _make_fleet(n_hosts=5, n_sections=4)
        compress(inputs, workers=1, on_section=on_section)

        sections = {name for name, _ in events}
        for s in sections:
            assert (s, "start") in events
            assert (s, "done") in events


class TestSingleSectionHelper:
    """_compress_single_section produces correct output."""

    def test_single_section_output_matches(self) -> None:
        from decoct.compress import _compress_single_section
        from decoct.storage import DuckDBStore

        inputs = _make_fleet(n_hosts=5, n_sections=3)
        store = DuckDBStore()
        store.ingest_fleet(inputs)

        tier_b_full, tier_c_full = compress(inputs, workers=1)

        section = "section_0"
        hosts = store.get_hosts_for_section(section)
        section_type = store.get_section_type(section)
        section_b, result_c = _compress_single_section(
            store, section, hosts, section_type,
        )

        for class_name in section_b:
            assert class_name in tier_b_full
            assert tier_b_full[class_name] == section_b[class_name]

        store.close()


class TestListSectionParallel:
    """Parallel mode works with list-of-dicts sections."""

    def test_list_section_parallel(self) -> None:
        fleet: dict[str, dict[str, Any]] = {}
        for i in range(6):
            host = f"host-{i:03d}"
            fleet[host] = {
                "dict_section": {
                    "id": f"host-{i}",
                    "shared": "common",
                    "param": i,
                },
                "list_section": [
                    {"name": f"item-{j}", "type": "shared_type", "val": j}
                    for j in range(3)
                ],
            }
        tier_b_seq, tier_c_seq = compress(fleet, workers=1)
        tier_b_par, tier_c_par = compress(fleet, workers=2)
        assert tier_b_seq == tier_b_par
        assert tier_c_seq == tier_c_par
