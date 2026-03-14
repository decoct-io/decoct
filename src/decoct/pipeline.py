"""Pipeline orchestrator.

Runs the full compression pipeline: parse -> section -> secrets -> compress
-> reconstruct/validate -> output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from decoct.compress import compress
from decoct.formats import detect_format
from decoct.reconstruct import validate_reconstruction
from decoct.secrets.detection import AuditEntry


@dataclass
class PipelineConfig:
    """Configuration for a pipeline run."""

    secrets: bool = True
    validate: bool = True
    xml_validate: bool = True


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    tier_b: dict[str, Any] = field(default_factory=dict)
    tier_c: dict[str, dict[str, Any]] = field(default_factory=dict)
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    format: str = "yaml"
    secrets_audit: list[AuditEntry] = field(default_factory=list)
    validation_ok: bool = True
    validation_errors: list[str] = field(default_factory=list)


def _load_file(path: Path) -> tuple[dict[str, Any], str]:
    """Load a single input file into a sectioned dict.

    Returns (sections_dict, format_name).
    """
    fmt = detect_format(path)

    if fmt == "xml":
        from decoct.xml_sections import parse_xml_to_sections

        sections = parse_xml_to_sections(path)
        return sections, "xml"

    if fmt == "json":
        raw = path.read_text()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"_root": data}, "json"
        return data, "json"

    if fmt == "ini":
        from decoct.formats import ini_to_commented_map

        raw = path.read_text()
        doc = ini_to_commented_map(raw)
        # Convert CommentedMap to plain dict for compression
        return _to_plain_dict(doc), "ini"

    # YAML
    raw = path.read_text()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        return {"_root": data}, "yaml"
    return data, "yaml"


def _to_plain_dict(obj: Any) -> Any:
    """Convert CommentedMap/CommentedSeq to plain dict/list."""
    if isinstance(obj, dict):
        return {k: _to_plain_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_plain_dict(item) for item in obj]
    return obj


def _input_extensions() -> set[str]:
    return {".yaml", ".yml", ".json", ".ini", ".conf", ".cfg", ".cnf", ".properties", ".xml"}


def run_pipeline(
    sources: str | Path,
    config: PipelineConfig | None = None,
) -> PipelineResult:
    """Run the compression pipeline.

    Args:
        sources: Directory containing input files, or a single file.
        config: Pipeline configuration. Uses defaults if None.

    Returns:
        PipelineResult with tier_b, tier_c, and validation results.
    """
    if config is None:
        config = PipelineConfig()

    sources = Path(sources)
    result = PipelineResult()

    # 1. Discover and load input files
    if sources.is_file():
        input_files = [sources]
    else:
        input_files = sorted(
            f for f in sources.iterdir()
            if f.is_file() and f.suffix.lower() in _input_extensions()
        )

    if not input_files:
        return result

    inputs: dict[str, dict[str, Any]] = {}
    detected_format = "yaml"

    for path in input_files:
        host = path.stem
        sections, fmt = _load_file(path)
        inputs[host] = sections
        detected_format = fmt

    result.format = detected_format

    # 2. Secrets masking
    if config.secrets:
        from decoct.secrets.document_masker import mask_document

        for host_data in inputs.values():
            audit = mask_document(host_data)
            result.secrets_audit.extend(audit)

    result.inputs = inputs

    # 3. Compress
    tier_b, tier_c = compress(inputs)
    result.tier_b = tier_b
    result.tier_c = tier_c

    # 4. Validate reconstruction (before list class embedding)
    if config.validate:
        ok, errors = validate_reconstruction(inputs, tier_b, tier_c)
        result.validation_ok = ok
        result.validation_errors = errors

    # 5. XML validation (before list class embedding)
    if config.xml_validate and detected_format == "xml":
        from decoct.reconstruct import reconstruct_host
        from decoct.xml_reconstruct import validate_xml_roundtrip

        for host in sorted(inputs):
            if host in tier_c:
                reconstructed = reconstruct_host(tier_b, tier_c[host])
                ok, diffs = validate_xml_roundtrip(inputs[host], reconstructed)
                if not ok:
                    result.validation_ok = False
                    for d in diffs:
                        result.validation_errors.append(f"{host}/xml: {d}")

    # 6. List class embedding (cosmetic post-processing, after validation)
    from decoct.passes.list_compress import embed_list_classes, scan_list_classes

    list_class_registry: dict = {}
    scan_results: dict = {}
    for host in sorted(inputs):
        host_results = scan_list_classes(inputs[host], list_class_registry)
        if host_results:
            scan_results[host] = host_results

    if scan_results:
        embed_list_classes(tier_b, tier_c, scan_results)

    if list_class_registry:
        tier_b["_list_classes"] = list_class_registry

    return result


def write_output(
    result: PipelineResult,
    output_dir: str | Path,
) -> None:
    """Write pipeline results to output directory.

    Creates:
      - ``tier_b.yaml`` — class definitions
      - ``{hostname}.yaml`` — per-host compressed deltas
    """
    from decoct.render import assert_no_subclass_refs, render_yaml

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    assert_no_subclass_refs(result.tier_b)

    (output_dir / "tier_b.yaml").write_text(render_yaml(result.tier_b))

    for host in sorted(result.tier_c):
        (output_dir / f"{host}.yaml").write_text(render_yaml(result.tier_c[host]))
