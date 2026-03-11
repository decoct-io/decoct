"""Dataclasses for Tier A spec format (R4 — enhanced Tier A)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TierATypeDescription:
    """LLM-generated description for a single entity type."""

    summary: str
    key_differentiators: list[str] = field(default_factory=list)


@dataclass
class TierASpec:
    """Top-level Tier A spec loaded from YAML."""

    version: int  # must be 1
    generated_by: str = "claude-code"  # "claude-code" or "decoct-infer"
    corpus_description: str = ""
    how_to_use: list[str] = field(default_factory=list)
    type_descriptions: dict[str, TierATypeDescription] = field(default_factory=dict)
