#!/usr/bin/env python3
"""Projection spec inference — model comparison eval harness.

Compares multiple LLM models on projection spec quality across entity types.
Measures coverage, granularity, and token efficiency of inferred specs.

Runs all (model × type) combinations in parallel via concurrent.futures.

Usage:
    python scripts/eval_projection_models.py
    python scripts/eval_projection_models.py --models google/gemini-2.5-flash --types sshd
    python scripts/eval_projection_models.py --workers 4
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.learn_projections import infer_projection_spec
from decoct.projections.generator import generate_projection
from decoct.projections.models import ProjectionSpec, SubjectSpec
from decoct.projections.path_matcher import collect_matching_paths
from decoct.projections.spec_loader import dump_projection_spec, load_projection_spec
from decoct.tokens import count_tokens

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_MODELS = [
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "google/gemini-3-flash-preview",
    "google/gemini-3.1-pro-preview",
    "deepseek/deepseek-v3.2",
    "moonshotai/kimi-k2.5",
]

DEFAULT_TYPES: list[dict[str, str]] = [
    {"type_id": "iosxr-access-pe", "output_dir": "output/iosxr"},
    {"type_id": "mariadb", "output_dir": "output/hybrid-infra"},
    {"type_id": "entra-conditional-access", "output_dir": "output/entra-intune"},
    {"type_id": "sshd", "output_dir": "output/hybrid-infra"},
    {"type_id": "postgresql", "output_dir": "output/hybrid-infra"},
]

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_API_KEY_ENV = "OPENROUTER_API_KEY"

RETRY_DELAY = 5.0
MAX_RETRIES = 1
DEFAULT_WORKERS = 8  # one thread per model by default

# ── Metrics dataclass ─────────────────────────────────────────────────────────


@dataclass
class ProjectionMetrics:
    """Quality metrics for a single (model x type) evaluation."""

    model: str
    type_id: str
    subject_count: int = 0
    total_attrs: int = 0
    matched_attrs: int = 0
    attr_coverage_pct: float = 0.0
    pb_total: int = 0
    pb_matched: int = 0
    pb_coverage_pct: float = 0.0
    avg_projection_tokens: float = 0.0
    max_projection_tokens: int = 0
    total_projection_tokens: int = 0
    avg_attrs_per_subject: float = 0.0
    elapsed_seconds: float = 0.0
    error: str | None = None
    uncovered_paths: list[str] = field(default_factory=list)


# ── Path collection (fixed) ───────────────────────────────────────────────────


def _collect_all_paths_fixed(tier_b: dict[str, Any], tier_c: dict[str, Any]) -> set[str]:
    """Collect every attribute path from Tier B and Tier C.

    Fixes upstream ``_collect_all_paths`` which reads override structural keys
    (``owner``, ``delta``) instead of drilling into the ``delta`` dict for
    actual attribute paths.
    """
    paths: set[str] = set()

    # Base class keys
    for key in tier_b.get("base_class", {}):
        paths.add(key)

    # Class own_attrs
    for cls_data in tier_b.get("classes", {}).values():
        for key in cls_data.get("own_attrs", {}):
            paths.add(key)

    # Subclass own_attrs
    for sub_data in tier_b.get("subclasses", {}).values():
        for key in sub_data.get("own_attrs", {}):
            paths.add(key)

    # Composite templates
    for path_group in tier_b.get("composite_templates", {}).values():
        if isinstance(path_group, str):
            paths.add(path_group)
        elif isinstance(path_group, dict):
            for tmpl_data in path_group.values():
                if isinstance(tmpl_data, dict):
                    elements = tmpl_data.get("elements", [])
                    if isinstance(elements, list):
                        for elem in elements:
                            if isinstance(elem, dict):
                                for key in elem:
                                    paths.add(key)
                    elif isinstance(elements, dict):
                        for key in elements:
                            paths.add(key)

    # Phone book schema
    instance_data = tier_c.get("instance_data", {})
    for key in instance_data.get("schema", []):
        paths.add(key)

    # Instance attrs
    for entity_attrs in tier_c.get("instance_attrs", {}).values():
        if isinstance(entity_attrs, dict):
            for key in entity_attrs:
                paths.add(key)

    # Overrides — drill into delta subkey for actual attribute paths
    for entity_overrides in tier_c.get("overrides", {}).values():
        if isinstance(entity_overrides, dict):
            delta = entity_overrides.get("delta", entity_overrides)
            if isinstance(delta, dict):
                for key in delta:
                    paths.add(key)

    # B composite deltas
    for entity_deltas in tier_c.get("b_composite_deltas", {}).values():
        if isinstance(entity_deltas, dict):
            for key in entity_deltas:
                paths.add(key)

    return paths


# ── Coverage computation ──────────────────────────────────────────────────────


def compute_coverage(
    tier_b: dict[str, Any],
    tier_c: dict[str, Any],
    spec: ProjectionSpec,
) -> tuple[int, int, int, int, list[str]]:
    """Compute attribute and phone book coverage.

    Returns (total_attrs, matched_attrs, pb_total, pb_matched, uncovered_paths).
    """
    all_paths = _collect_all_paths_fixed(tier_b, tier_c)

    # Union of all subject patterns
    all_include: list[str] = []
    all_related: list[str] = []
    for subj in spec.subjects:
        all_include.extend(subj.include_paths)
        all_related.extend(rp.path for rp in subj.related_paths)

    matched = collect_matching_paths(all_paths, all_include, all_related)

    # Phone book coverage
    schema = tier_c.get("instance_data", {}).get("schema", [])
    pb_total = len(schema)
    pb_matched = sum(1 for col in schema if col in matched)

    uncovered = sorted(all_paths - matched)

    return len(all_paths), len(matched), pb_total, pb_matched, uncovered


def compute_subject_stats(
    tier_b: dict[str, Any],
    tier_c: dict[str, Any],
    subject: SubjectSpec,
) -> tuple[int, int]:
    """For a subject: count matched attributes and projection tokens.

    Returns (attr_count, token_count).
    """
    all_paths = _collect_all_paths_fixed(tier_b, tier_c)
    related_patterns = [rp.path for rp in subject.related_paths]
    matching = collect_matching_paths(all_paths, subject.include_paths, related_patterns)
    attr_count = len(matching)

    # Generate the projection and count tokens
    projection = generate_projection(tier_b, tier_c, subject)
    yaml = YAML(typ="rt")
    yaml.default_flow_style = False
    stream = StringIO()
    yaml.dump(projection, stream)
    token_count = count_tokens(stream.getvalue())

    return attr_count, token_count


# ── Single eval run ───────────────────────────────────────────────────────────


def _load_tier_data(output_dir: Path, type_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load Tier B and Tier C YAML for a given type."""
    yaml = YAML(typ="safe")

    classes_file = output_dir / f"{type_id}_classes.yaml"
    if not classes_file.exists():
        msg = f"Tier B file not found: {classes_file}"
        raise FileNotFoundError(msg)
    tier_b = yaml.load(classes_file.read_text())

    instances_file = output_dir / f"{type_id}_instances.yaml"
    tier_c: dict[str, Any] = {}
    if instances_file.exists():
        loaded = yaml.load(instances_file.read_text())
        if isinstance(loaded, dict):
            tier_c = loaded

    return tier_b, tier_c


