"""Benchmark harness for measuring compression performance."""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.tokens import count_tokens

_INPUT_EXTENSIONS = {".yaml", ".yml", ".json", ".ini", ".conf", ".cfg", ".cnf", ".properties"}


@dataclass
class TierResult:
    """Result from running a single compression tier."""

    tier_name: str
    input_tokens: int
    output_tokens: int
    pass_results: list[dict[str, Any]] = field(default_factory=list)
    pass_timings: dict[str, float] = field(default_factory=dict)
    total_time: float = 0.0

    @property
    def savings_tokens(self) -> int:
        """Tokens saved by this tier."""
        return self.input_tokens - self.output_tokens

    @property
    def savings_pct(self) -> float:
        """Percentage of tokens saved."""
        if self.input_tokens == 0:
            return 0.0
        return (self.savings_tokens / self.input_tokens) * 100


@dataclass
class FileResult:
    """Benchmark result for a single file."""

    path: str
    format: str
    platform: str | None
    input_tokens: int
    input_lines: int
    tiers: dict[str, TierResult] = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    """Aggregate benchmark report across all files."""

    files: list[FileResult] = field(default_factory=list)
    encoding: str = "cl100k_base"
    timestamp: str = ""


def _expand_paths(paths: list[str | Path], recursive: bool = False) -> list[Path]:
    """Expand file and directory paths to individual config files."""
    result: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in sorted(path.glob(pattern)):
                if child.is_file() and child.suffix.lower() in _INPUT_EXTENSIONS:
                    result.append(child)
        elif path.is_file():
            result.append(path)
    return result


def _dump_yaml(doc: Any) -> str:
    """Dump a YAML document to string."""
    yaml = YAML(typ="rt")
    stream = StringIO()
    yaml.dump(doc, stream)
    return stream.getvalue()


def _build_tier_pipelines(
    platform: str | None,
    assertions: list[Any] | None,
    corpus_schema: Any | None = None,
) -> dict[str, Any]:
    """Build pipeline instances for each applicable compression tier.

    Returns a dict mapping tier name to a Pipeline instance.

    Args:
        platform: Detected or explicit platform name.
        assertions: Pre-loaded assertion objects for full tier.
        corpus_schema: Corpus-learned Schema for corpus tier.
    """
    from decoct.passes.emit_classes import EmitClassesPass
    from decoct.passes.prune_empty import PruneEmptyPass
    from decoct.passes.strip_comments import StripCommentsPass
    from decoct.passes.strip_secrets import StripSecretsPass
    from decoct.pipeline import Pipeline

    tiers: dict[str, Any] = {}

    # Generic tier: always available
    generic_passes: list[Any] = [
        StripSecretsPass(),
        StripCommentsPass(),
        PruneEmptyPass(),
    ]
    tiers["generic"] = Pipeline(generic_passes)

    # Schema tier: requires platform detection or explicit schema
    if platform:
        from decoct.passes.strip_defaults import StripDefaultsPass
        from decoct.schemas.loader import load_schema
        from decoct.schemas.resolver import resolve_schema

        try:
            schema = load_schema(resolve_schema(platform))
            schema_passes: list[Any] = [
                StripSecretsPass(),
                StripCommentsPass(),
                StripDefaultsPass(schema=schema),
                EmitClassesPass(schema=schema),
                PruneEmptyPass(),
            ]
            tiers["schema"] = Pipeline(schema_passes)
        except (KeyError, FileNotFoundError, ValueError):
            pass

    # Corpus tier: uses corpus-learned schema
    if corpus_schema:
        from decoct.passes.strip_defaults import StripDefaultsPass

        corpus_passes: list[Any] = [
            StripSecretsPass(),
            StripCommentsPass(),
            StripDefaultsPass(schema=corpus_schema),
            EmitClassesPass(schema=corpus_schema),
            PruneEmptyPass(),
        ]
        tiers["corpus"] = Pipeline(corpus_passes)

    # Full tier: requires schema + assertions
    if platform and assertions:
        from decoct.passes.annotate_deviations import AnnotateDeviationsPass
        from decoct.passes.deviation_summary import DeviationSummaryPass
        from decoct.passes.strip_conformant import StripConformantPass
        from decoct.passes.strip_defaults import StripDefaultsPass
        from decoct.schemas.loader import load_schema
        from decoct.schemas.resolver import resolve_schema

        try:
            schema = load_schema(resolve_schema(platform))
            full_passes: list[Any] = [
                StripSecretsPass(),
                StripCommentsPass(),
                StripDefaultsPass(schema=schema),
                EmitClassesPass(schema=schema),
                StripConformantPass(assertions=assertions),
                AnnotateDeviationsPass(assertions=assertions),
                DeviationSummaryPass(assertions=assertions),
                PruneEmptyPass(),
            ]
            tiers["full"] = Pipeline(full_passes)
        except (KeyError, FileNotFoundError, ValueError):
            pass

    return tiers


