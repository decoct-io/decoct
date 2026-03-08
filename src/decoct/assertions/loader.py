"""Assertion file loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

from decoct.assertions.models import Assertion, Match, Severity

_VALID_SEVERITY = {"must", "should", "may"}


def _parse_match(data: dict[str, Any]) -> Match:
    """Parse a match dict into a Match object."""
    if "path" not in data:
        msg = "Match missing required field 'path'"
        raise ValueError(msg)

    range_val = data.get("range")
    if range_val is not None:
        if not isinstance(range_val, list) or len(range_val) != 2:
            msg = f"Match 'range' must be a list of [min, max], got: {range_val}"
            raise ValueError(msg)

    return Match(
        path=str(data["path"]),
        value=data.get("value"),
        pattern=data.get("pattern"),
        range=range_val,
        contains=data.get("contains"),
        not_value=data.get("not_value"),
    )


def _parse_assertion(data: dict[str, Any], index: int) -> Assertion:
    """Parse a single assertion dict."""
    for required in ("id", "assert", "rationale", "severity"):
        if required not in data:
            msg = f"Assertion at index {index} missing required field '{required}'"
            raise ValueError(msg)

    severity = data["severity"]
    if severity not in _VALID_SEVERITY:
        msg = f"Assertion '{data['id']}' severity must be one of {_VALID_SEVERITY}, got '{severity}'"
        raise ValueError(msg)

    match = None
    if "match" in data:
        match = _parse_match(data["match"])

    related = data.get("related")
    if related is not None:
        related = list(related)

    return Assertion(
        id=str(data["id"]),
        assert_=str(data["assert"]),
        rationale=str(data["rationale"]),
        severity=cast(Severity, severity),
        match=match,
        exceptions=data.get("exceptions"),
        example=data.get("example"),
        related=related,
        source=data.get("source"),
    )


def load_assertions(path: str | Path) -> list[Assertion]:
    """Load and validate an assertions YAML file."""
    path = Path(path)
    yaml = YAML(typ="safe")
    data = yaml.load(path)

    if not isinstance(data, dict) or "assertions" not in data:
        msg = f"Assertions file must contain an 'assertions' key: {path}"
        raise ValueError(msg)

    items = data["assertions"]
    if not isinstance(items, list):
        msg = f"'assertions' must be a list: {path}"
        raise ValueError(msg)

    return [_parse_assertion(item, i) for i, item in enumerate(items)]