def run_single_eval(
    type_id: str,
    output_dir: Path,
    model: str,
    base_url: str,
    api_key_env: str,
) -> tuple[ProjectionMetrics, ProjectionSpec | None]:
    """Run full eval pipeline for one (model x type) pair.

    Returns (metrics, spec) — spec is None on failure.
    """
    metrics = ProjectionMetrics(model=model, type_id=type_id)
    start = time.monotonic()

    try:
        # Load data
        tier_b, tier_c = _load_tier_data(output_dir, type_id)

        # Infer spec with retry
        spec: ProjectionSpec | None = None
        last_err: Exception | None = None
        for attempt in range(1 + MAX_RETRIES):
            try:
                spec = infer_projection_spec(
                    output_dir=output_dir,
                    type_id=type_id,
                    model=model,
                    base_url=base_url,
                    api_key_env=api_key_env,
                )
                break
            except Exception as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        if spec is None:
            metrics.error = str(last_err)
            metrics.elapsed_seconds = time.monotonic() - start
            return metrics, None

        # Coverage
        total_attrs, matched_attrs, pb_total, pb_matched, uncovered = compute_coverage(
            tier_b, tier_c, spec
        )
        metrics.subject_count = len(spec.subjects)
        metrics.total_attrs = total_attrs
        metrics.matched_attrs = matched_attrs
        metrics.attr_coverage_pct = (matched_attrs / total_attrs * 100) if total_attrs else 0.0
        metrics.pb_total = pb_total
        metrics.pb_matched = pb_matched
        metrics.pb_coverage_pct = (pb_matched / pb_total * 100) if pb_total else 100.0
        metrics.uncovered_paths = uncovered[:20]  # cap for output size

        # Per-subject stats
        subject_attrs: list[int] = []
        subject_tokens: list[int] = []
        for subj in spec.subjects:
            attr_count, token_count = compute_subject_stats(tier_b, tier_c, subj)
            subject_attrs.append(attr_count)
            subject_tokens.append(token_count)

        if subject_tokens:
            metrics.avg_projection_tokens = sum(subject_tokens) / len(subject_tokens)
            metrics.max_projection_tokens = max(subject_tokens)
            metrics.total_projection_tokens = sum(subject_tokens)
        if subject_attrs:
            metrics.avg_attrs_per_subject = sum(subject_attrs) / len(subject_attrs)

        metrics.elapsed_seconds = time.monotonic() - start
        return metrics, spec

    except Exception as e:
        metrics.error = str(e)
        metrics.elapsed_seconds = time.monotonic() - start
        return metrics, None


