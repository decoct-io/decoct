"""Dataclasses for projection spec format (R3 — subject projections)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RelatedPath:
    """Cross-reference inclusion for a subject projection."""

    path: str  # dotted path pattern (supports glob wildcards)
    reason: str = ""  # why this path is related to the subject


@dataclass
class SubjectSpec:
    """One subject within a projection spec."""

    name: str  # subject identifier, e.g. "bgp", "interfaces"
    description: str = ""  # human-readable description
    include_paths: list[str] = field(default_factory=list)  # glob patterns to include
    related_paths: list[RelatedPath] = field(default_factory=list)  # cross-reference paths
    example_questions: list[str] = field(default_factory=list)  # sample questions this subject answers


@dataclass
class ProjectionSpec:
    """Top-level projection spec loaded from YAML."""

    version: int  # must be 1
    source_type: str  # entity type this applies to, e.g. "iosxr-access-pe"
    generated_by: str = "claude-code"  # tool that generated this spec
    subjects: list[SubjectSpec] = field(default_factory=list)  # subject definitions
