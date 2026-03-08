"""Schema data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Confidence = Literal["authoritative", "high", "medium", "low"]


@dataclass
class Schema:
    """Platform schema defining defaults and system-managed fields."""

    platform: str
    source: str
    confidence: Confidence
    defaults: dict[str, Any] = field(default_factory=dict)
    drop_patterns: list[str] = field(default_factory=list)
    system_managed: list[str] = field(default_factory=list)