# ── Output formatting ─────────────────────────────────────────────────────────

_HEADER_FMT = "  {:<35s} {:>4s} {:>8s} {:>7s} {:>7s} {:>7s} {:>7s} {:>7s} {:>6s}"
_ROW_FMT = "  {:<35s} {:>4d} {:>7.1f}% {:>6.1f}% {:>7.0f} {:>7d} {:>7d} {:>6.1f} {:>5.1f}s"
_ERR_FMT = "  {:<35s}  ** ERROR: {}"


def print_comparison_table(results: dict[str, list[ProjectionMetrics]]) -> None:
    """Print per-type comparison tables and overall rankings."""
    sep = "=" * 72

    print(f"\n{sep}")
    print("  PROJECTION SPEC INFERENCE — MODEL COMPARISON")
    print(sep)

    for type_id, metrics_list in results.items():
        print(f"\n--- {type_id} ---")
        print(_HEADER_FMT.format(
            "Model", "Subj", "AttrCov%", "PBCov%",
            "AvgTok", "MaxTok", "TotTok", "Avg/Sub", "Time",
        ))
        for m in metrics_list:
            if m.error:
                print(_ERR_FMT.format(m.model, m.error[:50]))
            else:
                print(_ROW_FMT.format(
                    m.model,
                    m.subject_count,
                    m.attr_coverage_pct,
                    m.pb_coverage_pct,
                    m.avg_projection_tokens,
                    m.max_projection_tokens,
                    m.total_projection_tokens,
                    m.avg_attrs_per_subject,
                    m.elapsed_seconds,
                ))

    # Overall rankings — average metrics across types per model
    print(f"\n{sep}")
    print("  OVERALL MODEL RANKINGS")
    print(sep)

    model_agg: dict[str, list[ProjectionMetrics]] = {}
    for metrics_list in results.values():
        for m in metrics_list:
            if m.error:
                continue
            model_agg.setdefault(m.model, []).append(m)

    print(_HEADER_FMT.format(
        "Model", "Runs", "AttrCov%", "PBCov%",
        "AvgTok", "MaxTok", "TotTok", "Avg/Sub", "Time",
    ))

    ranked: list[tuple[str, float, int, float, float, float, int, int, float, float]] = []
    for model, ms in sorted(model_agg.items()):
        n = len(ms)
        avg_attr_cov = sum(m.attr_coverage_pct for m in ms) / n
        avg_pb_cov = sum(m.pb_coverage_pct for m in ms) / n
        avg_avg_tok = sum(m.avg_projection_tokens for m in ms) / n
        avg_max_tok = max(m.max_projection_tokens for m in ms)
        avg_tot_tok = sum(m.total_projection_tokens for m in ms) // n
        avg_attrs_subj = sum(m.avg_attrs_per_subject for m in ms) / n
        avg_time = sum(m.elapsed_seconds for m in ms) / n
        ranked.append((
            model, avg_attr_cov, n, avg_pb_cov, avg_avg_tok,
            avg_attrs_subj, avg_max_tok, avg_tot_tok, avg_time, avg_attr_cov,
        ))

    # Sort by coverage descending
    ranked.sort(key=lambda r: r[1], reverse=True)
    for model, _, n, pb_cov, avg_tok, attrs_subj, max_tok, tot_tok, avg_time, attr_cov in ranked:
        print(f"  {model:<35s} {n:>4d} {attr_cov:>7.1f}% {pb_cov:>6.1f}% "
              f"{avg_tok:>7.0f} {max_tok:>7d} {tot_tok:>7d} {attrs_subj:>6.1f} {avg_time:>5.1f}s")

    if not ranked:
        print("  (no successful runs)")


