"""Token estimation (char/4 stub) (§11.2)."""

from __future__ import annotations

from typing import Any

from decoct.core.io import yaml_serialize


def token_estimate_value(value: Any) -> float:
    """Estimate token count for a value."""
    return len(yaml_serialize(value)) / 4.0


def token_estimate_attrs(attrs: dict[str, Any]) -> float:
    """Estimate token count for a set of attributes."""
    total = 0.0
    for path, value in attrs.items():
        total += len(path) / 4.0 + token_estimate_value(value) + 2
    return total


def token_estimate_class(attrs: dict[str, Any]) -> float:
    """Estimate token count for a class definition."""
    return token_estimate_attrs(attrs) + 8


def token_estimate_override(delta: dict[str, Any]) -> float:
    """Estimate token count for an override delta."""
    if not delta:
        return 0.0
    return token_estimate_attrs(delta) + 4


def token_estimate_id_set(entity_ids: list[str]) -> float:
    """Estimate token count for a set of entity IDs."""
    return len(str(entity_ids)) / 4.0
