"""Strip-defaults pass — remove values matching platform schema defaults."""

from __future__ import annotations

from typing import Any

from decoct.passes.base import BasePass, PassResult, register_pass
from decoct.passes.drop_fields import _path_matches, drop_fields
from decoct.schemas.models import Schema


def _walk_and_strip_defaults(node: Any, path: str, defaults: dict[str, Any]) -> int:
    """Walk a YAML tree, removing leaves that match schema defaults. Returns count removed."""
    count = 0
    if isinstance(node, dict):
        keys_to_drop: list[str] = []
        for key in list(node.keys()):
            child_path = f"{path}.{key}" if path else str(key)
            child = node[key]
            # Check if this leaf matches a default
            if not isinstance(child, (dict, list)):
                for pattern, default_value in defaults.items():
                    if _path_matches(child_path, pattern) and _values_equal(child, default_value):
                        keys_to_drop.append(key)
                        break
            elif isinstance(child, (dict, list)):
                count += _walk_and_strip_defaults(child, child_path, defaults)

        for key in keys_to_drop:
            del node[key]
            count += 1

    elif isinstance(node, list):
        for i, child in enumerate(node):
            child_path = f"{path}.{i}" if path else str(i)
            if isinstance(child, (dict, list)):
                count += _walk_and_strip_defaults(child, child_path, defaults)

    return count


def _values_equal(actual: Any, default: Any) -> bool:
    """Compare values, handling type coercion between YAML types."""
    if actual == default:
        return True
    # Handle string/bool/int comparisons from YAML parsing
    try:
        if str(actual).lower() == str(default).lower():
            return True
    except (ValueError, TypeError):
        pass
    return False


def strip_defaults(doc: Any, schema: Schema, *, skip_low_confidence: bool = False) -> int:
    """Strip default values from a YAML document using a schema.

    Also applies the schema's drop_patterns and system_managed lists.

    Args:
        doc: YAML document to modify in-place.
        schema: Loaded schema with defaults, drop_patterns, system_managed.
        skip_low_confidence: If True, skip stripping when schema confidence
            is 'low' or 'medium'.

    Returns:
        Total count of fields removed.
    """
    count = 0

    if skip_low_confidence and schema.confidence in ("low", "medium"):
        return 0

    # Strip defaults
    if schema.defaults:
        count += _walk_and_strip_defaults(doc, "", schema.defaults)

    # Apply drop_patterns from schema
    if schema.drop_patterns:
        count += drop_fields(doc, schema.drop_patterns)

    # Apply system_managed from schema
    if schema.system_managed:
        count += drop_fields(doc, schema.system_managed)

    return count


@register_pass
class StripDefaultsPass(BasePass):
    """Remove values matching platform schema defaults."""

    name = "strip-defaults"
    run_after = ["strip-secrets", "strip-comments"]
    run_before: list[str] = []

    def __init__(self, schema: Schema | None = None, *, skip_low_confidence: bool = False) -> None:
        self.schema = schema
        self.skip_low_confidence = skip_low_confidence

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        schema = self.schema or kwargs.get("schema")
        if schema is None:
            return PassResult(name=self.name, items_removed=0)
        count = strip_defaults(doc, schema, skip_low_confidence=self.skip_low_confidence)
        return PassResult(name=self.name, items_removed=count)