# ── Save results ──────────────────────────────────────────────────────────────


def save_results(
    eval_dir: Path,
    results: dict[str, list[ProjectionMetrics]],
    specs: dict[tuple[str, str], ProjectionSpec],
) -> None:
    """Save spec YAMLs and comparison JSON to eval directory."""
    eval_dir.mkdir(parents=True, exist_ok=True)

    # Save individual specs
    for (model, type_id), spec in specs.items():
        model_slug = model.replace("/", "_")
        model_dir = eval_dir / model_slug
        model_dir.mkdir(parents=True, exist_ok=True)
        spec_path = model_dir / f"{type_id}_spec.yaml"
        spec_path.write_text(dump_projection_spec(spec))

    # Save comparison JSON
    comparison: dict[str, Any] = {}
    for type_id, metrics_list in results.items():
        comparison[type_id] = [asdict(m) for m in metrics_list]

    comparison_path = eval_dir / "comparison.json"
    comparison_path.write_text(json.dumps(comparison, indent=2, default=str))
    print(f"\nResults saved to {eval_dir}/")


# ── Resolve type_id -> output_dir ────────────────────────────────────────────

_TYPE_DIR_MAP: dict[str, str] = {t["type_id"]: t["output_dir"] for t in DEFAULT_TYPES}


def resolve_output_dir(type_id: str) -> Path:
    """Resolve a type_id to its output directory."""
    if type_id in _TYPE_DIR_MAP:
        return Path(_TYPE_DIR_MAP[type_id])
    # Try each known output dir
    for candidate in ["output/iosxr", "output/hybrid-infra", "output/entra-intune"]:
        p = Path(candidate)
        if (p / f"{type_id}_classes.yaml").exists():
            return p
    msg = f"Cannot find output dir for type '{type_id}'"
    raise FileNotFoundError(msg)


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare LLM models on projection spec inference quality.",
    )
    parser.add_argument(
        "--models", nargs="+", default=DEFAULT_MODELS,
        help="Models to evaluate (default: all 8)",
    )
    parser.add_argument(
        "--types", nargs="+",
        default=[t["type_id"] for t in DEFAULT_TYPES],
        help="Entity types to evaluate (default: all 5)",
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL,
        help=f"OpenAI-compatible API base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--api-key-env", default=DEFAULT_API_KEY_ENV,
        help=f"Env var for API key (default: {DEFAULT_API_KEY_ENV})",
    )
    parser.add_argument(
        "--output-dir", default="internals/projection_eval",
        help="Directory to save results (default: internals/projection_eval)",
    )
    parser.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS,
        help=f"Max parallel API calls (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--recompute", action="store_true",
        help="Recompute metrics from existing spec YAMLs (no API calls)",
    )
    args = parser.parse_args()

    # Validate types resolve
    type_dirs: list[tuple[str, Path]] = []
    for type_id in args.types:
        try:
            output_dir = resolve_output_dir(type_id)
            type_dirs.append((type_id, output_dir))
        except FileNotFoundError as e:
            print(f"WARNING: Skipping {type_id}: {e}", file=sys.stderr)

    if not type_dirs:
        print("ERROR: No valid entity types to evaluate.", file=sys.stderr)
        sys.exit(1)

    eval_dir = Path(args.output_dir)

    if args.recompute:
        _run_recompute(args, type_dirs, eval_dir)
    else:
        _run_full_eval(args, type_dirs, eval_dir)


def _recompute_from_spec(
    type_id: str,
    output_dir: Path,
    model: str,
    spec: ProjectionSpec,
) -> ProjectionMetrics:
    """Recompute metrics from an existing spec (no LLM call)."""
    metrics = ProjectionMetrics(model=model, type_id=type_id)
    start = time.monotonic()

    tier_b, tier_c = _load_tier_data(output_dir, type_id)

    total_attrs, matched_attrs, pb_total, pb_matched, uncovered = compute_coverage(
        tier_b, tier_c, spec
    )
    metrics.subject_count = len(spec.subjects)
    metrics.total_attrs = total_attrs
    metrics.matched_attrs = matched_attrs
    metrics.attr_coverage_pct = (matched_attrs / total_attrs * 100) if total_attrs else 0.0
    metrics.pb_total = pb_total
    metrics.pb_matched = pb_matched
    metrics.pb_coverage_pct = (pb_matched / pb_total * 100) if pb_total else 100.0
    metrics.uncovered_paths = uncovered[:20]

    subject_attrs: list[int] = []
    subject_tokens: list[int] = []
    for subj in spec.subjects:
        attr_count, token_count = compute_subject_stats(tier_b, tier_c, subj)
        subject_attrs.append(attr_count)
        subject_tokens.append(token_count)

    if subject_tokens:
        metrics.avg_projection_tokens = sum(subject_tokens) / len(subject_tokens)
        metrics.max_projection_tokens = max(subject_tokens)
        metrics.total_projection_tokens = sum(subject_tokens)
    if subject_attrs:
        metrics.avg_attrs_per_subject = sum(subject_attrs) / len(subject_attrs)

    metrics.elapsed_seconds = time.monotonic() - start
    return metrics


