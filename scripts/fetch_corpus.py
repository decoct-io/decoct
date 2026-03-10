#!/usr/bin/env python3
"""Fetch public config files and benchmark decoct compression against them.

Usage:
    python scripts/fetch_corpus.py                    # fetch + benchmark
    python scripts/fetch_corpus.py --fetch-only       # just fetch
    python scripts/fetch_corpus.py --benchmark-only   # run on existing corpus
    python scripts/fetch_corpus.py --clean            # re-fetch everything
    python scripts/fetch_corpus.py --verbose          # per-pass timing
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus"
CACHE_DIR = CORPUS_DIR / ".cache"
RESULTS_DIR = CORPUS_DIR / "results"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"

# Each source: repo URL, file globs to sparse-checkout, expected platform for filtering.
# Files that don't detect as the expected platform are discarded.
CORPUS_SOURCES: list[dict[str, str | list[str]]] = [
    {
        "repo": "https://github.com/docker/awesome-compose.git",
        "platform": "docker-compose",
        "patterns": ["**/compose.yaml", "**/compose.yml", "**/docker-compose.yaml", "**/docker-compose.yml"],
    },
    {
        "repo": "https://github.com/kubernetes/examples.git",
        "platform": "kubernetes",
        "patterns": ["**/*.yaml"],
    },
    {
        "repo": "https://github.com/ansible/ansible-examples.git",
        "platform": "ansible-playbook",
        "patterns": ["**/*.yml"],
    },
    {
        "repo": "https://github.com/prometheus/prometheus.git",
        "platform": "prometheus",
        "patterns": ["documentation/examples/*.yml"],
    },
    {
        "repo": "https://github.com/actions/starter-workflows.git",
        "platform": "github-actions",
        "patterns": ["**/*.yml"],
    },
    {
        "repo": "https://github.com/traefik/traefik.git",
        "platform": "traefik",
        "patterns": ["traefik.sample.yml", "traefik.sample.toml"],
    },
    {
        "repo": "https://github.com/canonical/cloud-init.git",
        "platform": "cloud-init",
        "patterns": ["doc/examples/cloud-config*.txt"],
        "rename_ext": ".yaml",
    },
    {
        "repo": "https://github.com/hashicorp-education/learn-terraform-state.git",
        "platform": "terraform-state",
        "patterns": ["*.tfstate"],
        "rename_ext": ".json",
    },
]


def _repo_slug(repo_url: str) -> str:
    """Extract a slug like 'awesome-compose' from a repo URL."""
    return repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


def _load_manifest() -> dict[str, dict[str, str]]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def _save_manifest(manifest: dict[str, dict[str, str]]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")


def clone_repo(repo_url: str) -> Path:
    """Sparse-clone a repo into the cache directory. Returns clone path."""
    slug = _repo_slug(repo_url)
    clone_dir = CACHE_DIR / slug

    if clone_dir.exists():
        # Already cloned — pull latest
        subprocess.run(
            ["git", "-C", str(clone_dir), "pull", "--ff-only"],
            capture_output=True,
        )
        return clone_dir

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git", "clone",
            "--filter=blob:none",
            "--sparse",
            "--depth=1",
            repo_url,
            str(clone_dir),
        ],
        check=True,
        capture_output=True,
    )
    return clone_dir


def _match_patterns(path: Path, base: Path, patterns: list[str]) -> bool:
    """Check if a file path matches any of the glob patterns."""
    rel = str(path.relative_to(base))
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def copy_files(
    clone_dir: Path,
    platform: str,
    patterns: list[str],
    rename_ext: str | None = None,
) -> list[Path]:
    """Copy matching files from clone into corpus/<platform>/<slug>/."""
    slug = clone_dir.name
    dest_dir = CORPUS_DIR / platform / slug
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for f in sorted(clone_dir.rglob("*")):
        if not f.is_file():
            continue
        if f.parts and ".git" in f.parts:
            continue
        if not _match_patterns(f, clone_dir, patterns):
            continue

        rel = f.relative_to(clone_dir)
        target = dest_dir / rel
        if rename_ext:
            target = target.with_suffix(rename_ext)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        copied.append(target)

    return copied


def filter_by_platform(files: list[Path], expected_platform: str) -> tuple[list[Path], int]:
    """Remove files that don't auto-detect as the expected platform.

    Returns (kept_files, removed_count).
    """
    from decoct.formats import detect_platform, load_input

    kept: list[Path] = []
    removed = 0
    for f in files:
        try:
            doc, _ = load_input(f)
            detected = detect_platform(doc)
            if detected == expected_platform:
                kept.append(f)
            else:
                f.unlink()
                removed += 1
        except Exception:  # noqa: BLE001
            f.unlink()
            removed += 1

    return kept, removed


def _get_head_sha(clone_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def fetch_all(*, clean: bool = False) -> dict[str, list[Path]]:
    """Clone all repos and copy matching files into the corpus.

    Returns a dict mapping platform to list of corpus file paths.
    """
    if clean and CORPUS_DIR.exists():
        shutil.rmtree(CORPUS_DIR)

    manifest = _load_manifest()
    corpus_files: dict[str, list[Path]] = {}

    for source in CORPUS_SOURCES:
        repo_url = str(source["repo"])
        platform = str(source["platform"])
        patterns = list(source["patterns"])  # type: ignore[arg-type]
        rename_ext = str(source["rename_ext"]) if "rename_ext" in source else None
        slug = _repo_slug(repo_url)

        print(f"  [{platform}] {slug} ... ", end="", flush=True)

        try:
            clone_dir = clone_repo(repo_url)
        except subprocess.CalledProcessError as exc:
            print(f"CLONE FAILED: {exc}")
            continue

        # Disable sparse checkout cone mode and set patterns for full match
        subprocess.run(
            ["git", "-C", str(clone_dir), "sparse-checkout", "disable"],
            capture_output=True,
        )

        copied = copy_files(clone_dir, platform, patterns, rename_ext)
        kept, removed = filter_by_platform(copied, platform)

        sha = _get_head_sha(clone_dir)
        manifest[slug] = {
            "repo": repo_url,
            "platform": platform,
            "sha": sha,
            "fetched": datetime.now(tz=timezone.utc).isoformat(),
            "files_copied": len(copied),
            "files_kept": len(kept),
            "files_filtered": removed,
        }

        corpus_files[platform] = corpus_files.get(platform, []) + kept
        print(f"{len(kept)} files (filtered {removed})")

    _save_manifest(manifest)

    # Clean up empty platform directories
    for d in sorted(CORPUS_DIR.iterdir()):
        if d.is_dir() and d.name not in (".cache", "results") and not any(d.rglob("*")):
            d.rmdir()

    return corpus_files


def run_benchmark_on_corpus(*, verbose: bool = False, corpus_tier: bool = False) -> None:
    """Run decoct benchmark on the corpus and save results."""
    from decoct.benchmark import (
        BenchmarkReport,
        format_report_json,
        format_report_markdown,
        run_benchmark,
    )

    # Gather platform directories (skip .cache, results)
    platform_dirs = [
        d for d in sorted(CORPUS_DIR.iterdir())
        if d.is_dir() and d.name not in (".cache", "results")
    ]

    if not platform_dirs:
        print("No corpus files found. Run with --fetch-only first.")
        sys.exit(1)

    tier_msg = " (with corpus learning)" if corpus_tier else ""
    print(f"\nBenchmarking {len(platform_dirs)} platforms{tier_msg} ...")
    report: BenchmarkReport = run_benchmark(
        [str(d) for d in platform_dirs],
        recursive=True,
        learn_corpus=corpus_tier,
    )

    if not report.files:
        print("No files were successfully benchmarked.")
        sys.exit(1)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")

    md_path = RESULTS_DIR / f"benchmark-{ts}.md"
    md_text = format_report_markdown(report, verbose=verbose)
    md_path.write_text(md_text + "\n")

    json_path = RESULTS_DIR / f"benchmark-{ts}.json"
    json_text = format_report_json(report)
    json_path.write_text(json_text + "\n")

    print(md_text)
    print(f"\nResults saved to:\n  {md_path}\n  {json_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch public config corpus and benchmark decoct compression.",
    )
    parser.add_argument("--fetch-only", action="store_true", help="Only fetch files, skip benchmark")
    parser.add_argument("--benchmark-only", action="store_true", help="Benchmark existing corpus, skip fetch")
    parser.add_argument("--clean", action="store_true", help="Delete corpus and re-fetch everything")
    parser.add_argument("--verbose", action="store_true", help="Include per-pass timing in report")
    parser.add_argument(
        "--corpus-tier", action="store_true",
        help="Learn compression classes from corpus and add a 'corpus' benchmark tier",
    )
    args = parser.parse_args()

    if args.fetch_only and args.benchmark_only:
        parser.error("--fetch-only and --benchmark-only are mutually exclusive")

    if not args.benchmark_only:
        print("Fetching corpus ...")
        corpus = fetch_all(clean=args.clean)
        total = sum(len(v) for v in corpus.values())
        print(f"\nCorpus ready: {total} files across {len(corpus)} platforms")

    if not args.fetch_only:
        run_benchmark_on_corpus(verbose=args.verbose, corpus_tier=args.corpus_tier)


if __name__ == "__main__":
    main()
