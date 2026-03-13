"""Dataclasses for ingestion spec format (§R1 — LLM-assisted ingestion review)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CompositePathSpec:
    """Override for composite value detection at a specific path."""

    path: str  # dotted path, supports fnmatch wildcards
    kind: str  # "map" or "list"
    reason: str = ""


@dataclass
class RelationshipHintSpec:
    """Hint for inter-entity relationship discovery."""

    source_field: str  # attribute path on source entity
    target_field: str  # attribute path to match on target entities
    label: str  # relationship label


@dataclass
class IngestionEntry:
    """A single file-matching rule in the ingestion spec."""

    file_pattern: str  # fnmatch glob pattern against filename stem
    platform: str  # schema_type_hint to assign
    description: str = ""
    composite_paths: list[CompositePathSpec] = field(default_factory=list)
    relationship_hints: list[RelationshipHintSpec] = field(default_factory=list)


@dataclass
class IngestionSpec:
    """Top-level ingestion spec loaded from YAML."""

    version: int  # must be 1
    adapter: str = "standard"  # e.g. "standard", "hybrid-infra"
    generated_by: str = "claude-code"
    entries: list[IngestionEntry] = field(default_factory=list)