def _run_recompute(
    args: argparse.Namespace,
    type_dirs: list[tuple[str, Path]],
    eval_dir: Path,
) -> None:
    """Recompute metrics from existing spec YAMLs on disk."""
    print(f"Recomputing metrics from specs in {eval_dir}/")

    results: dict[str, list[ProjectionMetrics]] = {}
    specs: dict[tuple[str, str], ProjectionSpec] = {}
    count = 0

    for type_id, output_dir in type_dirs:
        results[type_id] = []
        for model in args.models:
            model_slug = model.replace("/", "_")
            spec_path = eval_dir / model_slug / f"{type_id}_spec.yaml"
            if not spec_path.exists():
                m = ProjectionMetrics(model=model, type_id=type_id, error="spec not found")
                results[type_id].append(m)
                count += 1
                print(f"  [{count}] {model} x {type_id}: SKIP (no spec)")
                continue

            spec = load_projection_spec(spec_path)
            specs[(model, type_id)] = spec
            metrics = _recompute_from_spec(type_id, output_dir, model, spec)
            results[type_id].append(metrics)
            count += 1
            print(f"  [{count}] {model} x {type_id}: "
                  f"{metrics.subject_count} subj, "
                  f"{metrics.attr_coverage_pct:.1f}% cov, "
                  f"{metrics.total_projection_tokens} tok")

    print_comparison_table(results)
    save_results(eval_dir, results, specs)


def _run_full_eval(
    args: argparse.Namespace,
    type_dirs: list[tuple[str, Path]],
    eval_dir: Path,
) -> None:
    """Run full eval with LLM API calls in parallel."""
    # Build work items
    work: list[tuple[str, Path, str]] = []
    for type_id, output_dir in type_dirs:
        for model in args.models:
            work.append((type_id, output_dir, model))

    total = len(work)
    print(f"Evaluating {len(args.models)} models x {len(type_dirs)} types = {total} API calls")
    print(f"Workers: {args.workers}")
    print(f"Models: {', '.join(args.models)}")
    print(f"Types: {', '.join(t for t, _ in type_dirs)}")

    # Run in parallel
    all_metrics: dict[tuple[str, str], ProjectionMetrics] = {}
    specs: dict[tuple[str, str], ProjectionSpec] = {}
    done_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_key = {}
        for type_id, output_dir, model in work:
            fut = pool.submit(
                run_single_eval,
                type_id=type_id,
                output_dir=output_dir,
                model=model,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
            )
            future_to_key[fut] = (model, type_id)

        for fut in as_completed(future_to_key):
            model, type_id = future_to_key[fut]
            done_count += 1
            try:
                metrics, spec = fut.result()
            except Exception as e:
                metrics = ProjectionMetrics(model=model, type_id=type_id, error=str(e))
                spec = None

            all_metrics[(model, type_id)] = metrics
            if spec:
                specs[(model, type_id)] = spec
                print(f"  [{done_count}/{total}] {model} x {type_id}: "
                      f"{metrics.subject_count} subj, "
                      f"{metrics.attr_coverage_pct:.1f}% cov, "
                      f"{metrics.total_projection_tokens} tok "
                      f"({metrics.elapsed_seconds:.1f}s)")
            else:
                err = (metrics.error or "unknown")[:60]
                print(f"  [{done_count}/{total}] {model} x {type_id}: ERROR — {err}")

    # Assemble results grouped by type (preserving model order)
    results: dict[str, list[ProjectionMetrics]] = {}
    for type_id, _ in type_dirs:
        results[type_id] = []
        for model in args.models:
            key = (model, type_id)
            if key in all_metrics:
                results[type_id].append(all_metrics[key])

    print_comparison_table(results)
    save_results(eval_dir, results, specs)


if __name__ == "__main__":
    main()
