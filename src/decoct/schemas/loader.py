"""Schema file loader."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from ruamel.yaml import YAML

from decoct.schemas.models import Confidence, Schema

_VALID_CONFIDENCE = {"authoritative", "high", "medium", "low"}


def load_schema(path: str | Path) -> Schema:
    """Load and validate a schema YAML file."""
    path = Path(path)
    yaml = YAML(typ="safe")
    data = yaml.load(path)

    if not isinstance(data, dict):
        msg = f"Schema file must be a YAML mapping, got {type(data).__name__}: {path}"
        raise ValueError(msg)

    for required in ("platform", "source", "confidence"):
        if required not in data:
            msg = f"Schema missing required field '{required}': {path}"
            raise ValueError(msg)

    confidence = data["confidence"]
    if confidence not in _VALID_CONFIDENCE:
        msg = f"Schema confidence must be one of {_VALID_CONFIDENCE}, got '{confidence}': {path}"
        raise ValueError(msg)

    return Schema(
        platform=str(data["platform"]),
        source=str(data["source"]),
        confidence=cast(Confidence, confidence),
        defaults=dict(data.get("defaults") or {}),
        drop_patterns=list(data.get("drop_patterns") or []),
        system_managed=list(data.get("system_managed") or []),
    )