def benchmark_file(
    path: Path,
    *,
    schema: str | None = None,
    assertions: list[Any] | None = None,
    encoding: str = "cl100k_base",
    corpus_schema: Any | None = None,
) -> FileResult:
    """Benchmark a single file across all applicable compression tiers.

    Args:
        path: Path to the input file.
        schema: Explicit schema name or path. If None, auto-detect.
        assertions: Pre-loaded assertion objects for full tier.
        encoding: Tiktoken encoding name.
        corpus_schema: Corpus-learned Schema for corpus tier.

    Returns:
        FileResult with per-tier compression statistics.
    """
    from decoct.formats import detect_format, detect_platform, load_input

    doc, raw_text = load_input(path)
    fmt = detect_format(path)
    input_tokens = count_tokens(raw_text, encoding)
    input_lines = raw_text.count("\n")

    # Determine platform
    platform = schema or detect_platform(doc)

    # Build tier pipelines
    tier_pipelines = _build_tier_pipelines(platform, assertions, corpus_schema=corpus_schema)

    file_result = FileResult(
        path=str(path),
        format=fmt,
        platform=platform,
        input_tokens=input_tokens,
        input_lines=input_lines,
    )

    for tier_name, pipeline in tier_pipelines.items():
        doc_copy = copy.deepcopy(doc)
        t0 = time.monotonic()
        stats = pipeline.run(doc_copy)
        elapsed = time.monotonic() - t0

        output_text = _dump_yaml(doc_copy)
        output_tokens = count_tokens(output_text, encoding)

        pass_result_dicts = [
            {"name": pr.name, "items_removed": pr.items_removed}
            for pr in stats.pass_results
        ]

        file_result.tiers[tier_name] = TierResult(
            tier_name=tier_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pass_results=pass_result_dicts,
            pass_timings=stats.pass_timings,
            total_time=elapsed,
        )

    return file_result


def _load_all_docs(
    paths: list[Path],
) -> dict[str, list[tuple[Path, Any]]]:
    """Load all documents and group by detected platform.

    Returns {platform: [(path, doc), ...]}.
    """
    from decoct.formats import detect_platform, load_input

    grouped: dict[str, list[tuple[Path, Any]]] = {}
    for file_path in paths:
        try:
            doc, _ = load_input(file_path)
            platform = detect_platform(doc) or "unknown"
            grouped.setdefault(platform, []).append((file_path, doc))
        except Exception:  # noqa: BLE001
            continue
    return grouped


def run_benchmark(
    paths: list[str | Path],
    *,
    assertions_path: str | None = None,
    encoding: str = "cl100k_base",
    recursive: bool = False,
    learn_corpus: bool = False,
) -> BenchmarkReport:
    """Run benchmark across a corpus of config files.

    Args:
        paths: File or directory paths to benchmark.
        assertions_path: Path to assertions file for full tier.
        encoding: Tiktoken encoding name.
        recursive: Recurse into subdirectories.
        learn_corpus: If True, run a two-pass approach: first learn
            compression classes from the corpus, then benchmark with
            the corpus-learned schema as an additional tier.

    Returns:
        BenchmarkReport with per-file and aggregate results.
    """
    assertions = None
    if assertions_path:
        from decoct.assertions.loader import load_assertions

        assertions = load_assertions(assertions_path)

    expanded = _expand_paths(paths, recursive)

    # Pass 1: learn corpus schemas if requested
    corpus_schemas: dict[str, Any] = {}
    if learn_corpus:
        from decoct.corpus_classes import classes_to_schema, learn_classes

        grouped = _load_all_docs(expanded)
        for platform, file_docs in grouped.items():
            if platform == "unknown" or len(file_docs) < 3:
                continue
            docs = [doc for _, doc in file_docs]
            classes = learn_classes(docs, encoding=encoding)
            if classes:
                corpus_schemas[platform] = classes_to_schema(classes, platform)

    # Pass 2: benchmark each file
    report = BenchmarkReport(
        encoding=encoding,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )

    for file_path in expanded:
        try:
            # Determine platform for corpus schema lookup
            cs = None
            if corpus_schemas:
                from decoct.formats import detect_platform, load_input

                doc, _ = load_input(file_path)
                detected = detect_platform(doc)
                if detected:
                    cs = corpus_schemas.get(detected)

            result = benchmark_file(
                file_path, assertions=assertions, encoding=encoding, corpus_schema=cs,
            )
            report.files.append(result)
        except Exception:  # noqa: BLE001
            # Skip files that fail to parse
            continue

    return report


