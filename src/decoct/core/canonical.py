"""Canonical serialization, equality, and key functions (§2.4)."""

from __future__ import annotations

import json
from typing import Any

from decoct.core.composite_value import CompositeValue

# Types considered scalar-like for phone book routing
SCALAR_TYPES = frozenset({"string", "number", "boolean", "null", "enum"})


def encode_canonical(value: Any) -> Any:
    """Encode a value for canonical JSON serialization.

    Handles CompositeValue, tuples, enums, dicts, lists, and scalars.
    Normalizes types so CANONICAL_KEY is truly authoritative.
    """
    if value is None:
        return None
    if isinstance(value, CompositeValue):
        return encode_canonical(value.data)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # Normalize float to int if lossless
        if value == int(value) and not (value == 0.0 and str(value).startswith("-")):
            return int(value)
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, tuple):
        return [encode_canonical(v) for v in value]
    if isinstance(value, list):
        return [encode_canonical(v) for v in value]
    if isinstance(value, dict):
        return {str(k): encode_canonical(v) for k, v in sorted(value.items())}
    # Fallback for other types
    return str(value)


def CANONICAL_KEY(value: Any) -> str:
    """Authoritative equality key for grouping and ordering (§2.4)."""
    return json.dumps(
        encode_canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def CANONICAL_EQUAL(a: Any, b: Any) -> bool:
    """Check canonical equality between two values (§2.4)."""
    return CANONICAL_KEY(a) == CANONICAL_KEY(b)


def VALUE_KEY(value: Any) -> str:
    """Value key for grouping — alias for CANONICAL_KEY (§2.4)."""
    return CANONICAL_KEY(value)


def ITEM_KEY(path: str, value: Any) -> tuple[str, str]:
    """Item key combining path and canonical value key (§2.4)."""
    return (path, CANONICAL_KEY(value))


def IS_SCALAR_LIKE(attribute_type: str) -> bool:
    """Check if attribute type is scalar-like for phone book routing (§7.3).

    composite_template_ref is explicitly excluded, regardless of statistical profile.
    """
    if attribute_type == "composite_template_ref":
        return False
    return attribute_type in SCALAR_TYPES
