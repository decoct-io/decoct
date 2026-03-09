"""Emit-classes pass — add default class definitions as header comments.

After strip-defaults removes known platform defaults, this pass adds a comment
block at the top of the document listing what was stripped, grouped by category.
This allows LLMs reading the compressed output to reconstruct full configs.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ruamel.yaml.comments import CommentedMap

from decoct.passes.base import BasePass, PassResult, register_pass
from decoct.schemas.models import Schema


def _classify_defaults(defaults: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Group schema defaults into named classes by path prefix.

    Returns mapping of class_name → {path: default_value}.
    """
    classes: dict[str, dict[str, Any]] = defaultdict(dict)

    for path, value in defaults.items():
        parts = path.split(".")
        class_name = _derive_class_name(parts)
        classes[class_name][path] = value

    return dict(classes)


def _derive_class_name(parts: list[str]) -> str:
    """Derive a human-readable class name from path segments.

    Groups by the first meaningful segment (after stripping wildcards),
    with a second level for deep nesting.
    """
    meaningful = [p for p in parts if p not in ("*", "**")]

    if not meaningful:
        return "defaults"

    # Single top-level key (e.g., "Port", "manage_etc_hosts")
    if len(meaningful) == 1:
        return "top-level-defaults"

    # First meaningful segment is the category
    category = meaningful[0].rstrip("s")  # de-pluralise

    # If 3+ meaningful segments, include the second as subcategory
    # e.g., services.healthcheck.interval → service-healthcheck-defaults
    # But services.restart → service-defaults
    if len(meaningful) >= 3:
        return f"{category}-{meaningful[1]}-defaults"
    else:
        return f"{category}-defaults"


def _format_class_block(
    platform: str,
    classes: dict[str, dict[str, Any]],
) -> str:
    """Format the class definition comment block."""
    lines = [f"decoct: defaults stripped using {platform} schema"]

    for class_name, defaults in sorted(classes.items()):
        # Format as: @class name: key=value, key=value, ...
        pairs = []
        for path, value in sorted(defaults.items()):
            # Use the leaf key name for readability
            leaf = path.rsplit(".", 1)[-1]
            pairs.append(f"{leaf}={value}")
        summary = ", ".join(pairs)
        # Truncate very long lines
        if len(summary) > 100:
            summary = summary[:97] + "..."
        lines.append(f"@class {class_name}: {summary}")

    return "\n".join(lines)


def emit_classes(doc: Any, schema: Schema) -> int:
    """Add default class definitions as header comments on the document.

    Returns the number of classes emitted.
    """
    if not isinstance(doc, CommentedMap):
        return 0

    if not schema.defaults:
        return 0

    classes = _classify_defaults(schema.defaults)
    if not classes:
        return 0

    comment_text = _format_class_block(schema.platform, classes)

    # Set as a comment before the first key
    doc.yaml_set_start_comment(comment_text)

    return len(classes)


@register_pass
class EmitClassesPass(BasePass):
    """Add default class definitions as document header comments."""

    name = "emit-classes"
    run_after = ["strip-defaults", "prune-empty"]
    run_before = ["annotate-deviations", "deviation-summary"]

    def __init__(self, schema: Schema | None = None) -> None:
        self.schema = schema

    def run(self, doc: Any, **kwargs: Any) -> PassResult:
        schema = self.schema or kwargs.get("schema")
        if schema is None:
            return PassResult(name=self.name, items_removed=0)
        count = emit_classes(doc, schema)
        return PassResult(name=self.name, items_removed=0, details=[f"{count} classes emitted"])