def format_report_markdown(report: BenchmarkReport, *, verbose: bool = False) -> str:
    """Format a BenchmarkReport as markdown text.

    Args:
        report: The benchmark report to format.
        verbose: Include per-pass timing details.

    Returns:
        Markdown-formatted report string.
    """
    lines: list[str] = []
    lines.append(f"# decoct benchmark — {report.timestamp}")
    lines.append(f"Encoding: {report.encoding}  |  Files: {len(report.files)}")
    lines.append("")

    if not report.files:
        lines.append("No files processed.")
        return "\n".join(lines)

    # Collect all tier names across files
    all_tiers: list[str] = []
    for f in report.files:
        for t in f.tiers:
            if t not in all_tiers:
                all_tiers.append(t)

    # Per-file table
    lines.append("## Per-File Results")
    lines.append("")
    tier_headers = " | ".join(all_tiers)
    header = f"| File | Platform | Lines | Tokens | {tier_headers} |"
    separator = "|------|----------|------:|-------:|" + "|".join("-------:" for _ in all_tiers) + "|"
    lines.append(header)
    lines.append(separator)

    for f in report.files:
        name = Path(f.path).name
        platform = f.platform or "-"
        tier_values: list[str] = []
        for t in all_tiers:
            if t in f.tiers:
                tier_values.append(f"{f.tiers[t].savings_pct:.1f}%")
            else:
                tier_values.append("-")
        tier_cols = " | ".join(tier_values)
        lines.append(f"| {name} | {platform} | {f.input_lines} | {f.input_tokens} | {tier_cols} |")

    lines.append("")

    # Aggregate summary
    lines.append("## Aggregate Summary")
    lines.append("")

    for tier_name in all_tiers:
        tier_files = [f for f in report.files if tier_name in f.tiers]
        if not tier_files:
            continue
        total_input = sum(f.tiers[tier_name].input_tokens for f in tier_files)
        total_output = sum(f.tiers[tier_name].output_tokens for f in tier_files)
        saved = total_input - total_output
        pct = (saved / total_input * 100) if total_input else 0
        lines.append(
            f"**{tier_name}**: {total_input} → {total_output} tokens "
            f"(saved {saved}, {pct:.1f}%) across {len(tier_files)} files"
        )

    lines.append("")

    # By platform
    platforms: dict[str, list[FileResult]] = {}
    for f in report.files:
        key = f.platform or "unknown"
        platforms.setdefault(key, []).append(f)

    if len(platforms) > 1 or (len(platforms) == 1 and "unknown" not in platforms):
        lines.append("## By Platform")
        lines.append("")
        for platform_name, platform_files in sorted(platforms.items()):
            lines.append(f"### {platform_name} ({len(platform_files)} files)")
            tier_parts: list[str] = []
            for tier_name in all_tiers:
                tier_subset = [f for f in platform_files if tier_name in f.tiers]
                if not tier_subset:
                    continue
                total_input = sum(f.tiers[tier_name].input_tokens for f in tier_subset)
                total_output = sum(f.tiers[tier_name].output_tokens for f in tier_subset)
                pct = ((total_input - total_output) / total_input * 100) if total_input else 0
                tier_parts.append(f"{tier_name}: {pct:.1f}%")
            lines.append("  " + "  |  ".join(tier_parts))
            lines.append("")

    # Verbose: per-pass timing
    if verbose:
        lines.append("## Pass Timings")
        lines.append("")
        for f in report.files:
            lines.append(f"### {Path(f.path).name}")
            for tier_name, tier in f.tiers.items():
                lines.append(f"  **{tier_name}** ({tier.total_time:.3f}s)")
                for pass_name, elapsed in tier.pass_timings.items():
                    lines.append(f"    {pass_name}: {elapsed:.3f}s")
            lines.append("")

    return "\n".join(lines)


def format_report_json(report: BenchmarkReport) -> str:
    """Format a BenchmarkReport as JSON.

    Args:
        report: The benchmark report to format.

    Returns:
        JSON-formatted report string.
    """
    data: dict[str, Any] = {
        "encoding": report.encoding,
        "timestamp": report.timestamp,
        "files": [],
    }

    for f in report.files:
        file_data: dict[str, Any] = {
            "path": f.path,
            "format": f.format,
            "platform": f.platform,
            "input_tokens": f.input_tokens,
            "input_lines": f.input_lines,
            "tiers": {},
        }
        for tier_name, tier in f.tiers.items():
            file_data["tiers"][tier_name] = {
                "tier_name": tier.tier_name,
                "input_tokens": tier.input_tokens,
                "output_tokens": tier.output_tokens,
                "savings_tokens": tier.savings_tokens,
                "savings_pct": round(tier.savings_pct, 1),
                "pass_results": tier.pass_results,
                "pass_timings": {k: round(v, 4) for k, v in tier.pass_timings.items()},
                "total_time": round(tier.total_time, 4),
            }
        data["files"].append(file_data)

    # Aggregate summary
    all_tiers: list[str] = []
    for f in report.files:
        for t in f.tiers:
            if t not in all_tiers:
                all_tiers.append(t)

    summary: dict[str, Any] = {}
    for tier_name in all_tiers:
        tier_files = [f for f in report.files if tier_name in f.tiers]
        if not tier_files:
            continue
        total_input = sum(f.tiers[tier_name].input_tokens for f in tier_files)
        total_output = sum(f.tiers[tier_name].output_tokens for f in tier_files)
        saved = total_input - total_output
        pct = (saved / total_input * 100) if total_input else 0
        summary[tier_name] = {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "savings_tokens": saved,
            "savings_pct": round(pct, 1),
            "file_count": len(tier_files),
        }
    data["summary"] = summary

    return json.dumps(data, indent=2)
