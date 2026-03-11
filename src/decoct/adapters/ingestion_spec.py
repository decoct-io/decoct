"""Ingestion spec loader and matcher (§R1 — LLM-assisted ingestion review)."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from decoct.adapters.ingestion_models import (
    CompositePathSpec,
    IngestionEntry,
    IngestionSpec,
    RelationshipHintSpec,
)


def load_ingestion_spec(path: str | Path) -> IngestionSpec:
    """Load and validate an ingestion spec from YAML.

    Raises:
        FileNotFoundError: if the spec file does not exist
        ValueError: if the spec is invalid
    """
    path = Path(path)
    yaml = YAML(typ="safe")
    raw: dict[str, Any] = yaml.load(path.read_text())

    if not isinstance(raw, dict):
        msg = f"Ingestion spec must be a YAML mapping, got {type(raw).__name__}"
        raise ValueError(msg)

    # Validate version
    version = raw.get("version")
    if version != 1:
        msg = f"Unsupported ingestion spec version: {version!r} (expected 1)"
        raise ValueError(msg)

    adapter = raw.get("adapter")
    if not adapter or not isinstance(adapter, str):
        msg = "Ingestion spec must have a non-empty 'adapter' string"
        raise ValueError(msg)

    generated_by = raw.get("generated_by", "claude-code")

    entries: list[IngestionEntry] = []
    for i, entry_raw in enumerate(raw.get("entries", [])):
        if not isinstance(entry_raw, dict):
            msg = f"Entry {i} must be a mapping"
            raise ValueError(msg)

        file_pattern = entry_raw.get("file_pattern")
        if not file_pattern or not isinstance(file_pattern, str):
            msg = f"Entry {i} must have a non-empty 'file_pattern' string"
            raise ValueError(msg)

        platform = entry_raw.get("platform")
        if not platform or not isinstance(platform, str):
            msg = f"Entry {i} must have a non-empty 'platform' string"
            raise ValueError(msg)

        composite_paths: list[CompositePathSpec] = []
        for j, cp_raw in enumerate(entry_raw.get("composite_paths", [])):
            kind = cp_raw.get("kind", "")
            if kind not in ("map", "list"):
                msg = f"Entry {i}, composite_paths[{j}].kind must be 'map' or 'list', got {kind!r}"
                raise ValueError(msg)
            composite_paths.append(CompositePathSpec(
                path=cp_raw["path"],
                kind=kind,
                reason=cp_raw.get("reason", ""),
            ))

        relationship_hints: list[RelationshipHintSpec] = []
        for rh_raw in entry_raw.get("relationship_hints", []):
            relationship_hints.append(RelationshipHintSpec(
                source_field=rh_raw["source_field"],
                target_field=rh_raw["target_field"],
                label=rh_raw["label"],
            ))

        entries.append(IngestionEntry(
            file_pattern=file_pattern,
            platform=platform,
            description=entry_raw.get("description", ""),
            composite_paths=composite_paths,
            relationship_hints=relationship_hints,
        ))

    return IngestionSpec(
        version=version,
        adapter=adapter,
        generated_by=generated_by,
        entries=entries,
    )


def match_entry(spec: IngestionSpec, filename: str) -> IngestionEntry | None:
    """Find the first matching entry for a filename (stem, not full path).

    Uses fnmatch against entry.file_pattern. Returns None if no entry matches.
    """
    for entry in spec.entries:
        if fnmatch(filename, entry.file_pattern):
            return entry
    return None
