"""Performance benchmark for DuckDB storage backend.

Generates synthetic fleet data and measures ingestion + compression
time and peak memory usage.

Usage:
    python benchmarks/bench_storage.py [--hosts 100,1000,10000]
    python benchmarks/bench_storage.py --ingest-only --hosts 1000,10000
"""

from __future__ import annotations

import argparse
import time
import tracemalloc
from typing import Any

from decoct.compress import compress_db
from decoct.storage import DuckDBStore

SECTIONS_PER_HOST = 15
PATHS_PER_SECTION = 50
NESTING_DEPTH = 3


def _generate_section(host_idx: int, section_idx: int) -> dict[str, Any]:
    """Generate a synthetic section with ~50 leaf paths."""
    section: dict[str, Any] = {}
    path_count = 0
    groups_per_level = 5
    keys_per_group = 5

    for g in range(groups_per_level):
        group: dict[str, Any] = {}
        for k in range(keys_per_group):
            if path_count >= PATHS_PER_SECTION:
                break
            # Most values shared across hosts (for compression),
            # one unique per host (for identity/deltas)
            if k == 0:
                group[f"id_{k}"] = f"host-{host_idx:05d}-s{section_idx}-g{g}"
            elif k < 3:
                group[f"shared_{k}"] = f"common-value-{section_idx}-{g}-{k}"
            else:
                group[f"param_{k}"] = k * 100 + section_idx
            path_count += 1
        if group:
            section[f"group_{g}"] = group
        if path_count >= PATHS_PER_SECTION:
            break

    return section


def generate_fleet(num_hosts: int) -> dict[str, dict[str, Any]]:
    """Generate a synthetic fleet with the given number of hosts."""
    fleet: dict[str, dict[str, Any]] = {}
    for i in range(num_hosts):
        hostname = f"host-{i:05d}"
        sections: dict[str, Any] = {}
        for s in range(SECTIONS_PER_HOST):
            sections[f"section_{s}"] = _generate_section(i, s)
        fleet[hostname] = sections
    return fleet


def bench_ingest(num_hosts: int) -> dict[str, Any]:
    """Benchmark ingestion only (no compression)."""
    print(f"\n--- {num_hosts} hosts (ingest only) ---")

    t0 = time.perf_counter()
    fleet = generate_fleet(num_hosts)
    gen_time = time.perf_counter() - t0
    print(f"  Data generation: {gen_time:.2f}s")

    tracemalloc.start()

    t0 = time.perf_counter()
    store = DuckDBStore()
    store.ingest_fleet(fleet)
    ingest_time = time.perf_counter() - t0
    print(f"  Ingestion:       {ingest_time:.2f}s")

    del fleet

    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    sections = store.get_sections()
    total_hosts = len(store.get_hosts_for_section(sections[0])) if sections else 0
    store.close()

    peak_mb = peak_bytes / (1024 * 1024)
    print(f"  Peak memory:     {peak_mb:.1f} MB")
    print(f"  Sections:        {len(sections)}")
    print(f"  Hosts/section:   {total_hosts}")

    return {
        "hosts": num_hosts,
        "ingest_s": round(ingest_time, 2),
        "peak_mb": round(peak_mb, 1),
    }


def bench_full(num_hosts: int, workers: int = 1) -> dict[str, Any]:
    """Benchmark ingestion + compression."""
    label = f"workers={workers}" if workers > 1 else "sequential"
    print(f"\n--- {num_hosts} hosts ({label}) ---")

    t0 = time.perf_counter()
    fleet = generate_fleet(num_hosts)
    gen_time = time.perf_counter() - t0
    print(f"  Data generation: {gen_time:.2f}s")

    tracemalloc.start()

    t0 = time.perf_counter()
    store = DuckDBStore()
    store.ingest_fleet(fleet)
    ingest_time = time.perf_counter() - t0
    print(f"  Ingestion:       {ingest_time:.2f}s")

    del fleet

    t0 = time.perf_counter()
    tier_b, tier_c = compress_db(store, workers=workers)
    compress_time = time.perf_counter() - t0
    print(f"  Compression:     {compress_time:.2f}s")

    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    store.close()

    peak_mb = peak_bytes / (1024 * 1024)
    total_time = ingest_time + compress_time
    print(f"  Total time:      {total_time:.2f}s")
    print(f"  Peak memory:     {peak_mb:.1f} MB")
    print(f"  Classes:         {len(tier_b)}")
    print(f"  Hosts in tier_c: {len(tier_c)}")

    return {
        "hosts": num_hosts,
        "workers": workers,
        "ingest_s": round(ingest_time, 2),
        "compress_s": round(compress_time, 2),
        "total_s": round(total_time, 2),
        "peak_mb": round(peak_mb, 1),
        "classes": len(tier_b),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DuckDB storage benchmark")
    parser.add_argument(
        "--hosts",
        default="10,50",
        help="Comma-separated host counts (default: 10,50)",
    )
    parser.add_argument(
        "--workers",
        default="1",
        help="Comma-separated worker counts for parallel benchmark (default: 1)",
    )
    parser.add_argument(
        "--ingest-only",
        action="store_true",
        help="Benchmark ingestion only (skip compression)",
    )
    args = parser.parse_args()

    host_counts = [int(x.strip()) for x in args.hosts.split(",")]
    worker_counts = [int(x.strip()) for x in args.workers.split(",")]

    print("DuckDB Storage Backend Benchmark")
    print(f"Config: {SECTIONS_PER_HOST} sections/host, ~{PATHS_PER_SECTION} paths/section")

    results = []
    for n in host_counts:
        if args.ingest_only:
            results.append(bench_ingest(n))
        else:
            for w in worker_counts:
                results.append(bench_full(n, workers=w))

    print("\n=== Summary ===")
    if args.ingest_only:
        print(f"{'Hosts':>8} {'Ingest':>8} {'Peak MB':>10}")
        for r in results:
            print(f"{r['hosts']:>8} {r['ingest_s']:>7.2f}s {r['peak_mb']:>9.1f}")
    else:
        print(f"{'Hosts':>8} {'Workers':>8} {'Ingest':>8} {'Compress':>10} {'Total':>8} {'Peak MB':>10} {'Classes':>8}")
        for r in results:
            print(
                f"{r['hosts']:>8} {r['workers']:>8} {r['ingest_s']:>7.2f}s {r['compress_s']:>9.2f}s "
                f"{r['total_s']:>7.2f}s {r['peak_mb']:>9.1f} {r['classes']:>8}"
            )


if __name__ == "__main__":
    main()
