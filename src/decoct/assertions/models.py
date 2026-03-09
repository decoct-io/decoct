"""Assertion data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Severity = Literal["must", "should", "may"]


@dataclass
class Match:
    """Match condition for an assertion."""

    path: str
    value: Any = None
    pattern: str | None = None
    range: list[float | int] | None = None
    contains: Any = None
    not_value: Any = None
    exists: bool | None = None


@dataclass
class Assertion:
    """A design standard assertion."""

    id: str
    assert_: str
    rationale: str
    severity: Severity
    match: Match | None = None
    exceptions: str | None = None
    example: str | None = None
    related: list[str] | None = None
    source: str | None = None
